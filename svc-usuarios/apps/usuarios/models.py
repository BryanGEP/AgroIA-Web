import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from apps.usuarios.managers import UsuarioManager

validar_telefono = RegexValidator(
    r"^\+?\d{10,15}$", "El teléfono debe tener de 10 a 15 dígitos (puede iniciar con +)."
)
validar_codigo_postal = RegexValidator(r"^\d{5}$", "El código postal debe tener 5 dígitos.")


class Usuario(AbstractUser):
    """Usuario de AgroIA-Web. Se identifica por correo; el `id` (UUID, como en ms-usuarios)
    es el `user_id` del JWT y el `usuario_id` que guardan los demás servicios."""

    class Rol(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        ADMINISTRADOR = "administrador", "Administrador"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    first_name = None
    last_name = None

    email = models.EmailField("correo", unique=True)
    nombre = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=16, blank=True, validators=[validar_telefono])
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CLIENTE)
    email_verificado = models.BooleanField(default=False)
    # Se incrementa para que ningún refresh emitido antes vuelva a renovar (logout-todo,
    # restablecer o cambiar la contraseña). Viaja en el claim `token_version`.
    token_version = models.PositiveIntegerField(default=0)
    acepto_privacidad_en = models.DateTimeField(null=True, blank=True)
    version_privacidad = models.CharField(max_length=20, blank=True)
    # Sin endpoint para activarlo todavía: el login responde 501 (sección 12).
    tiene_2fa = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    objects = UsuarioManager()

    class Meta:
        ordering = ["-date_joined", "email"]
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


class CambioRol(models.Model):
    """Quién cambió el rol de un usuario y cuándo (PATCH /usuarios/<id>/rol/)."""

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="cambios_de_rol")
    rol_anterior = models.CharField(max_length=20, choices=Usuario.Rol.choices)
    rol_nuevo = models.CharField(max_length=20, choices=Usuario.Rol.choices)
    # Si se borra al administrador, el registro se conserva sin él.
    cambiado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="roles_cambiados",
    )
    cambiado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cambiado_en", "-id"]
        verbose_name = "cambio de rol"
        verbose_name_plural = "cambios de rol"

    def __str__(self) -> str:
        return f"{self.usuario}: {self.rol_anterior} → {self.rol_nuevo}"


class CorreoEnviado(models.Model):
    """Idempotencia del consumidor de correos: un evento `correo_solicitado` se envía una
    sola vez aunque llegue dos veces (ver apps/usuarios/eventos.py y docs/eventos.md).

    No guarda el contenido ni el enlace del correo. `omitido` es True si al procesar ya no
    tocaba enviarlo (por ejemplo, el correo ya estaba verificado o la cuenta desactivada).
    """

    evento_id = models.UUIDField(unique=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="correos")
    tipo_correo = models.CharField(max_length=20)
    omitido = models.BooleanField(default=False)
    procesado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-procesado_en", "-id"]
        verbose_name = "correo enviado"
        verbose_name_plural = "correos enviados"

    def __str__(self) -> str:
        return f"{self.tipo_correo} a {self.usuario_id} ({self.procesado_en:%Y-%m-%d %H:%M})"
