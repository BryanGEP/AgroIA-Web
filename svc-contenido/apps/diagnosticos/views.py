from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agroia_comun.permisos import EsDuenoOAdmin, es_administrador, usuario_id
from apps.diagnosticos import servicios
from apps.diagnosticos.serializers import (
    CrearDiagnosticoSerializer,
    DiagnosticoSerializer,
    SolicitarDiagnosticoSerializer,
)
from config.limites import DEMASIADAS, LIMITES_IA

ID = OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, description="ObjectId.")
SIN_TOKEN = {401: OpenApiResponse(description="Sin token o token inválido.")}
SIN_ROL = {403: OpenApiResponse(description="El token no trae un rol válido.")}


class DiagnosticoViewSet(viewsets.GenericViewSet):
    """Historial de diagnósticos. El cliente ve los suyos; el administrador, todos."""

    permission_classes = [IsAuthenticated, EsDuenoOAdmin]
    serializer_class = DiagnosticoSerializer
    # Sin ORM: los filtros se validan con serializers y se aplican en servicios.py.
    filter_backends = []
    parser_classes = [MultiPartParser, FormParser]
    lookup_field = "id"
    lookup_value_regex = "[^/]+"

    @extend_schema(
        summary="Listar diagnósticos",
        description=(
            "Paginado de 20 en 20, los más recientes primero. El cliente ve los suyos; "
            "el administrador ve todos."
        ),
        responses={200: DiagnosticoSerializer(many=True), **SIN_TOKEN, **SIN_ROL},
    )
    def list(self, request):
        consulta = servicios.consulta(usuario_id(request), es_administrador(request))
        pagina = self.paginate_queryset(consulta)
        datos = DiagnosticoSerializer(pagina, many=True, context={"request": request}).data
        return self.get_paginated_response(datos)

    @extend_schema(
        summary="Guardar un diagnóstico",
        description=(
            "Guarda la imagen (JPG, PNG o WebP, máximo 5 MB) con default_storage y el resultado "
            "que devolvió svc-ia. `probabilidades` va como texto JSON con las tres clases, que "
            "deben sumar 1, y `confianza` debe ser la probabilidad de `clase`."
        ),
        request={"multipart/form-data": CrearDiagnosticoSerializer},
        responses={
            201: DiagnosticoSerializer,
            400: OpenApiResponse(description="Imagen o resultado inválidos (`validacion`)."),
            **SIN_TOKEN,
            **SIN_ROL,
        },
    )
    def create(self, request):
        datos = CrearDiagnosticoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        diagnostico = servicios.crear(usuario_id(request), **datos.validated_data)
        return Response(
            DiagnosticoSerializer(diagnostico, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Ver un diagnóstico",
        description="Dueño o administrador. Para cualquier otro usuario responde 404.",
        parameters=[ID],
        responses={
            200: DiagnosticoSerializer,
            **SIN_TOKEN,
            **SIN_ROL,
            404: OpenApiResponse(description="No existe, el id no es válido o es de otro."),
        },
    )
    def retrieve(self, request, id=None):
        diagnostico = servicios.obtener(usuario_id(request), es_administrador(request), id)
        return Response(DiagnosticoSerializer(diagnostico, context={"request": request}).data)

    @extend_schema(
        summary="Foto de un diagnóstico",
        description=(
            "Devuelve el archivo de la foto (JPG, PNG o WebP) solo al dueño o a un "
            "administrador; para cualquier otro usuario responde 404, igual que el detalle. "
            "Lleva `Cache-Control: private`: la foto es un dato personal y no debe guardarse "
            "en cachés compartidas. Es la única forma de obtener la foto: svc-contenido no la "
            "sirve como archivo estático."
        ),
        parameters=[ID],
        responses={
            (200, "image/*"): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="El archivo de la imagen."
            ),
            **SIN_TOKEN,
            **SIN_ROL,
            404: OpenApiResponse(description="No existe, el id no es válido o es de otro."),
        },
    )
    @action(detail=True, methods=["get"], url_path="imagen", url_name="imagen")
    def imagen(self, request, id=None):
        diagnostico = servicios.obtener(usuario_id(request), es_administrador(request), id)
        archivo, tipo = servicios.abrir_imagen(diagnostico)
        respuesta = FileResponse(archivo, content_type=tipo)
        respuesta["Cache-Control"] = "private, max-age=3600"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta

    @extend_schema(
        summary="Solicitar un diagnóstico (asíncrono)",
        description=(
            "Guarda la foto (JPG o PNG, máximo 5 MB) y deja el diagnóstico `pendiente`. Pone una "
            "copia temporal de la imagen en Redis (vence con la solicitud) y publica "
            "`diagnostico_solicitado`, que lleva solo los ids. Responde 202 de inmediato; el "
            "estado se consulta en `GET /diagnosticos/<id>/`. Si el worker de svc-ia no puede "
            "clasificar (hoy, `modelo_no_disponible`), queda `fallido` y se borra la foto."
        ),
        request={"multipart/form-data": SolicitarDiagnosticoSerializer},
        responses={
            202: DiagnosticoSerializer,
            400: OpenApiResponse(description="Imagen inválida (`validacion`)."),
            **SIN_TOKEN,
            **SIN_ROL,
            **DEMASIADAS,
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="solicitar",
        url_name="solicitar",
        throttle_classes=LIMITES_IA,
    )
    def solicitar(self, request):
        datos = SolicitarDiagnosticoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        diagnostico = servicios.solicitar(usuario_id(request), datos.validated_data["imagen"])
        return Response(
            DiagnosticoSerializer(diagnostico, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )
