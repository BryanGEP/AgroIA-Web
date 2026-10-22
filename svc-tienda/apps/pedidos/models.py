from django.db import models

from apps.catalogo.models import Producto

# usuario_id es el id de svc-usuarios: entero, sin ForeignKey (vive en otra base).


class Carrito(models.Model):
    usuario_id = models.PositiveBigIntegerField(unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Carrito del usuario {self.usuario_id}"


class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    cantidad = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["carrito", "producto"], name="item_carrito_producto_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0), name="item_carrito_cantidad_positiva"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cantidad} x {self.producto}"


class Pedido(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PAGADO = "pagado", "Pagado"
        ENVIADO = "enviado", "Enviado"
        ENTREGADO = "entregado", "Entregado"
        CANCELADO = "cancelado", "Cancelado"

    class MetodoPago(models.TextChoices):
        # Todos son simulados: ninguna entrega integra una pasarela de pago.
        TARJETA = "tarjeta", "Tarjeta (pago simulado)"
        TRANSFERENCIA = "transferencia", "Transferencia (pago simulado)"
        CONTRA_ENTREGA = "contra_entrega", "Contra entrega (pago simulado)"

    usuario_id = models.PositiveBigIntegerField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    # Copia de la dirección al momento de comprar.
    direccion_envio = models.JSONField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    envio = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=15, choices=MetodoPago.choices)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        indexes = [models.Index(fields=["usuario_id", "-creado_en"], name="pedido_usuario_fecha")]

    def __str__(self) -> str:
        return f"Pedido {self.pk} ({self.get_estado_display()})"


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    # Copias: si el producto cambia después, el pedido conserva lo que se compró.
    nombre_producto = models.CharField(max_length=150)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad = models.PositiveIntegerField()
    importe = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0), name="item_pedido_cantidad_positiva"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cantidad} x {self.nombre_producto}"
