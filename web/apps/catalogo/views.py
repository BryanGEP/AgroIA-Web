"""Catálogo público: listado con filtros (HTMX y sin JavaScript), detalle e imágenes."""

import math
import re
from urllib.parse import urlencode

from clientes import tienda
from clientes.tienda import NoEncontrado, TiendaNoDisponible
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET

from apps.catalogo.forms import FiltrosCatalogo

POR_PAGINA = 20  # el tamaño de página de svc-tienda
RUTA_IMAGEN = re.compile(r"^productos/[\w\-./]+$")


def pagina_no_disponible(request: HttpRequest) -> HttpResponse:
    return render(request, "errores/no_disponible.html", status=503)


def _numero_de_pagina(request: HttpRequest) -> int:
    try:
        return max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        return 1


def _es_parcial(request: HttpRequest) -> bool:
    """Fragmento si es HTMX, salvo cuando HTMX reconstruye el historial (pide la página)."""
    return bool(request.htmx) and not request.htmx.history_restore_request


@require_GET
def lista(request: HttpRequest) -> HttpResponse:
    # Sin JavaScript el formulario envía también los campos vacíos; se quitan para que la
    # URL quede limpia y se pueda compartir (con HTMX se quitan antes de enviar).
    if not request.htmx and any(valor == "" for valor in request.GET.values()):
        limpios = [(k, v) for k, v in request.GET.items() if v != ""]
        return redirect(f"{request.path}?{urlencode(limpios)}" if limpios else request.path)

    cliente = tienda.obtener_cliente()
    try:
        categorias = cliente.categorias()
    except TiendaNoDisponible:
        return pagina_no_disponible(request)

    filtros = FiltrosCatalogo(request.GET or None, categorias=categorias)
    filtros.is_valid()
    pagina = _numero_de_pagina(request)
    try:
        datos = cliente.productos({**filtros.parametros(), "page": pagina})
        pagina_fuera = False
    except NoEncontrado:
        datos, pagina_fuera = {"count": 0, "results": []}, True
    except TiendaNoDisponible:
        return pagina_no_disponible(request)

    total_paginas = max(math.ceil(datos["count"] / POR_PAGINA), 1)
    contexto = {
        "filtros": filtros,
        "categorias": categorias,
        "productos": datos["results"],
        "total": datos["count"],
        "pagina": pagina,
        "total_paginas": total_paginas,
        "paginas": range(1, total_paginas + 1),
        "pagina_fuera": pagina_fuera,
    }
    plantilla = (
        "catalogo/parciales/_resultados.html" if _es_parcial(request) else "catalogo/lista.html"
    )
    respuesta = render(request, plantilla, contexto)
    # La misma URL devuelve página completa o fragmento: que el navegador no los confunda.
    patch_vary_headers(respuesta, ["HX-Request"])
    return respuesta


@require_GET
def detalle(request: HttpRequest, slug: str) -> HttpResponse:
    cliente = tienda.obtener_cliente()
    try:
        producto = cliente.producto(slug)
    except NoEncontrado:
        return render(request, "404.html", {"recurso": "producto"}, status=404)
    except TiendaNoDisponible:
        return pagina_no_disponible(request)
    try:
        categorias = cliente.categorias()
    except TiendaNoDisponible:
        categorias = []
    return render(
        request, "catalogo/detalle.html", {"producto": producto, "categorias": categorias}
    )


@require_GET
def imagen(request: HttpRequest, ruta: str) -> HttpResponse:
    """Reenvía una imagen de producto de svc-tienda sin exponer el servicio hacia afuera."""
    if not RUTA_IMAGEN.match(ruta) or ".." in ruta:
        raise Http404
    try:
        archivo = tienda.obtener_cliente().imagen(ruta)
    except NoEncontrado as error:
        raise Http404 from error
    except TiendaNoDisponible:
        return HttpResponse(status=502)
    if not archivo.tipo.startswith("image/"):
        raise Http404
    respuesta = HttpResponse(archivo.contenido, content_type=archivo.tipo)
    respuesta["Cache-Control"] = "public, max-age=3600"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta
