"""
==============================================================================
BusDrex - SUITE DE PRUEBAS AUTOMATIZADAS EN 3FN (apps/reservas/tests.py)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Cobertura obligatoria implementada:
1. Estructura de BD: Existencia de las 15 tablas del DBML y restricciones UNIQUE clave.
2. Pasajeros: Reutilización de un único registro por RUT sin sobreescritura de nombre.
3. Precios: Dinámicos en carro según tipo de asiento vs Historial congelado en DetalleVenta.
4. Ciclo transaccional y concurrencia:
   - Carro no descuenta stock.
   - Checkout crea Venta PENDIENTE sin descontar stock.
   - Pago con select_for_update() descuenta atómicamente y emite Boletos.
   - Rechazo íntegro si un asiento ya fue tomado concurrentemente.
   - Cancelación repone stock una sola vez (idempotente) y anula boletos.
5. Integridad referencial (PROTECT): HTTP 409 Conflict al eliminar datos dependientes.
6. Filtros avanzados (django-filter) en terminales, rutas, servicios, ventas y boletos.
==============================================================================
"""

import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import connection, IntegrityError
from django.db.models import ProtectedError
from django.utils import timezone
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Usuario
from transporte.models import Region, Ciudad, Terminal, Bus, Ruta, Servicio, Asiento, Oferta
from reservas.models import Pasajero, CarroPasajes, ItemCarro, Venta, DetalleVenta, Boleto
from reservas.services import (
    realizar_checkout,
    procesar_pago_venta,
    procesar_cancelacion_venta,
)


class BaseBusDrexTestCase(APITestCase):
    """Configuración base para pruebas de BusDrex."""

    def setUp(self):
        # 1. Usuarios del sistema
        self.pasajero_user = Usuario.objects.create_user(
            username='pasajero_test',
            email='pasajero@test.cl',
            password='Password123!',
            first_name='Juan',
            last_name='Pérez',
            telefono='+56911223344',
            rol=Usuario.ROL_PASAJERO
        )

        self.admin_user = Usuario.objects.create_user(
            username='admin_test',
            email='admin@test.cl',
            password='AdminPassword123!',
            first_name='Carlos',
            last_name='Administrador',
            rol=Usuario.ROL_ADMIN_FLOTA,
            is_staff=True,
            is_superuser=True
        )

        # 2. Geografía normalizada (3FN)
        self.region_rm = Region.objects.create(nombre='Región Metropolitana')
        self.region_biobio = Region.objects.create(nombre='Región del Biobío')

        self.ciudad_stgo = Ciudad.objects.create(nombre='Santiago', region=self.region_rm)
        self.ciudad_conce = Ciudad.objects.create(nombre='Concepción', region=self.region_biobio)

        self.terminal_stgo = Terminal.objects.create(nombre='Terminal San Borja', ciudad=self.ciudad_stgo)
        self.terminal_conce = Terminal.objects.create(nombre='Terminal Collao', ciudad=self.ciudad_conce)

        # 3. Flota y Rutas
        self.bus = Bus.objects.create(
            patente='BUSD-26',
            modelo='Marcopolo G8 1800 DD',
            capacidad_total=40,
            tipo_bus=Bus.TIPO_SALON_CAMA
        )

        self.ruta = Ruta.objects.create(
            origen=self.terminal_stgo,
            destino=self.terminal_conce,
            duracion_minutos=360
        )

        # 4. Servicio e inventario de asientos
        self.servicio = Servicio.objects.create(
            ruta=self.ruta,
            bus=self.bus,
            fecha_hora_salida=timezone.now() + timedelta(days=2),
            tarifa_semicama=Decimal('15000.00'),
            tarifa_cama=Decimal('25000.00')
        )
        self.servicio.generar_asientos_automaticamente()

        # Asientos clasificados
        self.asiento_cama = self.servicio.asientos.get(numero_asiento=1)  # Cama (1..12)
        self.asiento_semicama = self.servicio.asientos.get(numero_asiento=20)  # Semicama (13..40)


