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


RESUMEN = {
    "id": "6afe7fe1ae4b683f2b9e996f",
    "usuario_id": 10,
    "titulo": "Manchas en hojas",
    "creada_en": "2026-11-18T22:49:37-06:00",
    "actualizada_en": "2026-11-18T22:50:02-06:00",
}


@extend_schema_serializer(
    examples=[OpenApiExample("Conversación", value=RESUMEN, response_only=True)]
)
class ConversacionResumenSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    usuario_id = serializers.IntegerField(read_only=True)
    titulo = serializers.CharField(read_only=True)
    creada_en = serializers.DateTimeField(read_only=True)
    actualizada_en = serializers.DateTimeField(read_only=True)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Conversación con mensajes",
            value={
                **RESUMEN,
                "mensajes": [
                    {
                        "rol": "usuario",
                        "texto": "¿Qué es la roña del aguacate?",
                        "fecha": "2026-11-18T22:49:50-06:00",
                    },
                    {
                        "rol": "agente",
                        "texto": "La roña la causa el hongo Elsinoë perseae: forma costras "
                        "cafés, ásperas y corchosas en la cáscara.",
                        "fuentes": [
                            "Marroquín-Pimentel (1999), Revista Chapingo Serie Horticultura 5"
                        ],
                        "fecha": "2026-11-18T22:50:02-06:00",
                    },
                ],
            },
            response_only=True,
        )
    ]
)
class ConversacionSerializer(ConversacionResumenSerializer):
    mensajes = MensajeSerializer(many=True, read_only=True)
