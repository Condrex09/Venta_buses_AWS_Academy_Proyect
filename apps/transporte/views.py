"""
==============================================================================
BusDrex - MÓDULO: TRANSPORTE (apps/transporte/views.py)
Controladores y Vistas de DRF para la Gestión de Transporte, Geografía y Servicios en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Endpoints implementados:
- GET /api/servicios/buscar/ : Búsqueda pública avanzada con filtros
- GET /api/servicios/{id}/asientos/ : Consulta pública del plano y disponibilidad de asientos
- CRUD /api/regiones/ : Catálogo de regiones (lectura pública, CRUD ADMIN_FLOTA)
- CRUD /api/ciudades/ : Catálogo de ciudades por región (lectura pública, CRUD ADMIN_FLOTA)
- CRUD /api/terminales/ : Catálogo de terminales por ciudad (lectura pública, CRUD ADMIN_FLOTA)
- CRUD /api/buses/ : Catálogo de flota de buses con filtros
- CRUD /api/rutas/ : Catálogo de rutas interurbanas con filtros
- CRUD /api/servicios/ : CRUD de servicios para Administrador de Flota
- CRUD /api/asientos/ : Gestión de asientos para Administrador de Flota
- CRUD /api/ofertas/ : Catálogo público y gestión de ofertas y promociones
- Manejo estricto de ProtectedError devolviendo HTTP 409 Conflict.
==============================================================================
"""

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from .models import Region, Ciudad, Terminal, Bus, Ruta, Servicio, Asiento, Oferta
from .serializers import (
    RegionSerializer,
    CiudadSerializer,
    TerminalSerializer,
    BusSerializer,
    RutaSerializer,
    ServicioListSerializer,
    ServicioWriteSerializer,
    AsientoSerializer,
    AsientoAdminSerializer,
    OfertaSerializer,
)
from .filters import (
    RegionFilter,
    CiudadFilter,
    ServicioFilter,
    TerminalFilter,
    RutaFilter,
    BusFilter,
    OfertaFilter,
)
from usuarios.permissions import IsAdminFlotaOrReadOnly


class ProteccionIntegridadMixin:
    """
    Mixin para capturar excepciones ProtectedError al eliminar registros protegidos por FK
    y retornar una respuesta HTTP 409 Conflict con mensaje descriptivo en español.
    """
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError as e:
            return Response(
                {
                    "error": "Conflicto de integridad referencial.",
                    "detalle": "No es posible eliminar este registro porque se encuentra referenciado por otros datos activos en el sistema (PROTECT).",
                    "mensaje": "Verifique y elimine las dependencias asociadas antes de intentar borrar este elemento."
                },
                status=status.HTTP_409_CONFLICT
            )


