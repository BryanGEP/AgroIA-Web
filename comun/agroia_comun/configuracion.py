"""Configuración de la validación de JWT y del log de seguridad para config/settings.py.

Está separada de autenticacion.py porque settings.py se carga antes que Django y no
puede importar simplejwt. Ver autenticacion.py para el uso completo.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Emisor de los tokens (claim `iss`) si no se define JWT_ISSUER. svc-usuarios firma con
# este valor y los demás servicios rechazan cualquier otro (ver docs/contrato-identidad.md).
ISSUER_POR_DEFECTO = "agroia-usuarios"


def validar_modo_auth(auth_activa: bool, debug: bool) -> None:
    """Impide arrancar con la autenticación apagada fuera del desarrollo local."""
    if not auth_activa and not debug:
        raise ImproperlyConfigured(
            "AUTH_ACTIVA=False solo se permite con DJANGO_DEBUG=True (desarrollo local)."
        )


# Valor de DJANGO_SECRET_KEY en .env.example: es público, así que nunca sirve fuera del
# desarrollo local.
SECRET_KEY_DE_EJEMPLO = "cambia-esta-clave-por-una-cadena-larga-y-aleatoria"
LARGO_MINIMO_SECRET_KEY = 50
CARACTERES_DISTINTOS_SECRET_KEY = 5


def validar_secret_key(secret_key: str, debug: bool) -> None:
    """Con DEBUG=False no arranca con la clave de ejemplo ni con una clave débil.

    Firma los enlaces de verificación de correo y de recuperación, y las sesiones. Mismos
    criterios que la advertencia security.W009 de `manage.py check --deploy`.
    """
    if debug:
        return
    if secret_key == SECRET_KEY_DE_EJEMPLO:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY es la de .env.example, que es pública. Genera una propia: "
            'python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
    if (
        len(secret_key) < LARGO_MINIMO_SECRET_KEY
        or len(set(secret_key)) < CARACTERES_DISTINTOS_SECRET_KEY
        or secret_key.startswith("django-insecure-")
    ):
        raise ImproperlyConfigured(
            f"DJANGO_SECRET_KEY es débil: usa al menos {LARGO_MINIMO_SECRET_KEY} caracteres "
            'aleatorios (python -c "import secrets; print(secrets.token_urlsafe(50))").'
        )


# Backends que no entregan el correo: lo imprimen, lo guardan en memoria o lo descartan.
BACKENDS_DE_CORREO_SOLO_DESARROLLO = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
)


def validar_backend_de_correo(backend: str, debug: bool) -> None:
    """Con DEBUG=False exige un backend que envíe de verdad (SMTP): el de consola dejaría
    los enlaces de recuperación de contraseña escritos en el log."""
    if not debug and backend in BACKENDS_DE_CORREO_SOLO_DESARROLLO:
        raise ImproperlyConfigured(
            f"EMAIL_BACKEND={backend} solo se permite con DJANGO_DEBUG=True: imprime los "
            "enlaces de los correos en el log. Configura SMTP (EMAIL_BACKEND, EMAIL_HOST...)."
        )


def leer_llave_publica(ruta: str, auth_activa: bool) -> str:
    """Lee la llave pública PEM. Con AUTH_ACTIVA, si no existe, el servicio no arranca."""
    if ruta and Path(ruta).is_file():
        return Path(ruta).read_text(encoding="utf-8")
    if auth_activa:
        raise ImproperlyConfigured(
            f"No se encontró la llave pública JWT en '{ruta}'. "
            "Genera las llaves con infra/generar_llaves.py."
        )
    return ""


def configurar_jwt(llave_publica: str, issuer: str = ISSUER_POR_DEFECTO) -> dict:
    """Bloque SIMPLE_JWT para validar tokens: solo la llave pública, nunca la privada."""
    if not issuer:
        raise ImproperlyConfigured("JWT_ISSUER no puede estar vacío.")
    return {
        "ALGORITHM": "RS256",
        "VERIFYING_KEY": llave_publica,
        "ISSUER": issuer,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "USER_ID_CLAIM": "user_id",
        "TOKEN_TYPE_CLAIM": "token_type",
        "JTI_CLAIM": "jti",
        "LEEWAY": 0,
    }


def configurar_logging(nivel: str = "INFO") -> dict:
    """LOGGING de Django: el logger `seguridad` escribe una línea JSON por evento en la
    consola (ver seguridad.py); lo demás conserva el comportamiento de Django."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"solo_mensaje": {"format": "%(message)s"}},
        "handlers": {
            "seguridad": {"class": "logging.StreamHandler", "formatter": "solo_mensaje"},
        },
        "loggers": {
            "seguridad": {"handlers": ["seguridad"], "level": nivel, "propagate": False},
        },
    }
