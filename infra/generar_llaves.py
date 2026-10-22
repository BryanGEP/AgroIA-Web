"""Genera el par de llaves RSA con el que svc-usuarios firma los JWT (RS256).

Uso, desde la raíz del repo y con el venv de la raíz activo:

    python infra/generar_llaves.py

Crea infra/llaves/privada.pem y infra/llaves/publica.pem si no existen. Nunca las
sobrescribe: para regenerarlas, borra la carpeta infra/llaves/ primero (todos los
tokens emitidos dejarán de ser válidos). La carpeta está en .gitignore.
"""

import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

CARPETA = Path(__file__).resolve().parent / "llaves"
PRIVADA = CARPETA / "privada.pem"
PUBLICA = CARPETA / "publica.pem"
BITS = 2048


def generar() -> None:
    if PRIVADA.exists() or PUBLICA.exists():
        print(f"Las llaves ya existen en {CARPETA}; no se modificó nada.")
        return

    CARPETA.mkdir(parents=True, exist_ok=True)
    llave = rsa.generate_private_key(public_exponent=65537, key_size=BITS)

    PRIVADA.write_bytes(
        llave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLICA.write_bytes(
        llave.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    if os.name == "posix":
        PRIVADA.chmod(0o600)

    print(f"Llaves generadas en {CARPETA}:")
    print(f"  {PRIVADA.name}  (solo para svc-usuarios, nunca la compartas)")
    print(f"  {PUBLICA.name}  (para validar tokens en todos los servicios)")


if __name__ == "__main__":
    sys.exit(generar())
