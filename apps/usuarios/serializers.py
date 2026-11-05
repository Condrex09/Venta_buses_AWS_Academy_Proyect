"""
==============================================================================
BusDrex - MÓDULO: USUARIOS (apps/usuarios/serializers.py)
Serializadores de Usuario y Token JWT con Claims Personalizados (3FN)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Implementa:
- CustomTokenObtainPairSerializer: Inyecta claims en el JWT (rol, username, email, nombre)
  y retorna datos del usuario autenticado en la respuesta JSON. Se excluye 'rut' (ahora en Pasajero).
- UsuarioRegistroSerializer: Auto-registro público seguro. SIEMPRE asigna rol PASAJERO.
- UsuarioDetalleSerializer: Consulta del perfil del usuario autenticado.
- UsuarioGestionAdminSerializer: Para que el Administrador de Flota gestione usuarios.
==============================================================================
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Usuario


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializador extendido de SimpleJWT para incluir Claims de Rol en el Token JWT.
    Inyecta 'rol', 'username', 'email' y 'nombre_completo' en el payload firmado.
    El claim 'rut' se retira cumpliendo la 3FN.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # ----------------------------------------------------------------------
        # INYECCIÓN DE CLAIMS PERSONALIZADOS EN EL PAYLOAD DEL JWT
        # ----------------------------------------------------------------------
        token['username'] = user.username
        token['email'] = user.email
        token['rol'] = user.rol
        token['is_staff'] = user.is_staff
        token['nombre_completo'] = f"{user.first_name} {user.last_name}".strip() or user.username

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # ----------------------------------------------------------------------
        # INFORMACIÓN ENRIQUECIDA EN EL CUERPO DE LA RESPUESTA HTTP
        # ----------------------------------------------------------------------
        data['usuario'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'nombre_completo': f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username,
            'rol': self.user.rol,
            'telefono': self.user.telefono,
            'is_admin_flota': self.user.is_admin_flota,
        }
        return data


class UsuarioRegistroSerializer(serializers.ModelSerializer):
    """
    Serializador para el auto-registro de nuevos usuarios en BusDrex.
    REGLA DE SEGURIDAD CRÍTICA:
    - Todo auto-registro genera SIEMPRE un usuario con rol 'PASAJERO'.
    - El campo 'rol' es de solo lectura y cualquier valor enviado por el cliente es ignorado.
    - Se eliminó el campo 'rut' para respetar la Tercera Forma Normal (3FN).
    - Garantiza la creación inmediata del Carro de Pasajes (OneToOne) en la base de datos.
    """
    password = serializers.CharField(
        write_only=True,
        min_length=6,
        style={'input_type': 'password'},
        help_text="Contraseña mínima de 6 caracteres."
    )
    confirmar_password = serializers.CharField(
        write_only=True,
        min_length=6,
        style={'input_type': 'password'},
        help_text="Confirmación idéntica de la contraseña."
    )

    class Meta:
        model = Usuario
        fields = [
            'id',
            'username',
            'email',
            'password',
            'confirmar_password',
            'first_name',
            'last_name',
            'telefono',
            'rol',
        ]
        read_only_fields = ['id', 'rol']

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirmar_password'):
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        return attrs

    def create(self, validated_data):
        # ----------------------------------------------------------------------
        # LIMPIEZA DE ATRIBUTOS PRIVILEGIADOS Y FORZADO DE ROL PASAJERO
        # ----------------------------------------------------------------------
        validated_data.pop('confirmar_password', None)
        validated_data.pop('rol', None)
        validated_data.pop('is_staff', None)
        validated_data.pop('is_superuser', None)
        password = validated_data.pop('password')

        usuario = Usuario(**validated_data)
        usuario.rol = Usuario.ROL_PASAJERO
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.set_password(password)
        usuario.save()

        # ----------------------------------------------------------------------
        # GARANTIZAR CREACIÓN DEL CARRO DE PASAJES PERSISTENTE (1 A 1)
        # ----------------------------------------------------------------------
        from reservas.models import CarroPasajes
        CarroPasajes.objects.get_or_create(usuario=usuario)

        return usuario


class UsuarioDetalleSerializer(serializers.ModelSerializer):
    """
    Serializador para consultar el perfil del usuario autenticado.
    """
    rol_display = serializers.CharField(source='get_rol_display', read_only=True)

    class Meta:
        model = Usuario
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'telefono',
            'rol',
            'rol_display',
            'is_admin_flota',
            'is_active',
            'date_joined',
        ]
        read_only_fields = fields


class UsuarioGestionAdminSerializer(serializers.ModelSerializer):
    """
    Serializador para la administración de usuarios por parte del Administrador de Flota.
    Permite listar usuarios y activar/desactivar cuentas (is_active).
    """
    rol_display = serializers.CharField(source='get_rol_display', read_only=True)

    class Meta:
        model = Usuario
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'telefono',
            'rol',
            'rol_display',
            'is_active',
            'date_joined',
        ]
        read_only_fields = ['id', 'username', 'email', 'date_joined']
