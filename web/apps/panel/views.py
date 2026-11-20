"""Panel de administración: productos, categorías, pedidos y usuarios.

Todas las vistas llevan @rol_requerido("administrador"): un cliente que entre por URL
vuelve al inicio con «No tienes permiso». Cada servicio vuelve a revisar el rol.
"""

import json

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.cuentas.decoradores import rol_requerido
from apps.cuentas.servicios import ErrorApi
from apps.panel import servicios
from apps.panel.forms import Categoria, Producto
from apps.panel.servicios import ESTADOS

ADMIN = "administrador"


def _pagina(request: HttpRequest) -> int:
    try:
        return max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        return 1


def _no_disponible(request, error: ErrorApi) -> HttpResponse:
    return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)


@rol_requerido(ADMIN)
def inicio(request: HttpRequest) -> HttpResponse:
    return redirect("panel:productos")


# --- Productos ----------------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def productos(request: HttpRequest) -> HttpResponse:
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "categoria": request.GET.get("categoria", ""),
        "activo": request.GET.get("activo", ""),
        "page": _pagina(request),
    }
    try:
        datos = servicios.productos(request, filtros)
        categorias = servicios.categorias(request)
    except ErrorApi as error:
        if error.estado in (400, 404):
            return redirect("panel:productos")
        return _no_disponible(request, error)
    contexto = {"productos": datos, "categorias": categorias, "filtros": filtros}
    plantilla = "panel/parciales/_productos.html" if request.htmx else "panel/productos.html"
    return render(request, plantilla, contexto)


@rol_requerido(ADMIN)
@require_http_methods(["GET", "POST"])
def producto(request: HttpRequest, slug: str | None = None) -> HttpResponse:
    try:
        categorias = servicios.categorias(request)
        actual = servicios.producto(request, slug) if slug else None
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return _no_disponible(request, error)

    if request.method == "POST":
        formulario = Producto(request.POST, request.FILES, categorias=categorias)
        if formulario.is_valid():
            try:
                guardado = servicios.guardar_producto(
                    request, slug, formulario.datos_para_api(), formulario.cleaned_data["imagen"]
                )
            except ErrorApi as error:
                formulario.agregar_errores_de_api(error)
            else:
                messages.success(request, f"Guardamos «{guardado['nombre']}».")
                return redirect("panel:productos")
        status = 400
    else:
        inicial = {}
        if actual:
            inicial = {
                c: actual.get(c)
                for c in (
                    "nombre",
                    "categoria",
                    "precio",
                    "stock",
                    "unidad",
                    "descripcion",
                    "activo",
                )
            }
            inicial["ficha_tecnica"] = json.dumps(
                actual.get("ficha_tecnica") or {}, ensure_ascii=False, indent=2
            )
        else:
            inicial = {"activo": True, "unidad": "pieza"}
        formulario = Producto(initial=inicial, categorias=categorias)
        status = 200
    return render(
        request,
        "panel/producto.html",
        {"formulario": formulario, "producto": actual},
        status=status,
    )


@rol_requerido(ADMIN)
@require_POST
def desactivar_producto(request: HttpRequest, slug: str) -> HttpResponse:
    try:
        servicios.desactivar_producto(request, slug)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, "Desactivamos el producto: ya no aparece en la tienda.")
    return redirect("panel:productos")


# --- Categorías ---------------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def categorias(request: HttpRequest) -> HttpResponse:
    try:
        lista = servicios.categorias(request)
    except ErrorApi as error:
        return _no_disponible(request, error)
    return render(request, "panel/categorias.html", {"categorias": lista})


