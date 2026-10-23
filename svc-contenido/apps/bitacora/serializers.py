from datetime import datetime, time, timedelta

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Pedido creado",
            value={
                "tipo": "pedido_creado",
                "usuario_id": 10,
                "servicio": "svc-tienda",
                "datos": {"pedido_id": 7, "total": "840.50"},
            },
            request_only=True,
        )
    ]
)
class EventoSerializer(serializers.Serializer):
    id = serializers.CharField(source="_id", read_only=True)
    tipo = serializers.RegexField(
        r"^[a-z][a-z0-9_]*$",
        max_length=50,
        error_messages={"invalid": "Usa minúsculas, números y guiones bajos (pedido_creado)."},
    )
    usuario_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    servicio = serializers.CharField(max_length=50)
    datos = serializers.DictField(required=False, default=dict)
    fecha = serializers.DateTimeField(read_only=True)


class FiltroBitacoraSerializer(serializers.Serializer):
    """Filtros de GET /bitacora/. Las fechas son días completos en la zona del servidor."""

    tipo = serializers.CharField(required=False, max_length=50)
    desde = serializers.DateField(required=False, help_text="AAAA-MM-DD, inclusive.")
    hasta = serializers.DateField(required=False, help_text="AAAA-MM-DD, inclusive.")

    def validate(self, datos: dict) -> dict:
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError({"hasta": ["Debe ser igual o posterior a desde."]})
        zona = timezone.get_current_timezone()
        if desde:
            datos["desde"] = datetime.combine(desde, time.min, tzinfo=zona)
        if hasta:
            datos["hasta"] = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=zona)
        return datos
