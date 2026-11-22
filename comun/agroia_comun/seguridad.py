"""Registro de eventos de seguridad: una línea JSON por evento en el logger `seguridad`.

    registrar_evento("login_fallido", request, email="ana@example.com")

Cada línea lleva `evento`, `fecha`, `servicio`, `ip`, `metodo`, `ruta`, `usuario_id` (si
el token es válido) y los datos extra. Nunca registra contraseñas ni tokens: cualquier dato
cuya llave contenga una palabra de CLAVES_SENSIBLES se descarta antes de escribir.

La IP es la misma que usa el límite de intentos (REST_FRAMEWORK["NUM_PROXIES"] = 1): el
último valor de X-Forwarded-For, que pone el gateway, o REMOTE_ADDR si no viene. Por eso
los puertos directos de los servicios solo se publican en 127.0.0.1 (ver
docs/contrato-identidad.md).
"""

import json
import logging
from datetime import UTC, datetime

from django.conf import settings

from agroia_comun.eventos import correlacion

logger = logging.getLogger("seguridad")

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


def ip_cliente(request) -> str | None:
    """IP del cliente con un proxy de confianza (el gateway). Sirve también para axes
    (AXES_CLIENT_IP_CALLABLE)."""
    meta = getattr(request, "META", None) or {}
    reenviada = meta.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        ultima = reenviada.split(",")[-1].strip()
        if ultima:
            return ultima
    return meta.get("REMOTE_ADDR")


def _usuario_id(request) -> str | None:
    try:
        usuario = getattr(request, "user", None)
    except Exception:  # el token no es válido: DRF vuelve a lanzar el error al leer `user`
        return None
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None
    return str(usuario.id)


def sin_datos_sensibles(datos: dict) -> dict:
    return {
        llave: valor
        for llave, valor in datos.items()
        if not any(palabra in llave.lower() for palabra in CLAVES_SENSIBLES)
    }


def registrar_evento(evento: str, request=None, nivel: int = logging.INFO, **datos) -> None:
    registro = {
        "evento": evento,
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "servicio": getattr(settings, "NOMBRE_SERVICIO", ""),
        "correlacion_id": correlacion.actual(),
    }
    if request is not None:
        registro.update(
            ip=ip_cliente(request),
            metodo=getattr(request, "method", None),
            ruta=getattr(request, "path", None),
            usuario_id=_usuario_id(request),
        )
    registro.update(sin_datos_sensibles(datos))
    logger.log(nivel, json.dumps(registro, ensure_ascii=False, default=str))
