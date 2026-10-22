"""Emite un token de acceso JWT para DESARROLLO Y PRUEBAS. No usar en producción.

Mientras svc-usuarios no emite tokens (Entrega 3), este script firma uno con la llave
privada de infra/llaves/ y los mismos claims que emitirá svc-usuarios: token_type,
user_id, rol, email_verificado, token_version, iss, iat, exp y jti.

Uso, desde la raíz del repo y con el venv de la raíz activo:

    python infra/emitir_token.py --usuario-id 10 --rol cliente
    python infra/emitir_token.py --usuario-id 1 --rol administrador --minutos 480
    python infra/emitir_token.py --usuario-id 12 --rol cliente --sin-verificar

El token se imprime en la salida; úsalo como `Authorization: Bearer <token>` o en el
botón Authorize de /api/docs/. Cualquiera con la llave privada puede firmar tokens: la
llave nunca se sube al repositorio ni se copia a otros servicios.
"""

import argparse
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

ISSUER = "agroia-usuarios"
LLAVE_POR_DEFECTO = Path(__file__).resolve().parent / "llaves" / "privada.pem"


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emite un token de acceso de desarrollo (solo para desarrollo y pruebas)."
    )
    parser.add_argument("--usuario-id", type=int, required=True, help="Id del usuario.")
    parser.add_argument(
        "--rol", choices=["cliente", "administrador"], default="cliente", help="Rol del usuario."
    )
    parser.add_argument(
        "--sin-verificar",
        action="store_true",
        help="Emite el token con email_verificado=false.",
    )
    parser.add_argument("--minutos", type=int, default=60, help="Vigencia (por defecto 60).")
    parser.add_argument("--llave", type=Path, default=LLAVE_POR_DEFECTO, help="Llave privada PEM.")
    return parser.parse_args()


def emitir(usuario_id: int, rol: str, verificado: bool, minutos: int, llave: str) -> str:
    ahora = datetime.now(UTC)
    claims = {
        "token_type": "access",
        "user_id": usuario_id,
        "rol": rol,
        "email_verificado": verificado,
        "token_version": 0,
        "iss": ISSUER,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, llave, algorithm="RS256")


def main() -> int:
    args = argumentos()
    if not args.llave.is_file():
        print(
            f"No existe la llave privada {args.llave}. Genérala con infra/generar_llaves.py.",
            file=sys.stderr,
        )
        return 1
    if args.minutos <= 0:
        print("--minutos debe ser mayor que 0.", file=sys.stderr)
        return 1
    print(
        emitir(
            args.usuario_id,
            args.rol,
            not args.sin_verificar,
            args.minutos,
            args.llave.read_text(encoding="utf-8"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
