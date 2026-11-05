"""
==============================================================================
BusDrex - MÓDULO: USUARIOS (apps/usuarios/views.py)
Controladores de Autenticación, Emisión JWT, Registro, Logout y Gestión
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
Expone los endpoints de:
- POST /api/auth/login/ : Login JWT con claims de rol + Apertura de sesión Django
- POST /api/auth/logout/ : Cierre de sesión, blacklist del refresh token y cierre de sesión Django
- POST /api/auth/register/ : Registro público seguro (rol PASAJERO estricto)
- GET /api/auth/perfil/ : Perfil del usuario autenticado
- CRUD /api/admin/usuarios/ : Gestión de usuarios para Administrador de Flota (listar, activar/desactivar)
==============================================================================
"""

from django.contrib.auth import login, logout
from rest_framework import generics, viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

from .models import Usuario
from .serializers import (
    CustomTokenObtainPairSerializer,
    UsuarioRegistroSerializer,
    UsuarioDetalleSerializer,
    UsuarioGestionAdminSerializer,
)
from .permissions import IsAdminFlota
from reservas.models import CarroPasajes


# ==============================================================================
# 1. LOGIN CON CLAIMS Y SESIÓN SINCRONIZADA (POST /api/auth/login/)
# ==============================================================================
@extend_schema(
    tags=['Autenticación y Cuentas'],
    summary='Iniciar sesión y obtener tokens JWT con claims de rol',
    description=(
        "Genera un par de tokens (Access y Refresh) firmados con JWT.\n"
        "El payload del token incluye claims extendidos: `rol` (PASAJERO o ADMIN_FLOTA), "
        "`username`, `email` y `nombre_completo`.\n"
        "Adicionalmente, abre una sesión estándar en Django para compatibilidad con vistas web y Swagger."
    ),
    responses={
        200: OpenApiResponse(description="Tokens generados exitosamente y sesión iniciada."),
        401: OpenApiResponse(description="Credenciales de acceso inválidas."),
    }
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Vista personalizada para el login JWT usando CustomTokenObtainPairSerializer.
    Sincroniza la sesión de Django para permitir navegación protegida en Swagger UI.
    """
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            # Obtener usuario validado
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid()
            user = getattr(serializer, 'user', None)

            if user is not None:
                # --------------------------------------------------------------
                # INICIAR SESIÓN DE DJANGO (COOKIES PARA SWAGGER Y WEB)
                # --------------------------------------------------------------
                login(request, user)

                # Garantizar que el pasajero tenga su CarroPasajes
                if user.is_pasajero:
                    CarroPasajes.objects.get_or_create(usuario=user)

        return response


# ==============================================================================
# 2. LOGOUT SEGURO CON REVOCACIÓN DE TOKEN (POST /api/auth/logout/)
# ==============================================================================
@extend_schema(
    tags=['Autenticación y Cuentas'],
    summary='Cerrar sesión y revocar Refresh Token (Blacklist)',
    description=(
        "Agrega el refresh token a la lista negra (Blacklist) impidiendo renovar accesos.\n"
        "Cierra también la sesión de Django en el servidor.\n"
        "IMPORTANTE: El carro de compras del usuario NO se elimina, persiste íntegro en MySQL."
    ),
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'refresh': {'type': 'string', 'description': 'Token de refresco a revocar'}
            },
            'required': ['refresh']
        }
    },
    responses={
        200: OpenApiResponse(description="Sesión cerrada exitosamente y token revocado."),
        400: OpenApiResponse(description="Token de refresco inválido o faltante.")
    }
)
class UsuarioLogoutView(APIView):
    """
    Endpoint para revocar el Refresh Token (blacklist) y cerrar la sesión web de Django.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                # Si el token ya expiró o es inválido, continuamos con el cierre de sesión web
                pass
            except Exception as e:
                return Response(
                    {"error": f"Error al revocar el token: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Cierre de sesión web de Django
        if request.user and request.user.is_authenticated:
            logout(request)

        return Response(
            {
                "mensaje": "Sesión cerrada exitosamente. El carro de compras permanece guardado en su cuenta.",
                "carro_conservado": True
            },
            status=status.HTTP_200_OK
        )


# ==============================================================================
# 3. REGISTRO PÚBLICO SEGURO (POST /api/auth/register/)
# ==============================================================================
@extend_schema(
    tags=['Autenticación y Cuentas'],
    summary='Registro de nuevo usuario pasajero',
    description=(
        "Permite el auto-registro público de clientes.\n"
        "Por motivos de seguridad, todo registro público crea SIEMPRE un usuario con rol `PASAJERO`.\n"
        "Cualquier intento de enviar `rol: ADMIN_FLOTA`, `is_staff` o `is_superuser` es ignorado."
    ),
    responses={
        201: UsuarioDetalleSerializer,
        400: OpenApiResponse(description="Errores de validación de datos o contraseñas no coincidentes.")
    }
)
class UsuarioRegistroView(generics.CreateAPIView):
    """
    Endpoint público para la creación de cuentas de pasajeros.
    """
    queryset = Usuario.objects.all()
    serializer_class = UsuarioRegistroSerializer
    permission_classes = [permissions.AllowAny]


# ==============================================================================
# 4. PERFIL DEL USUARIO AUTENTICADO (GET /api/auth/perfil/)
# ==============================================================================
@extend_schema(
    tags=['Autenticación y Cuentas'],
    summary='Consultar perfil del usuario autenticado',
    description='Retorna los datos del usuario actualmente autenticado mediante el token Bearer JWT.'
)
class PerfilUsuarioView(generics.RetrieveAPIView):
    """
    Endpoint privado para obtener los detalles del usuario en sesión.
    """
    serializer_class = UsuarioDetalleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ==============================================================================
# 5. GESTIÓN ADMINISTRATIVA DE USUARIOS (CRUD /api/admin/usuarios/)
# ==============================================================================
@extend_schema(
    tags=['Gestión de Usuarios (Administrador)'],
    description=(
        "Permite al Administrador de Flota listar todos los usuarios del sistema, "
        "consultar detalles específicos y activar o desactivar cuentas (campo `is_active`)."
    )
)
class AdminUsuarioViewSet(viewsets.ModelViewSet):
    """
    Controlador para que el Administrador de Flota gestione las cuentas de usuarios.
    """
    queryset = Usuario.objects.all().order_by('-date_joined')
    serializer_class = UsuarioGestionAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminFlota]
    filterset_fields = ['rol', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['id', 'username', 'date_joined']
    http_method_names = ['get', 'patch', 'head', 'options']
