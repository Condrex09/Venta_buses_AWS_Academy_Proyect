"""
==============================================================================
BusDrex - MÓDULO: USUARIOS (apps/usuarios/urls.py)
Rutas de Autenticación, Cuentas y Logout
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    UsuarioLogoutView,
    UsuarioRegistroView,
    PerfilUsuarioView,
)

app_name = 'usuarios'

urlpatterns = [
    # Autenticación JWT con claims de rol y sincronización de sesión
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    # Cierre de sesión seguro y revocación de Refresh Token en Blacklist
    path('logout/', UsuarioLogoutView.as_view(), name='logout'),
    # Renovación de access token usando refresh token
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Registro público de nuevos pasajeros (rol forzado a PASAJERO)
    path('register/', UsuarioRegistroView.as_view(), name='registro'),
    # Perfil del usuario actualmente autenticado
    path('perfil/', PerfilUsuarioView.as_view(), name='perfil'),
]
