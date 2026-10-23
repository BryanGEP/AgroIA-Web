"""Validación del JWT RS256 con PyJWT y la llave pública (svc-ia no usa comun, que es de DRF).

Mismas reglas que agroia_comun: emisor `agroia-usuarios`, vencimiento obligatorio,
`token_type: "access"` y `user_id`. Sin token o token inválido: 401. Token sin un rol
válido: 403, salvo con AUTH_ACTIVA=False, que solo apaga la revisión de rol: el token
sigue siendo obligatorio porque las solicitudes son por usuario.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.errores import ErrorApi

ISSUER = "agroia-usuarios"
ROLES = ("cliente", "administrador")
_ENCABEZADO = {"WWW-Authenticate": 'Bearer realm="api"'}

esquema_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="jwtAuth",
    description=(
        "Token de acceso RS256 emitido por svc-usuarios. En desarrollo: "
        "`python infra/emitir_token.py --usuario-id 10 --rol cliente`."
    ),
)


@dataclass(frozen=True)
class Usuario:
    id: int
    rol: str | None
    email_verificado: bool

    @property
    def es_administrador(self) -> bool:
        return self.rol == "administrador"


@lru_cache(maxsize=1)
def llave_publica() -> str:
    ruta = settings.jwt_public_key_path
    if ruta and Path(ruta).is_file():
        return Path(ruta).read_text(encoding="utf-8")
    if settings.auth_activa:
        raise RuntimeError(
            f"No se encontró la llave pública JWT en '{ruta}'. "
            "Genera las llaves con infra/generar_llaves.py."
        )
    return ""


def _token_invalido() -> ErrorApi:
    return ErrorApi(401, "token_invalido", "El token no es válido o ya venció.", _ENCABEZADO)


def usuario_autenticado(
    credenciales: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
) -> Usuario:
    if credenciales is None:
        raise ErrorApi(
            401, "no_autenticado", "No se enviaron las credenciales de autenticación.", _ENCABEZADO
        )
    llave = llave_publica()
    if not llave:
        raise _token_invalido()
    try:
        claims = jwt.decode(
            credenciales.credentials,
            llave,
            algorithms=["RS256"],
            issuer=ISSUER,
            options={"require": ["exp", "iss", "jti"]},
        )
    except jwt.PyJWTError as error:
        raise _token_invalido() from error
    if claims.get("token_type") != "access" or not isinstance(claims.get("user_id"), int):
        raise _token_invalido()
    return Usuario(
        id=claims["user_id"],
        rol=claims.get("rol"),
        email_verificado=claims.get("email_verificado") is True,
    )


def usuario_con_rol(usuario: Usuario = Depends(usuario_autenticado)) -> Usuario:
    """Pide un rol válido (cliente o administrador), como EsDuenoOAdmin en comun."""
    if settings.auth_activa and usuario.rol not in ROLES:
        raise ErrorApi(403, "sin_permiso", "No tienes permiso para hacer esta acción.")
    return usuario
