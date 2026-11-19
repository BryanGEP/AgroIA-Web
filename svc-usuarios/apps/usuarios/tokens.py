"""Emisión de los JWT (RS256) y tokens firmados de los enlaces de correo.

Claims de los JWT (docs/contrato-identidad.md): `token_type`, `user_id` (UUID en texto),
`rol`, `email_verificado`, `token_version`, `iss`, `iat`, `exp` y `jti`. Nada de datos
personales: el JWT se puede leer sin la llave.
"""

from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from apps.usuarios.models import Usuario

SALT_VERIFICACION = "verificacion-email"
VIGENCIA_VERIFICACION = 24 * 60 * 60  # segundos


def claims_de(usuario: Usuario) -> dict:
    """Claims propios, calculados con los datos actuales del usuario."""
    return {
        "rol": usuario.rol,
        "email_verificado": usuario.email_verificado,
        "token_version": usuario.token_version,
    }


def emitir_par(usuario: Usuario) -> dict:
    """Par nuevo: refresh de 7 días (queda registrado para la blacklist) y access de 15
    minutos con los mismos claims."""
    refresh = RefreshToken.for_user(usuario)
    for nombre, valor in claims_de(usuario).items():
        refresh[nombre] = valor
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


# --- Verificación de correo (sección 2) ---------------------------------------------


def token_de_verificacion(usuario: Usuario) -> str:
    return signing.TimestampSigner(salt=SALT_VERIFICACION).sign(str(usuario.pk))


def leer_token_de_verificacion(token: str) -> str:
    """El id del usuario. Lanza signing.SignatureExpired o signing.BadSignature."""
    return signing.TimestampSigner(salt=SALT_VERIFICACION).unsign(
        token, max_age=VIGENCIA_VERIFICACION
    )


# --- Recuperación de contraseña (sección 6) -----------------------------------------


def uid_de(usuario: Usuario) -> str:
    return urlsafe_base64_encode(force_bytes(usuario.pk))


def usuario_del_enlace(uid: str, token: str) -> Usuario | None:
    """El usuario activo del enlace si el token es válido. El token deja de servir en
    cuanto cambia la contraseña (depende de su hash) y vence con PASSWORD_RESET_TIMEOUT."""
    try:
        pk = force_str(urlsafe_base64_decode(uid))
        usuario = Usuario.objects.filter(pk=pk, is_active=True).first()
    except (ValueError, TypeError, OverflowError, UnicodeDecodeError, ValidationError):
        return None  # uid alterado o que no es un UUID
    if usuario is None or not default_token_generator.check_token(usuario, token):
        return None
    return usuario


def token_de_recuperacion(usuario: Usuario) -> str:
    return default_token_generator.make_token(usuario)
