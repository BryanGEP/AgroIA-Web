"""CorrelacionMiddleware: la correlación de cada petición en los servicios Django y el gateway.

    MIDDLEWARE = ["agroia_comun.correlacion.CorrelacionMiddleware", ...]

- Toma `X-Correlacion-Id` solo si es un UUID válido; si no viene o no lo es, genera uno.
- La guarda en la ContextVar de `agroia_comun.eventos.correlacion` (la usan los eventos,
  el log de seguridad y las llamadas del gateway a los servicios) y en
  `request.correlacion_id`.
- La devuelve en el encabezado `X-Correlacion-Id` de la respuesta.
- Al terminar la petición la restablece, también si hubo una excepción: nunca se arrastra
  a la siguiente petición del mismo hilo.
"""

from agroia_comun.eventos import correlacion
from agroia_comun.eventos.sobre import ENCABEZADO_CORRELACION


class CorrelacionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        valor, token = correlacion.establecer(request.headers.get(ENCABEZADO_CORRELACION))
        request.correlacion_id = valor
        try:
            respuesta = self.get_response(request)
        finally:
            correlacion.restablecer(token)
        respuesta[ENCABEZADO_CORRELACION] = valor
        return respuesta
