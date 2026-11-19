"""Emite un token de acceso JWT SOLO PARA PRUEBAS Y DESARROLLO. No usar en producción.

Desde la Entrega 3 el flujo normal es iniciar sesión: POST /api/v1/auth/login/ en
svc-usuarios devuelve el access y el refresh (ver docs/contrato-identidad.md). Este script
queda para casos que el login no cubre: probar un servicio sin levantar svc-usuarios, un
token vencido (--vencido) o un usuario que no existe en la base.

Firma con la llave privada de infra/llaves/ y los mismos claims que svc-usuarios:
token_type, user_id (UUID), rol, email_verificado, token_version, iss, iat, exp y jti.

Uso, desde la raíz del repo y con el venv de la raíz activo:

    python infra/emitir_token.py --rol cliente
    python infra/emitir_token.py --rol administrador --usuario-id <uuid>
    python infra/emitir_token.py --rol cliente --sin-verificar
    python infra/emitir_token.py --vencido

Sin --usuario-id se usa un UUID nuevo. El token se imprime en la salida; úsalo como
`Authorization: Bearer <token>` o en el botón Authorize de /api/docs/. Cualquiera con la
llave privada puede firmar tokens: la llave nunca se sube al repositorio ni se copia a
otros servicios.
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

ISSUER = os.environ.get("JWT_ISSUER") or "agroia-usuarios"
LLAVE_POR_DEFECTO = Path(__file__).resolve().parent / "llaves" / "privada.pem"


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emite un token de acceso de prueba (solo para desarrollo y pruebas)."
    )
    parser.add_argument(
        "--usuario-id",
        type=uuid.UUID,
        default=None,
        help="UUID del usuario (por defecto, uno nuevo).",
    )
    parser.add_argument(
        "--rol", choices=["cliente", "administrador"], default="cliente", help="Rol del usuario."
    )
    parser.add_argument(
        "--sin-verificar",
        action="store_true",
        help="Emite el token con email_verificado=false.",
    )
    parser.add_argument("--minutos", type=int, default=60, help="Vigencia (por defecto 60).")
    parser.add_argument(
        "--vencido",
        action="store_true",
        help="Emite un token que venció hace una hora (para probar el 401).",
    )
    parser.add_argument("--emisor", default=ISSUER, help=f"Claim iss (por defecto {ISSUER}).")
    parser.add_argument("--llave", type=Path, default=LLAVE_POR_DEFECTO, help="Llave privada PEM.")
    return parser.parse_args()


def emitir(
    usuario_id: uuid.UUID,
    rol: str,
    verificado: bool,
    minutos: int,
    llave: str,
    emisor: str = ISSUER,
) -> str:
    ahora = datetime.now(UTC)
    claims = {
        "token_type": "access",
        "user_id": str(usuario_id),
        "rol": rol,
        "email_verificado": verificado,
        "token_version": 0,
        "iss": emisor,
        # Un token vencido se emitió 15 minutos antes de vencer, como uno real.
        "iat": ahora if minutos > 0 else ahora + timedelta(minutes=minutos - 15),
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
    if args.minutos <= 0 and not args.vencido:
        print(
            "--minutos debe ser mayor que 0 (para un token vencido usa --vencido).", file=sys.stderr
        )
        return 1
    print(
        emitir(
            args.usuario_id or uuid.uuid4(),
            args.rol,
            not args.sin_verificar,
            -60 if args.vencido else args.minutos,
            args.llave.read_text(encoding="utf-8"),
            args.emisor,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
