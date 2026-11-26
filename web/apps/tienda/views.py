"""Carrito, checkout y mis pedidos. Con HTMX devuelven fragmentos (y el contador del menú
fuera de banda); sin JavaScript, la página completa o una redirección."""

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.cuentas import servicios as cuentas
from apps.cuentas.decoradores import login_requerido
from apps.cuentas.forms import Direccion
from apps.cuentas.servicios import ErrorApi
from apps.tienda import servicios
from apps.tienda.servicios import METODOS_DE_PAGO

ERRORES_DE_PRODUCTO = {"stock_insuficiente", "producto_no_disponible"}


class Cantidad(forms.Form):
    cantidad = forms.IntegerField(min_value=1, max_value=999)


class Checkout(forms.Form):
    direccion = forms.TypedChoiceField(coerce=int, label="Dirección de envío", choices=[])
    metodo_pago = forms.ChoiceField(
        label="Método de pago", choices=METODOS_DE_PAGO, widget=forms.RadioSelect
    )

    def __init__(self, *args, direcciones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].choices = [
            (d["id"], d.get("alias") or d["calle"]) for d in direcciones
        ]
        predeterminada = next((d["id"] for d in direcciones if d.get("predeterminada")), None)
        self.fields["direccion"].initial = predeterminada


def _volver(request: HttpRequest, por_defecto: str) -> str:
    destino = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return por_defecto


# --- Agregar al carrito -------------------------------------------------------------------


@login_requerido
@require_POST
def agregar(request: HttpRequest, slug: str) -> HttpResponse:
    formulario = Cantidad(request.POST or {"cantidad": 1})
    cantidad = formulario.cleaned_data["cantidad"] if formulario.is_valid() else 1
    contexto = {"slug": slug}
    try:
        servicios.agregar(request, slug, cantidad)
    except ErrorApi as error:
        contexto["error"] = error.mensaje if error.codigo != "validacion" else error.detalle
        if not request.htmx:
            messages.error(request, contexto["error"])
    else:
        if not request.htmx:
            messages.success(request, "Lo agregamos a tu carrito.")
    if request.htmx:
        return render(request, "tienda/parciales/_agregado.html", contexto)
    return redirect(_volver(request, reverse("tienda:carrito")))


# --- Carrito ------------------------------------------------------------------------------


def _carrito(request: HttpRequest, datos: dict, errores: dict | None = None, status=200):
    contexto = {"carrito": datos, "errores": errores or {}}
    plantilla = "tienda/parciales/_carrito.html" if request.htmx else "tienda/carrito.html"
    return render(request, plantilla, contexto, status=status)


@login_requerido
@require_GET
def carrito(request: HttpRequest) -> HttpResponse:
    try:
        datos = servicios.carrito(request)
    except ErrorApi as error:
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    return _carrito(request, datos)


def _cambio_en_carrito(request: HttpRequest, item_id: int, accion) -> HttpResponse:
    errores = {}
    try:
        datos = accion()
    except ErrorApi as error:
        if error.codigo in ERRORES_DE_PRODUCTO or error.codigo == "validacion":
            errores[item_id] = error.detalle if error.codigo != "validacion" else error.mensaje
        else:
            messages.error(request, error.mensaje)
        datos = servicios.carrito(request)
    if not request.htmx:
        for mensaje in errores.values():
            messages.error(request, mensaje)
        return redirect("tienda:carrito")
    return _carrito(request, datos, errores)


@login_requerido
@require_POST
def cambiar(request: HttpRequest, item_id: int) -> HttpResponse:
    formulario = Cantidad(request.POST)
    if not formulario.is_valid():
        mensaje = "La cantidad debe ser de 1 a 999."
        if not request.htmx:
            messages.error(request, mensaje)
            return redirect("tienda:carrito")
        return _carrito(request, servicios.carrito(request), {item_id: mensaje})
    cantidad = formulario.cleaned_data["cantidad"]
    return _cambio_en_carrito(
        request, item_id, lambda: servicios.cambiar_cantidad(request, item_id, cantidad)
    )


