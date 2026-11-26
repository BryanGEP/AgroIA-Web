import uuid

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from agroia_comun.eventos.en_django import correlacion_de
from agroia_comun.permisos import EsAdministrador, EsDuenoOAdmin, usuario_id
from apps.usuarios import servicios
from apps.usuarios.filters import UsuarioFilter
from apps.usuarios.models import Direccion, Usuario
from apps.usuarios.serializers import (
    CambiarPasswordSerializer,
    CambiarRolSerializer,
    CambioPasswordRespuestaSerializer,
    CorreoSerializer,
    DireccionSerializer,
    LoginRespuestaSerializer,
    LoginSerializer,
    MensajeSerializer,
    ParDeTokensSerializer,
    PerfilSerializer,
    RefreshSerializer,
    RegistroRespuestaSerializer,
    RegistroSerializer,
    RestablecerSerializer,
    TokenDeVerificacionSerializer,
    UsuarioAdminSerializer,
    UsuarioDelLoginSerializer,
)
from apps.usuarios.throttles import LimitePorCorreo

SIN_TOKEN = {401: OpenApiResponse(description="Sin token o token inválido.")}
SIN_ROL = {403: OpenApiResponse(description="El token no trae un rol válido.")}
INVALIDO = {400: OpenApiResponse(description="Datos inválidos (`validacion`, con `campos`).")}
NO_ENCONTRADO = {404: OpenApiResponse(description="No existe o no es tuya.")}
MENSAJE_REGISTRO = "Cuenta creada. Revisa tu correo para verificar tu cuenta."


class RegistroView(APIView):
    # Público: tampoco lee tokens, para que uno vencido no impida registrarse.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "registro"

    @extend_schema(
        summary="Registrar usuario",
        description=(
            "Público. Crea la cuenta como `cliente` y sin verificar; no devuelve tokens. "
            "El correo se normaliza (sin espacios y en minúsculas) y no puede repetirse "
            "aunque cambien las mayúsculas. La contraseña pasa los validadores de Django. "
            "Hay que aceptar el aviso de privacidad. Envía el correo de verificación. Errores "
            "en `campos`: `email_registrado`, `password_no_coincide`, `privacidad_no_aceptada` "
            "y los mensajes de contraseña. Límite: 5 por hora por IP."
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
            429: OpenApiResponse(
                description="Límite de intentos rebasado (`demasiados_intentos`)."
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
            correlacion_id=correlacion_de(request),
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
        description="Solo una dirección propia; la de otro usuario responde 404.",
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
            "`rol`, `q` (busca en correo, nombre y apellidos), `email_verificado`, `desde` "
            "(fecha de registro, hora de México) e `ids` (hasta 20 UUID separados por comas)."
        ),
        responses={
            200: UsuarioAdminSerializer(many=True),
            **INVALIDO,
            **SIN_TOKEN,
            403: OpenApiResponse(description="El usuario no es administrador."),
        },
    ),
    retrieve=extend_schema(
        summary="Ver un usuario (administrador)",
        description="Solo administrador. Los mismos campos que el listado.",
        responses={
            200: UsuarioAdminSerializer,
            **SIN_TOKEN,
            403: OpenApiResponse(description="El usuario no es administrador."),
            404: OpenApiResponse(description="No existe el usuario."),
        },
    ),
    rol=extend_schema(
        summary="Cambiar el rol de un usuario (administrador)",
        description=(
            "Solo administrador. Guarda quién cambió el rol y cuándo (admin de Django, "
            "«Cambios de rol»). Un administrador no puede quitarse su propio rol. El rol "
            "nuevo llega al token del usuario en su siguiente renovación."
        ),
        request=CambiarRolSerializer,
        responses={
            200: UsuarioAdminSerializer,
            **INVALIDO,
            **SIN_TOKEN,
            403: OpenApiResponse(description="El usuario no es administrador."),
            404: OpenApiResponse(description="No existe el usuario."),
            409: OpenApiResponse(description="`auto_degradacion`."),
        },
    ),
)
class UsuarioViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioAdminSerializer
    # Pide token aunque AUTH_ACTIVA sea False: son datos personales.
    permission_classes = [IsAuthenticated, EsAdministrador]
    filterset_class = UsuarioFilter
    ordering_fields = ["date_joined", "email"]
    ordering = ["-date_joined", "email"]

    def get_object(self):
        # Un id que no es UUID es un usuario que no existe (404), no un error del servidor.
        try:
            uuid.UUID(str(self.kwargs.get("pk")))
        except ValueError:
            raise NotFound() from None
        return super().get_object()

    def retrieve(self, request, *args, **kwargs):
        # Sin filtros del listado: el detalle es por id.
        self.filter_backends = []
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["patch"], url_path="rol", filter_backends=[])
    def rol(self, request, pk=None):
        datos = CambiarRolSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            usuario_pk = uuid.UUID(str(pk))
        except ValueError:
            raise NotFound() from None
        usuario = servicios.cambiar_rol(request, usuario_pk, datos.validated_data["rol"])
        return Response(UsuarioAdminSerializer(usuario).data)


