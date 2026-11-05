"""
==============================================================================
BusDrex - MÓDULO: USUARIOS (apps/usuarios/models.py)
Modelo de Usuario Personalizado en Tercera Forma Normal (3FN)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Cumplimiento 3FN:
- Tabla: `usuario` (db_table = 'usuario')
- Se elimina el campo `rut` de Usuario; el RUT y nombre de pasajeros que viajan
  se normalizan independientemente en la entidad `pasajero`.
- Roles estrictos: PASAJERO y ADMIN_FLOTA.
==============================================================================
"""

from django.db import models
from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """
    ==========================================================================
    MODELO DE USUARIO DEL SISTEMA (Tabla: usuario)
    ==========================================================================
    Extensión de AbstractUser para autenticación, autorización y control de roles.
    El RUT no se almacena aquí para cumplir 3FN (reside en la tabla 'pasajero').
    ==========================================================================
    """
    # --------------------------------------------------------------------------
    # BLOQUE DE DEFINICIÓN DE ROLES (EXACTAMENTE 2 ROLES DEL SISTEMA)
    # --------------------------------------------------------------------------
    ROL_PASAJERO = 'PASAJERO'
    ROL_ADMIN_FLOTA = 'ADMIN_FLOTA'

    ROLES_CHOICES = (
        (ROL_PASAJERO, 'Pasajero'),
        (ROL_ADMIN_FLOTA, 'Administrador de Flota'),
    )

    # --------------------------------------------------------------------------
    # CAMPOS DEL MODELO (COINCIDENCIA EXACTA CON busdrex.dbml)
    # --------------------------------------------------------------------------
    rol = models.CharField(
        max_length=20,
        choices=ROLES_CHOICES,
        default=ROL_PASAJERO,
        verbose_name="Rol en el Sistema",
        help_text="Define los privilegios de acceso (Pasajero o Administrador de Flota)."
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Teléfono de Contacto",
        help_text="Teléfono móvil para notificaciones de viaje (ej. +56912345678)."
    )

    # --------------------------------------------------------------------------
    # PROPIEDADES DE COMPROBACIÓN DE ROL
    # --------------------------------------------------------------------------
    @property
    def is_pasajero(self) -> bool:
        """Determina si el usuario tiene rol de pasajero."""
        return self.rol == self.ROL_PASAJERO

    @property
    def is_admin_flota(self) -> bool:
        """
        Determina si el usuario tiene rol de administrador de flota o superusuario.
        Los administradores de Django y superusuarios heredan privilegios de flota.
        """
        return self.rol == self.ROL_ADMIN_FLOTA or self.is_staff or self.is_superuser

    # --------------------------------------------------------------------------
    # METADATOS Y REPRESENTACIÓN (Tabla 'usuario' según DBML)
    # --------------------------------------------------------------------------
    class Meta:
        db_table = 'usuario'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['id']

    def __str__(self):
        nombre_completo = f"{self.first_name} {self.last_name}".strip()
        nombre_visible = nombre_completo if nombre_completo else self.username
        return f"{nombre_visible} ({self.get_rol_display()})"
