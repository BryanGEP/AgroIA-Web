"""Panel de administración: resumen, pedidos, productos, categorías, usuarios, bitácora y
estado de los eventos.

Todas las vistas llevan @rol_requerido("administrador"): sin sesión van al login y un
cliente que entre por URL vuelve al inicio con «No tienes permiso». Cada servicio vuelve a
revisar el rol con el token (401 sin token, 403 con otro rol).
"""

import json
from datetime import date, timedelta

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.cuentas.decoradores import rol_requerido
from apps.cuentas.servicios import ErrorApi
from apps.panel import servicios
from apps.panel.bitacora import TIPOS
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


def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _error_de_filtros(error: ErrorApi) -> str:
    if error.campos:
        return "Revisa los filtros: " + "; ".join(
            f"{campo}: {' '.join(mensajes)}" for campo, mensajes in error.campos.items()
        )
    return error.mensaje


# --- Resumen ------------------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    """Cada servicio llena sus tarjetas: si uno no responde, solo esas muestran el error."""
    hoy = timezone.localdate()
    contexto = {"umbral": servicios.umbral_stock_bajo(), "hoy": hoy, "semana": hoy - timedelta(6)}
    try:
        tienda = servicios.resumen_tienda(request)
    except ErrorApi as error:
        contexto["error_tienda"] = error.mensaje
    else:
        respaldo = tienda["ventas"].get("respaldo") or {}
        tienda["ventas"]["respaldo"]["primer_pagado_en"] = _fecha(respaldo.get("primer_pagado_en"))
        contexto["tienda"] = tienda
        contexto["nombres"] = servicios.nombres_de_usuarios(
            request, [p["usuario_id"] for p in tienda["ultimos_pedidos"]]
        )
    try:
        contexto["nuevos"] = servicios.usuarios_nuevos(request, contexto["semana"])
    except ErrorApi as error:
        contexto["error_usuarios"] = error.mensaje
    return render(request, "panel/inicio.html", contexto)


# --- Productos ----------------------------------------------------------------------------

ORDENES_DE_PRODUCTOS = {
    "": "Más recientes",
    "nombre": "Nombre (A-Z)",
    "stock": "Menos existencias",
    "-stock": "Más existencias",
    "precio": "Precio más bajo",
    "-precio": "Precio más alto",
}


@rol_requerido(ADMIN)
@require_GET
def productos(request: HttpRequest) -> HttpResponse:
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "categoria": request.GET.get("categoria", ""),
        "activo": request.GET.get("activo", ""),
        "stock": request.GET.get("stock", ""),
        "ordering": request.GET.get("ordering", ""),
        "page": _pagina(request),
    }
    if filtros["ordering"] not in ORDENES_DE_PRODUCTOS:
        filtros["ordering"] = ""
    consulta = {k: v for k, v in filtros.items() if k != "stock"}
    if filtros["stock"] == "bajo":
        consulta["stock_max"] = servicios.umbral_stock_bajo()
    elif filtros["stock"] == "agotado":
        consulta["disponible"] = "false"
    else:
        filtros["stock"] = ""
    try:
        datos = servicios.productos(request, consulta)
        categorias = servicios.categorias(request)
    except ErrorApi as error:
        if error.estado in (400, 404):
            return redirect("panel:productos")
        return _no_disponible(request, error)
    contexto = {
        "productos": datos,
        "categorias": categorias,
        "filtros": filtros,
        "umbral": servicios.umbral_stock_bajo(),
        "ordenes": ORDENES_DE_PRODUCTOS,
    }
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
    numero = request.GET.get("id", "").strip().lstrip("#")
    filtros = {
        "estado": request.GET.get("estado", ""),
        "id": numero if numero.isdigit() else "",
        "desde": request.GET.get("desde", ""),
        "hasta": request.GET.get("hasta", ""),
        "page": _pagina(request),
    }
    contexto = {"filtros": filtros, "estados": ESTADOS, "numero": numero}
    if numero and not numero.isdigit():
        contexto["error_filtros"] = "El número de pedido son solo dígitos, por ejemplo 94."
        datos = {"results": [], "count": 0}
    else:
        try:
            datos = servicios.pedidos(request, filtros)
        except ErrorApi as error:
            if error.estado == 404:
                return redirect("panel:pedidos")
            if error.estado != 400:
                return _no_disponible(request, error)
            contexto["error_filtros"] = _error_de_filtros(error)
            datos = {"results": [], "count": 0}
    contexto["pedidos"] = datos
    contexto["nombres"] = servicios.nombres_de_usuarios(
        request, [p.get("usuario_id") for p in datos.get("results", [])]
    )
    return render(request, "panel/pedidos.html", contexto)


