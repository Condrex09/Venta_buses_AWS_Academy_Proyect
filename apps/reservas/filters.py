"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/filters.py)
Filtros Avanzados para Ventas y Boletos en 3FN (django-filter)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos
==============================================================================
Configura filtros específicos para:
- Ventas / Órdenes (estado, rango de fechas, usuario)
- Boletos emitidos (estado, código UUID, RUT y nombre del pasajero)
==============================================================================
"""

import django_filters
from .models import Venta, Boleto


class VentaFilter(django_filters.FilterSet):
    """
    Filtro para órdenes de venta.
    Permite filtrar por estado (PENDIENTE, PAGADO, ENTREGADO, CANCELADO),
    rango de fechas de creación y usuario comprador.
    """
    estado = django_filters.ChoiceFilter(
        choices=Venta.ESTADOS_VENTA_CHOICES,
        label="Estado de la Venta"
    )
    usuario = django_filters.NumberFilter(
        field_name='usuario_id',
        label="ID del Usuario"
    )
    usuario_username = django_filters.CharFilter(
        field_name='usuario__username',
        lookup_expr='icontains',
        label="Nombre de Usuario"
    )
    fecha_desde = django_filters.DateTimeFilter(
        field_name='fecha_creacion',
        lookup_expr='gte',
        label="Fecha Mínima de Creación"
    )
    fecha_hasta = django_filters.DateTimeFilter(
        field_name='fecha_creacion',
        lookup_expr='lte',
        label="Fecha Máxima de Creación"
    )

    class Meta:
        model = Venta
        fields = ['estado', 'usuario', 'usuario_username', 'fecha_desde', 'fecha_hasta']


class BoletoFilter(django_filters.FilterSet):
    """
    Filtro para boletos emitidos en 3FN.
    Permite filtrar por estado (VALIDO, ANULADO), código de boleto, y datos del pasajero.
    """
    estado = django_filters.ChoiceFilter(
        choices=Boleto.ESTADOS_BOLETO_CHOICES,
        label="Estado del Boleto"
    )
    codigo_boleto = django_filters.CharFilter(
        lookup_expr='icontains',
        label="Código UUID del Boleto"
    )
    rut_pasajero = django_filters.CharFilter(
        field_name='detalle_venta__pasajero__rut',
        lookup_expr='icontains',
        label="RUT del Pasajero"
    )
    nombre_pasajero = django_filters.CharFilter(
        field_name='detalle_venta__pasajero__nombre_completo',
        lookup_expr='icontains',
        label="Nombre del Pasajero"
    )

    class Meta:
        model = Boleto
        fields = ['estado', 'codigo_boleto', 'rut_pasajero', 'nombre_pasajero']