# ==============================================================================
# 1. PRUEBA DE ESTRUCTURA DE BASE DE DATOS (15 TABLAS Y RESTRICCIONES UNIQUE)
# ==============================================================================
class Test3FNEstructuraBaseDatos(BaseBusDrexTestCase):
    """Valida la correspondencia exacta con busdrex.dbml."""

    def test_01_las_15_tablas_existen_con_nombres_dbml(self):
        """Comprueba que las 15 tablas del DBML existen físicamente en la base de datos."""
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            tablas_existentes = {row[0].lower() for row in cursor.fetchall()}

        tablas_requeridas = [
            'usuario', 'pasajero', 'region', 'ciudad', 'terminal',
            'ruta', 'bus', 'servicio', 'asiento', 'carro_pasajes',
            'item_carro', 'venta', 'detalle_venta', 'boleto', 'oferta'
        ]
        for tabla in tablas_requeridas:
            self.assertIn(
                tabla,
                tablas_existentes,
                f"La tabla requerida '{tabla}' del DBML no existe en MySQL."
            )

    def test_02_restricciones_unique_clave_en_modelos(self):
        """Verifica que las restricciones UNIQUE clave impidan duplicados a nivel de BD."""
        # 1. Pasajero: RUT único
        Pasajero.objects.create(rut='11111111-1', nombre_completo='Pasajero Uno')
        with self.assertRaises(IntegrityError):
            Pasajero.objects.create(rut='11111111-1', nombre_completo='Pasajero Dos')

        # 2. Ciudad: UNIQUE(nombre, region)
        with self.assertRaises(IntegrityError):
            Ciudad.objects.create(nombre='Santiago', region=self.region_rm)

        # 3. Terminal: UNIQUE(nombre, ciudad)
        with self.assertRaises(IntegrityError):
            Terminal.objects.create(nombre='Terminal San Borja', ciudad=self.ciudad_stgo)

        # 4. Ruta: UNIQUE(origen, destino)
        with self.assertRaises(IntegrityError):
            Ruta.objects.create(origen=self.terminal_stgo, destino=self.terminal_conce, duracion_minutos=300)

        # 5. Asiento: UNIQUE(servicio, numero_asiento)
        with self.assertRaises(IntegrityError):
            Asiento.objects.create(
                servicio=self.servicio,
                numero_asiento=1,
                tipo_asiento=Asiento.TIPO_CAMA,
                estado=Asiento.ESTADO_DISPONIBLE
            )

        # 6. CarroPasajes: OneToOne con Usuario
        carro_1 = CarroPasajes.objects.create(usuario=self.pasajero_user)
        with self.assertRaises(IntegrityError):
            CarroPasajes.objects.create(usuario=self.pasajero_user)

        # 7. ItemCarro: UNIQUE(carro, asiento)
        p = Pasajero.objects.create(rut='22222222-2', nombre_completo='Pasajero Tres')
        ItemCarro.objects.create(carro=carro_1, asiento=self.asiento_cama, pasajero=p)
        with self.assertRaises(IntegrityError):
            ItemCarro.objects.create(carro=carro_1, asiento=self.asiento_cama, pasajero=p)


# ==============================================================================
# 2. PRUEBA DE NORMALIZACIÓN Y REUTILIZACIÓN DE PASAJERO POR RUT
# ==============================================================================
class TestPasajeroNormalizacionYReutilizacion(BaseBusDrexTestCase):
    """Verifica que dos ítems con el mismo RUT compartan un único Pasajero sin sobrescribir el nombre."""

    def test_reutilizacion_de_pasajero_sin_sobrescritura(self):
        self.client.force_authenticate(user=self.pasajero_user)
        url = reverse('reservas:carro-pasajes')

        # Primer pasaje con RUT 12.345.678-5 y nombre original
        res_1 = self.client.post(url, {
            'asiento_id': self.asiento_cama.id,
            'nombre_pasajero': 'Roberto Gómez Bolaños',
            'rut_pasajero': '12.345.678-5'
        })
        self.assertEqual(res_1.status_code, status.HTTP_201_CREATED)

        pasajeros_con_ese_rut = Pasajero.objects.filter(rut='12345678-5')
        self.assertEqual(pasajeros_con_ese_rut.count(), 1)
        pasajero_creado = pasajeros_con_ese_rut.first()
        self.assertEqual(pasajero_creado.nombre_completo, 'Roberto Gómez Bolaños')

        # Segundo pasaje con el MISMO RUT pero intento de nombre distinto
        res_2 = self.client.post(url, {
            'asiento_id': self.asiento_semicama.id,
            'nombre_pasajero': 'Roberto Modificado Intruso',
            'rut_pasajero': '123456785'
        })
        self.assertEqual(res_2.status_code, status.HTTP_201_CREATED)

        # El conteo debe seguir siendo exactamente 1 y el nombre NO debe haberse sobrescrito
        self.assertEqual(Pasajero.objects.filter(rut='12345678-5').count(), 1)
        pasajero_actualizado = Pasajero.objects.get(rut='12345678-5')
        self.assertEqual(pasajero_actualizado.nombre_completo, 'Roberto Gómez Bolaños')

        # Ambos ítems en el carro deben apuntar a la misma FK de pasajero
        carro = CarroPasajes.objects.get(usuario=self.pasajero_user)
        items = list(carro.items.all())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].pasajero_id, items[1].pasajero_id)


