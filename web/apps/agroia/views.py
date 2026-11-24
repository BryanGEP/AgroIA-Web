"""Pantallas del chat con AgroIA y del widget flotante. El flujo (asíncrono, por eventos)
está en servicios.py.

La página /agroia/ y el widget comparten los parciales (`_conversacion`, `_turno`,
`_espera`, `_fallida`, `_reintentar`, `mensaje_chat`) y las vistas de la solicitud
(`solicitud`, `reintentar`): el widget solo agrega cómo elige su conversación.
"""

import contextlib

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.agroia import servicios
from apps.cuentas.decoradores import login_requerido, redirigir
from apps.cuentas.servicios import ErrorApi

ESPERA = "agroia/parciales/_espera.html"
HEREDADA = "agroia/parciales/_reintentar.html"
# La pregunta no entró: el componente `chat` (static/js) no vacía el campo de texto.
CONSERVAR = "X-Conservar-Pregunta"
FALLIDA = "agroia/parciales/_fallida.html"
TURNO = "agroia/parciales/_turno.html"
PANEL = "agroia/parciales/_widget_panel.html"
# Evento de HTMX al llegar la respuesta (o la fallida): el widget pone el punto de
# «respuesta nueva» y suena el aviso si el sonido está activo.
RESPUESTA_LISTA = "agroia-respuesta"


class Pregunta(forms.Form):
    pregunta = forms.CharField(
        label="Tu pregunta",
        max_length=4000,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": 2,
                "placeholder": "Por ejemplo: ¿cómo distingo la roña de la antracnosis?",
            }
        ),
    )


def _contexto_de_solicitud(conversacion_id: str, datos: dict | None) -> dict:
    datos = datos or {}
    return {
        "conversacion_id": conversacion_id,
        "solicitud": datos,
        "intervalo": servicios.intervalo(datos),
        "mensaje_de_fallo": servicios.mensaje_de_fallo(datos.get("codigo")),
        "se_puede_reintentar": datos.get("codigo") in servicios.SE_PUEDE_REINTENTAR,
    }


def _contexto_de_conversacion(conversacion: dict | None) -> dict:
    """Lo que necesita `_conversacion.html`: los mensajes y el estado de la solicitud.
    Lo usan la página y el widget."""
    mensajes = (conversacion or {}).get("mensajes", [])
    datos_solicitud = (conversacion or {}).get("solicitud")
    contexto = {
        "conversacion": conversacion,
        "mensajes": mensajes,
        "sin_respuesta_heredada": servicios.sin_respuesta_heredada(mensajes, datos_solicitud),
        # La última pregunta se quedó sin respuesta porque la solicitud falló.
        "mostrar_fallida": bool(
            (datos_solicitud or {}).get("estado") == "fallido"
            and mensajes
            and mensajes[-1].get("rol") == "usuario"
        ),
    }
    if conversacion:
        contexto.update(_contexto_de_solicitud(conversacion["id"], datos_solicitud))
    return contexto


def _pantalla(request, conversacion=None, formulario=None, status=200):
    try:
        lista = servicios.conversaciones(request)
    except ErrorApi as error:
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    contexto = {
        "conversaciones": lista,
        "formulario": formulario or Pregunta(),
        **_contexto_de_conversacion(conversacion),
    }
    return render(request, "agroia/chat.html", contexto, status=status)


def _error_parcial(request, conversacion_id: str | None, mensaje: str) -> HttpResponse:
    if request.htmx:
        respuesta = render(request, TURNO, {"error": mensaje, "conversacion_id": conversacion_id})
        respuesta[CONSERVAR] = "1"
        return respuesta
    messages.error(request, mensaje)
    if conversacion_id:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    return redirect("agroia:inicio")


def _respuesta_a_pregunta(request, conversacion_id: str, pregunta: str, datos: dict, **extra):
    """La pregunta entró: su burbuja y la espera (o la fallida, si no se pudo enviar). La
    comparten la página y el widget."""
    contexto = {"pregunta": pregunta, **_contexto_de_solicitud(conversacion_id, datos), **extra}
    return render(request, TURNO, contexto)


def _respuesta_a_error(request, conversacion_id: str | None, error: ErrorApi, **extra):
    """La pregunta no entró. `conversacion_llena` ofrece empezar otra; el 429 (muchas
    preguntas seguidas) o el 409 no guardaron nada: la conversación y su polling siguen
    igual, y el texto escrito se conserva."""
    if error.codigo == "conversacion_llena" and request.htmx:
        return render(request, TURNO, {"llena": True, "conversacion_id": conversacion_id, **extra})
    return _error_parcial(request, conversacion_id, servicios.mensaje_de_error(error))