@rol_requerido(ADMIN)
@require_GET
def pedido(request: HttpRequest, pedido_id: int) -> HttpResponse:
    try:
        datos = servicios.pedido(request, pedido_id)
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return _no_disponible(request, error)
    contexto = {"pedido": datos, "estados": dict(ESTADOS)}
    try:
        cliente_id = datos.get("usuario_id")
        contexto["cliente"] = servicios.usuario(request, cliente_id) if cliente_id else None
    except ErrorApi:
        contexto["cliente"] = None
    try:
        contexto["linea"] = servicios.linea_de_tiempo(request, pedido_id)
    except ErrorApi as error:
        contexto["error_linea"] = error.mensaje
    return render(request, "panel/pedido.html", contexto)


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
        "email_verificado": request.GET.get("email_verificado", ""),
        "page": _pagina(request),
    }
    if filtros["email_verificado"] not in ("true", "false"):
        filtros["email_verificado"] = ""
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
    destino = request.POST.get("volver", "")
    if destino == "detalle":
        return redirect("panel:usuario", usuario_id=usuario_id)
    return redirect("panel:usuarios")


@rol_requerido(ADMIN)
@require_GET
def usuario(request: HttpRequest, usuario_id) -> HttpResponse:
    try:
        datos = servicios.usuario(request, str(usuario_id))
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return _no_disponible(request, error)
    contexto = {"perfil": datos, "yo": request.session["usuario"]["id"]}
    try:
        contexto["pedidos"] = servicios.pedidos(request, {"usuario_id": str(usuario_id)})
    except ErrorApi as error:
        contexto["error_pedidos"] = error.mensaje
    return render(request, "panel/usuario.html", contexto)


# --- Bitácora y eventos -------------------------------------------------------------------


@rol_requerido(ADMIN)
@require_GET
def bitacora(request: HttpRequest) -> HttpResponse:
    filtros = {
        "tipo": request.GET.get("tipo", ""),
        "usuario_id": request.GET.get("usuario_id", "").strip(),
        "correlacion_id": request.GET.get("correlacion_id", "").strip(),
        "pedido_id": request.GET.get("pedido_id", "").strip(),
        "desde": request.GET.get("desde", ""),
        "hasta": request.GET.get("hasta", ""),
        "page": _pagina(request),
    }
    contexto = {"filtros": filtros, "tipos": TIPOS}
    try:
        datos = servicios.bitacora(request, filtros)
    except ErrorApi as error:
        if error.estado == 404:
            return redirect("panel:bitacora")
        if error.estado != 400:
            if request.htmx:
                contexto["error_servicio"] = error.mensaje
                return render(request, "panel/parciales/_bitacora.html", contexto)
            return _no_disponible(request, error)
        contexto["error_filtros"] = _error_de_filtros(error)
        datos = {"results": [], "count": 0}
    contexto["eventos"] = datos
    contexto["nombres"] = servicios.nombres_de_usuarios(
        request,
        [e.get("usuario_id") for e in datos.get("results", [])]
        + [(e.get("datos") or {}).get("cambiado_por") for e in datos.get("results", [])],
    )
    plantilla = "panel/parciales/_bitacora.html" if request.htmx else "panel/bitacora.html"
    return render(request, plantilla, contexto)


@rol_requerido(ADMIN)
@require_GET
def eventos(request: HttpRequest) -> HttpResponse:
    """Solo lectura. Con HTMX («Actualizar») devuelve solo el estado; sin polling."""
    contexto = {"actualizado": timezone.localtime()}
    try:
        contexto["estado"] = servicios.estado_eventos(request)
    except ErrorApi as error:
        contexto["error"] = error.mensaje
    plantilla = "panel/parciales/_eventos.html" if request.htmx else "panel/eventos.html"
    return render(request, plantilla, contexto)
