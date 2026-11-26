import redis
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from agroia_comun.errores import ErrorDeNegocio
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
            "Solo administrador. Filtros: `tipo`, `usuario_id` (usuario afectado), "
            "`correlacion_id` (todos los eventos de un flujo), `pedido_id` (la línea de tiempo "
            "de un pedido), `desde` y `hasta` (AAAA-MM-DD, ambos inclusive). Paginado de 20 en "
            "20, los más recientes primero."
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
            "Solo administrador; la fecha la pone el servidor. Los eventos de negocio llegan "
            "solos por Redis (consumidor `consumir_eventos`, ver docs/eventos.md); este POST "
            "queda para registros manuales."
        ),
        request=EventoSerializer,
        responses={201: EventoSerializer, **ERRORES_ADMIN},
    )
    def create(self, request):
        datos = EventoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        evento = servicios.registrar(**datos.validated_data)
        return Response(EventoSerializer(evento).data, status=status.HTTP_201_CREATED)


class _ConsumidorSerializer(serializers.Serializer):
    nombre = serializers.CharField()
    pendientes = serializers.IntegerField()
    inactivo_ms = serializers.IntegerField()


class _GrupoSerializer(serializers.Serializer):
    grupo = serializers.CharField()
    pendientes = serializers.IntegerField()
    sin_leer = serializers.IntegerField(allow_null=True, help_text="Retraso del grupo (lag).")
    consumidores = _ConsumidorSerializer(many=True)


class _StreamSerializer(serializers.Serializer):
    stream = serializers.CharField()
    largo = serializers.IntegerField()
    grupos = _GrupoSerializer(many=True)


class _FallidoSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Id del mensaje en el stream de fallidos.")
    fecha = serializers.DateTimeField(allow_null=True)
    tipo = serializers.CharField(allow_null=True)
    grupo = serializers.CharField(allow_null=True)
    stream = serializers.CharField(allow_null=True)
    intentos = serializers.IntegerField(allow_null=True)
    motivo = serializers.CharField(allow_null=True, help_text="Solo el nombre de la excepción.")
    datos_omitidos = serializers.CharField(allow_null=True)


class _FallidosSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    ultimos = _FallidoSerializer(many=True, help_text="Los 10 más recientes.")


class EstadoEventosSerializer(serializers.Serializer):
    streams = _StreamSerializer(many=True)
    fallidos = _FallidosSerializer()


class EstadoEventosView(APIView):
    """Estado de los streams de eventos, para el panel de administración (solo lectura)."""

    permission_classes = [EsAdministrador]

    @extend_schema(
        summary="Estado de los eventos",
        description=(
            "Solo administrador. Lo mismo que `python -m agroia_comun.eventos estado`: cada "
            "stream con su largo; por grupo, los pendientes, el retraso (`sin_leer`) y los "
            "consumidores con su tiempo inactivo; y los últimos 10 fallidos con su fecha, tipo, "
            "grupo, intentos y el **nombre** de la excepción. Nunca el sobre ni sus datos. "
            "Reprocesar y descartar siguen siendo comandos (ver docs/eventos.md, «Operación»)."
        ),
        responses={
            200: EstadoEventosSerializer,
            401: OpenApiResponse(description="Sin token o token inválido."),
            403: OpenApiResponse(description="El usuario no es administrador."),
            503: OpenApiResponse(description="Redis no responde (`eventos_no_disponible`)."),
        },
        examples=[
            OpenApiExample(
                "Estado",
                response_only=True,
                value={
                    "streams": [
                        {
                            "stream": "agroia:eventos:tienda",
                            "largo": 42,
                            "grupos": [
                                {
                                    "grupo": "svc-contenido",
                                    "pendientes": 0,
                                    "sin_leer": 0,
                                    "consumidores": [
                                        {"nombre": "a1b2c3", "pendientes": 0, "inactivo_ms": 1200}
                                    ],
                                }
                            ],
                        }
                    ],
                    "fallidos": {
                        "total": 1,
                        "ultimos": [
                            {
                                "id": "1795210684000-0",
                                "fecha": "2026-11-26T18:30:00+00:00",
                                "tipo": "pedido_creado",
                                "grupo": "svc-contenido",
                                "stream": "agroia:eventos:tienda",
                                "intentos": 4,
                                "motivo": "ConnectionError",
                                "datos_omitidos": None,
                            }
                        ],
                    },
                },
            )
        ],
    )
    def get(self, request):
        try:
            datos = servicios.estado_de_eventos()
        except redis.RedisError as error:
            raise ErrorDeNegocio(
                "eventos_no_disponible",
                "No pudimos leer el estado de los eventos. Intenta de nuevo en un momento.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error
        return Response(datos)
