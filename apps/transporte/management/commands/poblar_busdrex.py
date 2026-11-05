"""
==============================================================================
BusDrex - COMANDO DE GESTIÓN: poblar_busdrex.py
Semillero de Datos para Demostración y Evaluación Académica en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Puebla la base de datos MySQL con:
1. Usuario Administrador de Flota y Pasajero Demo (credenciales desde .env).
2. Regiones y Ciudades chilenas normalizadas (3FN).
3. Terminales por ciudad (3FN: terminal -> ciudad -> región).
4. Flota de Buses interurbanos (Semicama, Salón Cama, Premium).
5. Rutas interurbanas con 'duracion_minutos' (entero).
6. Servicios programados a futuro con tarifas diferenciadas (Semicama / Cama)
   y generación automática de inventario de asientos.
7. Pasajeros de ejemplo en el maestro con RUT chileno normalizado.
8. Ofertas comerciales interurbanas activas.
==============================================================================
Ejecutar con:
    python manage.py poblar_busdrex
==============================================================================
"""

import os
from decimal import Decimal
from datetime import timedelta, date
from django.core.management.base import BaseCommand
from django.utils import timezone
from usuarios.models import Usuario
from transporte.models import Region, Ciudad, Terminal, Bus, Ruta, Servicio, Asiento, Oferta
from reservas.models import CarroPasajes, Pasajero


