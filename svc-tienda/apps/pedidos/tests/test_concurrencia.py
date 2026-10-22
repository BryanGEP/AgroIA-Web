"""Dos clientes compitiendo por la última pieza: select_for_update evita vender de más.

Usa transacciones reales de PostgreSQL (transaction=True) y dos hilos con su propia
conexión. En SQLite esta prueba no tendría sentido.
"""

import threading

import pytest
from django.db import connection

from agroia_comun.errores import ErrorDeNegocio
from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos import servicios
from apps.pedidos.models import Carrito, ItemCarrito, Pedido
from tests.datos import DIRECCION


@pytest.mark.django_db(transaction=True)
def test_dos_pedidos_compiten_por_el_ultimo_producto():
    producto = ProductoFactory(stock=1)
    usuarios = (20, 21)
    for usuario in usuarios:
        carrito = Carrito.objects.create(usuario_id=usuario)
        ItemCarrito.objects.create(carrito=carrito, producto=producto, cantidad=1)

    barrera = threading.Barrier(len(usuarios))
    resultados: list[str] = []

    def comprar(usuario: int) -> None:
        try:
            barrera.wait(timeout=10)
            servicios.crear_pedido_desde_carrito(usuario, DIRECCION, "tarjeta")
            resultados.append("ok")
        except ErrorDeNegocio as error:
            resultados.append(error.codigo)
        finally:
            connection.close()

    hilos = [threading.Thread(target=comprar, args=(u,)) for u in usuarios]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert sorted(resultados) == ["ok", "stock_insuficiente"]
    producto.refresh_from_db()
    assert producto.stock == 0
    assert Pedido.objects.count() == 1
