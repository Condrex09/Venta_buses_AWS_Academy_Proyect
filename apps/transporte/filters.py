"""
==============================================================================
BusDrex - MÓDULO: TRANSPORTE (apps/transporte/filters.py)
Filtros Avanzados para Catálogos, Geografía y Servicios (django-filter en 3FN)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos
==============================================================================
"""

import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Region, Ciudad, Terminal, Ruta, Bus, Servicio, Asiento, Oferta


class RegionFilter(django_filters.FilterSet):
    """Filtro para catálogo de regiones."""
    nombre = django_filters.CharFilter(lookup_expr='icontains', label="Nombre de la Región")

    class Meta:
        model = Region
        fields = ['nombre']


class CiudadFilter(django_filters.FilterSet):
    """Filtro para catálogo de ciudades asociadas a regiones."""
    nombre = django_filters.CharFilter(lookup_expr='icontains', label="Nombre de la Ciudad")
    region = django_filters.NumberFilter(field_name='region_id', label="ID de Región")
    region_nombre = django_filters.CharFilter(
        field_name='region__nombre',
        lookup_expr='icontains',
        label="Nombre de la Región"
    )

    class Meta:
        model = Ciudad
        fields = ['nombre', 'region', 'region_nombre']


class TerminalFilter(django_filters.FilterSet):
    """Filtro para terminales y localidades normalizadas."""
    nombre = django_filters.CharFilter(lookup_expr='icontains', label="Nombre del Terminal")
    ciudad = django_filters.NumberFilter(field_name='ciudad_id', label="ID de Ciudad")
    ciudad_nombre = django_filters.CharFilter(
        field_name='ciudad__nombre',
        lookup_expr='icontains',
        label="Nombre de Ciudad"
    )
    region = django_filters.NumberFilter(field_name='ciudad__region_id', label="ID de Región")
    region_nombre = django_filters.CharFilter(
        field_name='ciudad__region__nombre',
        lookup_expr='icontains',
        label="Nombre de Región"
    )

    class Meta:
        model = Terminal
        fields = ['nombre', 'ciudad', 'ciudad_nombre', 'region', 'region_nombre']


class RutaFilter(django_filters.FilterSet):
    """Filtro para rutas interurbanas en 3FN."""
    origen = django_filters.NumberFilter(field_name='origen_id', label="ID Terminal de Origen")
    destino = django_filters.NumberFilter(field_name='destino_id', label="ID Terminal de Destino")
    origen_ciudad = django_filters.CharFilter(
        field_name='origen__ciudad__nombre',
        lookup_expr='icontains',
        label="Ciudad de Origen"
    )
    destino_ciudad = django_filters.CharFilter(
        field_name='destino__ciudad__nombre',
        lookup_expr='icontains',
        label="Ciudad de Destino"
    )
    origen_ciudad_id = django_filters.NumberFilter(
        field_name='origen__ciudad_id',
        label="ID Ciudad de Origen"
    )
    destino_ciudad_id = django_filters.NumberFilter(
        field_name='destino__ciudad_id',
        label="ID Ciudad de Destino"
    )

    class Meta:
        model = Ruta
        fields = ['origen', 'destino', 'origen_ciudad', 'destino_ciudad', 'origen_ciudad_id', 'destino_ciudad_id']


