"""Cuando la renovación del token falla (SesionExpirada), manda al login con ?next=."""

from clientes.api import SesionExpirada
from django.contrib import messages

from apps.cuentas.decoradores import redirigir, url_de_login


class SesionExpiradaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, SesionExpirada):
            return None
        # La sesión ya se vació en SesionApi.expirar().
        messages.warning(request, "Tu sesión expiró. Inicia sesión de nuevo.")
        return redirigir(request, url_de_login(request))
