"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/serializers.py)
Serializadores para Carro, DetalleVenta, Boletos y Ventas en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Cumplimiento 3FN:
- ItemCarroSerializer expone 'nombre_pasajero', 'rut_pasajero' y 'precio'
  calculado dinámicamente desde el asiento asociado.
- DetalleVentaSerializer obtiene datos del pasajero desde la entidad 'Pasajero'.
- BoletoSerializer se relaciona OneToOne con DetalleVenta y expone campos
  delegados a través de dicha relación para el frontend.
- VentaSerializer expone detalles y boletos emitidos.
==============================================================================
"""

from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from .models import CarroPasajes, ItemCarro, Venta, DetalleVenta, Boleto, Pasajero
from transporte.models import Asiento


class PasajeroSerializer(serializers.ModelSerializer):
    """
    Serializador para el maestro de pasajeros (3FN).
    """
    class Meta:
        model = Pasajero
        fields = ['id', 'rut', 'nombre_completo']


class ItemCarroSerializer(serializers.ModelSerializer):
    """
    Serializador de lectura para los ítems presentes en el carro de pasajes.
    Expone detalles completos del servicio, bus, ruta y pasajero asignado.
    Calcula el precio dinámicamente según tarifa y categoría de asiento.
    """
    numero_asiento = serializers.IntegerField(source='asiento.numero_asiento', read_only=True)
    tipo_asiento = serializers.CharField(source='asiento.tipo_asiento', read_only=True)
    tipo_asiento_display = serializers.CharField(source='asiento.get_tipo_asiento_display', read_only=True)
    servicio_id = serializers.IntegerField(source='asiento.servicio_id', read_only=True)
    origen = serializers.CharField(source='asiento.servicio.ruta.origen.ciudad.nombre', read_only=True)
    destino = serializers.CharField(source='asiento.servicio.ruta.destino.ciudad.nombre', read_only=True)
    fecha_hora_salida = serializers.DateTimeField(source='asiento.servicio.fecha_hora_salida', read_only=True)
    tipo_bus = serializers.CharField(source='asiento.servicio.bus.get_tipo_bus_display', read_only=True)
    nombre_pasajero = serializers.CharField(source='pasajero.nombre_completo', read_only=True)
    rut_pasajero = serializers.CharField(source='pasajero.rut', read_only=True)
    pasajero_id = serializers.IntegerField(source='pasajero.id', read_only=True)
    precio = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    precio_unitario = serializers.DecimalField(source='precio', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ItemCarro
        fields = [
            'id',
            'asiento_id',
            'numero_asiento',
            'tipo_asiento',
            'tipo_asiento_display',
            'servicio_id',
            'origen',
            'destino',
            'fecha_hora_salida',
            'tipo_bus',
            'pasajero_id',
            'nombre_pasajero',
            'rut_pasajero',
            'precio',
            'precio_unitario',
            'fecha_agregado',
        ]


class ItemCarroCreateSerializer(serializers.Serializer):
    """
    Serializador para agregar un pasaje al carro de compras.
    Requiere asiento_id y los datos nominativos del pasajero (nombre y RUT).
    Valida disponibilidad preliminar y vigencia horaria sin descontar stock.
    """
    asiento_id = serializers.IntegerField(
        required=True,
        help_text="ID único del asiento físico a reservar."
    )
    nombre_pasajero = serializers.CharField(
        max_length=150,
        required=True,
        help_text="Nombre completo del pasajero que viajará."
    )
    rut_pasajero = serializers.CharField(
        max_length=20,
        required=True,
        help_text="RUT o documento de identidad del pasajero."
    )

    def validate_asiento_id(self, value):
        try:
            asiento = Asiento.objects.select_related('servicio').get(id=value)
        except Asiento.DoesNotExist:
            raise serializers.ValidationError("El asiento especificado no existe.")

        # Verificación preliminar de disponibilidad
        if asiento.estado == Asiento.ESTADO_OCUPADO:
            raise serializers.ValidationError(
                f"El asiento #{asiento.numero_asiento} ya se encuentra ocupado."
            )

        # Verificación de que el bus no haya zarpado
        if asiento.servicio.fecha_hora_salida <= timezone.now():
            raise serializers.ValidationError(
                "No se puede agregar al carro un asiento de un servicio que ya ha zarpado."
            )

        return value


class CarroPasajesSerializer(serializers.ModelSerializer):
    """
    Serializador del carro de compras persistente.
    Incluye todos los ítems agregados y el cálculo del monto total en tiempo real.
    """
    items = ItemCarroSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    cantidad_items = serializers.SerializerMethodField()
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)

    class Meta:
        model = CarroPasajes
        fields = [
            'id',
            'usuario',
            'usuario_username',
            'cantidad_items',
            'total',
            'items',
            'fecha_actualizacion',
        ]
        read_only_fields = ['id', 'usuario', 'fecha_actualizacion']

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total(self, obj):
        return obj.calcular_total()

    @extend_schema_field(serializers.IntegerField())
    def get_cantidad_items(self, obj) -> int:
        return obj.total_items()


class DetalleVentaSerializer(serializers.ModelSerializer):
    """
    Serializador para los detalles inmutables de pasajes de una venta (historial congelado).
    """
    numero_asiento = serializers.IntegerField(source='asiento.numero_asiento', read_only=True)
    tipo_asiento = serializers.CharField(source='asiento.tipo_asiento', read_only=True)
    tipo_asiento_display = serializers.CharField(source='asiento.get_tipo_asiento_display', read_only=True)
    servicio_id = serializers.IntegerField(source='asiento.servicio_id', read_only=True)
    origen = serializers.CharField(source='asiento.servicio.ruta.origen.ciudad.nombre', read_only=True)
    destino = serializers.CharField(source='asiento.servicio.ruta.destino.ciudad.nombre', read_only=True)
    fecha_hora_salida = serializers.DateTimeField(source='asiento.servicio.fecha_hora_salida', read_only=True)
    nombre_pasajero = serializers.CharField(source='pasajero.nombre_completo', read_only=True)
    rut_pasajero = serializers.CharField(source='pasajero.rut', read_only=True)
    pasajero_id = serializers.IntegerField(source='pasajero.id', read_only=True)

    class Meta:
        model = DetalleVenta
        fields = [
            'id',
            'asiento_id',
            'numero_asiento',
            'tipo_asiento',
            'tipo_asiento_display',
            'servicio_id',
            'origen',
            'destino',
            'fecha_hora_salida',
            'pasajero_id',
            'nombre_pasajero',
            'rut_pasajero',
            'precio_unitario',
        ]


class BoletoSerializer(serializers.ModelSerializer):
    """
    Serializador para boletos/tickets electrónicos emitidos en 3FN.
    Obtiene sus atributos relacionales a través de 'detalle_venta'.
    """
    numero_asiento = serializers.IntegerField(source='detalle_venta.asiento.numero_asiento', read_only=True)
    tipo_asiento = serializers.CharField(source='detalle_venta.asiento.tipo_asiento', read_only=True)
    tipo_asiento_display = serializers.CharField(source='detalle_venta.asiento.get_tipo_asiento_display', read_only=True)
    servicio_id = serializers.IntegerField(source='detalle_venta.asiento.servicio_id', read_only=True)
    origen = serializers.CharField(source='detalle_venta.asiento.servicio.ruta.origen.ciudad.nombre', read_only=True)
    destino = serializers.CharField(source='detalle_venta.asiento.servicio.ruta.destino.ciudad.nombre', read_only=True)
    terminal_origen = serializers.CharField(source='detalle_venta.asiento.servicio.ruta.origen.nombre', read_only=True)
    terminal_destino = serializers.CharField(source='detalle_venta.asiento.servicio.ruta.destino.nombre', read_only=True)
    fecha_hora_salida = serializers.DateTimeField(source='detalle_venta.asiento.servicio.fecha_hora_salida', read_only=True)
    tipo_bus = serializers.CharField(source='detalle_venta.asiento.servicio.bus.get_tipo_bus_display', read_only=True)
    patente_bus = serializers.CharField(source='detalle_venta.asiento.servicio.bus.patente', read_only=True)
    nombre_pasajero = serializers.CharField(source='detalle_venta.pasajero.nombre_completo', read_only=True)
    rut_pasajero = serializers.CharField(source='detalle_venta.pasajero.rut', read_only=True)
    precio_pagado = serializers.DecimalField(source='detalle_venta.precio_unitario', max_digits=10, decimal_places=2, read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = Boleto
        fields = [
            'id',
            'codigo_boleto',
            'codigo_hash',
            'nombre_pasajero',
            'rut_pasajero',
            'numero_asiento',
            'tipo_asiento',
            'tipo_asiento_display',
            'servicio_id',
            'origen',
            'destino',
            'terminal_origen',
            'terminal_destino',
            'fecha_hora_salida',
            'tipo_bus',
            'patente_bus',
            'precio_pagado',
            'estado',
            'estado_display',
            'fecha_emision',
        ]


class VentaSerializer(serializers.ModelSerializer):
    """
    Serializador maestro de la Venta / Orden de compra.
    Contiene la lista anidada de detalles congelados y boletos emitidos.
    """
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    boletos = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id',
            'codigo_transaccion',
            'usuario_username',
            'total',
            'estado',
            'estado_display',
            'fecha_creacion',
            'detalles',
            'boletos',
        ]
        read_only_fields = ['id', 'codigo_transaccion', 'fecha_creacion', 'detalles', 'boletos']

    @extend_schema_field(BoletoSerializer(many=True))
    def get_boletos(self, obj):
        boletos = Boleto.objects.filter(detalle_venta__venta=obj).select_related(
            'detalle_venta__asiento__servicio__ruta__origen__ciudad',
            'detalle_venta__asiento__servicio__ruta__destino__ciudad',
            'detalle_venta__asiento__servicio__bus',
            'detalle_venta__pasajero'
        )
        return BoletoSerializer(boletos, many=True).data


class ActualizarEstadoVentaSerializer(serializers.ModelSerializer):
    """
    Serializador utilizado por el Administrador de Flota para modificar el estado de una venta.
    Utiliza estrictamente la tupla de CHOICES definida en el modelo.
    """
    class Meta:
        model = Venta
        fields = ['estado']

    def validate_estado(self, value):
        estados_validos = [choice[0] for choice in Venta.ESTADOS_VENTA_CHOICES]
        if value not in estados_validos:
            raise serializers.ValidationError(
                f"Estado inválido. Opciones válidas: {', '.join(estados_validos)}"
            )
        return value
