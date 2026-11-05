"""
==============================================================================
BusDrex - BACKEND PERSONALIZADO MYSQL: custom_mysql/base.py
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
Hereda del backend oficial de Django ('django.db.backends.mysql.base')
y anula el método check_database_version_supported() para permitir
el funcionamiento completo con versiones de MySQL 8.0.x (ej. 8.0.46),
evitando la restricción de versiones recientes de Django que exigen MySQL 8.4+.
==============================================================================
"""

from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper


class DatabaseWrapper(MySQLDatabaseWrapper):
    """
    Wrapper de base de datos MySQL con bypass de validación de versión mínima.
    """
    def check_database_version_supported(self):
        """
        Sobrescribe y anula la validación de versión mínima de MySQL de Django,
        permitiendo que MySQL 8.0.x se ejecute sin arrojar NotSupportedError.
        """
        pass
