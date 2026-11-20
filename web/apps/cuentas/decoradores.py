"""login_requerido y rol_requerido para las vistas del gateway (sección 11).

Leen la sesión del gateway, no el token: el rol de la sesión sale del último access que
emitió svc-usuarios. Cada servicio vuelve a revisar el rol con el token.
"""

from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def redirigir(request: HttpRequest, destino: str) -> HttpResponse:
    """Redirección que también funciona en peticiones de HTMX (HX-Redirect)."""
    if getattr(request, "htmx", False):
        respuesta = HttpResponse(status=204)
        respuesta["HX-Redirect"] = destino
        return respuesta
    return redirect(destino)


def url_de_login(request: HttpRequest) -> str:
    return f"{reverse('cuentas:iniciar_sesion')}?{urlencode({'next': request.get_full_path()})}"


def login_requerido(vista):
    @wraps(vista)
    def envoltura(request: HttpRequest, *args, **kwargs):
        if not request.session.get("access"):
            messages.info(request, "Inicia sesión para continuar.")
            return redirigir(request, url_de_login(request))
        return vista(request, *args, **kwargs)

    return envoltura


def rol_requerido(rol: str):
    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(request: HttpRequest, *args, **kwargs):
            if (request.session.get("usuario") or {}).get("rol") != rol:
                messages.error(request, "No tienes permiso para entrar ahí.")
                return redirigir(request, reverse("paginas:inicio"))
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
