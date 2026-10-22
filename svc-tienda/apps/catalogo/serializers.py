import json

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.catalogo.models import Categoria, Producto


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Categoría",
            value={
                "nombre": "Fungicidas",
                "descripcion": "Control de antracnosis, roña y otras enfermedades.",
            },
            request_only=True,
        )
    ]
)
class CategoriaSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(
        max_length=120, required=False, help_text="Se genera a partir del nombre si no se envía."
    )

    class Meta:
        model = Categoria
        fields = ["id", "nombre", "slug", "descripcion", "activa"]
        read_only_fields = ["id"]

    def validate_slug(self, valor: str) -> str:
        repetidos = Categoria.objects.filter(slug=valor)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe una categoría con este slug.")
        return valor


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Producto",
            value={
                "nombre": "Oxicloruro de cobre 50% PH",
                "categoria": "fungicidas",
                "descripcion": "Fungicida preventivo de contacto para antracnosis y roña.",
                "precio": "245.50",
                "stock": 30,
                "unidad": "kg",
                "ficha_tecnica": {
                    "ingrediente_activo": "Oxicloruro de cobre 50%",
                    "dosis": "2 a 3 kg/ha",
                    "presentacion": "Bolsa de 1 kg",
                },
            },
            request_only=True,
        )
    ]
)
class ProductoSerializer(serializers.ModelSerializer):
    categoria = serializers.SlugRelatedField(
        slug_field="slug", queryset=Categoria.objects.all(), help_text="Slug de la categoría."
    )
    slug = serializers.SlugField(
        max_length=170, required=False, help_text="Se genera a partir del nombre si no se envía."
    )
    disponible = serializers.SerializerMethodField(help_text="Hay stock (stock > 0).")

    class Meta:
        model = Producto
        fields = [
            "id",
            "nombre",
            "slug",
            "categoria",
            "descripcion",
            "precio",
            "stock",
            "unidad",
            "imagen",
            "ficha_tecnica",
            "activo",
            "disponible",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]

    def get_disponible(self, producto: Producto) -> bool:
        return producto.stock > 0

    def validate_slug(self, valor: str) -> str:
        repetidos = Producto.objects.filter(slug=valor)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un producto con este slug.")
        return valor

    def validate_ficha_tecnica(self, valor):
        # Con multipart (al subir imagen) la ficha llega como texto JSON.
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except json.JSONDecodeError as error:
                raise serializers.ValidationError("La ficha técnica no es JSON válido.") from error
        if not isinstance(valor, dict):
            raise serializers.ValidationError("La ficha técnica debe ser un objeto JSON.")
        return valor