class Command(BaseCommand):
    help = 'Puebla la base de datos MySQL con regiones, ciudades, terminales, flota, rutas, servicios, pasajeros y ofertas en 3FN.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("=================================================================="))
        self.stdout.write(self.style.WARNING("=== Iniciando carga de datos iniciales en 3FN para BusDrex ==="))
        self.stdout.write(self.style.WARNING("=================================================================="))

        # ----------------------------------------------------------------------
        # 1. USUARIOS DEL SISTEMA (CREDENCIALES DESDE .ENV)
        # ----------------------------------------------------------------------
        admin_user = os.environ.get('ADMIN_USERNAME', 'admin_flota')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'Admin1234!')
        pasajero_user = os.environ.get('PASAJERO_USERNAME', 'pasajero_demo')
        pasajero_pass = os.environ.get('PASAJERO_PASSWORD', 'Pasajero1234!')

        # Administrador de Flota (sin RUT en Usuario para cumplir 3FN)
        admin_flota, admin_creado = Usuario.objects.get_or_create(
            username=admin_user,
            defaults={
                'email': 'admin@busdrex.cl',
                'first_name': 'Carlos',
                'last_name': 'Mendoza',
                'rol': Usuario.ROL_ADMIN_FLOTA,
                'telefono': '+56987654321',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_flota.rol = Usuario.ROL_ADMIN_FLOTA
        admin_flota.is_staff = True
        admin_flota.set_password(admin_pass)
        admin_flota.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Administrador de Flota configurado: {admin_user} / {admin_pass}"))

        # Pasajero Demo
        pasajero, pas_creado = Usuario.objects.get_or_create(
            username=pasajero_user,
            defaults={
                'email': 'pasajero@busdrex.cl',
                'first_name': 'María',
                'last_name': 'González',
                'rol': Usuario.ROL_PASAJERO,
                'telefono': '+56912345678',
            }
        )
        pasajero.rol = Usuario.ROL_PASAJERO
        pasajero.set_password(pasajero_pass)
        pasajero.save()
        CarroPasajes.objects.get_or_create(usuario=pasajero)
        self.stdout.write(self.style.SUCCESS(f"[OK] Pasajero Demo configurado: {pasajero_user} / {pasajero_pass}"))

        # ----------------------------------------------------------------------
        # 2. MAESTRO DE PASAJEROS (3FN)
        # ----------------------------------------------------------------------
        pasajeros_ejemplo = [
            {'rut': '18987654-3', 'nombre_completo': 'María González López'},
            {'rut': '15234567-8', 'nombre_completo': 'Carlos Mendoza Silva'},
            {'rut': '20123456-K', 'nombre_completo': 'Benjamin Gómez Rojas'},
            {'rut': '12345678-5', 'nombre_completo': 'Rodrigo Tapia Morales'},
        ]
        for p_info in pasajeros_ejemplo:
            Pasajero.objects.get_or_create(
                rut=Pasajero.normalizar_rut(p_info['rut']),
                defaults={'nombre_completo': p_info['nombre_completo']}
            )
        self.stdout.write(self.style.SUCCESS(f"[OK] {len(pasajeros_ejemplo)} Pasajeros registrados en tabla 'pasajero'."))

        # ----------------------------------------------------------------------
        # 3. GEOGRAFÍA EN 3FN: REGIONES -> CIUDADES -> TERMINALES
        # ----------------------------------------------------------------------
        regiones_data = [
            'Región Metropolitana',
            'Región de Valparaíso',
            'Región de Coquimbo',
            'Región de Antofagasta',
            'Región del Biobío',
            'Región de La Araucanía',
            'Región de Los Lagos',
        ]
        regiones_map = {}
        for reg_nombre in regiones_data:
            reg, _ = Region.objects.get_or_create(nombre=reg_nombre)
            regiones_map[reg_nombre] = reg

        ciudades_data = [
            ('Santiago', 'Región Metropolitana'),
            ('Valparaíso', 'Región de Valparaíso'),
            ('Viña del Mar', 'Región de Valparaíso'),
            ('La Serena', 'Región de Coquimbo'),
            ('Antofagasta', 'Región de Antofagasta'),
            ('Concepción', 'Región del Biobío'),
            ('Temuco', 'Región de La Araucanía'),
            ('Osorno', 'Región de Los Lagos'),
            ('Puerto Montt', 'Región de Los Lagos'),
        ]
        ciudades_map = {}
        for c_nombre, r_nombre in ciudades_data:
            ciu, _ = Ciudad.objects.get_or_create(
                nombre=c_nombre,
                region=regiones_map[r_nombre]
            )
            ciudades_map[c_nombre] = ciu

        terminales_data = [
            ('Terminal San Borja', 'Santiago'),
            ('Terminal Sur', 'Santiago'),
            ('Terminal Rodoviario', 'Valparaíso'),
            ('Terminal de Buses', 'Viña del Mar'),
            ('Terminal Rodoviario de La Serena', 'La Serena'),
            ('Terminal Rodoviario Carlos Oviedo', 'Antofagasta'),
            ('Terminal Collao', 'Concepción'),
            ('Terminal Rodoviario de La Araucanía', 'Temuco'),
            ('Terminal Rodoviario de Osorno', 'Osorno'),
            ('Terminal Municipal', 'Puerto Montt'),
        ]
        terminales_map = {}
        for t_nombre, c_nombre in terminales_data:
            term, _ = Terminal.objects.get_or_create(
                nombre=t_nombre,
                ciudad=ciudades_map[c_nombre]
            )
            terminales_map[f"{c_nombre}-{t_nombre}"] = term

        self.stdout.write(self.style.SUCCESS(
            f"[OK] Geografía 3FN configurada: {len(regiones_map)} Regiones, "
            f"{len(ciudades_map)} Ciudades y {len(terminales_map)} Terminales."
        ))

        # ----------------------------------------------------------------------
        # 4. BUSES DE LA FLOTA
        # ----------------------------------------------------------------------
        buses_data = [
            {'patente': 'CJBB-45', 'modelo': 'Marcopolo Paradiso G8 1800 DD', 'capacidad_total': 40, 'tipo_bus': Bus.TIPO_SALON_CAMA},
            {'patente': 'DFTR-88', 'modelo': 'Volvo B430R Irizar i6', 'capacidad_total': 44, 'tipo_bus': Bus.TIPO_SEMICAMA},
            {'patente': 'GKLP-12', 'modelo': 'Scania Touring HD Premium Suite', 'capacidad_total': 32, 'tipo_bus': Bus.TIPO_PREMIUM},
            {'patente': 'HJ99-88', 'modelo': 'Mercedes-Benz Travego O580 DD', 'capacidad_total': 42, 'tipo_bus': Bus.TIPO_SALON_CAMA},
            {'patente': 'KLPX-23', 'modelo': 'Marcopolo Viaggio 1050', 'capacidad_total': 44, 'tipo_bus': Bus.TIPO_SEMICAMA},
        ]
        buses_map = {}
        for b_info in buses_data:
            b, _ = Bus.objects.get_or_create(
                patente=b_info['patente'],
                defaults={
                    'modelo': b_info['modelo'],
                    'capacidad_total': b_info['capacidad_total'],
                    'tipo_bus': b_info['tipo_bus']
                }
            )
            buses_map[b.patente] = b

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(buses_data)} Buses de flota registrados."))

        # ----------------------------------------------------------------------
        # 5. RUTAS INTERURBANAS (CON DURACION_MINUTOS)
        # ----------------------------------------------------------------------
        rutas_data = [
            {
                'origen': terminales_map['Santiago-Terminal San Borja'],
                'destino': terminales_map['Viña del Mar-Terminal de Buses'],
                'duracion_minutos': 105
            },
            {
                'origen': terminales_map['Santiago-Terminal San Borja'],
                'destino': terminales_map['Concepción-Terminal Collao'],
                'duracion_minutos': 360
            },
            {
                'origen': terminales_map['Santiago-Terminal Sur'],
                'destino': terminales_map['Temuco-Terminal Rodoviario de La Araucanía'],
                'duracion_minutos': 510
            },
            {
                'origen': terminales_map['Santiago-Terminal Sur'],
                'destino': terminales_map['Puerto Montt-Terminal Municipal'],
                'duracion_minutos': 720
            },
            {
                'origen': terminales_map['Santiago-Terminal San Borja'],
                'destino': terminales_map['La Serena-Terminal Rodoviario de La Serena'],
                'duracion_minutos': 360
            },
            {
                'origen': terminales_map['Concepción-Terminal Collao'],
                'destino': terminales_map['Temuco-Terminal Rodoviario de La Araucanía'],
                'duracion_minutos': 210
            },
            {
                'origen': terminales_map['Temuco-Terminal Rodoviario de La Araucanía'],
                'destino': terminales_map['Puerto Montt-Terminal Municipal'],
                'duracion_minutos': 240
            },
        ]
        rutas_creadas = []
        for r_info in rutas_data:
            ruta, _ = Ruta.objects.get_or_create(
                origen=r_info['origen'],
                destino=r_info['destino'],
                defaults={'duracion_minutos': r_info['duracion_minutos']}
            )
            rutas_creadas.append(ruta)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(rutas_creadas)} Rutas interurbanas registradas."))

        # ----------------------------------------------------------------------
        # 6. SERVICIOS CON FECHAS FUTURAS Y ASIENTOS CON DISTRIBUCIÓN
        # ----------------------------------------------------------------------
        ahora = timezone.now()
        # -----------------------------------------------------------------------
        # COBERTURA DE TIPOS DE BUS: al menos 1 servicio de cada categoria
        # para poder probar el filtro tipo_bus=SEMICAMA|SALON_CAMA|PREMIUM.
        # -----------------------------------------------------------------------
        servicios_data = [
            # Bus SALON_CAMA: ruta corta Stgo -> Vina del Mar
            {
                'ruta': rutas_creadas[0],
                'bus': buses_map['HJ99-88'],
                'fecha_hora_salida': ahora + timedelta(days=1, hours=2),
                'tarifa_semicama': Decimal('6990.00'),
                'tarifa_cama': Decimal('9990.00'),
            },
            # Bus SEMICAMA: ruta media Stgo -> Concepcion
            {
                'ruta': rutas_creadas[1],
                'bus': buses_map['DFTR-88'],
                'fecha_hora_salida': ahora + timedelta(days=1, hours=5),
                'tarifa_semicama': Decimal('16990.00'),
                'tarifa_cama': Decimal('24990.00'),
            },
            # Bus SALON_CAMA: ruta larga Stgo -> Temuco
            {
                'ruta': rutas_creadas[2],
                'bus': buses_map['CJBB-45'],
                'fecha_hora_salida': ahora + timedelta(days=1, hours=8),
                'tarifa_semicama': Decimal('22990.00'),
                'tarifa_cama': Decimal('32990.00'),
            },
            # Bus PREMIUM: ruta larga Stgo -> Puerto Montt (tipo_bus=PREMIUM principal)
            {
                'ruta': rutas_creadas[3],
                'bus': buses_map['GKLP-12'],
                'fecha_hora_salida': ahora + timedelta(days=2, hours=3),
                'tarifa_semicama': Decimal('28990.00'),
                'tarifa_cama': Decimal('39990.00'),
            },
            # Bus SEMICAMA: ruta media Stgo -> La Serena
            {
                'ruta': rutas_creadas[4],
                'bus': buses_map['KLPX-23'],
                'fecha_hora_salida': ahora + timedelta(days=2, hours=6),
                'tarifa_semicama': Decimal('14990.00'),
                'tarifa_cama': Decimal('21990.00'),
            },
            # Bus PREMIUM: ruta Stgo -> Concepcion (segunda salida Premium para pruebas)
            {
                'ruta': rutas_creadas[1],
                'bus': buses_map['GKLP-12'],
                'fecha_hora_salida': ahora + timedelta(days=3, hours=10),
                'tarifa_semicama': Decimal('24990.00'),
                'tarifa_cama': Decimal('34990.00'),
            },
        ]

        total_asientos = 0
        for s_info in servicios_data:
            servicio, creado = Servicio.objects.get_or_create(
                ruta=s_info['ruta'],
                bus=s_info['bus'],
                fecha_hora_salida=s_info['fecha_hora_salida'],
                defaults={
                    'tarifa_semicama': s_info['tarifa_semicama'],
                    'tarifa_cama': s_info['tarifa_cama'],
                }
            )
            servicio.generar_asientos_automaticamente()
            total_asientos += servicio.asientos.count()

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(servicios_data)} Servicios futuros con {total_asientos} asientos."))

        # ----------------------------------------------------------------------
        # 7. OFERTAS Y PROMOCIONES COMERCIALES (3FN)
        # ----------------------------------------------------------------------
        hoy = date.today()
        ofertas_data = [
            {
                'titulo': 'Escápate a la Costa: Santiago a Viña del Mar',
                'descripcion': 'Viaja cómodo y seguro a la costa central con tarifas promocionales en salidas seleccionadas.',
                'descuento_porcentaje': Decimal('25.00'),
                'ruta': rutas_creadas[0],
                'fecha_inicio': hoy,
                'fecha_fin': hoy + timedelta(days=60),
                'activa': True
            },
            {
                'titulo': 'Ruta del Biobío: Santiago a Concepción',
                'descripcion': 'Disfruta de nuestros buses Salón Cama de última generación con 20% de descuento en viajes de fin de semana.',
                'descuento_porcentaje': Decimal('20.00'),
                'ruta': rutas_creadas[1],
                'fecha_inicio': hoy,
                'fecha_fin': hoy + timedelta(days=90),
                'activa': True
            },
            {
                'titulo': 'Travesía Austral: Santiago a Puerto Montt y Los Lagos',
                'descripcion': 'Conéctate con los paisajes del sur en categoría Premium Suite y Salón Cama.',
                'descuento_porcentaje': Decimal('15.00'),
                'ruta': rutas_creadas[3],
                'fecha_inicio': hoy,
                'fecha_fin': hoy + timedelta(days=120),
                'activa': True
            },
        ]

        for o_info in ofertas_data:
            Oferta.objects.get_or_create(
                titulo=o_info['titulo'],
                defaults=o_info
            )

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(ofertas_data)} Ofertas comerciales creadas exitosamente."))
        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(self.style.SUCCESS("=== Población de datos iniciales completada con éxito ==="))
        self.stdout.write(self.style.SUCCESS("=================================================================="))
