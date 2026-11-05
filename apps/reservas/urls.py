"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/urls.py)
Rutas de Carro de Pasajes, Checkout, Pago, Boletos y Gestión de Ventas
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
"""

from django.urls import path
from .views import (
    CarroPasajesView,
    CheckoutView,
    PagarVentaView,
    CancelarVentaView,
    MisOrdenesView,
    MisBoletosView,
    ActualizarEstadoVentaView,
    AdminVentaViewSet,
    AdminCarrosView,
)

app_name = 'reservas'

urlpatterns = [
    # --------------------------------------------------------------------------
    # 1. ENDPOINTS DE CARRO Y CHECKOUT (PASAJERO)
    # --------------------------------------------------------------------------
    # GET (listar), POST (agregar pasaje), DELETE (vaciar o quitar ítem)
    path('carro-pasajes/', CarroPasajesView.as_view(), name='carro-pasajes'),
    # POST (checkout atómico: crea Venta PENDIENTE con precios congelados)
    path('ventas/checkout/', CheckoutView.as_view(), name='ventas-checkout'),
    # POST (pago atómico con select_for_update y emisión de boletos)
    path('ventas/<int:id>/pagar/', PagarVentaView.as_view(), name='ventas-pagar'),
    # POST (cancelación de orden propia PENDIENTE)
    path('ventas/<int:id>/cancelar/', CancelarVentaView.as_view(), name='ventas-cancelar'),
    # GET (historial de órdenes de compra del pasajero con filtros)
    path('mis-ordenes/', MisOrdenesView.as_view(), name='mis-ordenes'),
    # GET (historial de boletos del pasajero con filtros)
    path('mis-boletos/', MisBoletosView.as_view(), name='mis-boletos'),

    # --------------------------------------------------------------------------
    # 2. ENDPOINTS DE ADMINISTRACIÓN DE VENTAS Y CARROS (ADMIN FLOTA)
    # --------------------------------------------------------------------------
    # GET (listar todas las ventas del sistema con filtros)
    path('ventas/', AdminVentaViewSet.as_view({'get': 'list'}), name='admin-ventas-list'),
    path('ventas/<int:pk>/', AdminVentaViewSet.as_view({'get': 'retrieve'}), name='admin-ventas-detail'),
    # PATCH (actualizar estado de una orden con máquina de estados estricta)
    path('ventas/<int:id>/estado/', ActualizarEstadoVentaView.as_view(), name='ventas-actualizar-estado'),
    # GET / DELETE (inspección y vaciado administrativo de carros)
    path('admin/carros/', AdminCarrosView.as_view(), name='admin-carros'),
]
