"""
==============================================================================
BusDrex - MÓDULO: TRANSPORTE (apps/transporte/urls.py)
Rutas de Servicios, Terminales, Buses, Rutas, Asientos, Regiones, Ciudades y Ofertas
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ServicioBuscarView,
    ServicioAsientosView,
    ServicioViewSet,
    RegionViewSet,
    CiudadViewSet,
    TerminalViewSet,
    BusViewSet,
    RutaViewSet,
    AsientoViewSet,
    OfertaViewSet,
)

app_name = 'transporte'

router = DefaultRouter()
router.register(r'regiones', RegionViewSet, basename='region')
router.register(r'ciudades', CiudadViewSet, basename='ciudad')
router.register(r'servicios', ServicioViewSet, basename='servicio')
router.register(r'terminales', TerminalViewSet, basename='terminal')
router.register(r'buses', BusViewSet, basename='bus')
router.register(r'rutas', RutaViewSet, basename='ruta')
router.register(r'asientos', AsientoViewSet, basename='asiento')
router.register(r'ofertas', OfertaViewSet, basename='oferta')

urlpatterns = [
    # --------------------------------------------------------------------------
    # ENDPOINTS ESPECÍFICOS REQUERIDOS POR LA PAUTA
    # --------------------------------------------------------------------------
    # 1. Búsqueda pública con filtros (GET /api/servicios/buscar/)
    path('servicios/buscar/', ServicioBuscarView.as_view(), name='servicio-buscar'),

    # 2. Consulta de asientos por ID de servicio (GET /api/servicios/<id>/asientos/)
    path('servicios/<int:id>/asientos/', ServicioAsientosView.as_view(), name='servicio-asientos'),

    # 3. Router RESTful para CRUD de servicios, catálogos, geografía, asientos y ofertas
    path('', include(router.urls)),
]
