"""
==============================================================================
BusDrex - PRUEBAS DE CONCURRENCIA Y AISLAMIENTO ENTRE CUENTAS
(apps/reservas/tests_concurrencia.py)
Evaluacion 2: Programacion Back End | Anio: 2026
Estudiante: Benjamin Gomez | Seccion: AP-N4-C1
==============================================================================
Suite de pruebas obligatorias para el error de cruce de asientos detectado
por el profesor (dos cuentas comprando asientos del mismo servicio).

Usa TransactionTestCase con MySQL y hilos reales.
Cierra las conexiones de cada hilo al terminar (django.db.connection.close()).

Escenarios cubiertos:
1. Dos usuarios con el MISMO asiento en su orden PENDIENTE pagan al mismo tiempo:
   exactamente uno queda PAGADO y el otro recibe 409; ese asiento tiene un solo
   boleto VALIDO.
2. Escenario del profesor: usuario A y B tienen 20 asientos cada uno del mismo
   servicio, con 5 asientos en comun, y pagan al mismo tiempo: gana uno; el otro
   es rechazado COMPLETO (todos sus asientos siguen DISPONIBLES salvo los que
   gano A) y no queda ningun asiento con dos duenios. Verifica que la cantidad
   de asientos OCUPADOS equivale exactamente a la cantidad de boletos VALIDOS.
3. Con 20 asientos cada uno y sin asientos en comun, ambos pagos tienen exito
   y no se mezclan boletos entre cuentas.
4. Un usuario no puede pagar, cancelar ni ver la venta o los boletos de otro (404).
5. Cancelar una venta PAGADA repone sus asientos una sola vez y no afecta los
   de la otra cuenta.
==============================================================================
"""

import threading
import time
from decimal import Decimal
from datetime import timedelta

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from usuarios.models import Usuario
from transporte.models import Region, Ciudad, Terminal, Bus, Ruta, Servicio, Asiento
from reservas.models import Pasajero, CarroPasajes, ItemCarro, Venta, DetalleVenta, Boleto
from reservas.services import (
    realizar_checkout,
    procesar_pago_venta,
    procesar_cancelacion_venta,
)


