from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from apps.usuarios.managers import UsuarioManager

validar_telefono = RegexValidator(
    r"^\+?\d{10,15}$", "El teléfono debe tener de 10 a 15 dígitos (puede iniciar con +)."
)
validar_codigo_postal = RegexValidator(r"^\d{5}$", "El código postal debe tener 5 dígitos.")


class Usuario(AbstractUser):
    """Usuario de AgroIA-Web. Se identifica por correo; el `id` es el `user_id` del JWT."""

    class Rol(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        ADMINISTRADOR = "administrador", "Administrador"

    username = None
    first_name = None
    last_name = None

    email = models.EmailField("correo", unique=True)
    nombre = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=16, blank=True, validators=[validar_telefono])
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CLIENTE)
    email_verificado = models.BooleanField(default=False)
    # Se incrementa para invalidar todos los tokens del usuario (Entrega 3).
    token_version = models.PositiveIntegerField(default=0)
    acepto_privacidad_en = models.DateTimeField(null=True, blank=True)
    version_privacidad = models.CharField(max_length=20, blank=True)
    tiene_2fa = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    objects = UsuarioManager()

    class Meta:
        ordering = ["-date_joined", "-id"]
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()

    def get_short_name(self) -> str:
        return self.nombre


class Direccion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="direcciones")
    alias = models.CharField(max_length=50, blank=True)
    calle = models.CharField(max_length=150)
    numero = models.CharField(max_length=20)
    colonia = models.CharField(max_length=100)
    municipio = models.CharField(max_length=100)
    estado = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=5, validators=[validar_codigo_postal])
    referencias = models.CharField(max_length=255, blank=True)
    predeterminada = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-predeterminada", "-creada_en", "-id"]
        verbose_name = "dirección"
        verbose_name_plural = "direcciones"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario"],
                condition=models.Q(predeterminada=True),
                name="direccion_una_predeterminada_por_usuario",
            )
        ]

    def __str__(self) -> str:
        return self.alias or f"{self.calle} {self.numero}, {self.colonia}"
