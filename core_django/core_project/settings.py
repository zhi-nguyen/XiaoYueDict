import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'replace-this-in-production')
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'replace-this-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 't')

allowed_hosts_env = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(',') if host.strip()]

if not ALLOWED_HOSTS and DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'apps.assessments',
    'apps.exams',
    'apps.notes',
    'apps.dictionary_zh',
    'apps.dictionary_en',
    'apps.users',
    'apps.subscriptions',
    'apps.gamification',
    'apps.notifications',
    'apps.media',
    'apps.reports',
    'rest_framework_simplejwt',
]

AUTH_USER_MODEL = 'users.CustomUser'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.subscriptions.middleware.VolumeLimitMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core_project.urls'

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

WSGI_APPLICATION = 'core_project.wsgi.application'

# Database: use DATABASE_URL env var (PostgreSQL in Docker),
# falls back to SQLite for local development.
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS & CSRF Configuration — required for Cookie-based Credentials
CORS_ALLOW_CREDENTIALS = True
_cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    # Fallback to local dev domains for credentials support (cannot use '*' with credentials)
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ]

# Dynamic CORS regex matching for Vercel preview environments in non-debug mode
if not DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https:\/\/xiaoyue-dict-.*\.vercel\.app$",
    ]

CORS_EXPOSE_HEADERS = ['Retry-After']

# CSRF Trusted Origins (required for Django 4+ when behind reverse proxy)
_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
else:
    if not DEBUG:
        # Fallback to match production domains or preview domains dynamically if needed
        CSRF_TRUSTED_ORIGINS = [
            'https://cnendict.xyz',
            'https://www.cnendict.xyz',
        ]

# Production Security — Cloudflare Proxy terminates SSL, forwards X-Forwarded-Proto
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Ho_Chi_Minh'

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'calculate-streaks-every-midnight': {
        'task': 'apps.gamification.tasks.calculate_daily_streaks',
        'schedule': crontab(hour=0, minute=0),
    },
    'purge-old-pdf-exports-hourly': {
        'task': 'apps.notes.tasks.purge_old_pdf_exports_task',
        'schedule': crontab(minute=0),
    },
    'process-expired-subscriptions-nightly': {
        'task': 'apps.subscriptions.tasks.process_expired_subscriptions',
        'schedule': crontab(hour=0, minute=30),
    },
}

# Cache Configuration using Redis
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_CACHE_URL', 'redis://redis:6379/1'),
    }
}

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '60/minute',
        'exam_fetch': '10/minute',
    },
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core_project.authentication.CookieJWTAuthentication',
    )
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    
    # Cookie configurations
    'AUTH_COOKIE': 'access_token',
    'AUTH_COOKIE_REFRESH': 'refresh_token',
    'AUTH_COOKIE_SECURE': not DEBUG,
    'AUTH_COOKIE_HTTPONLY': True,
    'AUTH_COOKIE_SAME_SITE': 'Lax',
    'AUTH_COOKIE_USE_CSRF': True,
}

# External Data Storage (mounted from D:/XiaoYueDict_data)
XIAOYUE_DATA_ROOT = os.environ.get('XIAOYUE_DATA_ROOT', '/data')

# AI Service Availability Configuration
AI_SERVICE_AVAILABLE = os.environ.get('AI_SERVICE_AVAILABLE', 'True').lower() == 'true'
