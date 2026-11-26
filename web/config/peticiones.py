"""Log por petición del gateway (logger `peticiones`) sin tokens en las rutas.

Una línea JSON por petición, para seguir un flujo de punta a punta con su correlación:

    {"evento": "peticion", "metodo": "GET", "ruta": "restablecer/<str:uid>/<str:token>/",
     "estado": 200, "duracion_ms": 12, "correlacion_id": "…", "usuario_id": "…"}

`ruta` es siempre el **patrón** de la URL (el `route` de Django), nunca la ruta real ni la
query string: hay rutas que llevan un token (`/restablecer/<uid>/<token>/`) o lo llevan en
la query (`/verificar-correo/?token=…`). Una ruta que no existe se registra como
`(sin ruta)`.

Por la misma razón, `SinRutasReales` filtra los loggers de Django que escriben la ruta
real: el de runserver (`django.server`, una línea por petición: se descarta, porque este
log la reemplaza) y `django.request` («Not Found: /ruta», errores 500), donde la ruta se
cambia por su patrón.
"""

import json
import logging
import time
from datetime import UTC, datetime

from agroia_comun.eventos import correlacion

logger = logging.getLogger("peticiones")

SIN_RUTA = "(sin ruta)"


def patron_de(request) -> str:
    coincidencia = getattr(request, "resolver_match", None)
    return getattr(coincidencia, "route", None) or SIN_RUTA


class LogDePeticionesMiddleware:
    """Va después de CorrelacionMiddleware, para tener la correlación de la petición."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.perf_counter()
        respuesta = self.get_response(request)
        # Solo si la petición ya leyó la sesión: leerla aquí tocaría la base en páginas
        # públicas que no la usan.
        sesion = getattr(request, "session", None)
        usuario = (sesion.get("usuario") if sesion is not None and sesion.accessed else None) or {}
        logger.info(
            json.dumps(
                {
                    "evento": "peticion",
                    "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
                    "metodo": request.method,
                    "ruta": patron_de(request),
                    "estado": respuesta.status_code,
                    "duracion_ms": round((time.perf_counter() - inicio) * 1000),
                    "correlacion_id": correlacion.actual(),
                    "usuario_id": usuario.get("id"),
                },
                ensure_ascii=False,
            )
        )
        return respuesta


class SinRutasReales(logging.Filter):
    """Ningún log de Django escribe la ruta real (puede llevar un token)."""

    def filter(self, registro: logging.LogRecord) -> bool:
        if registro.name == "django.server":
            return False  # LogDePeticionesMiddleware ya registra cada petición
        request = getattr(registro, "request", None)
        if request is not None and registro.args:
            reales = {request.path, request.get_full_path()}
            registro.args = tuple(
                patron_de(request) if valor in reales else valor for valor in registro.args
            )
        return True