class ServicioFilter(django_filters.FilterSet):
    """
    ===========================================================================
    FILTRO AVANZADO DE SERVICIOS/ITINERARIOS (ServicioFilter)
    Evaluacion 2: Benjamin Gomez | Seccion AP-N4-C1 | 2026
    ===========================================================================
    Parametros soportados:
    - origen_ciudad       : Nombre parcial de la ciudad de origen (icontains)
    - destino_ciudad      : Nombre parcial de la ciudad de destino (icontains)
    - origen_terminal     : Nombre parcial del terminal de origen (icontains)
    - destino_terminal    : Nombre parcial del terminal de destino (icontains)
    - fecha_salida        : Fecha exacta YYYY-MM-DD
    - fecha_desde/hasta   : Rango de fecha y hora de salida
    - tipo_bus            : SEMICAMA | SALON_CAMA | PREMIUM (exacto; invalido -> HTTP 400)
    - tipo_asiento        : SEMICAMA | CAMA (filtra por disponibilidad de asientos)
    - tarifa_minima/maxima: Rango de tarifa en CLP
    - solo_disponibles    : true -> solo servicios con asientos libres
    - solo_futuros        : true -> solo servicios no zarpados
    ===========================================================================
    REGLA DE COMBINACION tipo_bus + tipo_asiento:
    - Bus SEMICAMA   -> solo ofrece asientos SEMICAMA.
                        tipo_bus=SEMICAMA + tipo_asiento=CAMA  -> 0 resultados.
    - Bus SALON_CAMA -> solo ofrece asientos CAMA.
                        tipo_bus=SALON_CAMA + tipo_asiento=SEMICAMA -> 0 resultados.
    - Bus PREMIUM    -> ofrece AMBOS tipos de asiento.
                        tipo_bus=PREMIUM + tipo_asiento=CAMA filtra solo los Premium
                        con asientos CAMA disponibles.
    Los dos filtros se combinan por AND (interseccion). El resultado vacio se
    muestra con el estado "Sin resultados" y boton "Limpiar Filtros" en el front.
    ===========================================================================
    """

    origen_ciudad = django_filters.CharFilter(
        field_name='ruta__origen__ciudad__nombre',
        lookup_expr='icontains',
        label="Ciudad de Origen"
    )
    destino_ciudad = django_filters.CharFilter(
        field_name='ruta__destino__ciudad__nombre',
        lookup_expr='icontains',
        label="Ciudad de Destino"
    )
    origen_terminal = django_filters.CharFilter(
        field_name='ruta__origen__nombre',
        lookup_expr='icontains',
        label="Terminal de Origen"
    )
    destino_terminal = django_filters.CharFilter(
        field_name='ruta__destino__nombre',
        lookup_expr='icontains',
        label="Terminal de Destino"
    )
    fecha_salida = django_filters.DateFilter(
        field_name='fecha_hora_salida__date',
        label="Fecha de Salida Exacta (YYYY-MM-DD)"
    )
    fecha_desde = django_filters.DateTimeFilter(
        field_name='fecha_hora_salida',
        lookup_expr='gte',
        label="Fecha y Hora de Salida Minima"
    )
    fecha_hasta = django_filters.DateTimeFilter(
        field_name='fecha_hora_salida',
        lookup_expr='lte',
        label="Fecha y Hora de Salida Maxima"
    )
    # tipo_bus: implementado via method para poder retornar HTTP 400 con mensaje en espanol
    # si llega un valor que no sea SEMICAMA, SALON_CAMA o PREMIUM.
    tipo_bus = django_filters.CharFilter(
        method='filter_tipo_bus',
        label="Tipo de Bus (SEMICAMA | SALON_CAMA | PREMIUM). Valor invalido retorna HTTP 400."
    )
    tipo_asiento = django_filters.CharFilter(
        method='filter_tipo_asiento',
        label="Tipo de Asiento Disponible (SEMICAMA o CAMA)"
    )
    tarifa_minima = django_filters.NumberFilter(
        method='filter_tarifa_minima',
        label="Tarifa Minima (CLP)"
    )
    tarifa_maxima = django_filters.NumberFilter(
        method='filter_tarifa_maxima',
        label="Tarifa Maxima (CLP)"
    )
    solo_disponibles = django_filters.BooleanFilter(
        method='filter_solo_disponibles',
        label="Solo Servicios con Asientos Disponibles"
    )
    solo_futuros = django_filters.BooleanFilter(
        method='filter_solo_futuros',
        label="Solo Servicios Futuros (no zarpados)"
    )

    class Meta:
        model = Servicio
        fields = [
            'origen_ciudad',
            'destino_ciudad',
            'origen_terminal',
            'destino_terminal',
            'fecha_salida',
            'fecha_desde',
            'fecha_hasta',
            'tipo_bus',
            'tipo_asiento',
            'tarifa_minima',
            'tarifa_maxima',
            'solo_disponibles',
            'solo_futuros',
        ]

    # Valores validos para tipo_bus (extraidos de Bus.TIPOS_BUS_CHOICES)
    _TIPOS_BUS_VALIDOS = {c[0] for c in Bus.TIPOS_BUS_CHOICES}

    def filter_tipo_bus(self, queryset, name, value):
        """
        Filtra servicios por tipo de bus (SEMICAMA, SALON_CAMA o PREMIUM).
        Si el valor enviado no es valido, agrega un error al formulario para
        que la vista devuelva HTTP 400 con un mensaje descriptivo en espanol.
        """
        if not value:
            return queryset
        valor_upper = value.strip().upper()
        if valor_upper not in self._TIPOS_BUS_VALIDOS:
            tipos_str = ', '.join(sorted(self._TIPOS_BUS_VALIDOS))
            self.form.add_error(
                'tipo_bus',
                f"Valor invalido '{value}'. Los tipos de bus permitidos son: {tipos_str}."
            )
            return queryset.none()
        return queryset.filter(bus__tipo_bus=valor_upper)

    def filter_tipo_asiento(self, queryset, name, value):
        if value:
            return queryset.filter(
                asientos__tipo_asiento__iexact=value,
                asientos__estado=Asiento.ESTADO_DISPONIBLE
            ).distinct()
        return queryset

    def filter_tarifa_minima(self, queryset, name, value):
        if value is not None:
            return queryset.filter(
                Q(tarifa_semicama__gte=value) | Q(tarifa_cama__gte=value)
            )
        return queryset

    def filter_tarifa_maxima(self, queryset, name, value):
        if value is not None:
            return queryset.filter(
                Q(tarifa_semicama__lte=value) | Q(tarifa_cama__lte=value)
            )
        return queryset

    def filter_solo_disponibles(self, queryset, name, value):
        if value:
            return queryset.filter(asientos__estado=Asiento.ESTADO_DISPONIBLE).distinct()
        return queryset

    def filter_solo_futuros(self, queryset, name, value):
        if value:
            return queryset.filter(fecha_hora_salida__gt=timezone.now())
        return queryset


class BusFilter(django_filters.FilterSet):
    """Filtros para flota de buses."""
    tipo_bus = django_filters.ChoiceFilter(choices=Bus.TIPOS_BUS_CHOICES)

    class Meta:
        model = Bus
        fields = ['tipo_bus']


class OfertaFilter(django_filters.FilterSet):
    """Filtros para ofertas y promociones."""
    activa = django_filters.BooleanFilter(field_name='activa')

    class Meta:
        model = Oferta
        fields = ['activa']
