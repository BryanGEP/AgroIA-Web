"""Validación de un token de acceso sin DRF (la usa el proxy del gateway `web`).

Mismas reglas que `autenticacion.AutenticacionJWT` y que svc-ia (docs/contrato-identidad.md):
firma RS256 con la llave pública, emisor `JWT_ISSUER`, `exp`, `iss` y `jti` obligatorios,
`token_type == "access"` y `user_id` UUID. No consulta la base de svc-usuarios.
"""

import uuid

import jwt


class TokenInvalido(Exception):
    """El token no se pudo validar. El motivo no se muestra al cliente."""


def validar_access(token: str, llave_publica: str, emisor: str) -> dict:
    """Devuelve los claims de un access válido o lanza TokenInvalido."""
    if not token or not llave_publica:
        raise TokenInvalido("sin token o sin llave pública")
    try:
        claims = jwt.decode(
            token,
            llave_publica,
            algorithms=["RS256"],
            issuer=emisor,
            options={"require": ["exp", "iss", "jti"]},
        )
    except jwt.PyJWTError as error:
        raise TokenInvalido(type(error).__name__) from error
    if claims.get("token_type") != "access":
        raise TokenInvalido("no es un token de acceso")
    try:
        uuid.UUID(str(claims.get("user_id")))
    except ValueError as error:
        raise TokenInvalido("user_id no es UUID") from error
    if not isinstance(claims.get("user_id"), str):
        raise TokenInvalido("user_id no es texto")
    return claims
