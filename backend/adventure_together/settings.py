"""
Django settings for AdventureTogether project.

AdventureTogether is a collaborative, event-based scavenger hunt platform
designed to incentivize high-quality open data contributions to OpenStreetMap,
Wikimedia Commons, and Wikidata.
"""

from pathlib import Path
import os
import sys

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add apps directory to Python path
sys.path.insert(0, str(BASE_DIR))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-adventure-together-platform-dev-key-change-in-production'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

# Application definition
INSTALLED_APPS = [
    # Django Core Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',

    # Third-Party Libraries
    'rest_framework',
    'rest_framework_gis',
    'corsheaders',
    'django_q',

    # AdventureTogether Domain Apps
    'apps.core',
    'apps.events',
    'apps.teams',
    'apps.quests',
    'apps.locations',
    'apps.submissions',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'adventure_together.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'adventure_together.wsgi.application'
ASGI_APPLICATION = 'adventure_together.asgi.application'

# Database Configuration
# Uses PostgreSQL with PostGIS in production/docker, with SpatiaLite fallback for lightweight local execution.
POSTGRES_DB = os.environ.get('POSTGRES_DB')

if POSTGRES_DB:
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.postgis',
            'NAME': POSTGRES_DB,
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.spatialite',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    # Standard location of SpatiaLite C extension library on Linux
    SPATIALITE_LIBRARY_PATH = os.environ.get('SPATIALITE_LIBRARY_PATH', 'mod_spatialite.so')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# CORS Configuration
# Enables seamless cross-origin requests from the Vue SPA during development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Django-Q2 Task Queue Configuration (Zero-Redis Architecture using PostgreSQL ORM)
Q_CLUSTER = {
    'name': 'AdventureTogetherCluster',
    'workers': int(os.environ.get('DJANGO_Q_WORKERS', 4)),
    'recycle': 500,
    # A harvest run makes several external calls (Overpass alone may take up to 90 s), so the
    # task timeout is generous; retry must stay above timeout or the ORM broker re-delivers
    # tasks that are still running.
    'timeout': 300,
    'retry': 360,
    'orm': 'default',  # Uses PostgreSQL ORM directly as the task broker
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Background Tasks',
}

# Cache
# Process-local in-memory cache; used e.g. for parsed conference schedule exports.
# Swap for a shared backend (database / memcached) if multiple web workers need to share it.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'adventure-together-default',
    }
}

# External open-data APIs used by the harvesters.
# OVERPASS_URL and GITHUB_TOKEN are secrets: they are only ever read from the environment,
# never committed, logged, or echoed. An empty OVERPASS_URL means "not configured".
OVERPASS_URL = os.environ.get('OVERPASS_URL', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
OSM_API_BASE = os.environ.get('OSM_API_BASE', 'https://api.openstreetmap.org/api/0.6')
OHM_API_BASE = os.environ.get('OHM_API_BASE', 'https://www.openhistoricalmap.org/api/0.6')
# Public OpenHistoricalMap Overpass endpoint (not a secret).
OHM_OVERPASS_URL = os.environ.get(
    'OHM_OVERPASS_URL', 'https://overpass-api.openhistoricalmap.org/api/interpreter'
)
WIKIMEDIA_COMMONS_API = os.environ.get('WIKIMEDIA_COMMONS_API', 'https://commons.wikimedia.org/w/api.php')
WIKIDATA_API = os.environ.get('WIKIDATA_API', 'https://www.wikidata.org/w/api.php')
PANORAMAX_API = os.environ.get('PANORAMAX_API', 'https://api.panoramax.xyz/api')
# Identifies us to the external APIs (OSM and Wikimedia policies require a descriptive UA).
HARVEST_USER_AGENT = os.environ.get(
    'HARVEST_USER_AGENT',
    'AdventureTogether-Harvester/1.0 (https://github.com/mwhilden/AdventureTogether)'
)

# Hosts the server may fetch Event.schedule_url from (exact host or any subdomain, https only).
# Event.schedule_url is client-writable, so this allowlist keeps the sessions endpoint from
# being used to make the server request arbitrary (e.g. internal) URLs.
SCHEDULE_URL_ALLOWED_HOSTS = [
    host.strip().lower()
    for host in os.environ.get('SCHEDULE_URL_ALLOWED_HOSTS', 'talks.osgeo.org,pretalx.com').split(',')
    if host.strip()
]
