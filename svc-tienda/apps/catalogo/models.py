from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024  # 5 MB


def validar_tamano_imagen(archivo) -> None:
    if archivo.size > TAMANO_MAXIMO_IMAGEN:
        raise ValidationError("La imagen no puede pesar más de 5 MB.")


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"

    def __str__(self) -> str:
        return self.nombre


class Producto(models.Model):
    class Unidad(models.TextChoices):
        PIEZA = "pieza", "Pieza"
        KG = "kg", "Kilogramo"
        LITRO = "litro", "Litro"
        COSTAL = "costal", "Costal"

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    unidad = models.CharField(max_length=10, choices=Unidad.choices, default=Unidad.PIEZA)
    # Se guarda con default_storage (STORAGES): en la Entrega 5 pasa a Cloud Storage.
    imagen = models.ImageField(
        upload_to="productos/",
        blank=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "webp"]),
            validar_tamano_imagen,
        ],
    )
    # Datos que cambian según el tipo de producto: dosis, composición, presentación...
    ficha_tecnica = models.JSONField(default=dict, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock__gte=0), name="producto_stock_no_negativo"
            ),
            models.CheckConstraint(
                condition=models.Q(precio__gt=0), name="producto_precio_positivo"
            ),
        ]

    def __str__(self) -> str:
        return self.nombre
