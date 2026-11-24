"""Pantallas del chat con AgroIA. El flujo (asíncrono, por eventos) está en servicios.py."""

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


def _pantalla(request, conversacion=None, formulario=None, status=200):
    try:
        lista = servicios.conversaciones(request)
    except ErrorApi as error:
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    mensajes = (conversacion or {}).get("mensajes", [])
    datos_solicitud = (conversacion or {}).get("solicitud")
    contexto = {
        "conversaciones": lista,
        "conversacion": conversacion,
        "mensajes": mensajes,
        "formulario": formulario or Pregunta(),
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
    return render(request, "agroia/chat.html", contexto, status=status)


def _error_parcial(request, conversacion_id: str, mensaje: str) -> HttpResponse:
    if request.htmx:
        respuesta = render(request, TURNO, {"error": mensaje, "conversacion_id": conversacion_id})
        respuesta[CONSERVAR] = "1"
        return respuesta
    messages.error(request, mensaje)
    return redirect("agroia:ver", conversacion_id=conversacion_id)


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
        if error.codigo == "conversacion_llena" and request.htmx:
            return render(request, TURNO, {"llena": True, "conversacion_id": conversacion_id})
        # 429 (muchas preguntas seguidas) o 409: no se guardó nada, la conversación y su
        # polling siguen igual, y el texto escrito se conserva.
        return _error_parcial(request, conversacion_id, servicios.mensaje_de_error(error))
    if not request.htmx:
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    contexto = {"pregunta": pregunta, **_contexto_de_solicitud(conversacion_id, datos)}
    return render(request, TURNO, contexto)


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
            return render(request, TURNO, {"error": "No encontramos esta pregunta."})
        # El servicio no responde: se sigue consultando, un poco más despacio.
        datos = {"estado": "pendiente"}
    contexto = _contexto_de_solicitud(conversacion_id, datos)
    if datos.get("estado") == "listo":
        return render(
            request,
            "componentes/mensaje_chat.html",
            {"rol": "agente", "texto": datos.get("respuesta", ""), "fuentes": datos.get("fuentes")},
        )
    if datos.get("estado") == "fallido":
        return render(request, FALLIDA, contexto)
    return render(request, ESPERA, contexto)


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
