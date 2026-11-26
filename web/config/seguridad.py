"""Encabezados y reglas de seguridad del gateway.

- PoliticaDeContenidoMiddleware: Content-Security-Policy y Permissions-Policy (el
  micrófono solo para este sitio) en todas las respuestas. Sin
  scripts ni estilos en línea y sin eval: HTMX y Alpine (versión CSP) se sirven desde
  static/vendor/ y la lógica vive en static/js/. /api/docs/ usa una política aparte
  porque Swagger UI carga su código de un CDN.
- OrigenPermitidoMiddleware: una petición a /api/ con un encabezado Origin que no es el
  del propio gateway ni está en CORS_ALLOWED_ORIGINS recibe 403 `origen_no_permitido`.
  Sin Origin (Postman, curl, una app) pasa: el control de acceso del proxy es el token.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agroia_comun.seguridad import registrar_evento

RUTA_DOCS = "/api/docs/"


class PoliticaDeContenidoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        respuesta = self.get_response(request)
        politica = settings.CSP_DOCS if request.path.startswith(RUTA_DOCS) else settings.CSP
        respuesta.headers.setdefault("Content-Security-Policy", politica)
        respuesta.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        return respuesta


def es_ruta_de_api(ruta: str) -> bool:
    return ruta.startswith("/api/") and not ruta.startswith(("/api/docs/", "/api/schema/"))


class OrigenPermitidoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        origen = request.headers.get("Origin")
        if origen and es_ruta_de_api(request.path) and not self.permitido(request, origen):
            registrar_evento("origen_no_permitido", request, origen=origen[:200])
            return JsonResponse(
                {
                    "error": "origen_no_permitido",
                    "detalle": "Este sitio no tiene permiso para usar la API de AgroIA.",
                },
                status=403,
            )
        return self.get_response(request)

    @staticmethod
    def permitido(request: HttpRequest, origen: str) -> bool:
        propio = f"{request.scheme}://{request.get_host()}"
        return origen == propio or origen in settings.CORS_ALLOWED_ORIGINS
