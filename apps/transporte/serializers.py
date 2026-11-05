"""
==============================================================================
BusDrex - MÓDULO: TRANSPORTE (apps/transporte/serializers.py)
Serializadores para Regiones, Ciudades, Terminales, Buses, Rutas, Servicios, Asientos y Ofertas
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Cumplimiento 3FN:
- RegionSerializer y CiudadSerializer para jerarquía geográfica normalizada.
- TerminalSerializer admite 'ciudad' (ID) al escribir y expone 'ciudad_nombre'
  y 'region_nombre' al leer para retrocompatibilidad con el frontend.
- RutaSerializer incorpora 'duracion_minutos' (entero) y 'duracion_formateada'.
- ServicioListSerializer y ServicioWriteSerializer para tarifas semicama/cama.
- AsientoSerializer y AsientoAdminSerializer con tipo_asiento y estado.
- OfertaSerializer según especificación DBML.
==============================================================================
"""

from rest_framework import serializers
from .models import Region, Ciudad, Terminal, Bus, Ruta, Servicio, Asiento, Oferta


class RegionSerializer(serializers.ModelSerializer):
    """
    Serializador para regiones político-administrativas de Chile (3FN).
    """
    class Meta:
        model = Region
        fields = ['id', 'nombre']


class CiudadSerializer(serializers.ModelSerializer):
    """
    Serializador para ciudades asociadas a regiones (3FN).
    Permite lectura con 'region_nombre' y escritura con 'region' (ID).
    """
    region_nombre = serializers.CharField(source='region.nombre', read_only=True)

    class Meta:
        model = Ciudad
        fields = ['id', 'nombre', 'region', 'region_nombre']


class TerminalSerializer(serializers.ModelSerializer):
    """
    Serializador para terminales de buses.
    Al escribir recibe 'ciudad' (ID). Al leer expone 'ciudad_nombre' y 'region_nombre'
    para garantizar máxima compatibilidad con el frontend Turbus.
    """
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    region_nombre = serializers.CharField(source='ciudad.region.nombre', read_only=True)

    class Meta:
        model = Terminal
        fields = [
            'id',
            'nombre',
            'ciudad',
            'ciudad_nombre',
            'region_nombre',
        ]


class BusSerializer(serializers.ModelSerializer):
    """
    Serializador para unidades de buses de la flota BusDrex.
    """
    tipo_bus_display = serializers.CharField(source='get_tipo_bus_display', read_only=True)

    class Meta:
        model = Bus
        fields = ['id', 'patente', 'modelo', 'capacidad_total', 'tipo_bus', 'tipo_bus_display']


class RutaSerializer(serializers.ModelSerializer):
    """
    Serializador para rutas entre terminales. Soporta lectura anidada y escritura por ID.
    Almacena duración en minutos (duracion_minutos) según la 3FN del DBML.
    """
    origen = TerminalSerializer(read_only=True)
    destino = TerminalSerializer(read_only=True)
    origen_id = serializers.PrimaryKeyRelatedField(
        queryset=Terminal.objects.all(), source='origen', write_only=True
    )
    destino_id = serializers.PrimaryKeyRelatedField(
        queryset=Terminal.objects.all(), source='destino', write_only=True
    )
    duracion_formateada = serializers.CharField(read_only=True)

    class Meta:
        model = Ruta
        fields = [
            'id',
            'origen',
            'destino',
            'origen_id',
            'destino_id',
            'duracion_minutos',
            'duracion_formateada',
        ]

    def validate(self, attrs):
        origen = attrs.get('origen')
        destino = attrs.get('destino')
        if origen and destino and origen == destino:
            raise serializers.ValidationError({"destino_id": "El terminal de destino debe ser distinto al de origen."})
        return attrs


class AsientoSerializer(serializers.ModelSerializer):
    """
    Serializador para consultar y representar asientos físicos con su tipo de confort
    (SEMICAMA o CAMA), disponibilidad y precio asociado al servicio.
    """
    tipo_asiento_display = serializers.CharField(source='get_tipo_asiento_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    precio = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Asiento
        fields = [
            'id',
            'servicio_id',
            'numero_asiento',
            'tipo_asiento',
            'tipo_asiento_display',
            'estado',
            'estado_display',
            'precio',
        ]
        read_only_fields = ['id', 'servicio_id', 'numero_asiento', 'precio', 'estado_display', 'tipo_asiento_display']


class AsientoAdminSerializer(serializers.ModelSerializer):
    """
    Serializador para gestión administrativa directa de asientos (CRUD admin).
    """
    tipo_asiento_display = serializers.CharField(source='get_tipo_asiento_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    precio = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Asiento
        fields = [
            'id',
            'servicio',
            'numero_asiento',
            'tipo_asiento',
            'tipo_asiento_display',
            'estado',
            'estado_display',
            'precio',
        ]


class ServicioListSerializer(serializers.ModelSerializer):
    """
    Serializador optimizado para la consulta pública y búsqueda de servicios/itinerarios.
    Incluye tarifas diferenciadas (Semicama y Salón Cama) y 'precio_desde'.
    """
    ruta = RutaSerializer(read_only=True)
    bus = BusSerializer(read_only=True)
    asientos_disponibles = serializers.SerializerMethodField()
    capacidad_total = serializers.IntegerField(source='bus.capacidad_total', read_only=True)
    precio_desde = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Servicio
        fields = [
            'id',
            'ruta',
            'bus',
            'fecha_hora_salida',
            'tarifa_semicama',
            'tarifa_cama',
            'precio_desde',
            'asientos_disponibles',
            'capacidad_total',
        ]

    def get_asientos_disponibles(self, obj) -> int:
        return obj.asientos_disponibles_count()


class ServicioWriteSerializer(serializers.ModelSerializer):
    """
    Serializador utilizado por el Administrador de Flota para crear y editar servicios.
    Soporta asignación de tarifa_semicama y tarifa_cama, y genera asientos automáticamente.
    """
    class Meta:
        model = Servicio
        fields = [
            'id',
            'ruta',
            'bus',
            'fecha_hora_salida',
            'tarifa_semicama',
            'tarifa_cama',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        servicio = super().create(validated_data)
        servicio.generar_asientos_automaticamente()
        return servicio


class OfertaSerializer(serializers.ModelSerializer):
    """
    Serializador para ofertas y promociones interurbanas (banners en Turbus.cl).
    """
    ruta_display = serializers.StringRelatedField(source='ruta', read_only=True)

    class Meta:
        model = Oferta
        fields = [
            'id',
            'titulo',
            'descripcion',
            'descuento_porcentaje',
            'ruta',
            'ruta_display',
            'fecha_inicio',
            'fecha_fin',
            'activa',
        ]

    def validate(self, attrs):
        """Valida que fecha_fin no sea anterior a fecha_inicio en la oferta."""
        fecha_inicio = attrs.get('fecha_inicio')
        fecha_fin = attrs.get('fecha_fin')
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise serializers.ValidationError({
                'fecha_fin': 'La fecha de fin de vigencia no puede ser anterior a la fecha de inicio.'
            })
        return attrs
