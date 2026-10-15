"""
Django settings for hemovida_project.
Configurado para el Sistema de Banco de Sangre "HemoVida"
Integración con Supabase, Render y Cloudflare Pages.
"""

from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env
load_dotenv(BASE_DIR / '.env')

# Clave secreta
SECRET_KEY = os.getenv('SECRET_KEY', '')

# Modo depuración
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
if not SECRET_KEY:
    if not DEBUG and 'test' not in __import__('sys').argv:
        raise ImproperlyConfigured('Configura SECRET_KEY para producción.')
    SECRET_KEY = 'django-insecure-local-development-only'

# Hosts permitidos (Permite configurar dominios o comodín '*')
allowed_hosts_env = os.getenv('ALLOWED_HOSTS')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()] if allowed_hosts_env else ['localhost', '127.0.0.1', '[::1]']
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])

# Aplicaciones instaladas
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Librerías de terceros
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',

    # Aplicaciones del dominio HemoVida
    'apps.seguridad',
    'apps.donantes',
    'apps.inventario',
]

SILENCED_SYSTEM_CHECKS = ['fields.W342']

# Middlewares
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Debe estar arriba de todo
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Soporte para servir archivos estáticos con WhiteNoise en producción (Render)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hemovida_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hemovida_project.wsgi.application'

# ============================================================================
# CONFIGURACIÓN DE BASE DE DATOS (Soporta Supabase, PostgreSQL local y SQLite)
# ============================================================================
import sys
USE_SQLITE = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1')
DATABASE_URL = os.getenv('DATABASE_URL')

if 'test' in sys.argv:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif USE_SQLITE and DEBUG:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3',
    }}
elif DATABASE_URL:
    try:
        db_config = dj_database_url.parse(
            DATABASE_URL.strip(), conn_max_age=60, conn_health_checks=True,
            ssl_require=not DEBUG,
        )
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured('DATABASE_URL no es una URI PostgreSQL válida.') from None
    if db_config['ENGINE'] != 'django.db.backends.postgresql':
        raise ImproperlyConfigured('DATABASE_URL debe apuntar a PostgreSQL / Supabase.')
    db_config['DISABLE_SERVER_SIDE_CURSORS'] = True
    db_config.setdefault('OPTIONS', {})['connect_timeout'] = 10
    DATABASES = {'default': db_config}
else:
    raise ImproperlyConfigured('Configura DATABASE_URL con la conexión de Supabase. SQLite solo se permite explícitamente en desarrollo.')

# Validación de Contraseñas (incluye el validador estricto con la política del trigger SQL)
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'apps.seguridad.validators.SecurePasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Configuración de Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.seguridad.authentication.CustomJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Configuración de Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# Configuración de CORS para Frontend React (Cloudflare Pages/Workers) y orígenes autorizados
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [v.strip() for v in os.getenv(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000' if DEBUG else ''
).split(',') if v.strip()]
# Origen de esta instalación, también cuando se conserva una lista CORS anterior.
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://hemovidax.siexecution2026.workers.dev').strip().rstrip('/')
if FRONTEND_URL and FRONTEND_URL not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(FRONTEND_URL)
CORS_ALLOW_CREDENTIALS = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-active-role',
]

# Internacionalización y Zona Horaria
LANGUAGE_CODE = 'es-bo'
TIME_ZONE = 'America/La_Paz'
USE_I18N = True
USE_TZ = True

# Archivos estáticos y WhiteNoise para producción en Render
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Runner para pruebas con modelos managed=False
TEST_RUNNER = 'apps.test_runner.UnmanagedModelTestRunner'

# ============================================================================
# CONFIGURACIÓN DE ENVÍO DE CORREOS ELECTRÓNICOS (SMTP)
# ============================================================================
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
if EMAIL_PORT == 465:
    EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'True').lower() in ('true', '1', 'yes')
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() in ('true', '1', 'yes')
else:
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f"Banco de Sangre HemoVida <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "Banco de Sangre HemoVida <seguridad@hemovida.org>")
EMAIL_TIMEOUT = 10
