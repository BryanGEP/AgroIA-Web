"""Pantallas del chat con AgroIA. La orquestación está en servicios.py."""

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.agroia import servicios
from apps.cuentas.decoradores import login_requerido, redirigir
from apps.cuentas.servicios import ErrorApi


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


def _pantalla(request, conversacion=None, formulario=None, turno=None, status=200):
    try:
        lista = servicios.conversaciones(request)
    except ErrorApi as error:
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    mensajes = (conversacion or {}).get("mensajes", [])
    contexto = {
        "conversaciones": lista,
        "conversacion": conversacion,
        "mensajes": mensajes,
        "pendiente": servicios.pendiente(mensajes),
        "formulario": formulario or Pregunta(),
        "turno": turno,
    }
    return render(request, "agroia/chat.html", contexto, status=status)


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
        turno = servicios.preguntar(request, conversacion["id"], pregunta)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
        return redirigir(request, reverse("agroia:inicio"))
    if turno.sin_respuesta:
        messages.warning(request, servicios.SIN_RESPUESTA)
    elif not turno.guardada:
        messages.warning(request, "AgroIA respondió, pero no pudimos guardar la respuesta.")
    return redirigir(request, reverse("agroia:ver", args=[conversacion["id"]]))


def _resultado(request: HttpRequest, conversacion_id: str, turno) -> HttpResponse:
    if request.htmx:
        return render(
            request,
            "agroia/parciales/_turno.html",
            {"turno": turno, "conversacion_id": conversacion_id},
        )
    if turno is not None and turno.sin_respuesta:
        messages.warning(request, servicios.SIN_RESPUESTA)
    if turno is not None and turno.llena:
        messages.warning(
            request, "Esta conversación llegó a su límite de mensajes. Inicia una nueva."
        )
    return redirect("agroia:ver", conversacion_id=conversacion_id)


@login_requerido
@require_POST
def preguntar(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    formulario = Pregunta(request.POST)
    if not formulario.is_valid():
        if request.htmx:
            return render(
                request,
                "agroia/parciales/_turno.html",
                {"error": "Escribe una pregunta.", "conversacion_id": conversacion_id},
            )
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    try:
        turno = servicios.preguntar(request, conversacion_id, formulario.cleaned_data["pregunta"])
    except ErrorApi as error:
        if request.htmx:
            return render(
                request,
                "agroia/parciales/_turno.html",
                {"error": error.mensaje, "conversacion_id": conversacion_id},
            )
        messages.error(request, error.mensaje)
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    return _resultado(request, conversacion_id, turno)


@login_requerido
@require_POST
def reintentar(request: HttpRequest, conversacion_id: str) -> HttpResponse:
    try:
        turno = servicios.reintentar(request, conversacion_id)
    except ErrorApi as error:
        if request.htmx:
            return render(
                request,
                "agroia/parciales/_turno.html",
                {"error": error.mensaje, "conversacion_id": conversacion_id},
            )
        messages.error(request, error.mensaje)
        return redirect("agroia:ver", conversacion_id=conversacion_id)
    if turno is not None:
        turno.pregunta = ""  # ya está en pantalla; solo se agrega la respuesta
    return _resultado(request, conversacion_id, turno)


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
