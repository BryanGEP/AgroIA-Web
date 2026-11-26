"""Proxy de API /api/<servicio>/<ruta> para clientes que no son navegador (Postman, una app).

    /api/usuarios/<ruta>  -> svc-usuarios  /api/v1/<ruta>
    /api/tienda/<ruta>    -> svc-tienda    /api/v1/<ruta>
    /api/contenido/<ruta> -> svc-contenido /api/v1/<ruta>
    /api/ia/<ruta>        -> svc-ia        /<ruta>  (svc-ia no lleva /api/v1/)

**El proxy nunca toma el token de la sesión.** Solo acepta `Authorization: Bearer <access>`.
Una petición con una cookie de sesión válida y sin ese encabezado se trata como anónima.
Por eso no necesita CSRF (csrf_exempt): ningún sitio ajeno puede usar la sesión del
navegador a través de esta ruta.
"""

from clientes import api
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from agroia_comun.seguridad import registrar_evento
from agroia_comun.tokens import TokenInvalido, validar_access
from apps.proxy import servicios

ENCABEZADO_401 = {"WWW-Authenticate": 'Bearer realm="api"'}


def _error(estado: int, codigo: str, detalle: str, encabezados: dict | None = None) -> JsonResponse:
    respuesta = JsonResponse({"error": codigo, "detalle": detalle}, status=estado)
    for nombre, valor in (encabezados or {}).items():
        respuesta[nombre] = valor
    return respuesta


def _denegar(request: HttpRequest, codigo: str, detalle: str) -> JsonResponse:
    registrar_evento("acceso_denegado", request, estado=401, error=codigo, capa="gateway")
    return _error(401, codigo, detalle, ENCABEZADO_401)


@csrf_exempt
def reenviar(request: HttpRequest, servicio: str, ruta: str) -> HttpResponse:
    destinos = api.servicios()
    if servicio not in destinos or not servicios.ruta_segura(ruta):
        return _error(404, "no_encontrado", "No se encontró el recurso solicitado.")

    # Solo el encabezado Authorization; request.session nunca se lee aquí.
    autorizacion = request.headers.get("Authorization", "")
    if autorizacion:
        token = servicios.token_bearer(autorizacion)
        try:
            validar_access(token or "", settings.JWT_LLAVE_PUBLICA, settings.JWT_ISSUER)
        except TokenInvalido:
            return _denegar(request, "token_invalido", "El token no es válido o ya venció.")
    elif not servicios.es_publica(servicio, request.method, ruta):
        return _denegar(
            request, "no_autenticado", "No se enviaron las credenciales de autenticación."
        )

    consulta = request.META.get("QUERY_STRING", "")
    try:
        respuesta = api.ClienteServicios(destinos).enviar(
            servicio,
            request.method,
            ruta + (f"?{consulta}" if consulta else ""),
            ip=api.ip_del_navegador(request),
            encabezados=servicios.encabezados_de_entrada(request.headers),
            content=request.body,
        )
    except api.ServicioNoDisponible as error:
        if error.tiempo_agotado:
            return _error(504, "tiempo_agotado", "El servicio tardó demasiado en responder.")
        return _error(502, "servicio_no_disponible", "El servicio no está disponible.")

    salida = HttpResponse(respuesta.content, status=respuesta.status_code)
    for nombre, valor in servicios.encabezados_de_salida(respuesta).items():
        salida[nombre] = valor
    if "Location" in respuesta.headers:
        destino = destinos[servicio]
        location = servicios.location_externa(
            respuesta.headers["Location"], destino.url, servicio, destino.prefijo
        )
        if location:
            salida["Location"] = location
    return salida
