"""Configuración de Django para svc-usuarios.

Todo sale de variables de entorno, documentadas en el .env.example de la raíz. En
Docker las pasa docker-compose.yml; en pytest, config/settings_pruebas.py completa
las que falten.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from agroia_comun.configuracion import configurar_jwt, leer_llave_publica, validar_modo_auth

BASE_DIR = Path(__file__).resolve().parent.parent


def variable(nombre: str, defecto: str | None = None) -> str:
    """Lee una variable de entorno; si es obligatoria y no existe, falla al arrancar."""
    valor = os.environ.get(nombre, defecto)
    if valor is None or valor == "":
        raise ImproperlyConfigured(f"Falta la variable de entorno {nombre}")
    return valor


def booleano(nombre: str, defecto: bool) -> bool:
    return os.environ.get(nombre, str(defecto)).strip().lower() in {"1", "true", "si", "yes"}


def lista(nombre: str, defecto: str = "") -> list[str]:
    return [valor.strip() for valor in os.environ.get(nombre, defecto).split(",") if valor.strip()]


SECRET_KEY = variable("DJANGO_SECRET_KEY")
DEBUG = booleano("DJANGO_DEBUG", False)
ALLOWED_HOSTS = lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Autenticación: True por defecto. Solo el .env local puede ponerla en False, y solo
# con DEBUG=True. Con False se apagan las revisiones de rol, pero los endpoints por
# usuario siguen pidiendo token (ver comun/README.md).
AUTH_ACTIVA = booleano("AUTH_ACTIVA", True)
validar_modo_auth(AUTH_ACTIVA, DEBUG)
JWT_PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH", "")
# En la Entrega 2 svc-usuarios solo valida tokens; en la Entrega 3 también los firmará.
SIMPLE_JWT = configurar_jwt(leer_llave_publica(JWT_PUBLIC_KEY_PATH, AUTH_ACTIVA))

# Solo svc-usuarios recibe la llave privada (firma los JWT).
JWT_PRIVATE_KEY_PATH = os.environ.get("JWT_PRIVATE_KEY_PATH", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Versión vigente del aviso de privacidad; se guarda en cada usuario al registrarse.
# Si el aviso cambia, se sube aquí y el gateway pedirá aceptar la nueva (Entrega 3).
VERSION_AVISO_PRIVACIDAD = variable("VERSION_AVISO_PRIVACIDAD", "2026-10")

AUTH_USER_MODEL = "usuarios.Usuario"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.usuarios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": variable("POSTGRES_DB"),
        "USER": variable("POSTGRES_USER"),
        "PASSWORD": variable("POSTGRES_PASSWORD"),
        "HOST": variable("POSTGRES_HOST", "postgres"),
        "PORT": variable("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ["email", "nombre", "apellidos"]},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Archivos siempre con default_storage: en la Entrega 5 se pasa a Cloud Storage
# cambiando solo esta configuración.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["agroia_comun.autenticacion.AutenticacionJWT"],
    # Todo pide token salvo los endpoints que declaran AllowAny.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "agroia_comun.errores.manejador_de_excepciones",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AgroIA-Web · svc-usuarios",
    "DESCRIPTION": "Registro, login, JWT, recuperación de contraseña, roles, perfil y direcciones.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
}
