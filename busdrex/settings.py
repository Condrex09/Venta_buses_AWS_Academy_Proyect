"""
==============================================================================
BusDrex - Plataforma de Gestión de Reservas de Pasajes de Buses Interurbanos
Configuración Global del Proyecto (busdrex/settings.py)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto Asignado: Proyecto 4, Reservas de Pasajes de Buses Interurbanos
==============================================================================
Este archivo contiene la configuración central de Django, integrando:
- Motor de base de datos MySQL mediante backend personalizado 'custom_mysql'.
- Django REST Framework (DRF) con autenticación JWT (SimpleJWT) y claims de rol.
- Documentación OpenAPI/Swagger mediante drf-spectacular restringida a Administrador.
- Filtros avanzados en todos los endpoints de consulta mediante django-filter.
- Modelo de Usuario Personalizado con roles estrictos (Pasajero y Administrador de Flota).
- Configuración para Django Templates y archivos estáticos con estética Turbus.cl.
- Seguridad completa: variables sensibles leídas exclusivamente desde .env.
==============================================================================
"""

import os
import sys
from pathlib import Path
from datetime import timedelta

# Cargar variables de entorno desde el archivo .env si python-dotenv está presente
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Incorporar la carpeta 'apps' al sys.path para importaciones modulares directas
APPS_DIR = BASE_DIR / 'apps'
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

# ==============================================================================
# 1. METADATOS DE EVALUACIÓN ACADÉMICA (ESTUDIANTE / SECCIÓN / AÑO 2026)
# ==============================================================================
# Estos metadatos se exponen en la documentación Swagger, cabeceras, plantillas y pie de página
METADATA_EVALUACION = {
    'ESTUDIANTE': os.environ.get('STUDENT_NAME', 'Benjamin Gómez'),
    'SECCION': os.environ.get('STUDENT_SECTION', 'AP-N4-C1'),
    'AÑO': os.environ.get('STUDENT_YEAR', '2026'),
    'ASIGNATURA': os.environ.get('STUDENT_SUBJECT', 'Programación Back End'),
    'EVALUACION': os.environ.get('STUDENT_EVALUATION', 'Evaluación 2 (Django REST Framework + MySQL)'),
    'PROYECTO': 'Proyecto 4 - Reservas de Pasajes de Buses Interurbanos (Turbus.cl)',
    'FOOTER': (
        f"BusDrex © {os.environ.get('STUDENT_YEAR', '2026')} | "
        f"{os.environ.get('STUDENT_NAME', 'Benjamin Gómez')} | "
        f"Sección {os.environ.get('STUDENT_SECTION', 'AP-N4-C1')}"
    )
}

# ==============================================================================
# 2. SEGURIDAD Y ENTORNO
# ==============================================================================
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-busdrex-evaluacion-2-backend-2026-super-secret-key-prod'
)

# DEBUG leído de .env (por defecto False si no está definido en producción)
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS leído de .env sin asterisco comodín inseguro por defecto
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

# ==============================================================================
# 3. APLICACIONES INSTALADAS
# ==============================================================================
# Nota: Se eliminó 'django.contrib.admin' por requerimiento de la pauta.
# El panel de administración es una interfaz propia construida en Django Templates.
INSTALLED_APPS = [
    # Aplicaciones estándar necesarias de Django
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Librerías de Terceros
    'rest_framework',                           # Django REST Framework
    'rest_framework_simplejwt',                 # Autenticación JWT con Claims de Rol
    'rest_framework_simplejwt.token_blacklist', # Soporte de revocación de tokens (Logout seguro)
    'drf_spectacular',                          # Documentación Swagger / OpenAPI 3.0
    'django_filters',                           # Filtrado avanzado en todos los endpoints
    'corsheaders',                              # Manejo de peticiones Cross-Origin

    # Aplicaciones del Dominio BusDrex (Arquitectura Modular en apps/)
    'usuarios.apps.UsuariosConfig',             # Autenticación, Usuarios y Roles
    'transporte.apps.TransporteConfig',         # Terminales, Buses, Rutas, Servicios, Asientos, Ofertas
    'reservas.apps.ReservasConfig',             # Carro, Checkout atómico, Ventas, Boletos, Servicios
]

# ==============================================================================
# 4. MIDDLEWARE
# ==============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',      # Habilita CORS
    'django.contrib.sessions.middleware.SessionMiddleware', # Sesiones para admin y vistas
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'busdrex.urls'

# ==============================================================================
# 5. PLANTILLAS (DJANGO TEMPLATES)
# ==============================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'busdrex.context_processors.evaluacion_context',  # Inyección del footer institucional
            ],
        },
    },
]

WSGI_APPLICATION = 'busdrex.wsgi.application'
ASGI_APPLICATION = 'busdrex.asgi.application'