# ==============================================================================
# BASE COMPARTIDA
# ==============================================================================
class BaseConcurrenciaTestCase(TransactionTestCase):
    """
    Base para pruebas de concurrencia con MySQL real.
    Usa TransactionTestCase para que cada hilo vea cambios confirmados (COMMIT)
    de otros hilos, lo cual es necesario para probar InnoDB row locking.
    """

    def setUp(self):
        # -- Usuarios --
        self.user_a = Usuario.objects.create_user(
            username='usuario_a_conc',
            email='a_conc@test.cl',
            password='Password123!',
            rol=Usuario.ROL_PASAJERO
        )
        self.user_b = Usuario.objects.create_user(
            username='usuario_b_conc',
            email='b_conc@test.cl',
            password='Password123!',
            rol=Usuario.ROL_PASAJERO
        )
        self.admin_user = Usuario.objects.create_user(
            username='admin_conc',
            email='admin_conc@test.cl',
            password='AdminPass123!',
            rol=Usuario.ROL_ADMIN_FLOTA,
            is_staff=True
        )

        # -- Geografia --
        self.region = Region.objects.create(nombre='Region Test Conc')
        self.ciudad_o = Ciudad.objects.create(nombre='CiudadOrigen Conc', region=self.region)
        self.ciudad_d = Ciudad.objects.create(nombre='CiudadDestino Conc', region=self.region)
        self.terminal_o = Terminal.objects.create(nombre='Terminal Origen Conc', ciudad=self.ciudad_o)
        self.terminal_d = Terminal.objects.create(nombre='Terminal Destino Conc', ciudad=self.ciudad_d)

        # -- Flota --
        self.bus = Bus.objects.create(
            patente='CONC-01',
            modelo='Bus Concurrencia Test',
            capacidad_total=40,
            tipo_bus=Bus.TIPO_SALON_CAMA
        )
        self.ruta = Ruta.objects.create(
            origen=self.terminal_o,
            destino=self.terminal_d,
            duracion_minutos=300
        )

        # -- Servicio con asientos futuros --
        self.servicio = Servicio.objects.create(
            ruta=self.ruta,
            bus=self.bus,
            fecha_hora_salida=timezone.now() + timedelta(days=5),
            tarifa_semicama=Decimal('15000.00'),
            tarifa_cama=Decimal('25000.00')
        )
        self.servicio.generar_asientos_automaticamente()

        # -- Pasajeros maestros --
        self.pasajero_a = Pasajero.objects.create(rut='11111111-C', nombre_completo='Pasajero A Concurrencia')
        self.pasajero_b = Pasajero.objects.create(rut='22222222-C', nombre_completo='Pasajero B Concurrencia')

    def _crear_orden_con_asientos(self, usuario, pasajero, asientos_list):
        """
        Crea una orden PENDIENTE con los asientos dados para el usuario.
        Retorna la venta creada.
        """
        carro, _ = CarroPasajes.objects.get_or_create(usuario=usuario)
        # Limpiar carro previo
        carro.items.all().delete()

        for asiento in asientos_list:
            ItemCarro.objects.get_or_create(
                carro=carro,
                asiento=asiento,
                defaults={'pasajero': pasajero}
            )

        return realizar_checkout(usuario)

    def _pagar_en_hilo(self, venta, resultados, indice):
        """
        Intenta pagar una venta en un hilo separado.
        Guarda el resultado (exito o error) en resultados[indice].
        Cierra la conexion de BD al terminar (requerido con TransactionTestCase).
        """
        try:
            venta_pagada = procesar_pago_venta(venta=venta)
            resultados[indice] = {'ok': True, 'venta': venta_pagada}
        except Exception as exc:
            resultados[indice] = {'ok': False, 'error': exc}
        finally:
            # CRITICO: cerrar la conexion del hilo para liberar el lock de MySQL
            connection.close()


# ==============================================================================
# 1. PRUEBA BASE: UN MISMO ASIENTO, DOS PAGOS SIMULTANEOS
# ==============================================================================
class TestUnAsientoDosPagosConcurrentes(BaseConcurrenciaTestCase):
    """
    Dos usuarios con el MISMO asiento en su orden PENDIENTE pagan al mismo tiempo.
    Exactamente uno queda PAGADO; el otro recibe error de conflicto.
    Ese asiento tiene un solo boleto VALIDO.
    """

    def test_exactamente_uno_paga_el_mismo_asiento(self):
        asiento_comun = self.servicio.asientos.get(numero_asiento=5)

        # Ambas ordenes con el mismo asiento
        venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, [asiento_comun])
        venta_b = self._crear_orden_con_asientos(self.user_b, self.pasajero_b, [asiento_comun])

        resultados = [None, None]

        hilo_a = threading.Thread(target=self._pagar_en_hilo, args=(venta_a, resultados, 0))
        hilo_b = threading.Thread(target=self._pagar_en_hilo, args=(venta_b, resultados, 1))

        hilo_a.start()
        hilo_b.start()
        hilo_a.join(timeout=30)
        hilo_b.join(timeout=30)

        # Exactamente uno debe haber tenido exito
        exitos = [r for r in resultados if r and r['ok']]
        fallos = [r for r in resultados if r and not r['ok']]

        self.assertEqual(len(exitos), 1, "Exactamente un pago debe tener exito.")
        self.assertEqual(len(fallos), 1, "Exactamente un pago debe ser rechazado.")

        # El asiento tiene exactamente un boleto VALIDO
        boletos_validos = Boleto.objects.filter(
            detalle_venta__asiento=asiento_comun,
            estado=Boleto.ESTADO_VALIDO
        ).count()
        self.assertEqual(boletos_validos, 1, "El asiento debe tener exactamente un boleto VALIDO.")

        # El asiento esta OCUPADO exactamente una vez
        asiento_comun.refresh_from_db()
        self.assertEqual(asiento_comun.estado, Asiento.ESTADO_OCUPADO)

        # La venta ganadora esta PAGADA; la perdedora sigue PENDIENTE
        venta_a.refresh_from_db()
        venta_b.refresh_from_db()
        estados = {venta_a.estado, venta_b.estado}
        self.assertIn(Venta.ESTADO_PAGADO, estados)
        self.assertIn(Venta.ESTADO_PENDIENTE, estados)


