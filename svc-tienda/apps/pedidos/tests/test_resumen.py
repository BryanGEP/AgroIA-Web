"""Resumen del panel (GET /api/v1/resumen/) y la fecha de pago (pagado_en)."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from agroia_comun.eventos.catalogo import STREAM_TIENDA
from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos import servicios
from apps.pedidos.models import Pedido
from apps.pedidos.tests.factories import ItemPedidoFactory, PedidoFactory
from tests.datos import CLIENTE_ID

pytestmark = pytest.mark.django_db

RESUMEN = "/api/v1/resumen/"
PEDIDOS = "/api/v1/pedidos/"
MEXICO = ZoneInfo("America/Mexico_City")
ADMIN = uuid.uuid4()


def en_mexico(*partes) -> datetime:
    return datetime(*partes, tzinfo=MEXICO)


def pedido_con_fechas(estado: str, total: str, creado_en: datetime, pagado_en=None) -> Pedido:
    pedido = PedidoFactory(estado=estado, total=Decimal(total))
    # creado_en es auto_now_add: se ajusta después de crear el pedido.
    Pedido.objects.filter(pk=pedido.pk).update(creado_en=creado_en, pagado_en=pagado_en)
    pedido.refresh_from_db()
    return pedido


# --- pagado_en ----------------------------------------------------------------


def test_pagar_pone_pagado_en_una_sola_vez(cliente):
    pedido = ItemPedidoFactory(pedido__usuario_id=CLIENTE_ID).pedido
    assert pedido.pagado_en is None

    respuesta = cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/")

    assert respuesta.status_code == 200
    pedido.refresh_from_db()
    assert pedido.pagado_en is not None
    assert respuesta.json()["pagado_en"] is not None
    primero = pedido.pagado_en

    # Las transiciones siguientes no lo tocan.
    servicios.cambiar_estado(pedido, Pedido.Estado.ENVIADO, ADMIN)
    servicios.cambiar_estado(pedido, Pedido.Estado.ENTREGADO, ADMIN)
    pedido.refresh_from_db()
    assert pedido.pagado_en == primero


def test_cancelar_un_pendiente_no_pone_pagado_en():
    pedido = ItemPedidoFactory().pedido

    servicios.cambiar_estado(pedido, Pedido.Estado.CANCELADO, ADMIN)

    pedido.refresh_from_db()
    assert pedido.estado == Pedido.Estado.CANCELADO
    assert pedido.pagado_en is None


def test_el_evento_de_estado_no_cambia_su_contrato(
    redis_de_eventos, django_capture_on_commit_callbacks
):
    pedido = ItemPedidoFactory().pedido

    with django_capture_on_commit_callbacks(execute=True):
        servicios.cambiar_estado(pedido, Pedido.Estado.PAGADO, ADMIN)

    [(_, campos)] = redis_de_eventos.xrange(STREAM_TIENDA)
    assert "pagado_en" not in json.loads(campos["sobre"])["datos"]


# --- Resumen ------------------------------------------------------------------


def test_resumen_sin_token_401(anonimo):
    assert anonimo.get(RESUMEN).status_code == 401


def test_resumen_con_rol_cliente_403(cliente):
    assert cliente.get(RESUMEN).status_code == 403


def test_resumen_umbral_invalido_400(admin):
    respuesta = admin.get(RESUMEN, {"umbral": "-1"})

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert "umbral" in respuesta.json()["campos"]


def test_resumen_cuenta_pedidos_por_estado(admin):
    PedidoFactory.create_batch(2, estado=Pedido.Estado.PENDIENTE)
    PedidoFactory(estado=Pedido.Estado.PAGADO)
    PedidoFactory(estado=Pedido.Estado.ENVIADO)

    cuerpo = admin.get(RESUMEN).json()

    assert cuerpo["pedidos"] == {"pendientes": 2, "por_enviar": 1}
    assert len(cuerpo["ultimos_pedidos"]) == 4


def test_ventas_por_pagado_en_con_respaldo_en_creado_en(admin, monkeypatch):
    ahora = en_mexico(2026, 11, 26, 23, 45)
    monkeypatch.setattr(timezone, "now", lambda: ahora)
    # Pagado a las 23:30 hora de México (05:30 UTC del día siguiente): cuenta para el 26.
    pedido_con_fechas(
        "pagado", "100.00", en_mexico(2026, 11, 26, 10), en_mexico(2026, 11, 26, 23, 30)
    )
    # Creado ayer, pagado hoy: cuenta hoy (por pagado_en).
    pedido_con_fechas("enviado", "200.00", en_mexico(2026, 11, 25, 9), en_mexico(2026, 11, 26, 8))
    # Viejo, sin pagado_en: cuenta por creado_en (hace 3 días).
    pedido_con_fechas("entregado", "300.00", en_mexico(2026, 11, 23, 12))
    # Del mes, fuera de los 7 días.
    pedido_con_fechas("pagado", "400.00", en_mexico(2026, 11, 2, 12), en_mexico(2026, 11, 2, 13))
    # Del mes anterior: no cuenta.
    pedido_con_fechas(
        "pagado", "500.00", en_mexico(2026, 10, 31, 12), en_mexico(2026, 10, 31, 23, 59)
    )
    # Ni los pendientes ni los cancelados son ventas.
    pedido_con_fechas("pendiente", "600.00", en_mexico(2026, 11, 26, 9))
    pedido_con_fechas(
        "cancelado", "700.00", en_mexico(2026, 11, 26, 9), en_mexico(2026, 11, 26, 9, 5)
    )

    ventas = admin.get(RESUMEN).json()["ventas"]

    assert ventas["hoy"] == {"total": "300.00", "pedidos": 2}
    assert ventas["ultimos_7_dias"] == {"total": "600.00", "pedidos": 3}
    assert ventas["mes"] == {"total": "1000.00", "pedidos": 4}
    assert ventas["respaldo"]["pedidos_sin_pagado_en"] == 1
    assert ventas["respaldo"]["primer_pagado_en"] == "2026-10-31"


def test_una_venta_de_las_23_30_no_cuenta_para_el_dia_siguiente(admin, monkeypatch):
    pedido_con_fechas(
        "pagado", "100.00", en_mexico(2026, 11, 26, 23), en_mexico(2026, 11, 26, 23, 30)
    )
    monkeypatch.setattr(timezone, "now", lambda: en_mexico(2026, 11, 27, 0, 10))

    ventas = admin.get(RESUMEN).json()["ventas"]

    assert ventas["hoy"] == {"total": "0.00", "pedidos": 0}
    assert ventas["ultimos_7_dias"]["total"] == "100.00"


def test_resumen_de_stock_con_el_umbral(admin):
    ProductoFactory(nombre="Urea", stock=3)
    ProductoFactory(nombre="Malla", stock=5)
    ProductoFactory(nombre="Caldo", stock=0)
    ProductoFactory(nombre="Mucho", stock=50)
    ProductoFactory(nombre="Inactivo", stock=0, activo=False)

    stock = admin.get(RESUMEN, {"umbral": 5}).json()["stock"]

    assert stock["umbral"] == 5
    assert stock["bajo"]["total"] == 2
    assert [p["nombre"] for p in stock["bajo"]["productos"]] == ["Urea", "Malla"]
    assert stock["agotados"]["total"] == 1
    assert stock["agotados"]["productos"][0]["nombre"] == "Caldo"


def test_filtros_de_fecha_de_pedidos_en_hora_de_mexico(admin):
    noche = pedido_con_fechas("pendiente", "100.00", en_mexico(2026, 11, 26, 23, 30))
    pedido_con_fechas("pendiente", "100.00", en_mexico(2026, 11, 27, 0, 30))

    respuesta = admin.get(PEDIDOS, {"desde": "2026-11-26", "hasta": "2026-11-26"})

    assert [p["id"] for p in respuesta.json()["results"]] == [noche.pk]


def test_filtro_de_pedidos_por_numero_y_usuario(admin):
    buscado = PedidoFactory()
    otro_usuario = uuid.uuid4()
    PedidoFactory(usuario_id=otro_usuario)

    assert [p["id"] for p in admin.get(PEDIDOS, {"id": buscado.pk}).json()["results"]] == [
        buscado.pk
    ]
    assert admin.get(PEDIDOS, {"usuario_id": str(otro_usuario)}).json()["count"] == 1


def test_filtro_de_fecha_invalida_400(admin):
    respuesta = admin.get(PEDIDOS, {"desde": "2026-13-45"})

    assert respuesta.status_code == 400
