"""Configuración de Django para web.

Todo sale de variables de entorno, documentadas en el .env.example de la raíz. En
Docker las pasa docker-compose.yml; en pytest, config/settings_pruebas.py completa
las que falten.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from agroia_comun.configuracion import (
    ISSUER_POR_DEFECTO,
    configurar_logging,
    leer_llave_publica,
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


NOMBRE_SERVICIO = "web"
SECRET_KEY = variable("DJANGO_SECRET_KEY")
DEBUG = booleano("DJANGO_DEBUG", False)
# Con DEBUG=False no arranca con la clave de .env.example ni con una débil.
validar_secret_key(SECRET_KEY, DEBUG)
ALLOWED_HOSTS = lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Autenticación: True por defecto. Solo el .env local puede ponerla en False.
AUTH_ACTIVA = booleano("AUTH_ACTIVA", True)
JWT_PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", ISSUER_POR_DEFECTO)
# El proxy /api/<servicio>/ valida el access antes de reenviar: sin la llave pública el
# gateway no arranca (aunque AUTH_ACTIVA sea False). Ver docs/contrato-identidad.md.
JWT_LLAVE_PUBLICA = leer_llave_publica(JWT_PUBLIC_KEY_PATH, True)

# Servicios internos a los que el gateway reenvía las peticiones.
URL_SVC_USUARIOS = os.environ.get("URL_SVC_USUARIOS", "http://svc-usuarios:8000")
URL_SVC_TIENDA = os.environ.get("URL_SVC_TIENDA", "http://svc-tienda:8000")
URL_SVC_CONTENIDO = os.environ.get("URL_SVC_CONTENIDO", "http://svc-contenido:8000")
URL_SVC_IA = os.environ.get("URL_SVC_IA", "http://svc-ia:8000")
# Segundos máximos de espera al llamar a un servicio; svc-ia aparte, porque el agente
# puede tardar hasta AGENTE_TIMEOUT (45 s); se deja margen para que responda svc-ia.
SERVICIOS_TIMEOUT = float(os.environ.get("SERVICIOS_TIMEOUT", "10"))
IA_TIMEOUT = float(os.environ.get("IA_TIMEOUT", "50"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "django_htmx",
    "django_tailwind_cli",
    "corsheaders",
    "apps.paginas",
    "apps.catalogo",
    "apps.cuentas",
    "apps.tienda",
    "apps.agroia",
    "apps.diagnostico",
    "apps.panel",
    "apps.proxy",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Content-Security-Policy en todas las respuestas (config/seguridad.py).
    "config.seguridad.PoliticaDeContenidoMiddleware",
    # 403 a /api/ desde un origen que no está en CORS_ALLOWED_ORIGINS; antes que CORS.
    "config.seguridad.OrigenPermitidoMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # SesionExpirada -> login con ?next= y "Tu sesión expiró".
    "apps.cuentas.middleware.SesionExpiradaMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.cuentas.context_processors.usuario",
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

# Las sesiones del gateway se guardan en web_db (backend de base de datos), con los JWT
# dentro: el navegador solo recibe la cookie de sesión (sección 11 de los requerimientos).
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60  # igual que el refresh
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Encabezados de seguridad (Django los pone; se dejan explícitos).
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Sin scripts ni estilos en línea, sin eval: HTMX y Alpine (versión CSP) desde
# static/vendor/ y la lógica en static/js/. `blob:` en img-src: la vista previa de la foto
# del diagnóstico antes de enviarla (URL.createObjectURL). /api/docs/ usa CSP_DOCS (Swagger UI).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; object-src 'none'"
)
CSP_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: "
    "https://cdn.jsdelivr.net; frame-ancestors 'none'; object-src 'none'"
)

# CORS solo para el proxy /api/. Orígenes desde el entorno, sin comodín y sin cookies
# cruzadas: el proxy solo acepta el token en Authorization, nunca la sesión.
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOWED_ORIGINS = lista("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = False
CORS_EXPOSE_HEADERS = ["Retry-After"]

# Las imágenes de diagnóstico pasan por el proxy; el resto de los cuerpos es JSON pequeño.
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
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
    # Fase 4: las clases de autenticación y permisos de agroia_comun (JWT + AUTH_ACTIVA).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AgroIA-Web · web (gateway)",
    "DESCRIPTION": (
        "Gateway: plantillas, sesión y proxy /api/<servicio>/<ruta> hacia los servicios, "
        "con validación del JWT. Las rutas del proxy están en web/README.md."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Mensajes en cookie: las páginas públicas no tocan la base (la sesión llega con el login).
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

LOGGING = configurar_logging()

# Tailwind 4 + daisyUI 5 con django-tailwind-cli (sin Node). El ejecutable se descarga al
# construir la imagen en /opt/tailwind (fuera del volumen del código); en local, en
# web/.django_tailwind_cli/. Entrada: static/css/fuente.css; salida: static/css/agroia.css.
TAILWIND_CLI_USE_DAISY_UI = True
TAILWIND_CLI_VERSION = "2.10.32"  # tailwind-cli-extra: Tailwind 4.3.3 + daisyUI 5.7.47
TAILWIND_CLI_PATH = os.environ.get("TAILWIND_CLI_PATH", ".django_tailwind_cli")
TAILWIND_CLI_SRC_CSS = "static/css/fuente.css"
TAILWIND_CLI_DIST_CSS = "css/agroia.css"
# CLAUDE.md fija la entrada en static/css/fuente.css. El aviso solo importa con un storage de
# manifiesto (ManifestStaticFilesStorage), que este proyecto no usa.
SILENCED_SYSTEM_CHECKS = ["django_tailwind_cli.W001"]
