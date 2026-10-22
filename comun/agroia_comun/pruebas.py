"""Utilidades para pruebas: llaves RSA temporales y tokens firmados.

Solo se usan en pruebas (de comun y de cada servicio). Los tokens llevan los mismos
claims que emitirá svc-usuarios. Para desarrollo manual existe infra/emitir_token.py.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agroia_comun.configuracion import ISSUER


def generar_par_de_llaves() -> tuple[str, str]:
    """Devuelve (privada, publica) en formato PEM."""
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = llave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    publica = (
        llave.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return privada, publica


def firmar_token(
    llave_privada: str,
    usuario_id: int = 1,
    rol: str | None = "cliente",
    email_verificado: bool = True,
    minutos: int = 15,
    **extra,
) -> str:
    """Firma un token de acceso RS256. Con rol=None el token no lleva el claim `rol`."""
    ahora = datetime.now(UTC)
    claims = {
        "token_type": "access",
        "user_id": usuario_id,
        "email_verificado": email_verificado,
        "token_version": 0,
        "iss": ISSUER,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "jti": uuid.uuid4().hex,
    }
    if rol is not None:
        claims["rol"] = rol
    claims.update(extra)
    return jwt.encode(claims, llave_privada, algorithm="RS256")
