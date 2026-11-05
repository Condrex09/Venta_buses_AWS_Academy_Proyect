"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/views.py)
Controladores del Ciclo Transaccional: Carro, Checkout, Pago, Boletos y Ventas en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Endpoints implementados:
- GET, POST, DELETE /api/carro-pasajes/ : Gestión de carro persistente (Pasajero)
- POST /api/ventas/checkout/ : Checkout atómico (Venta PENDIENTE con precios congelados)
- POST /api/ventas/{id}/pagar/ : Pago atómico con select_for_update() y emisión de boletos
- POST /api/ventas/{id}/cancelar/ : Cancelación por parte del pasajero (órdenes PENDIENTES)
- GET /api/mis-ordenes/ : Historial de ventas/órdenes del pasajero con filtros
- GET /api/mis-boletos/ : Historial de boletos del pasajero con filtros
- GET /api/ventas/ : Listado global de órdenes para Administrador de Flota
- PATCH /api/ventas/{id}/estado/ : Transición de estado para Administrador de Flota
- GET, DELETE /api/admin/carros/ : Inspección y vaciado de carros para Administrador
==============================================================================
"""

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from .models import CarroPasajes, ItemCarro, Venta, DetalleVenta, Boleto, Pasajero
from .serializers import (
    CarroPasajesSerializer,
    ItemCarroSerializer,
    ItemCarroCreateSerializer,
    VentaSerializer,
    BoletoSerializer,
    ActualizarEstadoVentaSerializer,
)
from .filters import VentaFilter, BoletoFilter
from .services import (
    realizar_checkout,
    procesar_pago_venta,
    procesar_cancelacion_venta,
    cambiar_estado_venta,
)
from transporte.models import Asiento
from usuarios.permissions import IsPasajero, IsAdminFlota


class ProteccionIntegridadReservasMixin:
    """Mixin para capturar ProtectedError y responder HTTP 409 Conflict."""
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "error": "Conflicto de integridad referencial.",
                    "detalle": "No es posible eliminar este registro porque se encuentra referenciado por otros datos activos en el sistema (PROTECT)."
                },
                status=status.HTTP_409_CONFLICT
            )


# ==============================================================================
# 1. GESTIÓN DEL CARRO DE PASAJES (GET, POST, DELETE /api/carro-pasajes/)
# ==============================================================================
class CarroPasajesView(APIView):
    """
    Controlador para la gestión del carro de compras persistente.
    Exclusivo para usuarios autenticados con rol de Pasajero.
    """
    permission_classes = [permissions.IsAuthenticated, IsPasajero]

    def get_or_create_carro(self, usuario):
        carro, _ = CarroPasajes.objects.get_or_create(usuario=usuario)
        return carro

    @extend_schema(
        tags=['Carro de Pasajes (Pasajero)'],
        summary='Consultar contenido del carro de pasajes persistente',
        description='Obtiene todos los asientos guardados en el carro activo del usuario con subtotales y total general.',
        responses={200: CarroPasajesSerializer}
    )
    def get(self, request):
        carro = self.get_or_create_carro(request.user)
        serializer = CarroPasajesSerializer(carro)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Carro de Pasajes (Pasajero)'],
        summary='Agregar pasaje al carro de compras',
        description=(
            "Agrega un asiento seleccionado con los datos nominativos del pasajero (nombre y RUT). "
            "Normaliza el RUT y busca/crea la entidad Pasajero de forma normalizada (3FN). "
            "Si el RUT ya existe, se reutiliza el Pasajero sin sobreescribir su nombre. "
            "Regla de negocio: En este paso NO se descuenta el stock de asientos en la base de datos."
        ),
        request=ItemCarroCreateSerializer,
        responses={
            201: ItemCarroSerializer,
            400: OpenApiResponse(description="Asiento no disponible, zarpado o ya agregado al carro.")
        }
    )
    def post(self, request):
        serializer = ItemCarroCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        asiento_id = serializer.validated_data['asiento_id']
        nombre_pasajero = serializer.validated_data['nombre_pasajero']
        rut_pasajero = serializer.validated_data['rut_pasajero']

        asiento = get_object_or_404(
            Asiento.objects.select_related(
                'servicio__ruta__origen__ciudad',
                'servicio__ruta__destino__ciudad',
                'servicio__bus'
            ),
            id=asiento_id
        )

        # Validación de disponibilidad y horario
        if asiento.estado != Asiento.ESTADO_DISPONIBLE:
            return Response(
                {"error": f"El asiento #{asiento.numero_asiento} ya no está disponible."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if asiento.servicio.fecha_hora_salida <= timezone.now():
            return Response(
                {"error": "El servicio de este asiento ya ha zarpado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        carro = self.get_or_create_carro(request.user)

        # Verificar si el asiento ya se encuentra en el carro del usuario
        if carro.items.filter(asiento=asiento).exists():
            return Response(
                {"error": "Este asiento ya se encuentra en su carro de compras."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------------------------
        # GESTIÓN NORMALIZADA DEL PASAJERO (3FN)
        # ----------------------------------------------------------------------
        # Se normaliza el RUT chileno y se realiza get_or_create.
        # Decisión de diseño: Si el RUT ya existe en el maestro de pasajeros,
        # se reutiliza y NO se sobrescribe su nombre para preservar la coherencia histórica.
        # ----------------------------------------------------------------------
        rut_normalizado = Pasajero.normalizar_rut(rut_pasajero)
        pasajero, _ = Pasajero.objects.get_or_create(
            rut=rut_normalizado,
            defaults={'nombre_completo': nombre_pasajero.strip()}
        )

        # Crear el ítem persistente (el precio se calcula dinámicamente desde el asiento)
        item = ItemCarro.objects.create(
            carro=carro,
            asiento=asiento,
            pasajero=pasajero
        )

        response_serializer = ItemCarroSerializer(item)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Carro de Pasajes (Pasajero)'],
        summary='Vaciar el carro o eliminar un ítem específico',
        description='Si se provee el query parameter `?item_id=X`, elimina dicho ítem. Sin parámetro, vacía todo el carro.',
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=int,
                required=False,
                location=OpenApiParameter.QUERY,
                description='ID del ítem individual a eliminar (opcional)'
            )
        ],
        responses={200: OpenApiResponse(description="Carro vaciado o ítem eliminado exitosamente.")}
    )
    def delete(self, request):
        carro = self.get_or_create_carro(request.user)
        item_id = request.query_params.get('item_id')

        if item_id:
            item = get_object_or_404(carro.items, id=item_id)
            item.delete()
            return Response(
                {"mensaje": f"Ítem #{item_id} eliminado exitosamente del carro."},
                status=status.HTTP_200_OK
            )

        cantidad_eliminados, _ = carro.items.all().delete()
        return Response(
            {"mensaje": "Carro de pasajes vaciado exitosamente.", "items_eliminados": cantidad_eliminados},
            status=status.HTTP_200_OK
        )


# ==============================================================================
# 2. CHECKOUT (POST /api/ventas/checkout/)
# ==============================================================================
@extend_schema(
    tags=['Ventas y Checkout (Pasajero)'],
    summary='Ejecutar checkout: crea orden PENDIENTE y congela precios en DetalleVenta',
    description=(
        "Toma el contenido del carro del pasajero, crea la Venta en estado PENDIENTE "
        "con sus registros asociados de DetalleVenta (precios unitarios congelados e inmutables), "
        "y vacía el carro.\n"
        "Regla crítica de negocio: Este paso NO descuenta stock ni marca asientos como ocupados."
    ),
    request=None,
    responses={
        201: VentaSerializer,
        400: OpenApiResponse(description="Carro vacío o servicio zarpado.")
    }
)
class CheckoutView(APIView):
    """
    Controlador para crear la orden de Venta PENDIENTE a partir del carro.
    """
    permission_classes = [permissions.IsAuthenticated, IsPasajero]

    def post(self, request):
        venta = realizar_checkout(usuario=request.user)
        serializer = VentaSerializer(venta)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ==============================================================================
# 3. PAGO DE VENTA (POST /api/ventas/{id}/pagar/)
# ==============================================================================
@extend_schema(
    tags=['Ventas y Checkout (Pasajero)'],
    summary='Pagar orden de venta: bloqueo pesimista select_for_update y emisión de boletos',
    description=(
        "Simula el pago de una orden en estado PENDIENTE.\n\n"
        "**Lógica Transaccional:**\n"
        "1. Bloqueo pesimista sobre las filas de los asientos en MySQL con `select_for_update()`.\n"
        "2. Valida atómicamente que TODOS los asientos sigan en estado `DISPONIBLE` y bus no haya zarpado.\n"
        "3. Si algún asiento está ocupado, se ejecuta Rollback completo y la orden se mantiene PENDIENTE (HTTP 400).\n"
        "4. Si todos están disponibles: Asientos pasan a `OCUPADO`, Venta a `PAGADO` y se emiten los Boletos (3FN OneToOne con DetalleVenta)."
    ),
    request=None,
    parameters=[
        OpenApiParameter(name='id', description='ID de la Venta a pagar', required=True, type=int, location=OpenApiParameter.PATH)
    ],
    responses={
        200: VentaSerializer,
        400: OpenApiResponse(description="Conflicto de disponibilidad o servicio zarpado.")
    }
)
class PagarVentaView(APIView):
    """
    Endpoint para pagar una orden de venta PENDIENTE y emitir los boletos.
    Filtra siempre por request.user: si la venta no es del usuario -> 404.
    Si hay conflicto de asientos -> 409 con lista de asientos en conflicto.
    """
    permission_classes = [permissions.IsAuthenticated, IsPasajero]

    def post(self, request, id=None, pk=None):
        # Aislamiento entre cuentas: get_object_or_404 con usuario=request.user
        # garantiza que una venta ajena devuelva 404, no una excepcion de permisos.
        venta_id = id or pk or self.kwargs.get('id') or self.kwargs.get('pk')
        venta = get_object_or_404(Venta, id=venta_id, usuario=request.user)

        try:
            venta_pagada = procesar_pago_venta(venta=venta, usuario=request.user)
        except ValidationError as exc:
            # Detectar conflicto de asientos (409) vs error de validacion generico (400)
            http_status = getattr(exc, 'status_code', status.HTTP_400_BAD_REQUEST)
            return Response(exc.detail, status=http_status)

        serializer = VentaSerializer(venta_pagada)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 4. CANCELACIÓN POR PASAJERO (POST /api/ventas/{id}/cancelar/)
# ==============================================================================
@extend_schema(
    tags=['Ventas y Checkout (Pasajero)'],
    summary='Cancelar orden propia en estado PENDIENTE',
    description='Permite al pasajero cancelar una orden que aún se encuentra en estado PENDIENTE.',
    request=None,
    parameters=[
        OpenApiParameter(name='id', description='ID de la Venta a cancelar', required=True, type=int, location=OpenApiParameter.PATH)
    ],
    responses={
        200: VentaSerializer,
        400: OpenApiResponse(description="Orden no cancelable por el pasajero.")
    }
)
class CancelarVentaView(APIView):
    """
    Endpoint para que el pasajero cancele su propia orden PENDIENTE.
    """
    permission_classes = [permissions.IsAuthenticated, IsPasajero]

    def post(self, request, id=None, pk=None):
        venta_id = id or pk or self.kwargs.get('id') or self.kwargs.get('pk')
        venta = get_object_or_404(Venta, id=venta_id, usuario=request.user)

        venta_cancelada = procesar_cancelacion_venta(venta=venta, usuario=request.user, es_admin=False)
        serializer = VentaSerializer(venta_cancelada)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 5. HISTORIAL DE ÓRDENES DEL PASAJERO (GET /api/mis-ordenes/)
# ==============================================================================
@extend_schema(
    tags=['Ventas y Checkout (Pasajero)'],
    summary='Consultar órdenes y compras del pasajero autenticado con filtros',
    description='Retorna todas las órdenes generadas por el usuario autenticado con filtros de estado y fechas.',
    responses={200: VentaSerializer(many=True)}
)
class MisOrdenesView(generics.ListAPIView):
    """
    Endpoint para consultar las órdenes propias del pasajero.
    """
    serializer_class = VentaSerializer
    permission_classes = [permissions.IsAuthenticated, IsPasajero]
    filterset_class = VentaFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not (self.request.user and self.request.user.is_authenticated):
            return Venta.objects.none()
        return Venta.objects.filter(usuario=self.request.user).prefetch_related(
            'detalles__asiento__servicio__ruta__origen__ciudad',
            'detalles__asiento__servicio__ruta__destino__ciudad',
            'detalles__asiento__servicio__bus',
            'detalles__pasajero',
            'detalles__boleto'
        ).order_by('-fecha_creacion')


# ==============================================================================
# 6. HISTORIAL DE BOLETOS EMITIDOS (GET /api/mis-boletos/)
# ==============================================================================
@extend_schema(
    tags=['Boletos y Pasajes (Pasajero)'],
    summary='Consultar boletos emitidos del pasajero autenticado con filtros',
    description='Retorna todos los boletos/tickets electrónicos adquiridos por el usuario actual con filtro de estado.',
    responses={200: BoletoSerializer(many=True)}
)
class MisBoletosView(generics.ListAPIView):
    """
    Endpoint para que el pasajero consulte el histórico de sus pasajes emitidos en 3FN.
    """
    serializer_class = BoletoSerializer
    permission_classes = [permissions.IsAuthenticated, IsPasajero]
    filterset_class = BoletoFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not (self.request.user and self.request.user.is_authenticated):
            return Boleto.objects.none()

        return Boleto.objects.filter(
            detalle_venta__venta__usuario=self.request.user
        ).select_related(
            'detalle_venta__asiento__servicio__ruta__origen__ciudad',
            'detalle_venta__asiento__servicio__ruta__destino__ciudad',
            'detalle_venta__asiento__servicio__bus',
            'detalle_venta__pasajero',
            'detalle_venta__venta'
        ).order_by('-fecha_emision')


# ==============================================================================
# 7. GESTIÓN GLOBAL DE VENTAS (ADMINISTRADOR DE FLOTA: GET /api/ventas/)
# ==============================================================================
@extend_schema(
    tags=['Gestión de Ventas (Administrador)'],
    summary='Listar todas las órdenes de venta del sistema con filtros avanzados',
    description='Permite al Administrador de Flota auditar y filtrar todas las compras del sistema.'
)
class AdminVentaViewSet(ProteccionIntegridadReservasMixin, viewsets.ReadOnlyModelViewSet):
    """
    Vista administrativa para consultar todas las ventas con filtros por estado, fecha y usuario.
    """
    queryset = Venta.objects.select_related('usuario').prefetch_related(
        'detalles__asiento__servicio__ruta__origen__ciudad',
        'detalles__asiento__servicio__ruta__destino__ciudad',
        'detalles__asiento__servicio__bus',
        'detalles__pasajero',
        'detalles__boleto'
    ).all().order_by('-fecha_creacion')
    serializer_class = VentaSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminFlota]
    filterset_class = VentaFilter


# ==============================================================================
# 8. ACTUALIZACIÓN DE ESTADO DE VENTA (PATCH /api/ventas/{id}/estado/)
# ==============================================================================
@extend_schema(
    tags=['Gestión de Ventas (Administrador)'],
    summary='Actualizar estado de una venta (Administrador de Flota)',
    description=(
        "Permite al Administrador de Flota cambiar el estado de una venta.\n"
        "Transiciones válidas: PENDIENTE->PAGADO, PENDIENTE->CANCELADO, "
        "PAGADO->ENTREGADO, PAGADO->CANCELADO.\n"
        "Cualquier otra transición es rechazada con HTTP 400."
    ),
    request=ActualizarEstadoVentaSerializer,
    parameters=[
        OpenApiParameter(name='id', description='ID de la Venta', required=True, type=int, location=OpenApiParameter.PATH)
    ],
    responses={
        200: VentaSerializer,
        400: OpenApiResponse(description="Transición de estado inválida."),
        404: OpenApiResponse(description="Venta no encontrada.")
    }
)
class ActualizarEstadoVentaView(APIView):
    """
    Endpoint exclusivo para Administradores de Flota para gestionar el ciclo de vida de una venta.
    Usa la misma logica de procesar_pago_venta que el endpoint del pasajero,
    garantizando coherencia en el control de concurrencia.
    Si hay conflicto de asientos en la transicion PENDIENTE->PAGADO -> 409.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminFlota]

    def patch(self, request, id=None, pk=None):
        venta_id = id or pk or self.kwargs.get('id') or self.kwargs.get('pk')
        venta = get_object_or_404(Venta, pk=venta_id)

        serializer = ActualizarEstadoVentaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nuevo_estado = serializer.validated_data['estado']

        try:
            # Ejecuta la transicion validada en la capa de servicios
            venta_actualizada = cambiar_estado_venta(venta=venta, nuevo_estado=nuevo_estado, es_admin=True)
        except ValidationError as exc:
            # Detectar conflicto de asientos (409) vs error de validacion generico (400)
            http_status = getattr(exc, 'status_code', status.HTTP_400_BAD_REQUEST)
            return Response(exc.detail, status=http_status)

        response_serializer = VentaSerializer(venta_actualizada)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 9. GESTIÓN ADMINISTRATIVA DE CARROS (GET, DELETE /api/admin/carros/)
