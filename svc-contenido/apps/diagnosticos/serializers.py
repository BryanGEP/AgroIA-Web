import json
import math

from django.core.files.storage import default_storage
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

CLASES = ["sano", "rona", "antracnosis"]
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024  # 5 MB
EXTENSIONES = {"jpg", "jpeg", "png", "webp"}


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


class DiagnosticoSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    usuario_id = serializers.IntegerField(read_only=True)
    imagen_url = serializers.SerializerMethodField()
    clase = serializers.ChoiceField(choices=CLASES, read_only=True)
    confianza = serializers.FloatField(read_only=True)
    probabilidades = serializers.DictField(child=serializers.FloatField(), read_only=True)
    modelo_version = serializers.CharField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)

    @extend_schema_field(serializers.URLField())
    def get_imagen_url(self, diagnostico: dict) -> str:
        url = default_storage.url(diagnostico["imagen"])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
