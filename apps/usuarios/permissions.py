"""
==============================================================================
BusDrex - MÓDULO: USUARIOS (apps/usuarios/permissions.py)
Clases de Permiso Personalizadas para Control de Acceso Basado en Roles (RBAC)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
Define los permisos específicos según la pauta de evaluación:
- IsPasajero: Permite acceso EXCLUSIVO a usuarios autenticados con rol PASAJERO.
  Se remueve la excepción para staff/superuser para garantizar aislamiento total.
- IsAdminFlota: Permite gestión administrativa completa (CRUD catálogo, servicios, ventas).
- IsAdminFlotaOrReadOnly: Permite lectura pública de catálogos y restringe mutaciones a Administrador.
==============================================================================
"""

from rest_framework import permissions
from .models import Usuario


class IsPasajero(permissions.BasePermission):
    """
    Permiso estricto que valida que el usuario esté autenticado, activo
    y posea exactamente el rol de Pasajero (Usuario.ROL_PASAJERO).
    No permite acceso a administradores de flota, garantizando el principio
    de mínimo privilegio y segregación funcional de roles.
    """
    message = "Acceso denegado: Se requiere ser un usuario autenticado con rol de Pasajero."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and getattr(request.user, 'rol', None) == Usuario.ROL_PASAJERO
        )


class IsAdminFlota(permissions.BasePermission):
    """
    Permiso que valida que el usuario sea Administrador de Flota
    (o cuente con privilegios de Staff / Superusuario en Django).
    """
    message = "Acceso denegado: Se requieren privilegios de Administrador de Flota."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and (
                getattr(request.user, 'rol', None) == Usuario.ROL_ADMIN_FLOTA
                or request.user.is_staff
                or request.user.is_superuser
            )
        )


class IsAdminFlotaOrReadOnly(permissions.BasePermission):
    """
    Permiso seguro para catálogos: cualquier usuario (incluso anónimo o pasajero)
    puede consultar (GET, HEAD, OPTIONS), pero solo un Administrador de Flota
    puede realizar mutaciones (POST, PUT, PATCH, DELETE).
    """
    message = "Acceso denegado: Solo el Administrador de Flota puede modificar este recurso."

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and (
                getattr(request.user, 'rol', None) == Usuario.ROL_ADMIN_FLOTA
                or request.user.is_staff
                or request.user.is_superuser
            )
        )
