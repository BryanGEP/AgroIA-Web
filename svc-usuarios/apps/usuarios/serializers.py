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
    # Máximo 128, como en los demás endpoints: evita mandar megabytes al hash y a los
    # validadores de contraseña.
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128, style={"input_type": "password"}
    )
    password_confirmacion = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128, style={"input_type": "password"}
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


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Cuenta creada",
            value={
                "id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
                "email": "maria.lopez@example.com",
                "mensaje": "Cuenta creada. Revisa tu correo para verificar tu cuenta.",
            },
            response_only=True,
        )
    ]
)
class RegistroRespuestaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    mensaje = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Editar perfil",
            value={"nombre": "María", "apellidos": "López Ramírez", "telefono": "3531234567"},
            request_only=True,
        ),
        OpenApiExample(
            "Perfil",
            value={
                "id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
                "email": "maria.lopez@example.com",
                "nombre": "María",
                "apellidos": "López Ramírez",
                "telefono": "3531234567",
                "rol": "cliente",
                "email_verificado": False,
                "tiene_2fa": False,
                "acepto_privacidad_en": "2026-11-18T22:50:07-06:00",
                "version_privacidad": "2026-11",
                "date_joined": "2026-11-18T22:50:07-06:00",
            },
            response_only=True,
        ),
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
        ),
        OpenApiExample(
            "Dirección guardada",
            value={
                "id": 10,
                "alias": "Huerta",
                "calle": "Camino a La Palma",
                "numero": "km 3",
                "colonia": "La Palma",
                "municipio": "Jiquilpan",
                "estado": "Michoacán",
                "codigo_postal": "59510",
                "referencias": "Portón verde",
                "predeterminada": True,
                "creada_en": "2026-11-18T22:50:10-06:00",
            },
            response_only=True,
        ),
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


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Usuario",
            value={
                "id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
                "email": "maria.lopez@example.com",
                "nombre": "María",
                "apellidos": "López Ramírez",
                "telefono": "3531234567",
                "rol": "cliente",
                "email_verificado": False,
                "is_active": True,
                "date_joined": "2026-11-18T22:50:07-06:00",
            },
            response_only=True,
        )
    ]
)
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


# --- Autenticación -------------------------------------------------------------------

ACCESS_EJEMPLO = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIn0.firma"
REFRESH_EJEMPLO = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCJ9.firma"
USUARIO_ID_EJEMPLO = "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d"


def _password(**extra) -> serializers.CharField:
    return serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}, **extra
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Login",
            value={"email": "maria.lopez@example.com", "password": "Aguacate-Hass-2026"},
            request_only=True,
        )
    ]
)
class LoginSerializer(serializers.Serializer):
    # CharField y no EmailField: un correo mal escrito también es "credenciales inválidas".
    email = serializers.CharField(max_length=254)
    password = _password(max_length=128)


class UsuarioDelLoginSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    rol = serializers.CharField()
    email_verificado = serializers.BooleanField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Sesión iniciada",
            value={
                "access": ACCESS_EJEMPLO,
                "refresh": REFRESH_EJEMPLO,
                "usuario": {
                    "id": USUARIO_ID_EJEMPLO,
                    "nombre": "María",
                    "rol": "cliente",
                    "email_verificado": True,
                },
            },
            response_only=True,
        )
    ]
)
class LoginRespuestaSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Token de acceso RS256; vence en 15 minutos.")
    refresh = serializers.CharField(help_text="Token de renovación; vence en 7 días.")
    usuario = UsuarioDelLoginSerializer()


@extend_schema_serializer(
    examples=[OpenApiExample("Refresh", value={"refresh": REFRESH_EJEMPLO}, request_only=True)]
)
class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Par nuevo",
            value={"access": ACCESS_EJEMPLO, "refresh": REFRESH_EJEMPLO},
            response_only=True,
        )
    ]
)
class ParDeTokensSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class MensajeSerializer(serializers.Serializer):
    mensaje = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Token del enlace",
            value={"token": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d:1tB2xY:Qm9yZGVyLXNpZ25hdHVyZQ"},
            request_only=True,
        )
    ]
)
class TokenDeVerificacionSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


@extend_schema_serializer(
    examples=[
        OpenApiExample("Correo", value={"email": "maria.lopez@example.com"}, request_only=True)
    ]
)
class CorreoSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def to_internal_value(self, data):
        if hasattr(data, "copy") and isinstance(data.get("email"), str):
            data = data.copy()
            data["email"] = normalizar_email(data["email"])
        return super().to_internal_value(data)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Restablecer",
            value={
                "uid": "OGQzZjZjMmEtMWI0ZS00ZjdhLTljNWQtMmU2ZjhhMGIxYzNk",
                "token": "cf3k2a-5d0f7b1c9e8a7d6c5b4a3f2e1d0c9b8a",
                "password": "Hass-Mendez-2026",
                "password_confirmacion": "Hass-Mendez-2026",
            },
            request_only=True,
        )
    ]
)
class RestablecerSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=100)
    password = _password(max_length=128)
    password_confirmacion = _password(max_length=128)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Cambiar contraseña",
            value={
                "password_actual": "Aguacate-Hass-2026",
                "password_nueva": "Hass-Mendez-2026",
                "password_confirmacion": "Hass-Mendez-2026",
            },
            request_only=True,
        )
    ]
)
class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = _password(max_length=128)
    password_nueva = _password(max_length=128)
    password_confirmacion = _password(max_length=128)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Contraseña cambiada",
            value={
                "access": ACCESS_EJEMPLO,
                "refresh": REFRESH_EJEMPLO,
                "mensaje": "Contraseña cambiada. Cerramos la sesión en tus otros dispositivos.",
            },
            response_only=True,
        )
    ]
)
class CambioPasswordRespuestaSerializer(ParDeTokensSerializer):
    mensaje = serializers.CharField()


@extend_schema_serializer(
    examples=[OpenApiExample("Nuevo rol", value={"rol": "administrador"}, request_only=True)]
)
class CambiarRolSerializer(serializers.Serializer):
    rol = serializers.ChoiceField(choices=Usuario.Rol.choices)
