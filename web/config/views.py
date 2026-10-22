"""Vistas de infraestructura del servicio (no pertenecen a ninguna app)."""

from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@extend_schema(
    summary="Estado del servicio",
    description="Comprobación de estado para Docker y el gateway. No requiere autenticación.",
    responses=inline_serializer("Salud", fields={"estado": serializers.CharField()}),
    examples=[OpenApiExample("Servicio activo", value={"estado": "ok"})],
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def salud(request: Request) -> Response:
    return Response({"estado": "ok"})