# ==============================================================================
# 2. ESCENARIO DEL PROFESOR: 20 ASIENTOS CADA UNO, 5 EN COMUN
# ==============================================================================
class TestEscenarioProfesor20AsientosCon5Comunes(BaseConcurrenciaTestCase):
    """
    Usuario A y B tienen 20 asientos cada uno del mismo servicio,
    con 5 asientos en comun, y pagan al mismo tiempo.
    - El ganador queda PAGADO con sus 20 asientos OCUPADOS.
    - El perdedor es rechazado COMPLETO: sus 20 asientos siguen DISPONIBLES
      (incluyendo los 15 exclusivos y los 5 comunes que gano el otro).
    - No queda ningun asiento con dos duenios.
    - Cantidad de asientos OCUPADOS == cantidad de boletos VALIDOS.
    """

    def setUp(self):
        super().setUp()
        # Necesitamos un bus con suficientes asientos (40 asientos, generados en setUp)
        todos = list(self.servicio.asientos.order_by('numero_asiento'))
        self.assertTrue(len(todos) >= 40, "Se necesitan al menos 40 asientos.")

        # A toma asientos 1..20; B toma asientos 16..35; comunes son 16..20 (5 asientos)
        self.asientos_a = todos[0:20]   # numeros 1 a 20
        self.asientos_b = todos[15:35]  # numeros 16 a 35
        self.asientos_comunes_nums = {a.numero_asiento for a in self.asientos_a} & \
                                     {a.numero_asiento for a in self.asientos_b}
        self.assertEqual(len(self.asientos_comunes_nums), 5,
                         "Deben haber exactamente 5 asientos en comun.")

    def test_escenario_profesor_gana_uno_pierde_otro_completo(self):
        venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, self.asientos_a)
        venta_b = self._crear_orden_con_asientos(self.user_b, self.pasajero_b, self.asientos_b)

        resultados = [None, None]

        hilo_a = threading.Thread(target=self._pagar_en_hilo, args=(venta_a, resultados, 0))
        hilo_b = threading.Thread(target=self._pagar_en_hilo, args=(venta_b, resultados, 1))

        hilo_a.start()
        hilo_b.start()
        hilo_a.join(timeout=60)
        hilo_b.join(timeout=60)

        exitos = [r for r in resultados if r and r['ok']]
        fallos = [r for r in resultados if r and not r['ok']]

        self.assertEqual(len(exitos), 1, "Exactamente un pago debe tener exito.")
        self.assertEqual(len(fallos), 1, "El otro pago debe ser rechazado completamente.")

        # Determinar ganador y perdedor
        venta_a.refresh_from_db()
        venta_b.refresh_from_db()

        if venta_a.estado == Venta.ESTADO_PAGADO:
            venta_ganadora = venta_a
            venta_perdedora = venta_b
            asientos_ganador = self.asientos_a
            asientos_perdedor = self.asientos_b
        else:
            venta_ganadora = venta_b
            venta_perdedora = venta_a
            asientos_ganador = self.asientos_b
            asientos_perdedor = self.asientos_a

        self.assertEqual(venta_ganadora.estado, Venta.ESTADO_PAGADO)
        self.assertEqual(venta_perdedora.estado, Venta.ESTADO_PENDIENTE)

        # Los asientos del ganador estan todos OCUPADOS
        for asiento in asientos_ganador:
            asiento.refresh_from_db()
            self.assertEqual(
                asiento.estado, Asiento.ESTADO_OCUPADO,
                f"Asiento #{asiento.numero_asiento} del ganador debe estar OCUPADO."
            )

        # Los asientos EXCLUSIVOS del perdedor (los que no comparte con el ganador)
        # deben estar DISPONIBLES (no se pagaron)
        ids_ganador = {a.id for a in asientos_ganador}
        asientos_exclusivos_perdedor = [a for a in asientos_perdedor if a.id not in ids_ganador]
        for asiento in asientos_exclusivos_perdedor:
            asiento.refresh_from_db()
            self.assertEqual(
                asiento.estado, Asiento.ESTADO_DISPONIBLE,
                f"Asiento exclusivo #{asiento.numero_asiento} del perdedor debe estar DISPONIBLE."
            )

        # No existe ningun asiento con dos boletos VALIDOS
        from django.db.models import Count
        asientos_con_dos_duenios = (
            Boleto.objects
            .filter(estado=Boleto.ESTADO_VALIDO)
            .values('detalle_venta__asiento')
            .annotate(total=Count('id'))
            .filter(total__gt=1)
        )
        self.assertEqual(
            asientos_con_dos_duenios.count(), 0,
            "Ningun asiento puede tener mas de un boleto VALIDO."
        )

        # Cantidad de asientos OCUPADOS == cantidad de boletos VALIDOS
        asientos_ocupados_count = (
            Asiento.objects.filter(
                servicio=self.servicio,
                estado=Asiento.ESTADO_OCUPADO
            ).count()
        )
        boletos_validos_count = (
            Boleto.objects.filter(
                detalle_venta__asiento__servicio=self.servicio,
                estado=Boleto.ESTADO_VALIDO
            ).count()
        )
        self.assertEqual(
            asientos_ocupados_count, boletos_validos_count,
            f"Asientos OCUPADOS ({asientos_ocupados_count}) debe ser igual a "
            f"Boletos VALIDOS ({boletos_validos_count})."
        )
        # El ganador tiene exactamente 20 asientos ocupados y 20 boletos
        self.assertEqual(asientos_ocupados_count, 20)
        self.assertEqual(boletos_validos_count, 20)


