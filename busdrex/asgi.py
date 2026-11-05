"""
ASGI config para el proyecto BusDrex.
Expone el callable ASGI como una variable a nivel de módulo llamada 'application'.
"""

import os
import sys

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'busdrex.settings')

# Agregar apps al sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
apps_dir = os.path.join(base_dir, 'apps')
if apps_dir not in sys.path:
    sys.path.insert(0, apps_dir)

application = get_asgi_application()
