from decimal import Decimal

from drf_spectacular.utils import OpenApiExample, extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.catalogo.models import Producto
from apps.pedidos import servicios
from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pedido

EJEMPLO_DIRECCION = {
    "alias": "Huerta",
    "calle": "Camino a La Palma",
    "numero": "km 3",
    "colonia": "La Palma",
    "municipio": "Jiquilpan",
    "estado": "Michoacán",
    "codigo_postal": "59510",
    "referencias": "Portón verde junto a la bodega",
}


# --- Carrito ------------------------------------------------------------------


class ProductoEnCarritoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ["slug", "nombre", "precio", "unidad", "imagen", "stock"]


class ItemCarritoSerializer(serializers.ModelSerializer):
    producto = ProductoEnCarritoSerializer(read_only=True)
    importe = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarrito
        fields = ["id", "producto", "cantidad", "importe"]

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_importe(self, item: ItemCarrito) -> str:
        return f"{item.producto.precio * item.cantidad:.2f}"


class CarritoSerializer(serializers.ModelSerializer):
    """Carrito con totales estimados con los precios actuales."""

    items = ItemCarritoSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    envio = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Carrito
        fields = ["id", "items", "subtotal", "envio", "total", "actualizado_en"]

    def _totales(self, carrito: Carrito) -> tuple[Decimal, Decimal, Decimal]:
        if not hasattr(self, "_cache_totales"):
            self._cache_totales = servicios.totales_del_carrito(carrito)
        return self._cache_totales

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_subtotal(self, carrito: Carrito) -> str:
        return f"{self._totales(carrito)[0]:.2f}"

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_envio(self, carrito: Carrito) -> str:
        return f"{self._totales(carrito)[1]:.2f}"

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_total(self, carrito: Carrito) -> str:
        return f"{self._totales(carrito)[2]:.2f}"


@extend_schema_serializer(
    examples=[OpenApiExample("Agregar", value={"producto": "urea-46-25-kg", "cantidad": 2})]
)
class AgregarItemSerializer(serializers.Serializer):
    producto = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Producto.objects.select_related("categoria"),
        help_text="Slug del producto.",
    )
    cantidad = serializers.IntegerField(min_value=1)


@extend_schema_serializer(examples=[OpenApiExample("Cambiar cantidad", value={"cantidad": 3})])
class CambiarCantidadSerializer(serializers.Serializer):
    cantidad = serializers.IntegerField(min_value=1)


# --- Pedidos ------------------------------------------------------------------


class DireccionEnvioSerializer(serializers.Serializer):
    """Mismos campos que `Direccion` de svc-usuarios (sin el usuario)."""

    alias = serializers.CharField(max_length=50, required=False, allow_blank=True)
    calle = serializers.CharField(max_length=150)
    numero = serializers.CharField(max_length=20)
    colonia = serializers.CharField(max_length=100)
    municipio = serializers.CharField(max_length=100)
    estado = serializers.CharField(max_length=100)
    codigo_postal = serializers.RegexField(
        r"^\d{5}$", error_messages={"invalid": "El código postal debe tener 5 dígitos."}
    )
    referencias = serializers.CharField(max_length=255, required=False, allow_blank=True)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Crear pedido",
            value={"direccion_envio": EJEMPLO_DIRECCION, "metodo_pago": "tarjeta"},
            request_only=True,
        )
    ]
)
class CrearPedidoSerializer(serializers.Serializer):
    direccion_envio = DireccionEnvioSerializer()
    metodo_pago = serializers.ChoiceField(
        choices=Pedido.MetodoPago.choices, help_text="Todos los métodos son simulados."
    )


class ItemPedidoSerializer(serializers.ModelSerializer):
    producto = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = ItemPedido
        fields = ["id", "producto", "nombre_producto", "precio_unitario", "cantidad", "importe"]


class PedidoSerializer(serializers.ModelSerializer):
    items = ItemPedidoSerializer(many=True, read_only=True)
    pago_simulado = serializers.SerializerMethodField(
        help_text="Siempre true: ninguna entrega integra una pasarela de pago."
    )

    class Meta:
        model = Pedido
        fields = [
            "id",
            "usuario_id",
            "estado",
            "direccion_envio",
            "items",
            "subtotal",
            "envio",
            "total",
            "metodo_pago",
            "pago_simulado",
            "creado_en",
        ]
        read_only_fields = fields

    def get_pago_simulado(self, pedido: Pedido) -> bool:
        return True


@extend_schema_serializer(examples=[OpenApiExample("Enviar", value={"estado": "enviado"})])
class CambiarEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Pedido.Estado.choices)