# === Autenticación (Entrega 3) ==========================================================

DEMASIADOS = {
    429: OpenApiResponse(
        description="Límite de intentos rebasado (`demasiados_intentos`); trae `Retry-After`."
    )
}


class _Publica(APIView):
    """Endpoint público: tampoco lee tokens, para que uno vencido no estorbe."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []


class _PublicaConLimite(_Publica):
    """Límite por IP (tasa `throttle_scope`)."""

    throttle_classes = [ScopedRateThrottle]


class _PublicaConCorreo(_Publica):
    """Límite por IP y, además, por el correo del cuerpo (tasa `<throttle_scope>_correo`)."""

    throttle_classes = [ScopedRateThrottle, LimitePorCorreo]


class LoginView(_PublicaConLimite):
    throttle_scope = "login"

    @extend_schema(
        summary="Iniciar sesión",
        description=(
            "Público. Devuelve el `access` (15 minutos) y el `refresh` (7 días), firmados con "
            "RS256; los claims están en docs/contrato-identidad.md. Correo inexistente, "
            "contraseña incorrecta y cuenta desactivada responden lo mismo. Límite: 10 por "
            "minuto por IP. Al quinto intento fallido de la misma combinación correo + IP, la "
            "cuenta queda bloqueada 15 minutos para esa IP, aun con la contraseña correcta."
        ),
        request=LoginSerializer,
        responses={
            200: LoginRespuestaSerializer,
            400: OpenApiResponse(description="Falta el correo o la contraseña (`validacion`)."),
            401: OpenApiResponse(description="`credenciales_invalidas`."),
            403: OpenApiResponse(description="`cuenta_bloqueada_temporalmente`."),
            **DEMASIADOS,
            501: OpenApiResponse(
                description="La cuenta tiene 2FA, que todavía no está disponible.",
                examples=[
                    OpenApiExample(
                        "2FA no disponible",
                        value={
                            "error": "2fa_no_disponible",
                            "detalle": "La autenticación de dos pasos todavía no está disponible.",
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request):
        datos = LoginSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario, par = servicios.iniciar_sesion(
            request, datos.validated_data["email"], datos.validated_data["password"]
        )
        return Response({**par, "usuario": UsuarioDelLoginSerializer(usuario).data})


class RenovarView(_Publica):
    @extend_schema(
        summary="Renovar el token",
        description=(
            "Público. Con un `refresh` vigente devuelve un par nuevo y el anterior entra a la "
            "blacklist: hay que reemplazar ambos. Los claims se recalculan con los datos "
            "actuales (rol, verificación). Falla si la cuenta se desactivó o si se cerraron "
            "todas las sesiones (cambió `token_version`)."
        ),
        request=RefreshSerializer,
        responses={
            200: ParDeTokensSerializer,
            **INVALIDO,
            401: OpenApiResponse(
                description=(
                    "`refresh_invalido`: vencido, alterado, en blacklist o de una sesión cerrada."
                )
            ),
        },
    )
    def post(self, request):
        datos = RefreshSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        return Response(servicios.renovar(request, datos.validated_data["refresh"]))


class LogoutView(APIView):
    @extend_schema(
        summary="Cerrar sesión",
        description=(
            "Mete el `refresh` a la blacklist. Si ya estaba o ya venció, responde igual. El "
            "`access` sigue sirviendo hasta que vence (máximo 15 minutos)."
        ),
        request=RefreshSerializer,
        responses={
            205: OpenApiResponse(description="Sesión cerrada; sin cuerpo."),
            400: OpenApiResponse(
                description="El refresh no es un token válido (`refresh_invalido`)."
            ),
            **SIN_TOKEN,
            403: OpenApiResponse(description="El refresh es de otro usuario (`sin_permiso`)."),
        },
    )
    def post(self, request):
        datos = RefreshSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.cerrar_sesion(request, datos.validated_data["refresh"])
        return Response(status=status.HTTP_205_RESET_CONTENT)


class LogoutTodoView(APIView):
    @extend_schema(
        summary="Cerrar sesión en todos los dispositivos",
        description=(
            "Ningún `refresh` emitido antes vuelve a renovar. Los `access` ya emitidos siguen "
            "sirviendo hasta que vencen (máximo 15 minutos), porque los demás servicios no "
            "consultan la base."
        ),
        request=None,
        responses={200: MensajeSerializer, **SIN_TOKEN},
    )
    def post(self, request):
        servicios.cerrar_todas_las_sesiones(request)
        return Response({"mensaje": "Cerraste sesión en todos tus dispositivos."})


class VerificarCorreoView(_Publica):
    @extend_schema(
        summary="Verificar correo",
        description=(
            "Público. Recibe el `token` del enlace `{FRONTEND_URL}/verificar-correo/?token=...` "
            "que llega por correo (vence en 24 horas). Si ya estaba verificado, responde 200."
        ),
        request=TokenDeVerificacionSerializer,
        responses={
            200: MensajeSerializer,
            400: OpenApiResponse(
                description="`token_invalido` (alterado) o `token_expirado` (pide otro)."
            ),
        },
    )
    def post(self, request):
        datos = TokenDeVerificacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        ya_estaba = servicios.verificar_correo(datos.validated_data["token"])
        mensaje = "Tu correo ya estaba verificado." if ya_estaba else "Correo verificado."
        return Response({"mensaje": mensaje})


class ReenviarVerificacionView(_PublicaConCorreo):
    throttle_scope = "reenviar_verificacion"

    @extend_schema(
        summary="Reenviar correo de verificación",
        description=(
            "Público. Siempre responde lo mismo, exista o no la cuenta. Límite: 3 por hora por "
            "IP y 3 por hora por correo."
        ),
        request=CorreoSerializer,
        responses={200: MensajeSerializer, **INVALIDO, **DEMASIADOS},
    )
    def post(self, request):
        datos = CorreoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.reenviar_verificacion(request, datos.validated_data["email"])
        return Response({"mensaje": servicios.MENSAJE_REENVIO})


class RecuperarView(_PublicaConCorreo):
    throttle_scope = "recuperar"

    @extend_schema(
        summary="Pedir enlace para restablecer la contraseña",
        description=(
            "Público. Siempre responde lo mismo, exista o no la cuenta. El enlace "
            "`{FRONTEND_URL}/restablecer/<uid>/<token>/` vence en 1 hora y sirve una sola vez. "
            "Límite: 3 por hora por IP y 3 por hora por correo."
        ),
        request=CorreoSerializer,
        responses={200: MensajeSerializer, **INVALIDO, **DEMASIADOS},
    )
    def post(self, request):
        datos = CorreoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.solicitar_recuperacion(request, datos.validated_data["email"])
        return Response({"mensaje": servicios.MENSAJE_RECUPERACION})


class RestablecerView(_Publica):
    @extend_schema(
        summary="Restablecer la contraseña",
        description=(
            "Público. Con el `uid` y el `token` del enlace fija la contraseña nueva (mismas "
            "reglas que el registro), cierra todas las sesiones, marca el correo como "
            "verificado y envía un aviso por correo."
        ),
        request=RestablecerSerializer,
        responses={
            200: MensajeSerializer,
            400: OpenApiResponse(
                description="`enlace_invalido`, o `validacion` con los errores de la contraseña."
            ),
        },
    )
    def post(self, request):
        datos = RestablecerSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.restablecer_password(
            request,
            datos.validated_data["uid"],
            datos.validated_data["token"],
            datos.validated_data["password"],
            datos.validated_data["password_confirmacion"],
        )
        return Response({"mensaje": "Contraseña restablecida. Inicia sesión con la nueva."})


class CambiarPasswordView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "cambiar_password"

    @extend_schema(
        summary="Cambiar mi contraseña",
        description=(
            "Pide la contraseña actual. Cierra la sesión en los demás dispositivos y devuelve "
            "un par nuevo para este. Envía un aviso por correo. Límite: 5 por hora por usuario."
        ),
        request=CambiarPasswordSerializer,
        responses={
            200: CambioPasswordRespuestaSerializer,
            400: OpenApiResponse(
                description="`password_actual_incorrecta`, `password_repetida` o `validacion`."
            ),
            **SIN_TOKEN,
            **DEMASIADOS,
        },
    )
    def post(self, request):
        datos = CambiarPasswordSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        par = servicios.cambiar_password(
            request,
            servicios.usuario_del_token(request),
            datos.validated_data["password_actual"],
            datos.validated_data["password_nueva"],
            datos.validated_data["password_confirmacion"],
        )
        mensaje = "Contraseña cambiada. Cerramos la sesión en tus otros dispositivos."
        return Response({**par, "mensaje": mensaje})