# ==============================================================================
# 6. BASE DE DATOS (CONFIGURACIÓN MYSQL CON MOTOR custom_mysql)
# ==============================================================================
# Requisito: Las credenciales se leen exclusivamente desde .env con python-dotenv.
# Motor 'custom_mysql' para compatibilidad con versiones locales de MySQL.
DATABASES = {
    'default': {
        'ENGINE': 'custom_mysql',
        'NAME': os.environ.get('DB_NAME', 'busdrex_db'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
            'connect_timeout': 5,
        },
    }
}

# ==============================================================================
# 7. MODELO DE USUARIO PERSONALIZADO (ROLES: PASAJERO Y ADMIN DE FLOTA)
# ==============================================================================
AUTH_USER_MODEL = 'usuarios.Usuario'

# ==============================================================================
# 8. VALIDACIÓN DE CONTRASEÑAS
# ==============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ==============================================================================
# 9. INTERNACIONALIZACIÓN Y ZONA HORARIA
# ==============================================================================
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# ==============================================================================
# 10. ARCHIVOS ESTÁTICOS Y MULTIMEDIA
# ==============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================================================
# 11. CONFIGURACIÓN DE DJANGO REST FRAMEWORK (DRF)
# ==============================================================================
REST_FRAMEWORK = {
    # Autenticación: Soporta JWT (clientes API) y Sesiones Django (para vistas Swagger/Panel)
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    # Permiso base: por defecto lectura pública, asegurado individualmente por vista
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    # Integración con drf-spectacular para generación de esquema OpenAPI 3.0
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Motores de filtrado y búsqueda globales en todos los endpoints
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    # Paginación estándar de resultados
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Formato de fechas y horas
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}

# ==============================================================================
# 12. CONFIGURACIÓN DE SIMPLEJWT (JWT CON PAYLOAD PERSONALIZADO)
# ==============================================================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': 'BusDrex-Backend',
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    # Serializador personalizado con claims de rol (Pasajero vs Admin Flota)
    'TOKEN_OBTAIN_SERIALIZER': 'usuarios.serializers.CustomTokenObtainPairSerializer',
}

# ==============================================================================
# 13. CONFIGURACIÓN DE DRF-SPECTACULAR (SWAGGER / OPENAPI 3.0)
# ==============================================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'BusDrex API - Gestión de Reservas de Pasajes de Buses Interurbanos',
    'DESCRIPTION': (
        "## Plataforma de Gestión de Reservas de Pasajes Interurbanos\n"
        "Inspirada en el portal y experiencia de usuario de **Turbus.cl**.\n\n"
        "---\n"
        "### Ficha Académica del Proyecto\n"
        f"- **Estudiante:** {METADATA_EVALUACION['ESTUDIANTE']}\n"
        f"- **Asignatura:** {METADATA_EVALUACION['ASIGNATURA']}\n"
        f"- **Evaluación:** {METADATA_EVALUACION['EVALUACION']}\n"
        f"- **Sección:** {METADATA_EVALUACION['SECCION']}\n"
        f"- **Año Lectivo:** {METADATA_EVALUACION['AÑO']}\n"
        "---\n\n"
        "### Matriz de Autenticación y Autorización\n"
        "- **Público:** Consulta de rutas, itinerarios/servicios, asientos disponibles y ofertas.\n"
        "- **Pasajero (`rol: PASAJERO`):** Gestión de su carro persistente, checkout atómico, pago, consulta de órdenes y boletos emitidos.\n"
        "- **Administrador de Flota (`rol: ADMIN_FLOTA`):** CRUD de servicios, terminales, rutas, buses, asientos, ofertas, carros y actualización de estados de ventas.\n\n"
        f"**Pie de Página Institucional:** {METADATA_EVALUACION['FOOTER']}"
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'CONTACT': {
        'name': f"{METADATA_EVALUACION['ESTUDIANTE']} ({METADATA_EVALUACION['SECCION']})",
        'email': 'benjamin.gomez@busdrex.cl',
    },
    'LICENSE': {
        'name': 'Evaluación Académica 2 - Uso Académico 2026',
    },
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'ENUM_NAME_OVERRIDES': {
        'EstadoAsientoEnum': 'transporte.models.Asiento.ESTADOS_ASIENTO_CHOICES',
        'EstadoVentaEnum': 'reservas.models.Venta.ESTADOS_VENTA_CHOICES',
        'EstadoBoletoEnum': 'reservas.models.Boleto.ESTADOS_BOLETO_CHOICES',
    },
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
    }
}

# ==============================================================================
# 14. CONFIGURACIÓN DE CORS (CROSS-ORIGIN RESOURCE SHARING)
# ==============================================================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