# ==============================================================================
@extend_schema(
    tags=['Gestión de Carros (Administrador)'],
    description='Permite al Administrador de Flota auditar todos los carros de compras y vaciar o quitar ítems.',
    responses={200: CarroPasajesSerializer(many=True)}
)
class AdminCarrosView(APIView):
    """
    Vista para que el Administrador de Flota inspeccione todos los carros activos del sistema.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminFlota]

    def get(self, request):
        carros = CarroPasajes.objects.select_related('usuario').prefetch_related(
            'items__asiento__servicio',
            'items__pasajero'
        ).all()
        serializer = CarroPasajesSerializer(carros, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        carro_id = request.query_params.get('carro_id')
        item_id = request.query_params.get('item_id')

        if not carro_id:
            return Response({"error": "Debe especificar '?carro_id=X'."}, status=status.HTTP_400_BAD_REQUEST)

        carro = get_object_or_404(CarroPasajes, id=carro_id)

        if item_id:
            item = get_object_or_404(carro.items, id=item_id)
            item.delete()
            return Response({"mensaje": f"Ítem #{item_id} eliminado del carro #{carro_id}."})

        eliminados, _ = carro.items.all().delete()
        return Response({"mensaje": f"Carro #{carro_id} vaciado exitosamente.", "eliminados": eliminados})
