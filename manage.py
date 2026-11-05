#!/usr/bin/env python
"""
==============================================================================
BusDrex - Plataforma de Gestión de Reservas de Pasajes de Buses Interurbanos
Evaluación 2: Programación Back End
Estudiante: Benjamin Gómez | Sección: AP-N4-C1 | Año: 2026
==============================================================================
Punto de entrada de línea de comandos para tareas administrativas de Django.
"""
import os
import sys

def main():
    """Ejecuta las tareas administrativas del proyecto BusDrex."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'busdrex.settings')
    
    # Agrega el directorio de aplicaciones ('apps') al path de Python para permitir
    # importaciones modulares limpias (ej. 'from usuarios.models import ...')
    base_dir = os.path.dirname(os.path.abspath(__file__))
    apps_dir = os.path.join(base_dir, 'apps')
    if apps_dir not in sys.path:
        sys.path.insert(0, apps_dir)
        
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Asegúrese de que esté instalado y "
            "disponible en su entorno virtual (ej. pip install -r requirements.txt)."
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
