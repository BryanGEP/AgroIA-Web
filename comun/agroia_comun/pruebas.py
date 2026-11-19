"""Utilidades para pruebas: llaves RSA temporales y tokens firmados.

Solo se usan en pruebas (de comun y de cada servicio). Los tokens llevan los mismos
claims que emite svc-usuarios al iniciar sesión. Para desarrollo manual existe
infra/emitir_token.py.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agroia_comun.configuracion import ISSUER_POR_DEFECTO

# Id de ejemplo para las pruebas que no necesitan uno en particular.
USUARIO_ID_PRUEBA = uuid.UUID("0b6f1c3e-6a4d-4f6e-9a51-6f0c2d7e8a10")


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
    usuario_id: uuid.UUID | str = USUARIO_ID_PRUEBA,
    rol: str | None = "cliente",
    email_verificado: bool = True,
    minutos: int = 15,
    emisor: str = ISSUER_POR_DEFECTO,
    **extra,
) -> str:
    """Firma un token de acceso RS256 con los claims de docs/contrato-identidad.md.

    Con rol=None el token no lleva el claim `rol`. `extra` sobrescribe cualquier claim.
    """
    ahora = datetime.now(UTC)
    claims = {
        "token_type": "access",
        "user_id": str(usuario_id),
        "email_verificado": email_verificado,
        "token_version": 0,
        "iss": emisor,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "jti": uuid.uuid4().hex,
    }
    if rol is not None:
        claims["rol"] = rol
    claims.update(extra)
    return jwt.encode(claims, llave_privada, algorithm="RS256")


def cargar_configuracion(carpeta, **variables) -> subprocess.CompletedProcess:
    """Importa `config.settings` del servicio en otro proceso, con las variables de entorno
    actuales más `variables`. Sirve para probar que el servicio no arranca con una
    configuración insegura (la importación falla con ImproperlyConfigured)."""
    entorno = {**os.environ, **variables}
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=carpeta,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=60,
    )