# ==============================================================================
# 3. PRECIOS DINÁMICOS DEL CARRO VS PRECIOS CONGELADOS EN DETALLEVENTA
# ==============================================================================
class TestPreciosDinamicosVsInmutablesDetalleVenta(BaseBusDrexTestCase):
    """
    Verifica que el precio del carro varía con la tarifa del servicio,
    pero el precio_unitario de DetalleVenta es inmutable tras el checkout.
    """

    def test_precios_dinamicos_en_carro_vs_congelados_en_detalle(self):
        carro, _ = CarroPasajes.objects.get_or_create(usuario=self.pasajero_user)
        pasajero = Pasajero.objects.create(rut='33333333-3', nombre_completo='Cliente Prueba')

        item = ItemCarro.objects.create(
            carro=carro,
            asiento=self.asiento_cama,  # Tipo CAMA -> tarifa_cama = $25.000
            pasajero=pasajero
        )

        # 1. El precio del ítem en carro es dinámico ($25.000)
        self.assertEqual(item.precio, Decimal('25000.00'))
        self.assertEqual(carro.calcular_total(), Decimal('25000.00'))

        # 2. Si el Administrador modifica la tarifa del servicio a $30.000:
        self.servicio.tarifa_cama = Decimal('30000.00')
        self.servicio.save()

        # El carro ahora calcula inmediatamente $30.000
        self.assertEqual(item.precio, Decimal('30000.00'))
        self.assertEqual(carro.calcular_total(), Decimal('30000.00'))

        # 3. Realizar Checkout: Congela el precio en DetalleVenta
        venta = realizar_checkout(usuario=self.pasajero_user)
        detalle = venta.detalles.first()
        self.assertEqual(detalle.precio_unitario, Decimal('30000.00'))
        self.assertEqual(venta.total, Decimal('30000.00'))

        # 4. Si la tarifa del servicio vuelve a cambiar a $45.000 después del checkout:
        self.servicio.tarifa_cama = Decimal('45000.00')
        self.servicio.save()

        # El DetalleVenta YA CREADO NO debe cambiar (inmutabilidad histórica)
        detalle.refresh_from_db()
        venta.refresh_from_db()
        self.assertEqual(detalle.precio_unitario, Decimal('30000.00'))
        self.assertEqual(venta.total, Decimal('30000.00'))


