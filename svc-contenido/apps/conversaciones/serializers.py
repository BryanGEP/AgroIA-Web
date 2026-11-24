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
    "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
    "titulo": "Manchas en hojas",
    "creada_en": "2026-11-18T22:49:37-06:00",
    "actualizada_en": "2026-11-18T22:50:02-06:00",
}


@extend_schema_serializer(
    examples=[OpenApiExample("Conversación", value=RESUMEN, response_only=True)]
)
class ConversacionResumenSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    usuario_id = serializers.UUIDField(read_only=True)
    titulo = serializers.CharField(read_only=True)
    creada_en = serializers.DateTimeField(read_only=True)
    actualizada_en = serializers.DateTimeField(read_only=True)


ESTADOS = ["pendiente", "listo", "fallido"]


class SolicitudSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    estado = serializers.ChoiceField(choices=ESTADOS, read_only=True)
    codigo = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="En `fallido`: `agente_no_disponible`, `pregunta_invalida`, `vencida`, "
        "`servicio_no_disponible` o `conversacion_llena`.",
    )
    creada_en = serializers.DateTimeField(read_only=True)
    vence_en = serializers.DateTimeField(read_only=True)
    actualizada_en = serializers.DateTimeField(read_only=True)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Pendiente",
            value={
                "id": "5b8e2f1c-3d4a-4e6b-9c7d-1a2b3c4d5e6f",
                "conversacion_id": "6afe7fe1ae4b683f2b9e996f",
                "estado": "pendiente",
                "codigo": None,
                "creada_en": "2026-11-22T12:00:00-06:00",
                "vence_en": "2026-11-22T12:03:00-06:00",
                "actualizada_en": "2026-11-22T12:00:00-06:00",
            },
            response_only=True,
        ),
        OpenApiExample(
            "Lista, con la respuesta",
            value={
                "id": "5b8e2f1c-3d4a-4e6b-9c7d-1a2b3c4d5e6f",
                "conversacion_id": "6afe7fe1ae4b683f2b9e996f",
                "estado": "listo",
                "codigo": None,
                "creada_en": "2026-11-22T12:00:00-06:00",
                "vence_en": "2026-11-22T12:03:00-06:00",
                "actualizada_en": "2026-11-22T12:00:06-06:00",
                "respuesta": "La roña deja costras corchosas en la cáscara.",
                "fuentes": ["Manual de enfermedades del aguacate"],
            },
            response_only=True,
        ),
    ]
)
class SolicitudConRespuestaSerializer(SolicitudSerializer):
    conversacion_id = serializers.CharField(read_only=True)
    respuesta = serializers.CharField(read_only=True, required=False)
    fuentes = serializers.ListField(child=serializers.CharField(), read_only=True, required=False)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Pregunta",
            value={"texto": "¿Cada cuánto aplico el fungicida cúprico?"},
            request_only=True,
        )
    ]
)
class PreguntaSerializer(serializers.Serializer):
    texto = serializers.CharField(max_length=4000, trim_whitespace=True)


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
    solicitud = SolicitudSerializer(
        read_only=True,
        allow_null=True,
        required=False,
        help_text="La última solicitud a la IA de esta conversación (si hay).",
    )