# ==============================================================================
# 1. BÚSQUEDA PÚBLICA DE SERVICIOS CON FILTROS (GET /api/servicios/buscar/)
# ==============================================================================
@extend_schema(
    tags=['Servicios e Itinerarios (Público)'],
    summary='Búsqueda pública de servicios e itinerarios con filtros avanzados',
    description=(
        "Permite a cualquier usuario consultar los servicios de viaje disponibles estilo Turbus.cl. "
        "Soporta filtros por: ciudad de origen (`origen_ciudad`), ciudad de destino (`destino_ciudad`), "
        "fecha de salida (`fecha_salida` formato YYYY-MM-DD), "
        "tipo de bus (`tipo_bus`: SEMICAMA | SALON_CAMA | PREMIUM — valor inválido devuelve HTTP 400), "
        "tipo de asiento (`tipo_asiento`: SEMICAMA o CAMA), rangos de tarifa, "
        "solo con disponibilidad y solo futuros. "
        "Regla de combinación: Bus SEMICAMA solo tiene asientos SEMICAMA; Bus SALON_CAMA solo CAMA; "
        "Bus PREMIUM tiene ambos tipos."
    ),
    responses={200: ServicioListSerializer(many=True)}
)
class ServicioBuscarView(generics.ListAPIView):
    """
    Endpoint público de búsqueda y cotización de pasajes.
    Utiliza django-filter para parametrización precisa.
    Si el FilterSet detecta un parámetro inválido (ej. tipo_bus desconocido),
    se retorna HTTP 400 con el mensaje de error en español.
    """
    queryset = Servicio.objects.select_related(
        'ruta__origen__ciudad__region',
        'ruta__destino__ciudad__region',
        'bus'
    ).prefetch_related('asientos').all().order_by('fecha_hora_salida')

    serializer_class = ServicioListSerializer
    permission_classes = [permissions.AllowAny]
    filterset_class = ServicioFilter
    search_fields = [
        'ruta__origen__ciudad__nombre',
        'ruta__destino__ciudad__nombre',
        'ruta__origen__nombre',
        'ruta__destino__nombre',
        'bus__modelo',
        'bus__patente',
    ]
    ordering_fields = ['fecha_hora_salida', 'tarifa_semicama', 'tarifa_cama']

    def list(self, request, *args, **kwargs):
        """
        Override de list para detectar errores de validación del FilterSet y
        retornar HTTP 400 con mensajes descriptivos en español en lugar de ignorarlos.
        """
        filterset = self.filterset_class(request.query_params, queryset=self.get_queryset())
        if not filterset.is_valid():
            return Response(
                {'error': 'Parámetros de filtro inválidos.', 'detalle': filterset.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().list(request, *args, **kwargs)


# ==============================================================================
# 2. CONSULTA PÚBLICA DE MAPA DE ASIENTOS (GET /api/servicios/{id}/asientos/)
# ==============================================================================
@extend_schema(
    tags=['Servicios e Itinerarios (Público)'],
    summary='Consultar mapa, tipo de confort y disponibilidad de asientos de un servicio',
    description=(
        "Retorna todos los asientos físicos del bus para el servicio especificado, "
        "indicando número, tipo de asiento (SEMICAMA o CAMA), precio aplicable "
        "y estado de ocupación (DISPONIBLE u OCUPADO)."
    ),
    parameters=[
        OpenApiParameter(name='id', description='ID del Servicio', required=True, type=int, location=OpenApiParameter.PATH)
    ],
    responses={
        200: OpenApiResponse(
            description="Listado completo de asientos y resumen de disponibilidad.",
            response=AsientoSerializer(many=True)
        ),
        404: OpenApiResponse(description="Servicio no encontrado.")
    }
)
class ServicioAsientosView(APIView):
    """
    Endpoint público para visualizar el plano de asientos y estado de ocupación del viaje.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk=None, id=None):
        servicio_id = pk or id or self.kwargs.get('id') or self.kwargs.get('pk')
        servicio = get_object_or_404(
            Servicio.objects.select_related(
                'bus',
                'ruta__origen__ciudad__region',
                'ruta__destino__ciudad__region'
            ),
            pk=servicio_id
        )

        if not servicio.asientos.exists():
            servicio.generar_asientos_automaticamente()

        asientos = servicio.asientos.all().order_by('numero_asiento')
        serializer = AsientoSerializer(asientos, many=True)

        return Response({
            'servicio_id': servicio.id,
            'origen': str(servicio.ruta.origen),
            'destino': str(servicio.ruta.destino),
            'fecha_hora_salida': servicio.fecha_hora_salida,
            'tipo_bus': servicio.bus.get_tipo_bus_display(),
            'tarifa_semicama': servicio.tarifa_semicama,
            'tarifa_cama': servicio.tarifa_cama,
            'precio_desde': servicio.precio_desde,
            'total_asientos': servicio.bus.capacidad_total,
            'asientos_disponibles': servicio.asientos_disponibles_count(),
            'asientos_ocupados': servicio.bus.capacidad_total - servicio.asientos_disponibles_count(),
            'asientos': serializer.data
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 3. GESTIÓN CRUD DE SERVICIOS (ADMINISTRADOR DE FLOTA)
# ==============================================================================
@extend_schema(
    tags=['Gestión de Flota (Administrador)'],
    description=(
        "Permite al Administrador de Flota crear, modificar, consultar o dar de baja servicios. "
        "Al crear un nuevo servicio, el sistema genera automáticamente el inventario de asientos "
        "con distribución de Salón Cama y Semicama en estado DISPONIBLE."
    )
)
class ServicioViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD completo de servicios e itinerarios.
    - Lectura (GET): Pública o autenticada.
    - Escritura: Exclusiva para Administrador de Flota.
    """
    queryset = Servicio.objects.select_related(
        'ruta__origen__ciudad__region',
        'ruta__destino__ciudad__region',
        'bus'
    ).all().order_by('fecha_hora_salida')
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = ServicioFilter
    ordering_fields = ['fecha_hora_salida', 'tarifa_semicama', 'tarifa_cama']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ServicioWriteSerializer
        return ServicioListSerializer


# ==============================================================================
# 4. VIEWSETS GEOGRÁFICOS Y DE TRANSPORTE (3FN)
# ==============================================================================
@extend_schema(tags=['Catálogos de Geografía y Transporte'])
class RegionViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para Regiones de Chile (3FN). Lectura pública, escritura solo ADMIN_FLOTA.
    """
    queryset = Region.objects.all().order_by('nombre')
    serializer_class = RegionSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = RegionFilter
    search_fields = ['nombre']


@extend_schema(tags=['Catálogos de Geografía y Transporte'])
class CiudadViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para Ciudades por Región (3FN). Lectura pública, escritura solo ADMIN_FLOTA.
    """
    queryset = Ciudad.objects.select_related('region').all().order_by('region__nombre', 'nombre')
    serializer_class = CiudadSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = CiudadFilter
    search_fields = ['nombre', 'region__nombre']


@extend_schema(tags=['Catálogos de Geografía y Transporte'])
class TerminalViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para terminales de buses. Recibe 'ciudad' (ID) y retorna 'ciudad_nombre' y 'region_nombre'.
    """
    queryset = Terminal.objects.select_related('ciudad__region').all().order_by('ciudad__nombre', 'nombre')
    serializer_class = TerminalSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = TerminalFilter
    search_fields = ['nombre', 'ciudad__nombre', 'ciudad__region__nombre']


@extend_schema(tags=['Catálogos de Geografía y Transporte'])
class BusViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para unidades de transporte de la flota BusDrex.
    """
    queryset = Bus.objects.all().order_by('patente')
    serializer_class = BusSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = BusFilter
    search_fields = ['patente', 'modelo', 'tipo_bus']


@extend_schema(tags=['Catálogos de Geografía y Transporte'])
class RutaViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para rutas y trayectos interurbanos con duración en minutos.
    """
    queryset = Ruta.objects.select_related(
        'origen__ciudad__region',
        'destino__ciudad__region'
    ).all().order_by('origen__ciudad__nombre', 'destino__ciudad__nombre')
    serializer_class = RutaSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = RutaFilter
    search_fields = ['origen__ciudad__nombre', 'destino__ciudad__nombre', 'origen__nombre', 'destino__nombre']


# ==============================================================================
# 5. GESTIÓN DE ASIENTOS (CRUD ADMINISTRADOR)
# ==============================================================================
@extend_schema(tags=['Gestión de Flota (Administrador)'])
class AsientoViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para gestión individual de asientos de servicios.
    Permite al Administrador de Flota actualizar tipo o estado de un asiento específico.
    """
    queryset = Asiento.objects.select_related(
        'servicio__ruta__origen__ciudad',
        'servicio__ruta__destino__ciudad',
        'servicio__bus'
    ).all().order_by('servicio', 'numero_asiento')
    serializer_class = AsientoAdminSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_fields = ['servicio', 'estado', 'tipo_asiento']


# ==============================================================================
# 6. GESTIÓN Y CONSULTA DE OFERTAS / PROMOCIONES
# ==============================================================================
@extend_schema(tags=['Ofertas y Promociones'])
class OfertaViewSet(ProteccionIntegridadMixin, viewsets.ModelViewSet):
    """
    CRUD para ofertas y promociones interurbanas estilo Turbus.cl.
    - Lectura (GET): Pública para alimentar el banner del Home.
    - Escritura: Exclusiva para Administrador de Flota.
    """
    queryset = Oferta.objects.select_related('ruta__origen', 'ruta__destino').all().order_by('-activa', 'fecha_fin')
    serializer_class = OfertaSerializer
    permission_classes = [IsAdminFlotaOrReadOnly]
    filterset_class = OfertaFilter
    search_fields = ['titulo', 'descripcion']
