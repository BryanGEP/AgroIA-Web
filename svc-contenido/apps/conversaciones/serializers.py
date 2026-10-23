from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[OpenApiExample("Nueva", value={"titulo": "Manchas en hojas"}, request_only=True)]
)
class CrearConversacionSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120, required=False, default="Nueva conversación")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Pregunta del usuario",
            value={"rol": "usuario", "texto": "¿Cómo distingo la roña de la antracnosis?"},
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta del agente",
            value={
                "rol": "agente",
                "texto": "La roña deja costras corchosas; la antracnosis, manchas hundidas.",
                "fuentes": ["Manual de enfermedades del aguacate"],
            },
            request_only=True,
        ),
    ]
)
class MensajeSerializer(serializers.Serializer):
    rol = serializers.ChoiceField(choices=["usuario", "agente"])
    texto = serializers.CharField(max_length=10000)
    fuentes = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        max_length=20,
        help_text="Solo en mensajes del agente.",
    )
    fecha = serializers.DateTimeField(read_only=True)

    def validate(self, datos: dict) -> dict:
        if datos.get("fuentes") and datos["rol"] != "agente":
            raise serializers.ValidationError(
                {"fuentes": ["Solo los mensajes del agente llevan fuentes."]}
            )
        return datos


class ConversacionResumenSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    usuario_id = serializers.IntegerField(read_only=True)
    titulo = serializers.CharField(read_only=True)
    creada_en = serializers.DateTimeField(read_only=True)
    actualizada_en = serializers.DateTimeField(read_only=True)


class ConversacionSerializer(ConversacionResumenSerializer):
    mensajes = MensajeSerializer(many=True, read_only=True)