# ==============================================================================
# 4. CICLO TRANSACCIONAL COMPLETO, CONCURRENCIA Y REPOSICIÓN DE STOCK
# ==============================================================================
class TestCicloTransaccionalConcurrenciaStock(BaseBusDrexTestCase):
    """
    Verifica:
    - Agregar al carro no descuenta stock.
    - Checkout crea venta PENDIENTE sin descontar stock.
    - Pago descuenta atómicamente a OCUPADO y emite Boletos con SHA-256.
    - Rechazo íntegro si un asiento fue tomado concurrentemente.
    - Cancelación repone una sola vez (idempotente) y anula boletos.
    """

    def test_ciclo_transaccional_y_concurrencia_completo(self):
        carro, _ = CarroPasajes.objects.get_or_create(usuario=self.pasajero_user)
        pasajero = Pasajero.objects.create(rut='44444444-4', nombre_completo='Pasajero Concurrencia')

        # 1. Agregar al carro NO descuenta stock
        ItemCarro.objects.create(carro=carro, asiento=self.asiento_cama, pasajero=pasajero)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.ESTADO_DISPONIBLE)

        # 2. Checkout crea la venta en PENDIENTE sin descontar stock
        venta = realizar_checkout(self.pasajero_user)
        self.assertEqual(venta.estado, Venta.ESTADO_PENDIENTE)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.ESTADO_DISPONIBLE)
        self.assertEqual(carro.items.count(), 0)  # Carro vaciado

        # 3. Pago descuenta atómicamente a OCUPADO y emite Boleto
        procesar_pago_venta(venta=venta, usuario=self.pasajero_user)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.ESTADO_OCUPADO)
        self.assertEqual(venta.estado, Venta.ESTADO_PAGADO)

        # Verifica que se haya emitido el boleto con UUID y SHA-256
        detalle = venta.detalles.first()
        self.assertTrue(hasattr(detalle, 'boleto'))
        boleto = detalle.boleto
        self.assertEqual(boleto.estado, Boleto.ESTADO_VALIDO)
        self.assertEqual(len(boleto.codigo_hash), 64)
        self.assertIsInstance(boleto.codigo_boleto, uuid.UUID)

        # 4. Cancelación repone stock a DISPONIBLE y marca boletos como ANULADO
        procesar_cancelacion_venta(venta=venta, es_admin=True)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.ESTADO_DISPONIBLE)
        boleto.refresh_from_db()
        self.assertEqual(boleto.estado, Boleto.ESTADO_ANULADO)

        # Idempotencia: cancelar una segunda vez no genera errores ni duplica
        procesar_cancelacion_venta(venta=venta, es_admin=True)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.ESTADO_DISPONIBLE)

    def test_pago_rechazado_atomicamente_si_asiento_ya_fue_ocupado(self):
        """Simula condición de carrera: si el asiento fue adquirido por otro usuario, se rechaza."""
        carro, _ = CarroPasajes.objects.get_or_create(usuario=self.pasajero_user)
        pasajero = Pasajero.objects.create(rut='55555555-5', nombre_completo='Pasajero Carrera')
        ItemCarro.objects.create(carro=carro, asiento=self.asiento_semicama, pasajero=pasajero)

        # Generar orden PENDIENTE
        venta = realizar_checkout(self.pasajero_user)

        # Simular que otra transacción pagó y ocupó el asiento mientras la orden estaba pendiente
        self.asiento_semicama.estado = Asiento.ESTADO_OCUPADO
        self.asiento_semicama.save()

        # El intento de pago debe fallar y ejecutar Rollback
        with self.assertRaises(Exception):
            procesar_pago_venta(venta=venta, usuario=self.pasajero_user)

        # La venta se mantiene PENDIENTE
        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.ESTADO_PENDIENTE)
        self.assertEqual(Boleto.objects.filter(detalle_venta__venta=venta).count(), 0)


