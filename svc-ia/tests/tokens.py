"""Llaves y tokens para las pruebas de svc-ia (mismos claims que emitirá svc-usuarios)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generar_par_de_llaves() -> tuple[str, str]:
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = llave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    publica = (
        llave.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return privada, publica


LLAVE_PRIVADA, LLAVE_PUBLICA = generar_par_de_llaves()


def firmar_token(
    usuario_id: int = 10,
    rol: str | None = "cliente",
    minutos: int = 15,
    llave: str = LLAVE_PRIVADA,
    **extra,
) -> str:
    ahora = datetime.now(UTC)
    claims = {
        "token_type": "access",
        "user_id": usuario_id,
        "email_verificado": True,
        "token_version": 0,
        "iss": "agroia-usuarios",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "jti": uuid.uuid4().hex,
    }
    if rol is not None:
        claims["rol"] = rol
    claims.update(extra)
    return jwt.encode(claims, llave, algorithm="RS256")


def encabezado(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