# ==============================================================================
# 3. SIN ASIENTOS EN COMUN: AMBOS PAGOS DEBEN TENER EXITO
# ==============================================================================
class TestDosPagosSinAsientosComunes(BaseConcurrenciaTestCase):
    """
    Con 20 asientos cada uno y sin asientos en comun, ambos pagos tienen
    exito y no se mezclan boletos entre cuentas.
    """

    def setUp(self):
        super().setUp()
        todos = list(self.servicio.asientos.order_by('numero_asiento'))
        self.assertTrue(len(todos) >= 40)
        # A toma 1..20, B toma 21..40 (sin overlap)
        self.asientos_a = todos[0:20]
        self.asientos_b = todos[20:40]

    def test_ambos_pagos_exitosos_sin_mezcla_de_boletos(self):
        venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, self.asientos_a)
        venta_b = self._crear_orden_con_asientos(self.user_b, self.pasajero_b, self.asientos_b)

        resultados = [None, None]

        hilo_a = threading.Thread(target=self._pagar_en_hilo, args=(venta_a, resultados, 0))
        hilo_b = threading.Thread(target=self._pagar_en_hilo, args=(venta_b, resultados, 1))

        hilo_a.start()
        hilo_b.start()
        hilo_a.join(timeout=60)
        hilo_b.join(timeout=60)

        # Ambos deben haber tenido exito
        for i, r in enumerate(resultados):
            self.assertIsNotNone(r, f"El hilo {i} no devolvio resultado.")
            self.assertTrue(r['ok'], f"El hilo {i} fallo: {r.get('error')}")

        venta_a.refresh_from_db()
        venta_b.refresh_from_db()
        self.assertEqual(venta_a.estado, Venta.ESTADO_PAGADO)
        self.assertEqual(venta_b.estado, Venta.ESTADO_PAGADO)

        # Los boletos de A pertenecen solo a la venta de A
        boletos_a = Boleto.objects.filter(
            detalle_venta__venta=venta_a,
            estado=Boleto.ESTADO_VALIDO
        )
        self.assertEqual(boletos_a.count(), 20)

        boletos_b = Boleto.objects.filter(
            detalle_venta__venta=venta_b,
            estado=Boleto.ESTADO_VALIDO
        )
        self.assertEqual(boletos_b.count(), 20)

        # No hay cruce: ningun boleto de A apunta a un asiento de B y viceversa
        ids_asientos_a = {a.id for a in self.asientos_a}
        ids_asientos_b = {a.id for a in self.asientos_b}

        for boleto in boletos_a:
            self.assertIn(
                boleto.detalle_venta.asiento_id, ids_asientos_a,
                "Un boleto de A apunta a un asiento que no le corresponde."
            )
        for boleto in boletos_b:
            self.assertIn(
                boleto.detalle_venta.asiento_id, ids_asientos_b,
                "Un boleto de B apunta a un asiento que no le corresponde."
            )