# ==============================================================================
# 5. INTEGRIDAD REFERENCIAL Y RESPUESTA HTTP 409 (MODELS.PROTECT)
# ==============================================================================
class TestProteccionIntegridadReferencial409(BaseBusDrexTestCase):
    """
    Verifica que la eliminación de registros referenciados con PROTECT
    retorne HTTP 409 Conflict y no un error 500 no controlado.
    """

    def test_eliminar_ciudad_con_terminales_devuelve_409(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('transporte:ciudad-detail', kwargs={'pk': self.ciudad_stgo.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('error', response.data)
        self.assertIn('conflicto', response.data['error'].lower())

    def test_eliminar_asiento_con_ventas_devuelve_409(self):
        self.client.force_authenticate(user=self.admin_user)
        # Crear venta y detalle que referencie a asiento_cama
        venta = Venta.objects.create(
            usuario=self.pasajero_user,
            total=Decimal('25000.00'),
            estado=Venta.ESTADO_PAGADO
        )
        pasajero = Pasajero.objects.create(rut='66666666-6', nombre_completo='Pasajero Histórico')
        DetalleVenta.objects.create(
            venta=venta,
            asiento=self.asiento_cama,
            pasajero=pasajero,
            precio_unitario=Decimal('25000.00')
        )

        url = reverse('transporte:asiento-detail', kwargs={'pk': self.asiento_cama.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


# ==============================================================================
# 6. PRUEBA DE FILTROS AVANZADOS (DJANGO-FILTER)
# ==============================================================================
class TestFiltrosAvanzados3FN(BaseBusDrexTestCase):
    """Verifica que los nuevos endpoints y filtros retornen los resultados esperados."""

    def test_filtros_regiones_ciudades_terminales_y_servicios(self):
        # 1. Filtro de ciudades por región
        url_ciudades = f"{reverse('transporte:ciudad-list')}?region={self.region_rm.id}"
        res_ciu = self.client.get(url_ciudades)
        self.assertEqual(res_ciu.status_code, status.HTTP_200_OK)
        ciudades = res_ciu.data.get('results', res_ciu.data)
        self.assertEqual(len(ciudades), 1)
        self.assertEqual(ciudades[0]['nombre'], 'Santiago')

        # 2. Filtro de terminales por nombre de ciudad
        url_terminales = f"{reverse('transporte:terminal-list')}?ciudad_nombre=Santiago"
        res_term = self.client.get(url_terminales)
        self.assertEqual(res_term.status_code, status.HTTP_200_OK)
        terminales = res_term.data.get('results', res_term.data)
        self.assertEqual(len(terminales), 1)
        self.assertEqual(terminales[0]['nombre'], 'Terminal San Borja')

        # 3. Búsqueda de servicios con filtros avanzados
        url_buscar = (
            f"{reverse('transporte:servicio-buscar')}?"
            f"origen_ciudad=Santiago&destino_ciudad=Concepción&tipo_asiento=CAMA&solo_disponibles=true"
        )
        res_serv = self.client.get(url_buscar)
        self.assertEqual(res_serv.status_code, status.HTTP_200_OK)
        servicios = res_serv.data.get('results', res_serv.data)
        self.assertGreaterEqual(len(servicios), 1)


# ==============================================================================
# 7. PRUEBA DEL FILTRO POR TIPO DE BUS (tipo_bus=SEMICAMA|SALON_CAMA|PREMIUM)
# ==============================================================================
class TestFiltroPorTipoBus(BaseBusDrexTestCase):
    """
    Verifica el filtro tipo_bus del endpoint /api/servicios/buscar/:
    - Filtrado correcto para cada tipo.
    - HTTP 400 para valores invalidos.
    - Combinacion tipo_bus + tipo_asiento (logica de interseccion).
    ===========================================================================
    REGLA DE COMBINACION documentada:
    - Bus SEMICAMA   -> solo asientos SEMICAMA. tipo_bus=SEMICAMA + tipo_asiento=CAMA  -> 0 resultados.
    - Bus SALON_CAMA -> solo asientos CAMA.     tipo_bus=SALON_CAMA + tipo_asiento=SEMICAMA -> 0 resultados.
    - Bus PREMIUM    -> tiene AMBOS tipos.       tipo_bus=PREMIUM + tipo_asiento=CAMA -> resultados Premium con CAMA.
    ===========================================================================
    """

    def setUp(self):
        super().setUp()
        # Bus PREMIUM adicional para las pruebas de este test
        self.bus_premium = Bus.objects.create(
            patente='PREM-99',
            modelo='Scania Touring Premium Suite Test',
            capacidad_total=28,
            tipo_bus=Bus.TIPO_PREMIUM
        )
        # Bus SEMICAMA adicional
        self.bus_semicama = Bus.objects.create(
            patente='SEMI-77',
            modelo='Volvo B430R Semicama Test',
            capacidad_total=44,
            tipo_bus=Bus.TIPO_SEMICAMA
        )

        # Servicio con bus PREMIUM (futuro)
        self.servicio_premium = Servicio.objects.create(
            ruta=self.ruta,
            bus=self.bus_premium,
            fecha_hora_salida=timezone.now() + timedelta(days=5),
            tarifa_semicama=Decimal('29990.00'),
            tarifa_cama=Decimal('39990.00')
        )
        self.servicio_premium.generar_asientos_automaticamente()

        # Servicio con bus SEMICAMA (futuro)
        self.servicio_semicama = Servicio.objects.create(
            ruta=self.ruta,
            bus=self.bus_semicama,
            fecha_hora_salida=timezone.now() + timedelta(days=6),
            tarifa_semicama=Decimal('12990.00'),
            tarifa_cama=Decimal('18990.00')
        )
        self.servicio_semicama.generar_asientos_automaticamente()

    def _url_buscar(self, **params):
        """Helper: construye la URL del endpoint de busqueda con los parametros indicados."""
        base = reverse('transporte:servicio-buscar')
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'{base}?{qs}' if qs else base

    def test_tipo_bus_premium_devuelve_solo_servicios_premium(self):
        """GET ?tipo_bus=PREMIUM debe devolver UNICAMENTE servicios con bus PREMIUM."""
        res = self.client.get(self._url_buscar(tipo_bus='PREMIUM'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        servicios = res.data.get('results', res.data)
        # Todos los resultados deben tener bus tipo PREMIUM
        ids_servicio = {s['id'] for s in servicios}
        self.assertIn(self.servicio_premium.id, ids_servicio)
        # El servicio base (SALON_CAMA) y el SEMICAMA NO deben aparecer
        self.assertNotIn(self.servicio.id, ids_servicio)
        self.assertNotIn(self.servicio_semicama.id, ids_servicio)

    def test_tipo_bus_semicama_devuelve_solo_servicios_semicama(self):
        """GET ?tipo_bus=SEMICAMA debe devolver UNICAMENTE servicios con bus SEMICAMA."""
        res = self.client.get(self._url_buscar(tipo_bus='SEMICAMA'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        servicios = res.data.get('results', res.data)
        ids_servicio = {s['id'] for s in servicios}
        self.assertIn(self.servicio_semicama.id, ids_servicio)
        # El bus base (SALON_CAMA) y el PREMIUM NO deben aparecer
        self.assertNotIn(self.servicio.id, ids_servicio)
        self.assertNotIn(self.servicio_premium.id, ids_servicio)

    def test_tipo_bus_invalido_devuelve_400(self):
        """GET ?tipo_bus=INVALIDO debe retornar HTTP 400 con mensaje descriptivo en espanol."""
        res = self.client.get(self._url_buscar(tipo_bus='INVALIDO'))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # La respuesta debe contener la clave 'error' o 'detalle' con info util
        self.assertTrue('error' in res.data or 'detalle' in res.data)

    def test_tipo_bus_premium_mas_tipo_asiento_cama_devuelve_premium_con_cama(self):
        """
        GET ?tipo_bus=PREMIUM&tipo_asiento=CAMA debe devolver solo servicios Premium
        que tengan asientos CAMA disponibles (Bus Premium tiene ambos tipos de asiento).
        """
        res = self.client.get(self._url_buscar(tipo_bus='PREMIUM', tipo_asiento='CAMA'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        servicios = res.data.get('results', res.data)
        # El servicio PREMIUM tiene asientos CAMA (nums 1..12 segun generar_asientos)
        ids_servicio = {s['id'] for s in servicios}
        self.assertIn(self.servicio_premium.id, ids_servicio)
        # Los no-Premium NO deben aparecer
        self.assertNotIn(self.servicio.id, ids_servicio)
        self.assertNotIn(self.servicio_semicama.id, ids_servicio)

    def test_tipo_bus_semicama_mas_tipo_asiento_cama_devuelve_cero_resultados(self):
        """
        GET ?tipo_bus=SEMICAMA&tipo_asiento=CAMA debe devolver 0 resultados.
        Un bus SEMICAMA solo tiene asientos SEMICAMA, no CAMA.
        Combinacion imposible segun la regla de combinacion documentada.
        """
        res = self.client.get(self._url_buscar(tipo_bus='SEMICAMA', tipo_asiento='CAMA'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        servicios = res.data.get('results', res.data)
        self.assertEqual(len(servicios), 0,
            "Un bus SEMICAMA no puede tener asientos CAMA: la combinacion debe devolver 0 resultados.")