@rol_requerido(ADMIN)
@require_http_methods(["GET", "POST"])
def categoria(request: HttpRequest, slug: str | None = None) -> HttpResponse:
    try:
        actual = servicios.categoria(request, slug) if slug else None
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return _no_disponible(request, error)
    if request.method == "POST":
        formulario = Categoria(request.POST)
        if formulario.is_valid():
            try:
                servicios.guardar_categoria(request, slug, formulario.cleaned_data)
            except ErrorApi as error:
                formulario.agregar_errores_de_api(error)
            else:
                messages.success(request, "Guardamos la categoría.")
                return redirect("panel:categorias")
        status = 400
    else:
        inicial = (
            {c: actual.get(c) for c in ("nombre", "descripcion", "activa")}
            if actual
            else {"activa": True}
        )
        formulario = Categoria(initial=inicial)
        status = 200
    return render(
        request,
        "panel/categoria.html",
        {"formulario": formulario, "categoria": actual},
        status=status,
    )


@rol_requerido(ADMIN)
@require_POST
def desactivar_categoria(request: HttpRequest, slug: str) -> HttpResponse:
    try:
        servicios.desactivar_categoria(request, slug)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, "Desactivamos la categoría.")
    return redirect("panel:categorias")


# --- Pedidos ------------------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def pedidos(request: HttpRequest) -> HttpResponse:
    filtros = {"estado": request.GET.get("estado", ""), "page": _pagina(request)}
    try:
        datos = servicios.pedidos(request, filtros)
    except ErrorApi as error:
        if error.estado in (400, 404):
            return redirect("panel:pedidos")
        return _no_disponible(request, error)
    return render(
        request, "panel/pedidos.html", {"pedidos": datos, "filtros": filtros, "estados": ESTADOS}
    )


@rol_requerido(ADMIN)
@require_GET
def pedido(request: HttpRequest, pedido_id: int) -> HttpResponse:
    try:
        datos = servicios.pedido(request, pedido_id)
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return _no_disponible(request, error)
    return render(request, "panel/pedido.html", {"pedido": datos, "estados": dict(ESTADOS)})


@rol_requerido(ADMIN)
@require_POST
def cambiar_estado(request: HttpRequest, pedido_id: int) -> HttpResponse:
    estado = request.POST.get("estado", "")
    try:
        datos = servicios.cambiar_estado(request, pedido_id, estado)
    except ErrorApi as error:
        mensaje = error.detalle if error.codigo == "transicion_invalida" else error.mensaje
        if request.htmx:
            datos = servicios.pedido(request, pedido_id)
            return render(
                request,
                "panel/parciales/_estado.html",
                {"pedido": datos, "estados": dict(ESTADOS), "error": mensaje},
            )
        messages.error(request, mensaje)
        return redirect("panel:pedido", pedido_id=pedido_id)
    if request.htmx:
        return render(
            request,
            "panel/parciales/_estado.html",
            {"pedido": datos, "estados": dict(ESTADOS), "aviso": "Estado actualizado."},
        )
    messages.success(request, "Estado actualizado.")
    return redirect("panel:pedido", pedido_id=pedido_id)


# --- Usuarios -----------------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def usuarios(request: HttpRequest) -> HttpResponse:
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "rol": request.GET.get("rol", ""),
        "page": _pagina(request),
    }
    try:
        datos = servicios.usuarios(request, filtros)
    except ErrorApi as error:
        if error.estado in (400, 404):
            return redirect("panel:usuarios")
        return _no_disponible(request, error)
    contexto = {"usuarios": datos, "filtros": filtros, "yo": request.session["usuario"]["id"]}
    return render(request, "panel/usuarios.html", contexto)


@rol_requerido(ADMIN)
@require_POST
def cambiar_rol(request: HttpRequest, usuario_id: str) -> HttpResponse:
    rol = request.POST.get("rol", "")
    try:
        servicios.cambiar_rol(request, usuario_id, rol)
    except ErrorApi as error:
        messages.error(
            request, error.detalle if error.codigo == "auto_degradacion" else error.mensaje
        )
    else:
        messages.success(
            request, "Cambiamos el rol. Se aplica en su siguiente inicio de sesión o renovación."
        )
    return redirect("panel:usuarios")
