from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agroia_comun.permisos import EsDuenoOAdmin, usuario_id
from apps.conversaciones import servicios
from apps.conversaciones.serializers import (
    ConversacionResumenSerializer,
    ConversacionSerializer,
    CrearConversacionSerializer,
    MensajeSerializer,
)

ID = OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, description="ObjectId.")
SIN_TOKEN = {401: OpenApiResponse(description="Sin token o token inválido.")}
SIN_ROL = {403: OpenApiResponse(description="El token no trae un rol válido.")}
INVALIDO = {400: OpenApiResponse(description="Datos inválidos (`validacion`, con `campos`).")}
NO_ENCONTRADO = {
    404: OpenApiResponse(description="No existe, el id no es válido o es de otro usuario.")
}


class ConversacionViewSet(viewsets.GenericViewSet):
    """Conversaciones con el agente. Son privadas: cada usuario, también el
    administrador, solo ve las suyas."""

    permission_classes = [IsAuthenticated, EsDuenoOAdmin]
    serializer_class = ConversacionSerializer
    # Sin ORM: los filtros se validan con serializers y se aplican en servicios.py.
    filter_backends = []
    lookup_field = "id"
    lookup_value_regex = "[^/]+"

    @extend_schema(
        summary="Listar mis conversaciones",
        description="Paginado de 20 en 20, las más recientes primero. No incluye los mensajes.",
        responses={200: ConversacionResumenSerializer(many=True), **SIN_TOKEN, **SIN_ROL},
    )
    def list(self, request):
        pagina = self.paginate_queryset(servicios.consulta_propias(usuario_id(request)))
        return self.get_paginated_response(ConversacionResumenSerializer(pagina, many=True).data)

    @extend_schema(
        summary="Crear conversación",
        request=CrearConversacionSerializer,
        responses={201: ConversacionSerializer, **INVALIDO, **SIN_TOKEN, **SIN_ROL},
    )
    def create(self, request):
        datos = CrearConversacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conversacion = servicios.crear(usuario_id(request), datos.validated_data["titulo"])
        return Response(ConversacionSerializer(conversacion).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Ver conversación con sus mensajes",
        parameters=[ID],
        responses={200: ConversacionSerializer, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    )
    def retrieve(self, request, id=None):
        conversacion = servicios.obtener_propia(usuario_id(request), id)
        return Response(ConversacionSerializer(conversacion).data)

    @extend_schema(
        summary="Borrar conversación",
        parameters=[ID],
        responses={204: None, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    )
    def destroy(self, request, id=None):
        servicios.borrar(usuario_id(request), id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Agregar mensaje",
        description=(
            "Agrega un mensaje del usuario o del agente (este último con `fuentes` opcionales). "
            f"Una conversación admite hasta {servicios.LIMITE_MENSAJES} mensajes; al llegar al "
            "límite responde 409 `conversacion_llena` y hay que iniciar otra."
        ),
        parameters=[ID],
        request=MensajeSerializer,
        responses={
            201: ConversacionSerializer,
            **INVALIDO,
            **SIN_TOKEN,
            **SIN_ROL,
            **NO_ENCONTRADO,
            409: OpenApiResponse(description="`conversacion_llena`."),
        },
    )
    @action(detail=True, methods=["post"])
    def mensajes(self, request, id=None):
        datos = MensajeSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conversacion = servicios.agregar_mensaje(
            usuario_id(request),
            id,
            datos.validated_data["rol"],
            datos.validated_data["texto"],
            datos.validated_data.get("fuentes"),
        )
        return Response(ConversacionSerializer(conversacion).data, status=status.HTTP_201_CREATED)
