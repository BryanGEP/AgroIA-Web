"""Configuración de la validación de JWT para config/settings.py.

Está separada de autenticacion.py porque settings.py se carga antes que Django y no
puede importar simplejwt. Ver autenticacion.py para el uso completo.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Emisor de los tokens: el `ISSUER` de SIMPLE_JWT en svc-usuarios.
ISSUER = "agroia-usuarios"


def validar_modo_auth(auth_activa: bool, debug: bool) -> None:
    """Impide arrancar con la autenticación apagada fuera del desarrollo local."""
    if not auth_activa and not debug:
        raise ImproperlyConfigured(
            "AUTH_ACTIVA=False solo se permite con DJANGO_DEBUG=True (desarrollo local)."
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


def configurar_jwt(llave_publica: str) -> dict:
    """Bloque SIMPLE_JWT para validar tokens: solo la llave pública, nunca la privada."""
    return {
        "ALGORITHM": "RS256",
        "VERIFYING_KEY": llave_publica,
        "ISSUER": ISSUER,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "USER_ID_CLAIM": "user_id",
        "TOKEN_TYPE_CLAIM": "token_type",
        "JTI_CLAIM": "jti",
        "LEEWAY": 0,
    }
