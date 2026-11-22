"""Log de seguridad, equivalente a agroia_comun.seguridad (que depende de Django; svc-ia solo
instala el núcleo de comun).

Una línea JSON por evento en el logger `seguridad`, con el mismo formato que los servicios
Django: `evento`, `fecha`, `servicio`, `ip`, `metodo`, `ruta`, `usuario_id` y los datos
extra. Nunca registra contraseñas ni tokens: los datos cuya llave contiene una palabra de
CLAVES_SENSIBLES se descartan.
"""

import json
import logging
from datetime import UTC, datetime

from fastapi import Request

logger = logging.getLogger("seguridad")
if not logger.handlers:  # uvicorn no configura este logger
    _salida = logging.StreamHandler()
    _salida.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_salida)
    logger.setLevel(logging.INFO)
    logger.propagate = False

CLAVES_SENSIBLES = (
    "password",
    "contrasena",
    "token",
    "refresh",
    "access",
    "authorization",
    "secreto",
    "uid",
)


def ip_cliente(request: Request) -> str | None:
    """Un proxy de confianza (el gateway): el último valor de X-Forwarded-For o, si no viene,
    la IP de la conexión. Igual que NUM_PROXIES = 1 en los servicios Django."""
    reenviada = request.headers.get("x-forwarded-for", "")
    ultima = reenviada.split(",")[-1].strip() if reenviada else ""
    if ultima:
        return ultima
    return request.client.host if request.client else None


def registrar_evento(evento: str, request: Request | None = None, **datos) -> None:
    registro = {
        "evento": evento,
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "servicio": "svc-ia",
    }
    if request is not None:
        registro.update(ip=ip_cliente(request), metodo=request.method, ruta=request.url.path)
    registro.update(
        {
            llave: valor
            for llave, valor in datos.items()
            if not any(palabra in llave.lower() for palabra in CLAVES_SENSIBLES)
        }
    )
    logger.info(json.dumps(registro, ensure_ascii=False, default=str))
