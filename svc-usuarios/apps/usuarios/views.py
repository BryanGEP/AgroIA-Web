from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agroia_comun.permisos import EsAdministrador, EsDuenoOAdmin, usuario_id
from apps.usuarios import servicios
from apps.usuarios.filters import UsuarioFilter
from apps.usuarios.models import Direccion, Usuario
from apps.usuarios.serializers import (
    DireccionSerializer,
    PerfilSerializer,
    RegistroRespuestaSerializer,
    RegistroSerializer,
    UsuarioAdminSerializer,
)

SIN_TOKEN = {401: OpenApiResponse(description="Sin token o token inválido.")}
SIN_ROL = {403: OpenApiResponse(description="El token no trae un rol válido.")}
INVALIDO = {400: OpenApiResponse(description="Datos inválidos (`validacion`, con `campos`).")}
NO_ENCONTRADO = {404: OpenApiResponse(description="No existe o no es tuya.")}
MENSAJE_REGISTRO = "Cuenta creada. Revisa tu correo para verificar tu cuenta."


class RegistroView(APIView):
    # Público: tampoco lee tokens, para que uno vencido no impida registrarse.
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Registrar usuario",
        description=(
            "Público. Crea la cuenta como `cliente` y sin verificar; no devuelve tokens. "
            "El correo se normaliza (sin espacios y en minúsculas) y no puede repetirse "
            "aunque cambien las mayúsculas. La contraseña pasa los validadores de Django. "
            "Hay que aceptar el aviso de privacidad. Errores en `campos`: `email_registrado`, "
            "`password_no_coincide`, `privacidad_no_aceptada` y los mensajes de contraseña."
        ),
        request=RegistroSerializer,
        responses={
            201: RegistroRespuestaSerializer,
            400: OpenApiResponse(
                description="Datos inválidos.",
                examples=[
                    OpenApiExample(
                        "Correo ya registrado",
                        value={
                            "error": "validacion",
                            "detalle": "Revisa los datos enviados.",
                            "campos": {"email": ["email_registrado"]},
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request):
        datos = RegistroSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = servicios.registrar_usuario(
            email=datos.validated_data["email"],
            password=datos.validated_data["password"],
            nombre=datos.validated_data["nombre"],
            apellidos=datos.validated_data["apellidos"],
        )
        return Response(
            {"id": usuario.id, "email": usuario.email, "mensaje": MENSAJE_REGISTRO},
            status=status.HTTP_201_CREATED,
        )


class PerfilView(APIView):
    """El usuario del token (su `user_id` es el `id` del Usuario)."""

    permission_classes = [IsAuthenticated, EsDuenoOAdmin]

    @extend_schema(
        summary="Ver mi perfil",
        responses={
            200: PerfilSerializer,
            **SIN_TOKEN,
            **SIN_ROL,
            404: OpenApiResponse(description="El usuario del token no existe."),
        },
    )
    def get(self, request):
        return Response(PerfilSerializer(servicios.usuario_del_token(request)).data)

    @extend_schema(
        summary="Editar mi perfil",
        description=(
            "Solo cambia `nombre`, `apellidos` y `telefono`. El correo, el rol y los campos "
            "de seguridad son de solo lectura y se ignoran si se envían."
        ),
        request=PerfilSerializer,
        responses={200: PerfilSerializer, **INVALIDO, **SIN_TOKEN, **SIN_ROL},
    )
    def patch(self, request):
        datos = PerfilSerializer(
            servicios.usuario_del_token(request), data=request.data, partial=True
        )
        datos.is_valid(raise_exception=True)
        datos.save()
        return Response(datos.data)


@extend_schema_view(
    list=extend_schema(
        summary="Mis direcciones",
        description="Solo las propias; la predeterminada primero.",
        responses={200: DireccionSerializer(many=True), **SIN_TOKEN, **SIN_ROL},
    ),
    retrieve=extend_schema(
        summary="Ver una dirección",
        responses={200: DireccionSerializer, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    ),
    create=extend_schema(
        summary="Agregar dirección",
        description=(
            "La primera dirección queda como predeterminada. Si la nueva viene con "
            "`predeterminada: true`, las demás dejan de serlo."
        ),
        responses={201: DireccionSerializer, **INVALIDO, **SIN_TOKEN, **SIN_ROL},
    ),
    partial_update=extend_schema(
        summary="Editar dirección",
        description="Con `predeterminada: true`, las demás dejan de serlo en la misma transacción.",
        responses={200: DireccionSerializer, **INVALIDO, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    ),
    destroy=extend_schema(
        summary="Borrar dirección",
        description="Si era la predeterminada, pasa a serlo la más reciente que quede.",
        responses={204: None, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    ),
)
class DireccionViewSet(viewsets.ModelViewSet):
    serializer_class = DireccionSerializer
    permission_classes = [IsAuthenticated, EsDuenoOAdmin]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # al generar el esquema OpenAPI
            return Direccion.objects.none()
        # Solo las propias, también para el administrador: las ajenas dan 404.
        return Direccion.objects.filter(usuario_id=usuario_id(self.request))

    def perform_create(self, serializer):
        usuario = servicios.usuario_del_token(self.request)
        serializer.instance = servicios.crear_direccion(usuario, serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = servicios.actualizar_direccion(
            serializer.instance, serializer.validated_data
        )

    def perform_destroy(self, instance):
        servicios.borrar_direccion(instance)


@extend_schema_view(
    list=extend_schema(
        summary="Listar usuarios (administrador)",
        description=(
            "Solo administrador. Paginado de 20 en 20, los más recientes primero. Filtros: "
            "`rol` y `q` (busca en correo, nombre y apellidos). El cambio de rol por API llega "
            "en la Entrega 3."
        ),
        responses={
            200: UsuarioAdminSerializer(many=True),
            **INVALIDO,
            **SIN_TOKEN,
            403: OpenApiResponse(description="El usuario no es administrador."),
        },
    )
)
class UsuarioViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioAdminSerializer
    # Pide token aunque AUTH_ACTIVA sea False: son datos personales.
    permission_classes = [IsAuthenticated, EsAdministrador]
    filterset_class = UsuarioFilter
    ordering_fields = ["date_joined", "email"]
    ordering = ["-date_joined", "-id"]
