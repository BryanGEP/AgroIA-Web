"""Lógica de negocio del carrito y los pedidos.

Toda operación que toca stock o dinero corre en transaction.atomic() y bloquea los
productos con select_for_update(), siempre ordenados por id para evitar deadlocks.
"""

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework import status

from agroia_comun.errores import ErrorDeNegocio
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


def obtener_carrito(usuario_id: int) -> Carrito:
    """El carrito del usuario; se crea la primera vez."""
    carrito, _ = Carrito.objects.get_or_create(usuario_id=usuario_id)
    return carrito


def agregar_al_carrito(usuario_id: int, producto: Producto, cantidad: int) -> ItemCarrito:
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


def vaciar_carrito(usuario_id: int) -> None:
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


def crear_pedido_desde_carrito(usuario_id: int, direccion_envio: dict, metodo_pago: str) -> Pedido:
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
    return pedido


def _cambiar_estado_bloqueado(pedido: Pedido, nuevo: str) -> Pedido:
    if nuevo not in TRANSICIONES[pedido.estado]:
        raise ErrorDeNegocio(
            "transicion_invalida",
            f"Un pedido {pedido.get_estado_display().lower()} no puede pasar a «{nuevo}».",
        )
    if nuevo == Pedido.Estado.CANCELADO:
        _devolver_stock(pedido)
    pedido.estado = nuevo
    pedido.save(update_fields=["estado"])
    return pedido


def _devolver_stock(pedido: Pedido) -> None:
    items = list(pedido.items.all())
    ids = sorted({item.producto_id for item in items})
    list(Producto.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    for item in items:
        Producto.objects.filter(pk=item.producto_id).update(stock=F("stock") + item.cantidad)


def cambiar_estado(pedido: Pedido, nuevo: str) -> Pedido:
    """Aplica una transición válida (pendiente→pagado→enviado→entregado, o cancelado
    desde pendiente o pagado). Al cancelar, devuelve el stock.
    """
    with transaction.atomic():
        bloqueado = Pedido.objects.select_for_update().get(pk=pedido.pk)
        return _cambiar_estado_bloqueado(bloqueado, nuevo)


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
        return _cambiar_estado_bloqueado(bloqueado, Pedido.Estado.PAGADO)
