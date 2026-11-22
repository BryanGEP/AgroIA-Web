"""Eventos de svc-tienda: pedido_creado y un solo pedido_estado_cambiado por transición
(también el pago), al confirmar y sin dirección ni nombres; nada si la operación falla."""

import json
import uuid
from decimal import Decimal

import pytest

from agroia_comun.eventos.catalogo import STREAM_TIENDA
from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos.models import Carrito, ItemCarrito, Pedido
from apps.pedidos.tests.factories import ItemPedidoFactory, PedidoFactory
from tests.datos import ADMIN_ID, CLIENTE_ID

pytestmark = pytest.mark.django_db

PEDIDOS = "/api/v1/pedidos/"


def publicados(redis) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis.xrange(STREAM_TIENDA)]


@pytest.fixture
def capturar(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


def carrito_con(*lineas):
    carrito = Carrito.objects.create(usuario_id=CLIENTE_ID)
    for producto, cantidad in lineas:
        ItemCarrito.objects.create(carrito=carrito, producto=producto, cantidad=cantidad)


def test_crear_pedido_publica_pedido_creado(cliente, direccion, redis_de_eventos, capturar):
    carrito_con(
        (ProductoFactory(nombre="Malla", precio=Decimal("300.00"), stock=5), 2),
        (ProductoFactory(nombre="Guantes", precio=Decimal("85.00"), stock=9), 3),
    )
    correlacion = str(uuid.uuid4())

    with capturar():
        respuesta = cliente.post(
            PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "transferencia"},
            format="json", HTTP_X_CORRELACION_ID=correlacion,
        )  # fmt: skip

    assert respuesta.status_code == 201
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "pedido_creado"
    assert sobre["origen"] == "svc-tienda"
    assert sobre["correlacion_id"] == correlacion
    assert sobre["datos"] == {
        "pedido_id": respuesta.json()["id"],
        "usuario_id": str(CLIENTE_ID),
        "total": "1005.00",  # 855 de productos + 150 de envío
        "productos": 2,
        "unidades": 5,
        "metodo_pago": "transferencia",
    }
    texto = json.dumps(sobre)
    assert direccion["calle"] not in texto and "Malla" not in texto


def test_sin_stock_no_crea_el_pedido_ni_publica(cliente, direccion, redis_de_eventos, capturar):
    carrito_con((ProductoFactory(stock=1), 3))

    with capturar():
        respuesta = cliente.post(
            PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "tarjeta"}, format="json"
        )

    assert respuesta.status_code == 409
    assert publicados(redis_de_eventos) == []
    assert not Pedido.objects.exists()


def test_pagar_publica_un_solo_evento(cliente, redis_de_eventos, capturar):
    pedido = ItemPedidoFactory(pedido__usuario_id=CLIENTE_ID).pedido

    with capturar():
        respuesta = cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/")

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "pedido_estado_cambiado"
    assert sobre["datos"] == {
        "pedido_id": pedido.pk,
        "usuario_id": str(CLIENTE_ID),
        "estado_anterior": "pendiente",
        "estado_nuevo": "pagado",
        "total": str(pedido.total),
        "cambiado_por": str(CLIENTE_ID),
    }


@pytest.mark.parametrize(
    "desde, hacia",
    [("pendiente", "cancelado"), ("pagado", "enviado"), ("enviado", "entregado"),
     ("pagado", "cancelado")],
)  # fmt: skip
def test_cada_transicion_del_admin_publica_un_evento(
    admin, redis_de_eventos, capturar, desde, hacia
):
    pedido = ItemPedidoFactory(pedido__usuario_id=CLIENTE_ID, pedido__estado=desde).pedido

    with capturar():
        respuesta = admin.patch(f"{PEDIDOS}{pedido.pk}/estado/", {"estado": hacia}, format="json")

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["datos"]["estado_anterior"] == desde
    assert sobre["datos"]["estado_nuevo"] == hacia
    assert sobre["datos"]["cambiado_por"] == str(ADMIN_ID)
    assert sobre["datos"]["usuario_id"] == str(CLIENTE_ID)


def test_una_transicion_invalida_no_publica(admin, redis_de_eventos, capturar):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)

    with capturar():
        respuesta = admin.patch(
            f"{PEDIDOS}{pedido.pk}/estado/", {"estado": "entregado"}, format="json"
        )

    assert respuesta.status_code == 409
    assert publicados(redis_de_eventos) == []


def test_pagar_dos_veces_publica_una_sola_vez(cliente, redis_de_eventos, capturar):
    pedido = ItemPedidoFactory(pedido__usuario_id=CLIENTE_ID).pedido

    with capturar():
        assert cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/").status_code == 200
    with capturar():
        assert cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/").status_code == 409

    assert len(publicados(redis_de_eventos)) == 1
