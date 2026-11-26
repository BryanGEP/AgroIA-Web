"""Páginas públicas: inicio, aviso de privacidad y páginas de error."""

from clientes import tienda
from clientes.tienda import TiendaNoDisponible
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

DESTACADOS = 8


@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    """Si svc-tienda no responde, la página se muestra igual sin categorías ni productos."""
    cliente = tienda.obtener_cliente()
    try:
        categorias = cliente.categorias()
        productos = cliente.productos({"disponible": "true"})["results"][:DESTACADOS]
        tienda_disponible = True
    except TiendaNoDisponible:
        categorias, productos, tienda_disponible = [], [], False
    return render(
        request,
        "paginas/inicio.html",
        {
            "categorias": categorias,
            "productos": productos,
            "tienda_disponible": tienda_disponible,
        },
    )


@require_GET
def aviso_privacidad(request: HttpRequest) -> HttpResponse:
    return render(request, "paginas/aviso_privacidad.html")


def no_encontrado(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "404.html", status=404)


def error_servidor(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)