@login_requerido
@require_POST
def quitar(request: HttpRequest, item_id: int) -> HttpResponse:
    return _cambio_en_carrito(request, item_id, lambda: servicios.quitar(request, item_id))


# --- Checkout -----------------------------------------------------------------------------


def _checkout(
    request, formulario=None, aviso_verificacion=False, formulario_direccion=None, status=200
):
    datos = servicios.carrito(request)
    direcciones = servicios.direcciones(request)
    contexto = {
        "carrito": datos,
        "direcciones": direcciones,
        "formulario": formulario or Checkout(direcciones=direcciones),
        "formulario_direccion": formulario_direccion or Direccion(),
        "aviso_verificacion": aviso_verificacion,
    }
    return render(request, "tienda/checkout.html", contexto, status=status)


@login_requerido
@require_http_methods(["GET", "POST"])
def checkout(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        try:
            datos = servicios.carrito(request)
        except ErrorApi as error:
            return render(
                request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503
            )
        if not datos.get("items"):
            messages.info(request, "Tu carrito está vacío. Agrega productos del catálogo.")
            return redirect("tienda:carrito")
        return _checkout(request)

    formulario = Checkout(request.POST, direcciones=servicios.direcciones(request))
    if not formulario.is_valid():
        return _checkout(request, formulario, status=400)
    try:
        pedido = servicios.crear_pedido(
            request, formulario.cleaned_data["direccion"], formulario.cleaned_data["metodo_pago"]
        )
    except ErrorApi as error:
        if error.codigo == "email_no_verificado":
            # En lugar del error: el aviso con el botón para reenviar el enlace.
            # Responde 200: es una pantalla con la indicación, no una página de error.
            return _checkout(request, formulario, aviso_verificacion=True)
        if error.codigo == "carrito_vacio":
            messages.info(request, "Tu carrito está vacío.")
            return redirect("tienda:carrito")
        formulario.add_error(None, error.mensaje if error.codigo == "validacion" else error.detalle)
        return _checkout(request, formulario, status=error.estado)
    messages.success(request, f"Recibimos tu pedido #{pedido['id']}. Ya puedes pagarlo.")
    return redirect("tienda:pedido", pedido_id=pedido["id"])


@login_requerido
@require_POST
def checkout_direccion(request: HttpRequest) -> HttpResponse:
    """Agregar una dirección sin salir del checkout."""
    formulario = Direccion(request.POST)
    if formulario.is_valid():
        try:
            cuentas.crear_direccion(request, **{**formulario.cleaned_data, "predeterminada": True})
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            messages.success(request, "Agregamos la dirección y la elegimos para este pedido.")
            return redirect("tienda:checkout")
    return _checkout(request, formulario_direccion=formulario, status=400)


# --- Mis pedidos --------------------------------------------------------------------------


@login_requerido
@require_GET
def mis_pedidos(request: HttpRequest) -> HttpResponse:
    try:
        pagina = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        pagina = 1
    try:
        datos = servicios.pedidos(request, pagina)
    except ErrorApi as error:
        if error.estado == 404:
            return redirect("tienda:mis_pedidos")
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    return render(request, "tienda/mis_pedidos.html", {"pedidos": datos, "pagina": pagina})


@login_requerido
@require_GET
def pedido(request: HttpRequest, pedido_id: int) -> HttpResponse:
    try:
        datos = servicios.pedido(request, pedido_id)
    except ErrorApi as error:
        if error.estado == 404:
            return render(request, "404.html", status=404)
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    return render(request, "tienda/pedido.html", {"pedido": datos})


@login_requerido
@require_POST
def pagar(request: HttpRequest, pedido_id: int) -> HttpResponse:
    try:
        servicios.pagar(request, pedido_id)
    except ErrorApi as error:
        messages.error(request, error.detalle)
    else:
        messages.success(request, "Pago registrado. Es un pago simulado: no se cobró nada.")
    return redirect("tienda:pedido", pedido_id=pedido_id)