# ==============================================================================
# 4. AISLAMIENTO ENTRE CUENTAS: PAGAR/CANCELAR/VER VENTA AJENA => 404
# ==============================================================================
class TestAislamientoEntreCuentas(BaseConcurrenciaTestCase):
    """
    Un usuario no puede pagar, cancelar ni ver la venta o los boletos de otro.
    Responde 404 en todos los casos.
    """

    def setUp(self):
        super().setUp()
        # Crear una orden para user_a
        asiento = self.servicio.asientos.get(numero_asiento=1)
        self.venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, [asiento])
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

    def test_usuario_b_no_puede_pagar_venta_de_a(self):
        """User B intenta pagar la venta de A -> 404."""
        url = f'/api/ventas/{self.venta_a.id}/pagar/'
        response = self.client_b.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # La venta de A sigue PENDIENTE
        self.venta_a.refresh_from_db()
        self.assertEqual(self.venta_a.estado, Venta.ESTADO_PENDIENTE)

    def test_usuario_b_no_puede_cancelar_venta_de_a(self):
        """User B intenta cancelar la venta de A -> 404."""
        url = f'/api/ventas/{self.venta_a.id}/cancelar/'
        response = self.client_b.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.venta_a.refresh_from_db()
        self.assertEqual(self.venta_a.estado, Venta.ESTADO_PENDIENTE)

    def test_mis_ordenes_solo_devuelve_ordenes_propias(self):
        """GET /api/mis-ordenes/ solo devuelve las ordenes del usuario autenticado."""
        # Crear venta para B tambien
        asiento_b = self.servicio.asientos.get(numero_asiento=2)
        venta_b = self._crear_orden_con_asientos(self.user_b, self.pasajero_b, [asiento_b])

        response_a = self.client_a.get('/api/mis-ordenes/')
        self.assertEqual(response_a.status_code, status.HTTP_200_OK)

        ordenes_a = response_a.data.get('results', response_a.data)
        ids_a = {o['id'] for o in ordenes_a}

        self.assertIn(self.venta_a.id, ids_a)
        self.assertNotIn(venta_b.id, ids_a)

    def test_mis_boletos_solo_devuelve_boletos_propios(self):
        """GET /api/mis-boletos/ solo devuelve los boletos del usuario autenticado."""
        # Pagar la venta de A para que tenga boletos
        procesar_pago_venta(venta=self.venta_a)

        response_b = self.client_b.get('/api/mis-boletos/')
        self.assertEqual(response_b.status_code, status.HTTP_200_OK)

        boletos_b = response_b.data.get('results', response_b.data)
        # B no tiene boletos; no debe ver los de A
        ids_ventas_en_boletos = {b.get('venta_id') or b.get('venta', {}).get('id') for b in boletos_b}
        self.assertNotIn(self.venta_a.id, ids_ventas_en_boletos)


