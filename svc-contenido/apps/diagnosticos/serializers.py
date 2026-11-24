import json
import math

from django.urls import reverse
from drf_spectacular.utils import OpenApiExample, extend_schema_field, extend_schema_serializer
from rest_framework import serializers

CLASES = ["sano", "rona", "antracnosis"]
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024  # 5 MB
EXTENSIONES = {"jpg", "jpeg", "png", "webp"}


class SolicitarDiagnosticoSerializer(serializers.Serializer):
    """La foto a diagnosticar (multipart/form-data). Solo JPG o PNG: los que lee svc-ia."""

    imagen = serializers.ImageField(help_text="JPG o PNG, máximo 5 MB.")

    def validate_imagen(self, imagen):
        if imagen.size > TAMANO_MAXIMO_IMAGEN:
            raise serializers.ValidationError("La imagen no puede pesar más de 5 MB.")
        inicio = imagen.read(8)
        imagen.seek(0)
        if not inicio.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
            raise serializers.ValidationError("Solo se aceptan imágenes JPG o PNG.")
        return imagen


class CrearDiagnosticoSerializer(serializers.Serializer):
    """Resultado de svc-ia más la imagen original. Se envía como multipart/form-data."""

    imagen = serializers.ImageField(help_text="JPG, PNG o WebP, máximo 5 MB.")
    clase = serializers.ChoiceField(choices=CLASES)
    confianza = serializers.FloatField(min_value=0.0, max_value=1.0)
    probabilidades = serializers.JSONField(
        help_text="Texto JSON con las tres clases, por ejemplo "
        '{"sano": 0.03, "rona": 0.06, "antracnosis": 0.91}.'
    )
    modelo_version = serializers.CharField(max_length=50)

    def validate_imagen(self, imagen):
        extension = imagen.name.rsplit(".", 1)[-1].lower() if "." in imagen.name else ""
        if extension not in EXTENSIONES:
            raise serializers.ValidationError("Solo se aceptan imágenes JPG, PNG o WebP.")
        if imagen.size > TAMANO_MAXIMO_IMAGEN:
            raise serializers.ValidationError("La imagen no puede pesar más de 5 MB.")
        return imagen

    def validate_probabilidades(self, valor):
        # En multipart el JSON llega como texto.
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except json.JSONDecodeError as error:
                raise serializers.ValidationError("No es JSON válido.") from error
        if not isinstance(valor, dict) or set(valor) != set(CLASES):
            raise serializers.ValidationError(
                f"Debe ser un objeto con exactamente estas claves: {', '.join(CLASES)}."
            )
        if not all(isinstance(p, int | float) and 0 <= p <= 1 for p in valor.values()):
            raise serializers.ValidationError("Cada probabilidad debe estar entre 0 y 1.")
        if not math.isclose(sum(valor.values()), 1.0, abs_tol=0.01):
            raise serializers.ValidationError("Las probabilidades deben sumar 1.")
        return {clase: float(valor[clase]) for clase in CLASES}

    def validate(self, datos: dict) -> dict:
        if not math.isclose(
            datos["confianza"], datos["probabilidades"][datos["clase"]], abs_tol=0.001
        ):
            raise serializers.ValidationError(
                {"confianza": ["Debe ser igual a la probabilidad de la clase elegida."]}
            )
        return datos


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Diagnóstico",
            value={
                "id": "6adad34bdf98ab47ebafa190",
                "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
                "imagen_url": (
                    "http://svc-contenido:8000/api/v1/diagnosticos/6adad34bdf98ab47ebafa190/imagen/"
                ),
                "clase": "antracnosis",
                "confianza": 0.91,
                "probabilidades": {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
                "modelo_version": "v1",
                "creado_en": "2026-10-22T21:23:55-06:00",
            },
            response_only=True,
        )
    ]
)
class DiagnosticoSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    usuario_id = serializers.UUIDField(read_only=True)
    imagen_url = serializers.SerializerMethodField()
    clase = serializers.ChoiceField(choices=CLASES, read_only=True, allow_null=True)
    confianza = serializers.FloatField(read_only=True, allow_null=True)
    probabilidades = serializers.DictField(
        child=serializers.FloatField(), read_only=True, allow_null=True
    )
    modelo_version = serializers.CharField(read_only=True, allow_null=True)
    creado_en = serializers.DateTimeField(read_only=True)
    estado = serializers.SerializerMethodField(
        help_text="`pendiente`, `listo` o `fallido` (los diagnósticos de antes, `listo`)."
    )
    codigo = serializers.CharField(read_only=True, allow_null=True, default=None)
    es_prueba = serializers.SerializerMethodField(
        help_text="True si lo dio el clasificador de prueba: no es un diagnóstico real."
    )

    @extend_schema_field(serializers.ChoiceField(choices=["pendiente", "listo", "fallido"]))
    def get_estado(self, diagnostico: dict) -> str:
        return diagnostico.get("estado") or "listo"

    def get_es_prueba(self, diagnostico: dict) -> bool:
        return str(diagnostico.get("modelo_version") or "").startswith("prueba-")

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_imagen_url(self, diagnostico: dict) -> str | None:
        """El endpoint protegido de la foto, no la ruta del archivo (son datos personales).
        None si ya no hay foto (un diagnóstico fallido la borra)."""
        if not diagnostico.get("imagen"):
            return None
        url = reverse("diagnostico-imagen", kwargs={"id": str(diagnostico["_id"])})
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