@login_requerido
@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    return _pantalla(request)


@login_requerido
@require_GET
def ver(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    try:
        conversacion = servicios.conversacion(request, conversacion_id)
    except ErrorApi as error:
        if error.estado == 404:
            return render(request, "404.html", status=404)
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    return _pantalla(request, conversacion)


@login_requerido
@require_POST
def nueva(request: HttpRequest) -> HttpResponse:
    """Crea una conversación con la primera pregunta como título y la pregunta."""
    formulario = Pregunta(request.POST)
    if not formulario.is_valid():
        return _pantalla(request, formulario=formulario, status=400)
    pregunta = formulario.cleaned_data["pregunta"]
    try:
        conversacion = servicios.crear(request, pregunta[:80])
    except ErrorApi as error:
        messages.error(request, error.mensaje)
        return redirigir(request, reverse("agroia:inicio"))
    try:
        servicios.preguntar(request, conversacion["id"], pregunta)
    except ErrorApi as error:
        # Sin la pregunta la conversación quedaría vacía: se borra.
        with contextlib.suppress(ErrorApi):
            servicios.borrar(request, conversacion["id"])
        messages.error(request, servicios.mensaje_de_error(error))
        return redirigir(request, reverse("agroia:inicio"))
    # La página de la conversación muestra «AgroIA está escribiendo…» y consulta el estado.
    return redirigir(request, reverse("agroia:ver", args=[conversacion["id"]]))


@login_requerido
@require_POST
def preguntar(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    formulario = Pregunta(request.POST)
    if not formulario.is_valid():
        return _error_parcial(request, conversacion_id, "Escribe una pregunta.")
    pregunta = formulario.cleaned_data["pregunta"]
    try:
        datos = servicios.preguntar(request, conversacion_id, pregunta)
    except ErrorApi as error:
        return _respuesta_a_error(request, conversacion_id, error)
    if not request.htmx:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    return _respuesta_a_pregunta(request, conversacion_id, pregunta, datos)


@login_requerido
@require_POST
def reintentar(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    """Pide otra respuesta a la última pregunta, sin repetirla en la conversación."""
    try:
        datos = servicios.reintentar(request, conversacion_id)
    except ErrorApi as error:
        if request.htmx:
            return _reintentar_otra_vez(request, conversacion_id, error)
        return _error_parcial(request, conversacion_id, servicios.mensaje_de_error(error))
    servicios.marcar_pendiente(request, conversacion_id, datos.get("estado") == "pendiente")
    if not request.htmx:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    plantilla = ESPERA if datos.get("estado") == "pendiente" else FALLIDA
    return render(request, plantilla, _contexto_de_solicitud(conversacion_id, datos))


def _reintentar_otra_vez(request, conversacion_id: str, error: ErrorApi) -> HttpResponse:
    """Reintentar no entró (por ejemplo, 429): se vuelve a mostrar el mismo aviso con su
    botón, más el motivo, para poder reintentar después sin recargar."""
    try:
        datos = servicios.solicitud(request, conversacion_id)
    except ErrorApi:
        datos = {}
    contexto = {
        **_contexto_de_solicitud(conversacion_id, datos),
        "aviso": servicios.mensaje_de_error(error),
    }
    if datos.get("estado") == "fallido":
        return render(request, FALLIDA, contexto)
    if datos.get("estado") == "pendiente":
        return render(request, ESPERA, contexto)
    return render(request, HEREDADA, contexto)


@login_requerido
@require_GET
def solicitud(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    """Lo que consulta el polling: sigue esperando, la respuesta o la fallida. Al llegar a
    `listo` o `fallido` la respuesta ya no trae `hx-trigger` y el polling se detiene."""
    if not request.htmx:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    try:
        datos = servicios.solicitud(request, conversacion_id)
    except ErrorApi as error:
        if error.estado == 404:
            servicios.marcar_pendiente(request, conversacion_id, False)
            return render(request, TURNO, {"error": "No encontramos esta pregunta."})
        # El servicio no responde: se sigue consultando, un poco más despacio.
        datos = {"estado": "pendiente"}
    contexto = _contexto_de_solicitud(conversacion_id, datos)
    if datos.get("estado") == "pendiente":
        return render(request, ESPERA, contexto)
    servicios.marcar_pendiente(request, conversacion_id, False)
    if datos.get("estado") == "listo":
        respuesta = render(
            request,
            "componentes/mensaje_chat.html",
            {"rol": "agente", "texto": datos.get("respuesta", ""), "fuentes": datos.get("fuentes")},
        )
    else:
        respuesta = render(request, FALLIDA, contexto)
    respuesta["HX-Trigger"] = RESPUESTA_LISTA
    return respuesta


@login_requerido
@require_POST
def borrar(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    try:
        servicios.borrar(request, conversacion_id)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, "Borramos la conversación.")
    return redirigir(request, reverse("agroia:inicio"))


# --- Widget flotante -------------------------------------------------------------------------


def _panel(request, **extra) -> HttpResponse:
    """El contenido del panel. Al visitante: el saludo y la invitación a entrar, sin
    llamar a ningún servicio. Al usuario: su conversación del widget, o el saludo con las
    preguntas sugeridas si todavía no tiene."""
    ruta = servicios.ruta_actual(request)
    contexto = {
        "sugerencias": servicios.sugerencias(
            ruta.split("?")[0], request.GET.get("producto") or request.POST.get("producto")
        ),
        "siguiente": ruta,
        **extra,
    }
    if not request.session.get("access"):
        return render(request, PANEL, contexto)
    conversacion = None
    conversacion_id = servicios.conversacion_del_widget(request)
    if conversacion_id:
        try:
            conversacion = servicios.conversacion(request, conversacion_id)
        except ErrorApi as error:
            if error.estado != 404:
                contexto["no_disponible"] = error.mensaje
            else:
                servicios.olvidar_widget(request)  # la borró en /agroia/: empieza otra
    contexto.update(_contexto_de_conversacion(conversacion))
    if conversacion:
        pendiente = (conversacion.get("solicitud") or {}).get("estado") == "pendiente"
        servicios.marcar_pendiente(request, conversacion["id"], pendiente)
    return render(request, PANEL, contexto)


@require_GET
def widget(request: HttpRequest) -> HttpResponse:
    """Se pide con HTMX la primera vez que se abre el widget en una página (o al cargarla,
    si estaba abierto o hay una pregunta pendiente). No pide sesión: el visitante también
    ve el saludo."""
    if not request.htmx:
        return redirect("agroia:inicio")
    return _panel(request)


@login_requerido
@require_POST
def widget_preguntar(request: HttpRequest) -> HttpResponse:
    """Pregunta en la conversación del widget; la crea con el primer mensaje. Si ya no
    existe (se borró en /agroia/), empieza otra."""
    formulario = Pregunta(request.POST)
    if not formulario.is_valid():
        return _error_parcial(request, None, "Escribe una pregunta.")
    pregunta = formulario.cleaned_data["pregunta"]
    extra = {"en_widget": True}
    conversacion_id = servicios.conversacion_del_widget(request)
    nueva = False
    for _ in range(2):  # el segundo intento solo si la conversación guardada ya no existe
        if not conversacion_id:
            try:
                conversacion_id = servicios.crear(request, pregunta[:80])["id"]
            except ErrorApi as error:
                return _error_parcial(request, None, error.mensaje)
            nueva = True
            servicios.usar_en_widget(request, conversacion_id)
        try:
            datos = servicios.preguntar(request, conversacion_id, pregunta)
        except ErrorApi as error:
            if error.estado == 404 and not nueva:
                servicios.olvidar_widget(request)
                conversacion_id = None
                continue
            if nueva:
                # Sin la pregunta la conversación quedaría vacía: se borra y se olvida.
                with contextlib.suppress(ErrorApi):
                    servicios.borrar(request, conversacion_id)
                servicios.olvidar_widget(request)
                conversacion_id = None
            return _respuesta_a_error(request, conversacion_id, error, **extra)
        break
    servicios.marcar_pendiente(request, conversacion_id, datos.get("estado") == "pendiente")
    if not request.htmx:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    # Las sugerencias solo están mientras no hay conversación: se quitan con la primera.
    return _respuesta_a_pregunta(
        request, conversacion_id, pregunta, datos, quitar_sugerencias=nueva, **extra
    )


@login_requerido
@require_POST
def widget_reiniciar(request: HttpRequest) -> HttpResponse:
    """Empieza una conversación nueva en el widget. La anterior no se borra: sigue en
    /agroia/."""
    servicios.olvidar_widget(request)
    if not request.htmx:
        return redirect("agroia:inicio")
    return _panel(request, reiniciado=True)
