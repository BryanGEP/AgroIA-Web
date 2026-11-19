"""Configuración de Django para svc-usuarios.

Todo sale de variables de entorno, documentadas en el .env.example de la raíz. En
Docker las pasa docker-compose.yml; en pytest, config/settings_pruebas.py completa
las que falten.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from agroia_comun.configuracion import (
    ISSUER_POR_DEFECTO,
    configurar_jwt,
    configurar_logging,
    leer_llave_publica,
    validar_backend_de_correo,
    validar_modo_auth,
    validar_secret_key,
)

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


NOMBRE_SERVICIO = "svc-usuarios"
SECRET_KEY = variable("DJANGO_SECRET_KEY")
DEBUG = booleano("DJANGO_DEBUG", False)
# Con DEBUG=False no arranca con la clave de .env.example ni con una débil.
validar_secret_key(SECRET_KEY, DEBUG)
ALLOWED_HOSTS = lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Autenticación: True por defecto. Solo el .env local puede ponerla en False, y solo
# con DEBUG=True. Con False se apagan las revisiones de rol, pero los endpoints por
# usuario siguen pidiendo token (ver comun/README.md).
AUTH_ACTIVA = booleano("AUTH_ACTIVA", True)
validar_modo_auth(AUTH_ACTIVA, DEBUG)
JWT_PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", ISSUER_POR_DEFECTO)

# Solo svc-usuarios recibe la llave privada: firma los tokens al iniciar sesión y al
# renovar. Sin ella (o sin la pública) el servicio no arranca, aunque AUTH_ACTIVA sea
# False. Contrato en docs/contrato-identidad.md.
JWT_PRIVATE_KEY_PATH = variable("JWT_PRIVATE_KEY_PATH")
if not Path(JWT_PRIVATE_KEY_PATH).is_file():
    raise ImproperlyConfigured(
        f"No se encontró la llave privada JWT en '{JWT_PRIVATE_KEY_PATH}'. "
        "Genera las llaves con infra/generar_llaves.py."
    )
SIMPLE_JWT = {
    **configurar_jwt(leer_llave_publica(JWT_PUBLIC_KEY_PATH, True), issuer=JWT_ISSUER),
    "SIGNING_KEY": Path(JWT_PRIVATE_KEY_PATH).read_text(encoding="utf-8"),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "id",
    "UPDATE_LAST_LOGIN": False,  # el login lo actualiza en servicios.py
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
# Caché compartida por los procesos del servicio: guarda los contadores del límite de
# intentos de DRF.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "svc-usuarios",
    }
}

# Correos (ver apps/usuarios/correos.py). En desarrollo se imprimen en la consola del
# contenedor: docker compose logs -f svc-usuarios.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
# Con DEBUG=False exige SMTP: la consola dejaría los enlaces de recuperación en el log.
validar_backend_de_correo(EMAIL_BACKEND, DEBUG)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = booleano("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or "AgroIA <no-responder@agroia.local>"
# Los enlaces de los correos apuntan al gateway, que tendrá las pantallas.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:8000").rstrip("/")
# Vigencia del enlace de recuperación de contraseña (segundos).
PASSWORD_RESET_TIMEOUT = 3600

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
    "rest_framework_simplejwt.token_blacklist",
    "axes",
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
    # Debe ir al final (documentación de django-axes).
    "axes.middleware.AxesMiddleware",
]

# AxesStandaloneBackend primero: rechaza el intento si la combinación correo + IP está
# bloqueada, antes de revisar la contraseña.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Bloqueo temporal tras 5 intentos fallidos de la misma combinación correo + IP: nadie
# puede bloquear la cuenta de otro desde su propia IP.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "email"
AXES_USERNAME_CALLABLE = "apps.usuarios.bloqueo.correo_del_intento"
# Misma IP que el límite de intentos de DRF (NUM_PROXIES = 1).
AXES_CLIENT_IP_CALLABLE = "agroia_comun.seguridad.ip_cliente"
# Respuesta del bloqueo con el formato común de errores (también en /admin/).
AXES_LOCKOUT_CALLABLE = "apps.usuarios.bloqueo.respuesta_de_bloqueo"
AXES_VERBOSE = False

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
    # Un proxy de confianza (el gateway): la IP del cliente es el último valor de
    # X-Forwarded-For. Ver docs/contrato-identidad.md.
    "NUM_PROXIES": 1,
    # Límite de intentos (ver apps/usuarios/throttles.py). Los `_correo` cuentan por el
    # correo del cuerpo; cambiar_password por usuario; los demás por IP.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "registro": "5/hour",
        "recuperar": "3/hour",
        "recuperar_correo": "3/hour",
        "reenviar_verificacion": "3/hour",
        "reenviar_verificacion_correo": "3/hour",
        "cambiar_password": "5/hour",
    },
}

LOGGING = configurar_logging()

SPECTACULAR_SETTINGS = {
    "TITLE": "AgroIA-Web · svc-usuarios",
    "DESCRIPTION": "Registro, login, JWT, recuperación de contraseña, roles, perfil y direcciones.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    # Esquema y ejemplos comunes en las respuestas de error (ver agroia_comun/openapi.py).
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "agroia_comun.openapi.documentar_errores",
    ],
}
