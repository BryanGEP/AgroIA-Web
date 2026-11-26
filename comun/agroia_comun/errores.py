"""Formato común de errores de la API.

Todas las respuestas de error siguen el formato
`{"error": "codigo_corto", "detalle": "mensaje para el usuario"}`. Los errores de
validación agregan `"campos": {"campo": ["mensaje", ...]}`.

Configuración en REST_FRAMEWORK:
    "EXCEPTION_HANDLER": "agroia_comun.errores.manejador_de_excepciones"

Cada 401 y 403 se registra como `acceso_denegado` en el log de seguridad (seguridad.py),
salvo los ErrorDeNegocio: esos los registra el servicio con un evento propio (por
ejemplo, `login_fallido`).
"""

import math

from django.core.exceptions import PermissionDenied as PermisoDenegadoDjango
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.views import exception_handler

from agroia_comun.seguridad import registrar_evento


class ErrorDeNegocio(exceptions.APIException):
    """Regla de negocio que no se cumple (stock insuficiente, transición inválida...).

    Se lanza desde servicios.py y el manejador la convierte al formato común.
    """

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, codigo: str, detalle: str, status_code: int | None = None):
        super().__init__(detail=detalle, code=codigo)
        self.codigo = codigo
        if status_code is not None:
            self.status_code = status_code


# Orden importante: las subclases antes que sus padres.
_CODIGOS = (
    (exceptions.ValidationError, "validacion", "Revisa los datos enviados."),
    (exceptions.NotAuthenticated, "no_autenticado", None),
    (exceptions.AuthenticationFailed, "token_invalido", "El token no es válido o ya venció."),
    (exceptions.PermissionDenied, "sin_permiso", None),
    (exceptions.NotFound, "no_encontrado", "No se encontró el recurso solicitado."),
    (exceptions.MethodNotAllowed, "metodo_no_permitido", None),
    (exceptions.ParseError, "json_invalido", "El cuerpo de la petición no es válido."),
    (exceptions.UnsupportedMediaType, "tipo_no_soportado", None),
    (exceptions.NotAcceptable, "formato_no_aceptado", None),
    (exceptions.Throttled, "demasiados_intentos", None),
)

# Códigos de 403 que una clase de permiso puede pedir con su atributo `code`.
_CODIGO_DRF_SIN_PERMISO = exceptions.PermissionDenied.default_code


def _primer_mensaje(detalle) -> str:
    if isinstance(detalle, dict):
        detalle = next(iter(detalle.values()), "")
    if isinstance(detalle, list):
        detalle = detalle[0] if detalle else ""
    return str(detalle)


def manejador_de_excepciones(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermisoDenegadoDjango):
        exc = exceptions.PermissionDenied()

    respuesta = exception_handler(exc, context)
    if respuesta is None:
        return None

    if isinstance(exc, ErrorDeNegocio):
        respuesta.data = {"error": exc.codigo, "detalle": str(exc.detail)}
        return respuesta

    codigo, mensaje_fijo = "error", None
    for clase, codigo_clase, mensaje in _CODIGOS:
        if isinstance(exc, clase):
            codigo, mensaje_fijo = codigo_clase, mensaje
            break
    if isinstance(exc, exceptions.PermissionDenied):
        propio = exc.get_codes()
        if isinstance(propio, str) and propio != _CODIGO_DRF_SIN_PERMISO:
            codigo = propio
    if isinstance(exc, exceptions.Throttled) and exc.wait:
        mensaje_fijo = f"Demasiados intentos. Intenta de nuevo en {math.ceil(exc.wait)} segundos."

    if respuesta.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        registrar_evento(
            "acceso_denegado",
            context.get("request"),
            estado=respuesta.status_code,
            error=codigo,
        )

    cuerpo = {"error": codigo, "detalle": mensaje_fijo or _primer_mensaje(exc.detail)}
    if isinstance(exc, exceptions.ValidationError):
        detalle = exc.detail
        cuerpo["campos"] = detalle if isinstance(detalle, dict) else {"non_field_errors": detalle}
    respuesta.data = cuerpo
    return respuesta
