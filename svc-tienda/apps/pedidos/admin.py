from django.contrib import admin

from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pedido


class ItemCarritoInline(admin.TabularInline):
    model = ItemCarrito
    extra = 0
    autocomplete_fields = ["producto"]


@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ["usuario_id", "creado_en", "actualizado_en"]
    search_fields = ["usuario_id"]
    inlines = [ItemCarritoInline]


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    can_delete = False
    readonly_fields = ["producto", "nombre_producto", "precio_unitario", "cantidad", "importe"]

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    """Los montos y las copias no se editan; el estado se cambia desde la API para que
    se respeten las transiciones y la devolución de stock."""

    list_display = ["id", "usuario_id", "estado", "metodo_pago", "total", "creado_en"]
    list_filter = ["estado", "metodo_pago"]
    search_fields = ["id", "usuario_id"]
    readonly_fields = [
        "usuario_id",
        "estado",
        "direccion_envio",
        "subtotal",
        "envio",
        "total",
        "metodo_pago",
        "creado_en",
    ]
    inlines = [ItemPedidoInline]
