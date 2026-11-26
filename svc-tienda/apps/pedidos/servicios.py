"""Lógica de negocio del carrito y los pedidos.

Toda operación que toca stock o dinero corre en transaction.atomic() y bloquea los
productos con select_for_update(), siempre ordenados por id para evitar deadlocks.

Eventos (docs/eventos.md), siempre después del commit: `pedido_creado` al crear el pedido y
un solo `pedido_estado_cambiado` por cada transición, también el pago, porque todas pasan
por `_cambiar_estado_bloqueado`. Validar y descontar stock sigue siendo síncrono.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Min, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status

from agroia_comun.errores import ErrorDeNegocio
from agroia_comun.eventos.en_django import publicar_al_confirmar
from apps.catalogo.models import Producto
from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pedido

CERO = Decimal("0.00")

TRANSICIONES = {
    Pedido.Estado.PENDIENTE: {Pedido.Estado.PAGADO, Pedido.Estado.CANCELADO},
    Pedido.Estado.PAGADO: {Pedido.Estado.ENVIADO, Pedido.Estado.CANCELADO},
    Pedido.Estado.ENVIADO: {Pedido.Estado.ENTREGADO},
    Pedido.Estado.ENTREGADO: set(),
    Pedido.Estado.CANCELADO: set(),
}
# Orden en que se muestran las opciones (el del flujo del pedido).
ORDEN_DE_ESTADOS = [estado for estado, _ in Pedido.Estado.choices]


def transiciones_permitidas(pedido: Pedido) -> list[str]:
    """Estados a los que el pedido puede pasar ahora (PATCH /pedidos/<id>/estado/)."""
    return [estado for estado in ORDEN_DE_ESTADOS if estado in TRANSICIONES[pedido.estado]]


def _validar_disponible(producto: Producto) -> None:
    if not producto.activo or not producto.categoria.activa:
        raise ErrorDeNegocio(
            "producto_no_disponible", f"El producto «{producto.nombre}» ya no está disponible."
        )


def _validar_stock(producto: Producto, cantidad: int) -> None:
    if cantidad > producto.stock:
        raise ErrorDeNegocio(
            "stock_insuficiente",
            f"No hay suficiente stock de «{producto.nombre}»: "
            f"pediste {cantidad} y quedan {producto.stock}.",
        )


# --- Carrito ------------------------------------------------------------------


def obtener_carrito(usuario_id: uuid.UUID) -> Carrito:
    """El carrito del usuario; se crea la primera vez."""
    carrito, _ = Carrito.objects.get_or_create(usuario_id=usuario_id)
    return carrito


def agregar_al_carrito(usuario_id: uuid.UUID, producto: Producto, cantidad: int) -> ItemCarrito:
    """Agrega un producto; si ya estaba, suma la cantidad. No aparta stock."""
    _validar_disponible(producto)
    with transaction.atomic():
        carrito = Carrito.objects.select_for_update().get(pk=obtener_carrito(usuario_id).pk)
        item = carrito.items.filter(producto=producto).first()
        nueva_cantidad = (item.cantidad if item else 0) + cantidad
        _validar_stock(producto, nueva_cantidad)
        if item is None:
            item = ItemCarrito.objects.create(carrito=carrito, producto=producto, cantidad=cantidad)
        else:
            item.cantidad = nueva_cantidad
            item.save(update_fields=["cantidad"])
        carrito.save(update_fields=["actualizado_en"])
    return item


def cambiar_cantidad(item: ItemCarrito, cantidad: int) -> ItemCarrito:
    _validar_disponible(item.producto)
    _validar_stock(item.producto, cantidad)
    item.cantidad = cantidad
    item.save(update_fields=["cantidad"])
    item.carrito.save(update_fields=["actualizado_en"])
    return item


def quitar_item(item: ItemCarrito) -> None:
    carrito = item.carrito
    item.delete()
    carrito.save(update_fields=["actualizado_en"])


def vaciar_carrito(usuario_id: uuid.UUID) -> None:
    ItemCarrito.objects.filter(carrito__usuario_id=usuario_id).delete()


def calcular_envio(subtotal: Decimal) -> Decimal:
    """Costo fijo (COSTO_ENVIO); gratis si el subtotal supera ENVIO_GRATIS_DESDE."""
    if subtotal > settings.ENVIO_GRATIS_DESDE:
        return CERO
    return settings.COSTO_ENVIO


def totales_del_carrito(carrito: Carrito) -> tuple[Decimal, Decimal, Decimal]:
    """(subtotal, envío, total) estimados con los precios actuales."""
    subtotal = sum(
        (item.producto.precio * item.cantidad for item in carrito.items.all()), start=CERO
    )
    envio = calcular_envio(subtotal) if subtotal else CERO
    return subtotal, envio, subtotal + envio


# --- Pedidos ------------------------------------------------------------------


def crear_pedido_desde_carrito(
    usuario_id: uuid.UUID, direccion_envio: dict, metodo_pago: str
) -> Pedido:
    """Convierte el carrito en pedido: valida y descuenta stock, copia nombre y precio,
    calcula subtotal, envío y total, y vacía el carrito. Todo o nada.
    """
    with transaction.atomic():
        carrito = Carrito.objects.select_for_update().filter(usuario_id=usuario_id).first()
        items = list(carrito.items.all()) if carrito else []
        if not items:
            raise ErrorDeNegocio(
                "carrito_vacio", "Tu carrito está vacío.", status_code=status.HTTP_400_BAD_REQUEST
            )

        productos = {
            producto.pk: producto
            for producto in Producto.objects.select_related("categoria")
            .select_for_update(of=("self",))
            .filter(pk__in=[item.producto_id for item in items])
            .order_by("pk")
        }

        lineas = []
        for item in items:
            producto = productos[item.producto_id]
            _validar_disponible(producto)
            _validar_stock(producto, item.cantidad)
            lineas.append((producto, item.cantidad, producto.precio * item.cantidad))

        subtotal = sum((importe for _, _, importe in lineas), start=CERO)
        envio = calcular_envio(subtotal)
        pedido = Pedido.objects.create(
            usuario_id=usuario_id,
            direccion_envio=direccion_envio,
            subtotal=subtotal,
            envio=envio,
            total=subtotal + envio,
            metodo_pago=metodo_pago,
        )
        ItemPedido.objects.bulk_create(
            ItemPedido(
                pedido=pedido,
                producto=producto,
                nombre_producto=producto.nombre,
                precio_unitario=producto.precio,
                cantidad=cantidad,
                importe=importe,
            )
            for producto, cantidad, importe in lineas
        )
        for producto, cantidad, _ in lineas:
            producto.stock -= cantidad
            producto.save(update_fields=["stock"])
        carrito.items.all().delete()
        publicar_al_confirmar(
            "pedido_creado",
            {
                "pedido_id": pedido.pk,
                "usuario_id": str(usuario_id),
                "total": str(pedido.total),
                "productos": len(lineas),
                "unidades": sum(cantidad for _, cantidad, _ in lineas),
                "metodo_pago": metodo_pago,
            },
        )
    return pedido


def _cambiar_estado_bloqueado(pedido: Pedido, nuevo: str, actor_id: uuid.UUID) -> Pedido:
    """Única puerta de las transiciones: aquí, y solo aquí, se publica el evento."""
    if nuevo not in TRANSICIONES[pedido.estado]:
        raise ErrorDeNegocio(
            "transicion_invalida",
            f"Un pedido {pedido.get_estado_display().lower()} no puede pasar a «{nuevo}».",
        )
    if nuevo == Pedido.Estado.CANCELADO:
        _devolver_stock(pedido)
    anterior = pedido.estado
    pedido.estado = nuevo
    campos = ["estado"]
    if nuevo == Pedido.Estado.PAGADO and pedido.pagado_en is None:
        pedido.pagado_en = timezone.now()
        campos.append("pagado_en")
    pedido.save(update_fields=campos)
    publicar_al_confirmar(
        "pedido_estado_cambiado",
        {
            "pedido_id": pedido.pk,
            "usuario_id": str(pedido.usuario_id),
            "estado_anterior": anterior,
            "estado_nuevo": nuevo,
            "total": str(pedido.total),
            "cambiado_por": str(actor_id),
        },
    )
    return pedido


def _devolver_stock(pedido: Pedido) -> None:
    items = list(pedido.items.all())
    ids = sorted({item.producto_id for item in items})
    list(Producto.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    for item in items:
        Producto.objects.filter(pk=item.producto_id).update(stock=F("stock") + item.cantidad)


def cambiar_estado(pedido: Pedido, nuevo: str, actor_id: uuid.UUID) -> Pedido:
    """Aplica una transición válida (pendiente→pagado→enviado→entregado, o cancelado
    desde pendiente o pagado). Al cancelar, devuelve el stock. `actor_id` es quién lo
    cambió (el administrador), para el evento.
    """
    with transaction.atomic():
        bloqueado = Pedido.objects.select_for_update().get(pk=pedido.pk)
        return _cambiar_estado_bloqueado(bloqueado, nuevo, actor_id)


def pagar_pedido(pedido: Pedido) -> Pedido:
    """Pago simulado: pasa el pedido de pendiente a pagado. No cobra nada."""
    with transaction.atomic():
        bloqueado = Pedido.objects.select_for_update().get(pk=pedido.pk)
        if bloqueado.estado != Pedido.Estado.PENDIENTE:
            raise ErrorDeNegocio(
                "transicion_invalida",
                f"Solo se pueden pagar pedidos pendientes; este está "
                f"{bloqueado.get_estado_display().lower()}.",
            )
        # Solo el dueño paga: él es quien lo cambió.
        return _cambiar_estado_bloqueado(bloqueado, Pedido.Estado.PAGADO, bloqueado.usuario_id)


# --- Resumen del panel de administración --------------------------------------------------

ESTADOS_DE_VENTA = (Pedido.Estado.PAGADO, Pedido.Estado.ENVIADO, Pedido.Estado.ENTREGADO)
MAXIMO_EN_LISTA = 10


def _ventas(pedidos, desde) -> dict:
    datos = pedidos.filter(fecha_venta__gte=desde).aggregate(
        total=Sum("total"), pedidos=Count("id")
    )
    total = (datos["total"] or CERO).quantize(CERO)
    return {"total": str(total), "pedidos": datos["pedidos"]}


def _productos_resumen(productos) -> dict:
    return {
        "total": productos.count(),
        "productos": [
            {"slug": p.slug, "nombre": p.nombre, "stock": p.stock}
            for p in productos.order_by("stock", "nombre")[:MAXIMO_EN_LISTA]
        ],
    }


def resumen(umbral: int) -> dict:
    """Números del inicio del panel, sin traer listas enteras.

    Ventas: pedidos pagados, enviados o entregados, por la fecha de pago (`pagado_en`); los
    pagados antes de que existiera ese campo cuentan por `creado_en`. Los días son de la zona
    del servidor (America/Mexico_City) aunque la base guarde en UTC.
    """
    ahora = timezone.localtime(timezone.now())
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    ventas = Pedido.objects.filter(estado__in=ESTADOS_DE_VENTA).annotate(
        fecha_venta=Coalesce("pagado_en", "creado_en")
    )
    sin_fecha = ventas.filter(pagado_en__isnull=True).count()
    primero = Pedido.objects.filter(pagado_en__isnull=False).aggregate(primero=Min("pagado_en"))
    primero = primero["primero"]
    activos = Producto.objects.filter(activo=True)
    return {
        "fecha": hoy.date().isoformat(),
        "pedidos": {
            "pendientes": Pedido.objects.filter(estado=Pedido.Estado.PENDIENTE).count(),
            "por_enviar": Pedido.objects.filter(estado=Pedido.Estado.PAGADO).count(),
        },
        "ventas": {
            "hoy": _ventas(ventas, hoy),
            "ultimos_7_dias": _ventas(ventas, hoy - timedelta(days=6)),
            "mes": _ventas(ventas, hoy.replace(day=1)),
            "respaldo": {
                "pedidos_sin_pagado_en": sin_fecha,
                "primer_pagado_en": (
                    timezone.localtime(primero).date().isoformat() if primero else None
                ),
            },
        },
        "stock": {
            "umbral": umbral,
            "bajo": _productos_resumen(activos.filter(stock__gt=0, stock__lte=umbral)),
            "agotados": _productos_resumen(activos.filter(stock=0)),
        },
        "ultimos_pedidos": [
            {
                "id": p.pk,
                "estado": p.estado,
                "total": str(p.total),
                "creado_en": p.creado_en,
                "usuario_id": str(p.usuario_id),
            }
            for p in Pedido.objects.order_by("-creado_en", "-id")[:5]
        ],
    }
