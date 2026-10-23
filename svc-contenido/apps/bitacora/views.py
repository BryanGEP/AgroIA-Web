from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.response import Response

from agroia_comun.permisos import EsAdministrador
from apps.bitacora import servicios
from apps.bitacora.serializers import EventoSerializer, FiltroBitacoraSerializer

ERRORES_ADMIN = {
    400: OpenApiResponse(description="Datos o filtros inválidos (`validacion`, con `campos`)."),
    401: OpenApiResponse(description="Sin token o token inválido."),
    403: OpenApiResponse(description="El usuario no es administrador."),
}


class BitacoraViewSet(viewsets.GenericViewSet):
    """Bitácora de actividad, solo para administradores."""

    permission_classes = [EsAdministrador]
    serializer_class = EventoSerializer
    # Sin ORM: los filtros se validan con serializers y se aplican en servicios.py.
    filter_backends = []

    @extend_schema(
        summary="Consultar la bitácora",
        description=(
            "Solo administrador. Filtros: `tipo`, `desde` y `hasta` (AAAA-MM-DD, ambos "
            "inclusive). Paginado de 20 en 20, los más recientes primero."
        ),
        parameters=[FiltroBitacoraSerializer],
        responses={200: EventoSerializer(many=True), **ERRORES_ADMIN},
    )
    def list(self, request):
        filtros = FiltroBitacoraSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(servicios.consulta(**filtros.validated_data))
        return self.get_paginated_response(EventoSerializer(pagina, many=True).data)

    @extend_schema(
        summary="Registrar un evento",
        description=(
            "Solo administrador; la fecha la pone el servidor. En la Entrega 4 la bitácora se "
            "llenará con los eventos que publiquen los servicios."
        ),
        request=EventoSerializer,
        responses={201: EventoSerializer, **ERRORES_ADMIN},
    )
    def create(self, request):
        datos = EventoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        evento = servicios.registrar(**datos.validated_data)
        return Response(EventoSerializer(evento).data, status=status.HTTP_201_CREATED)
