from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.usuarios.managers import normalizar_email
from apps.usuarios.models import Direccion, Usuario


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Registro",
            value={
                "nombre": "María",
                "apellidos": "López Ramírez",
                "email": "maria.lopez@example.com",
                "password": "Aguacate-Hass-2026",
                "password_confirmacion": "Aguacate-Hass-2026",
                "acepto_privacidad": True,
            },
            request_only=True,
        )
    ]
)
class RegistroSerializer(serializers.Serializer):
    """Los errores propios del registro llegan como mensaje del campo dentro de
    `validacion`: `email_registrado`, `password_no_coincide` y `privacidad_no_aceptada`."""

    nombre = serializers.CharField(max_length=150)
    apellidos = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    password_confirmacion = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    acepto_privacidad = serializers.BooleanField(
        required=False,
        allow_null=True,
        default=False,
        help_text="Debe ser true: aceptación del aviso de privacidad.",
    )

    def to_internal_value(self, data):
        # Normalizar antes de validar el formato: quitar espacios y pasar a minúsculas.
        if hasattr(data, "copy") and isinstance(data.get("email"), str):
            data = data.copy()
            data["email"] = normalizar_email(data["email"])
        return super().to_internal_value(data)

    def validate_email(self, email: str) -> str:
        if Usuario.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("email_registrado")
        return email

    def validate_acepto_privacidad(self, valor) -> bool:
        if valor is not True:
            raise serializers.ValidationError("privacidad_no_aceptada")
        return valor

    def validate(self, datos: dict) -> dict:
        if datos["password"] != datos["password_confirmacion"]:
            raise serializers.ValidationError({"password_confirmacion": ["password_no_coincide"]})
        temporal = Usuario(
            email=datos["email"], nombre=datos["nombre"], apellidos=datos["apellidos"]
        )
        try:
            validate_password(datos["password"], user=temporal)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)}) from error
        return datos


class RegistroRespuestaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    mensaje = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Editar perfil",
            value={"nombre": "María", "apellidos": "López Ramírez", "telefono": "3531234567"},
            request_only=True,
        )
    ]
)
class PerfilSerializer(serializers.ModelSerializer):
    """Solo se editan nombre, apellidos y teléfono; lo demás es de solo lectura."""

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nombre",
            "apellidos",
            "telefono",
            "rol",
            "email_verificado",
            "tiene_2fa",
            "acepto_privacidad_en",
            "version_privacidad",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "rol",
            "email_verificado",
            "tiene_2fa",
            "acepto_privacidad_en",
            "version_privacidad",
            "date_joined",
        ]


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Dirección",
            value={
                "alias": "Huerta",
                "calle": "Camino a La Palma",
                "numero": "km 3",
                "colonia": "La Palma",
                "municipio": "Jiquilpan",
                "estado": "Michoacán",
                "codigo_postal": "59510",
                "referencias": "Portón verde",
                "predeterminada": True,
            },
            request_only=True,
        )
    ]
)
class DireccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Direccion
        fields = [
            "id",
            "alias",
            "calle",
            "numero",
            "colonia",
            "municipio",
            "estado",
            "codigo_postal",
            "referencias",
            "predeterminada",
            "creada_en",
        ]
        read_only_fields = ["id", "creada_en"]


class UsuarioAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nombre",
            "apellidos",
            "telefono",
            "rol",
            "email_verificado",
            "is_active",
            "date_joined",
        ]
        read_only_fields = fields
