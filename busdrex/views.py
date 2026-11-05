"""
==============================================================================
BusDrex - CONTROLADORES WEB Y VISTAS DE ENRUTAMIENTO (busdrex/views.py)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Contiene:
1. Vistas protegidas para Swagger UI, Schema y Redoc (Exclusivas para ADMIN_FLOTA).
2. Redirección y Handler 404 seguro (Cualquier ruta no encontrada redirige al inicio).
3. Vistas de plantilla TemplateView para renderizado del frontend Turbus.cl.
==============================================================================
"""

from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.views.generic import TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


# ==============================================================================
# 1. SWAGGER / OPENAPI EXCLUSIVO PARA ADMINISTRADOR DE FLOTA (FASE 5)
# ==============================================================================
def admin_swagger_view(request):
    """
    Controlador protegido para Swagger UI (/api/docs/).
    - Si el usuario no ha iniciado sesión en el navegador: redirige a /login/?next=/api/docs/
    - Si el usuario es PASAJERO: retorna HTTP 403 Acceso Denegado.
    - Si el usuario es ADMIN_FLOTA (o superusuario): despliega Swagger UI interactivo.
    """
    if not request.user.is_authenticated:
        return redirect('/login/?next=/api/docs/')

    if not getattr(request.user, 'is_admin_flota', False):
        return HttpResponseForbidden(
            "<div style='font-family: Arial, sans-serif; text-align: center; padding: 50px;'>"
            "<h1 style='color: #e62629;'>403 - Acceso Denegado</h1>"
            "<p>La documentación Swagger UI está reservada <strong>exclusivamente</strong> para el Administrador de Flota.</p>"
            "<p>Su cuenta actual posee el rol de <strong>Pasajero</strong>.</p>"
            "<a href='/' style='display: inline-block; margin-top: 15px; padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 4px;'>Volver a BusDrex</a>"
            "</div>"
        )

    return SpectacularSwaggerView.as_view(url_name='schema')(request)


def admin_schema_view(request):
    """
    Controlador protegido para el esquema OpenAPI raw (/api/schema/).
    Requiere autenticación de sesión de Administrador de Flota.
    """
    if not request.user.is_authenticated:
        return redirect('/login/?next=/api/docs/')

    if not getattr(request.user, 'is_admin_flota', False):
        return HttpResponseForbidden("403 Acceso Denegado: Exclusivo para Administrador de Flota.")

    return SpectacularAPIView.as_view()(request)


def admin_redoc_view(request):
    """
    Controlador protegido para ReDoc (/api/redoc/).
    Requiere autenticación de sesión de Administrador de Flota.
    """
    if not request.user.is_authenticated:
        return redirect('/login/?next=/api/docs/')

    if not getattr(request.user, 'is_admin_flota', False):
        return HttpResponseForbidden("403 Acceso Denegado: Exclusivo para Administrador de Flota.")

    return SpectacularRedocView.as_view(url_name='schema')(request)


# ==============================================================================
# 2. MANEJO DE RUTAS NO ENCONTRADAS Y ADIÓS AL 404 (FASE 6)
# ==============================================================================
def redirect_to_home(request, exception=None):
    """
    Redirecciona de forma transparente cualquier URL inexistente al Home ('/'),
    evitando que el usuario vea un error 404 en el sistema.
    """
    return redirect('/')


# ==============================================================================
# 3. VISTAS DE PLANTILLAS WEB (DJANGO TEMPLATES - ESTILO TURBUS.CL)
# ==============================================================================
class HomeView(TemplateView):
    """Página de inicio con buscador '¿Dónde estás?', accesos rápidos y ofertas."""
    template_name = 'home.html'


class BuscarPasajesView(TemplateView):
    """Resultados de búsqueda de viajes con filtros dinámicos."""
    template_name = 'buscar.html'


class AsientosView(TemplateView):
    """Plano visual de asientos del bus (Salón Cama y Semicama)."""
    template_name = 'asientos.html'


class CarroView(TemplateView):
    """Gestión de pasajes seleccionados en el carro de compras."""
    template_name = 'carro.html'


class PagoView(TemplateView):
    """Pantalla de confirmación, resumen y pago seguro."""
    template_name = 'pago.html'


class MisPasajesView(TemplateView):
    """Historial de boletos electrónicos y órdenes de compra del pasajero."""
    template_name = 'mis_pasajes.html'


class LoginView(TemplateView):
    """Formulario de inicio de sesión."""
    template_name = 'login.html'


class RegistroView(TemplateView):
    """Formulario de auto-registro de nuevos pasajeros."""
    template_name = 'registro.html'


class PanelAdminView(TemplateView):
    """
    Panel de administración propio para el rol ADMIN_FLOTA.
    Si no cuenta con sesión de administrador, redirige al login.
    """
    template_name = 'panel_admin.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/?next=/panel/')
        if not getattr(request.user, 'is_admin_flota', False):
            return redirect('/')
        return super().dispatch(request, *args, **kwargs)