# ==============================================================================
# 5. CANCELACION REPONE UNA SOLA VEZ Y NO AFECTA LA OTRA CUENTA
# ==============================================================================
class TestCancelacionIdempotenteSinAfectarOtraCuenta(BaseConcurrenciaTestCase):
    """
    Cancelar una venta PAGADA repone sus asientos una sola vez y no
    afecta los asientos de la otra cuenta.
    """

    def setUp(self):
        super().setUp()
        todos = list(self.servicio.asientos.order_by('numero_asiento'))
        # A tiene asiento 1; B tiene asiento 2
        self.asiento_a = todos[0]
        self.asiento_b = todos[1]

    def test_cancelacion_repone_solo_asientos_propios(self):
        """
        A paga, B paga, A cancela: el asiento de A vuelve a DISPONIBLE,
        el asiento de B sigue OCUPADO.
        """
        venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, [self.asiento_a])
        venta_b = self._crear_orden_con_asientos(self.user_b, self.pasajero_b, [self.asiento_b])

        procesar_pago_venta(venta=venta_a)
        procesar_pago_venta(venta=venta_b)

        self.asiento_a.refresh_from_db()
        self.asiento_b.refresh_from_db()
        self.assertEqual(self.asiento_a.estado, Asiento.ESTADO_OCUPADO)
        self.assertEqual(self.asiento_b.estado, Asiento.ESTADO_OCUPADO)

        # A cancela su venta
        procesar_cancelacion_venta(venta=venta_a, es_admin=True)

        self.asiento_a.refresh_from_db()
        self.asiento_b.refresh_from_db()

        # El asiento de A vuelve a DISPONIBLE
        self.assertEqual(
            self.asiento_a.estado, Asiento.ESTADO_DISPONIBLE,
            "El asiento de A debe volver a DISPONIBLE tras cancelar."
        )
        # El asiento de B sigue OCUPADO (no afectado)
        self.assertEqual(
            self.asiento_b.estado, Asiento.ESTADO_OCUPADO,
            "El asiento de B NO debe verse afectado por la cancelacion de A."
        )

        # Los boletos de B siguen VALIDOS
        boleto_b = Boleto.objects.get(
            detalle_venta__venta=venta_b,
            estado=Boleto.ESTADO_VALIDO
        )
        self.assertIsNotNone(boleto_b)

    def test_cancelacion_doble_es_idempotente(self):
        """
        Cancelar la misma venta PAGADA dos veces solo repone el stock una vez
        y no genera errores.
        """
        venta_a = self._crear_orden_con_asientos(self.user_a, self.pasajero_a, [self.asiento_a])
        procesar_pago_venta(venta=venta_a)

        # Primera cancelacion
        procesar_cancelacion_venta(venta=venta_a, es_admin=True)
        self.asiento_a.refresh_from_db()
        self.assertEqual(self.asiento_a.estado, Asiento.ESTADO_DISPONIBLE)

        # Segunda cancelacion (idempotente, no debe fallar ni duplicar)
        procesar_cancelacion_venta(venta=venta_a, es_admin=True)
        self.asiento_a.refresh_from_db()
        self.assertEqual(
            self.asiento_a.estado, Asiento.ESTADO_DISPONIBLE,
            "El asiento debe seguir DISPONIBLE tras doble cancelacion."
        )

        # Boleto anulado, no duplicado
        boletos_anulados = Boleto.objects.filter(
            detalle_venta__venta=venta_a,
            estado=Boleto.ESTADO_ANULADO
        ).count()
        self.assertEqual(boletos_anulados, 1, "Debe haber exactamente un boleto ANULADO.")
