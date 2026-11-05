"""
==============================================================================
BusDrex - Enrutador Principal de URLs (busdrex/urls.py)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Centraliza el enrutamiento completo:
1. Vistas Web en Django Templates (Home, Buscar, Asientos, Carro, Pago, Mis Pasajes, Login, Registro, Panel).
2. Documentación Swagger / OpenAPI 3.0 restringida exclusivamente al ADMIN_FLOTA en /api/docs/.
3. Endpoints de Autenticación JWT con Claims (/api/auth/).
4. Endpoints de Transporte, Servicios y Asientos (/api/...).
5. Endpoints de Carro, Checkout atómico y Ventas (/api/...).
6. Gestión de Usuarios para Administrador de Flota (/api/admin/usuarios/).
7. Handler 404 y Catch-all: Cualquier ruta inexistente redirecciona al inicio ("/").
==============================================================================
"""

from django.urls import path, re_path, include
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .views import (
    admin_swagger_view,
    admin_schema_view,
    admin_redoc_view,
    redirect_to_home,
    HomeView,
    BuscarPasajesView,
    AsientosView,
    CarroView,
    PagoView,
    MisPasajesView,
    LoginView,
    RegistroView,
    PanelAdminView,
)
from usuarios.views import AdminUsuarioViewSet


# ==============================================================================
# VISTA DE METADATOS Y BIENVENIDA (FOOTER / METADATOS DEL ESTUDIANTE)
# ==============================================================================
@extend_schema(
    tags=['Metadatos de Evaluación'],
    summary='Consultar metadatos del estudiante y especificaciones del backend',
    description='Retorna los datos de identificación académica del estudiante (Nombre, Sección, Año 2026).',
    responses={
        200: OpenApiResponse(description="Metadatos de la evaluación académica y ficha del estudiante.")
    }
)
class ApiInfoView(APIView):
    """
    Endpoint informativo que expone los metadatos requeridos por la pauta de evaluación.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "plataforma": "BusDrex - Backend API RESTful",
            "version": "1.0.0",
            "año_academico": 2026,
            "metadatos_evaluacion": settings.METADATA_EVALUACION,
            "documentacion": {
                "swagger_ui": request.build_absolute_uri('/api/docs/'),
                "redoc": request.build_absolute_uri('/api/redoc/'),
                "openapi_schema": request.build_absolute_uri('/api/schema/'),
            },
            "matriz_roles": {
                "pasajero": "Gestión de carro propio, checkout, pago atómico, mis pasajes y boletos.",
                "admin_flota": "Gestión de terminales, rutas, buses, servicios, asientos, ofertas, carros y ventas."
            },
            "footer": settings.METADATA_EVALUACION['FOOTER']
        })


# ==============================================================================
# PATRONES DE URL
# ==============================================================================
urlpatterns = [
    # --------------------------------------------------------------------------
    # 1. PÁGINAS WEB (DJANGO TEMPLATES - ESTILO TURBUS.CL)
    # --------------------------------------------------------------------------
    path('', HomeView.as_view(), name='web-home'),
    path('buscar/', BuscarPasajesView.as_view(), name='web-buscar'),
    path('asientos/<int:id>/', AsientosView.as_view(), name='web-asientos'),
    path('carro/', CarroView.as_view(), name='web-carro'),
    path('pago/', PagoView.as_view(), name='web-pago'),
    path('mis-pasajes/', MisPasajesView.as_view(), name='web-mis-pasajes'),
    path('login/', LoginView.as_view(), name='web-login'),
    path('registro/', RegistroView.as_view(), name='web-registro'),
    path('panel/', PanelAdminView.as_view(), name='web-panel'),

    # --------------------------------------------------------------------------
    # 2. DOCUMENTACIÓN SWAGGER / OPENAPI (SOLO ADMIN_FLOTA - FASE 5)
    # --------------------------------------------------------------------------
    path('api/schema/', admin_schema_view, name='schema'),
    path('api/docs/', admin_swagger_view, name='swagger-ui'),
    path('api/redoc/', admin_redoc_view, name='redoc'),

    # --------------------------------------------------------------------------
    # 3. METADATOS INSTITUCIONALES DEL ESTUDIANTE
    # --------------------------------------------------------------------------
    path('api/info/', ApiInfoView.as_view(), name='api-info'),

    # --------------------------------------------------------------------------
    # 4. GESTIÓN ADMINISTRATIVA DE USUARIOS (ADMIN_FLOTA - FASE 3)
    # --------------------------------------------------------------------------
    path('api/admin/usuarios/', AdminUsuarioViewSet.as_view({'get': 'list'}), name='admin-usuarios-list'),
    path('api/admin/usuarios/<int:pk>/', AdminUsuarioViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='admin-usuarios-detail'),

    # --------------------------------------------------------------------------
    # 5. AUTENTICACIÓN Y ROLES (JWT CON CLAIMS)
    # --------------------------------------------------------------------------
    path('api/auth/', include('usuarios.urls', namespace='usuarios')),

    # --------------------------------------------------------------------------
    # 6. TRANSPORTE, SERVICIOS, ASIENTOS Y OFERTAS
    # --------------------------------------------------------------------------
    path('api/', include('transporte.urls', namespace='transporte')),

    # --------------------------------------------------------------------------
    # 7. RESERVAS, CARRO, CHECKOUT, VENTAS Y BOLETOS
    # --------------------------------------------------------------------------
    path('api/', include('reservas.urls', namespace='reservas')),

    # --------------------------------------------------------------------------
    # 8. ADIÓS AL 404 (CATCH-ALL AL FINAL DE PATRONES - FASE 6)
    # --------------------------------------------------------------------------
    re_path(r'^.*$', redirect_to_home, name='catch-all'),
]

# Handler 404 de respaldo a nivel de servidor Django
handler404 = 'busdrex.views.redirect_to_home'
