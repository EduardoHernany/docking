"""
Django settings for djangoAPI project.
Django 4.2.x
"""

from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

# --------------------------------------------------------------------------------------
# Paths & env
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------------------------
# Essentials
# --------------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
DEBUG = os.getenv("DEBUG", "False") == "True"

# Domínios que o Django aceita responder (HTTP Host header)
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    os.getenv("API_HOST", "plasmodocking.ecotechamazonia.com.br"),
]

# --------------------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # 3rd party
    "corsheaders",
    "django_celery_results",
    "rest_framework",
    "drf_spectacular",

    # Local apps
    "users",
    "macromolecules",
    "processes",
]

# --------------------------------------------------------------------------------------
# Middleware (corsheaders no topo!)
# --------------------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Se usar apenas JWT (sem session no front), o CSRF pode ser desativado:
    # "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "djangoAPI.urls"

# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "djangoAPI.wsgi.application"
ASGI_APPLICATION = "djangoAPI.asgi.application"

# --------------------------------------------------------------------------------------
# Database (PostgreSQL)
# --------------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "plasmodocking"),
        "USER": os.getenv("POSTGRES_USER", "plasmo"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------------------
# I18N / TZ
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static & Media
# --------------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------------------
# Arquivos de moléculas
# --------------------------------------------------------------------------------------
MOLECULES_BASE_DIR = BASE_DIR / "files" / "molecules"
os.makedirs(MOLECULES_BASE_DIR, exist_ok=True)

# --------------------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
CELERY_TASK_DEFAULT_QUEUE = "default"

# --------------------------------------------------------------------------------------
# E-mail (Resend) - fallback para console em dev
# --------------------------------------------------------------------------------------
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "PlasmoDocking <noreply@ecotechamazonia.com.br>")
PASSWORD_RESET_URL = os.getenv("PASSWORD_RESET_URL", "")
EMAIL_FALLBACK_TO_CONSOLE = os.getenv("EMAIL_FALLBACK_TO_CONSOLE", "True") == "True"

if EMAIL_FALLBACK_TO_CONSOLE or not RESEND_API_KEY:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --------------------------------------------------------------------------------------
# DRF & OpenAPI
# --------------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Apenas JWT no backend
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        # Se quiser navegar no browsable API com sessão, reative a linha abaixo e o CSRF:
        # "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PlasmoDocking API",
    "DESCRIPTION": "API para Users, Macromolecules e Processes",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=90),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --------------------------------------------------------------------------------------
# CORS (restrito a localhost e ao domínio do front)
# --------------------------------------------------------------------------------------
# Como você usa JWT em header (sem cookies), mantenha credentials=False.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://plasmodocking-unir.ecotechamazonia.com.br",
]
CORS_ALLOW_CREDENTIALS = False

# Headers/Métodos comuns
from corsheaders.defaults import default_headers, default_methods
CORS_ALLOW_METHODS = list(default_methods) + ["OPTIONS"]
CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
    "content-type",
    "x-requested-with",
]

# Se um dia usar cookies/CSRF com o frontend:
# CSRF_TRUSTED_ORIGINS = [
#     "https://plasmodocking-unir.ecotechamazonia.com.br",
# ]

# --------------------------------------------------------------------------------------
# Segurança (só ativa forte em produção)
# --------------------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Se for usar cookies cross-site, ajuste SameSite=None:
    # SESSION_COOKIE_SAMESITE = "None"
    # CSRF_COOKIE_SAMESITE = "None"

    # HSTS (opcional, após validar HTTPS)
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))  # ex.: 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# --------------------------------------------------------------------------------------
# Logging básico (útil pra diagnosticar CORS/headers)
# --------------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
        "corsheaders": {"handlers": ["console"], "level": "DEBUG"},
        "django.security.csrf": {"handlers": ["console"], "level": "DEBUG"},
    },
}
