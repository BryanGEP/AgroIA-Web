"""Lógica de negocio de usuarios: registro, autenticación, roles y direcciones.

La autenticación sigue las secciones 2 a 9 de docs/requerimientos-autenticacion.md: login,
renovación, logout, verificación de correo, recuperación y cambio de contraseña y cambio
de rol. Cada acción sensible deja un evento en el log de seguridad
(agroia_comun.seguridad), nunca con contraseñas ni tokens.
"""

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, user_logged_in
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from agroia_comun.errores import ErrorDeNegocio
from agroia_comun.eventos.en_django import publicar_al_confirmar
from agroia_comun.permisos import usuario_id
from agroia_comun.seguridad import registrar_evento
from apps.usuarios import bloqueo, tokens
from apps.usuarios.managers import normalizar_email
from apps.usuarios.models import CambioRol, Direccion, Usuario


def registrar_usuario(
    email: str, password: str, nombre: str, apellidos: str, correlacion_id: str | None = None
) -> Usuario:
    """Crea la cuenta sin verificar (rol cliente) y guarda la aceptación del aviso de
    privacidad con su fecha y versión. Todo o nada.

    Al confirmar publica `usuario_registrado` (solo el id y el rol: ni correo ni nombre) y
    `correo_solicitado` (el consumidor de correos envía la verificación). Si Redis no
    responde, el registro no falla: queda `evento_no_publicado` en el log."""
    with transaction.atomic():
        usuario = Usuario.objects.create_user(
            email=email,
            password=password,
            nombre=nombre,
            apellidos=apellidos,
            acepto_privacidad_en=timezone.now(),
            version_privacidad=settings.VERSION_AVISO_PRIVACIDAD,
        )
        _solicitar_correo(usuario, "verificacion")
        publicar_al_confirmar(
            "usuario_registrado",
            {"usuario_id": str(usuario.id), "rol": usuario.rol},
            correlacion_id,
        )
    return usuario


def usuario_del_token(request: Request) -> Usuario:
    """El Usuario cuyo id es el `user_id` del token; 404 si no existe o está inactivo."""
    return get_object_or_404(Usuario, id=usuario_id(request), is_active=True)


def _bloquear_usuario(usuario: Usuario) -> None:
    """Serializa los cambios de direcciones de un mismo usuario."""
    Usuario.objects.select_for_update().filter(pk=usuario.pk).first()


def _desmarcar_otras(usuario: Usuario, excepto: int | None = None) -> None:
    otras = Direccion.objects.filter(usuario=usuario, predeterminada=True)
    if excepto is not None:
        otras = otras.exclude(pk=excepto)
    otras.update(predeterminada=False)


def crear_direccion(usuario: Usuario, datos: dict) -> Direccion:
    """Crea una dirección. La primera queda como predeterminada; si la nueva lo es, las
    demás dejan de serlo en la misma transacción."""
    with transaction.atomic():
        _bloquear_usuario(usuario)
        es_la_primera = not Direccion.objects.filter(usuario=usuario).exists()
        predeterminada = bool(datos.get("predeterminada")) or es_la_primera
        if predeterminada:
            _desmarcar_otras(usuario)
        return Direccion.objects.create(
            usuario=usuario, **{**datos, "predeterminada": predeterminada}
        )


def actualizar_direccion(direccion: Direccion, datos: dict) -> Direccion:
    with transaction.atomic():
        _bloquear_usuario(direccion.usuario)
        if datos.get("predeterminada") is True:
            _desmarcar_otras(direccion.usuario, excepto=direccion.pk)
        for campo, valor in datos.items():
            setattr(direccion, campo, valor)
        direccion.save()
    return direccion


def borrar_direccion(direccion: Direccion) -> None:
    """Si se borra la predeterminada, pasa a serlo la más reciente que quede."""
    with transaction.atomic():
        usuario = direccion.usuario
        _bloquear_usuario(usuario)
        era_predeterminada = direccion.predeterminada
        direccion.delete()
        if era_predeterminada:
            reciente = (
                Direccion.objects.filter(usuario=usuario).order_by("-creada_en", "-id").first()
            )
            if reciente is not None:
                reciente.predeterminada = True
                reciente.save(update_fields=["predeterminada"])


# === Autenticación ===================================================================

MENSAJE_RECUPERACION = (
    "Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña."
)
MENSAJE_REENVIO = "Si el correo está registrado y sin verificar, te enviamos un enlace nuevo."


def _credenciales_invalidas() -> ErrorDeNegocio:
    return ErrorDeNegocio(
        "credenciales_invalidas", "Correo o contraseña incorrectos.", status.HTTP_401_UNAUTHORIZED
    )


def _refresh_invalido() -> ErrorDeNegocio:
    return ErrorDeNegocio(
        "refresh_invalido",
        "La sesión no es válida o ya venció. Inicia sesión de nuevo.",
        status.HTTP_401_UNAUTHORIZED,
    )


def _correo_para_log(texto: str) -> str:
    """El correo tal cual solo si parece un correo: alguien podría escribir su contraseña
    en el campo del correo, y el log nunca debe guardarla."""
    try:
        validate_email(texto)
    except DjangoValidationError:
        return "email_no_valido"
    return texto


def _solicitar_correo(usuario: Usuario, tipo_correo: str) -> None:
    """Pide el correo al consumidor de correos (evento `correo_solicitado`), solo si la
    transacción se guarda. El evento no lleva el token: lo genera el consumidor."""
    publicar_al_confirmar(
        "correo_solicitado", {"usuario_id": str(usuario.pk), "tipo_correo": tipo_correo}
    )


def validar_password_nueva(password: str, confirmacion: str, usuario: Usuario) -> None:
    """Mismas reglas que el registro: coincidir y pasar los validadores de Django."""
    if password != confirmacion:
        raise serializers.ValidationError({"password_confirmacion": ["password_no_coincide"]})
    try:
        validate_password(password, user=usuario)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"password": list(error.messages)}) from error


# --- Login (sección 3) ----------------------------------------------------------------


def iniciar_sesion(request, email: str, password: str) -> tuple[Usuario, dict]:
    """Devuelve el usuario y su par de tokens.

    Correo inexistente, contraseña incorrecta y cuenta desactivada responden igual (401
    `credenciales_invalidas`). axes cuenta cada fallo por correo + IP; al quinto, y
    mientras dure el bloqueo (aun con la contraseña correcta), responde 403.
    """
    email = normalizar_email(email)
    correo_para_log = _correo_para_log(email)
    # Se pasa la petición de DRF: axes deja ahí `axes_locked_out` y su middleware no
    # cambia la respuesta, así el error sale con el formato común.
    usuario = authenticate(request, email=email, password=password)
    if usuario is None:
        if getattr(request, "axes_locked_out", False):
            registrar_evento("cuenta_bloqueada", request, email=correo_para_log)
            raise ErrorDeNegocio(bloqueo.CODIGO, bloqueo.MENSAJE, status.HTTP_403_FORBIDDEN)
        registrar_evento("login_fallido", request, email=correo_para_log)
        raise _credenciales_invalidas()

    if usuario.tiene_2fa:
        # Sección 12 (2FA): aquí se responderá {"requiere_2fa": true, "token_temporal"}
        # firmado con TimestampSigner(salt="login-2fa"). Todavía no hay forma de activarlo.
        raise ErrorDeNegocio(
            "2fa_no_disponible",
            "La autenticación de dos pasos todavía no está disponible.",
            status.HTTP_501_NOT_IMPLEMENTED,
        )

    # Mismo aviso que django.contrib.auth.login(): actualiza last_login y reinicia los
    # intentos fallidos de axes (AXES_RESET_ON_SUCCESS).
    user_logged_in.send(sender=Usuario, request=request, user=usuario)
    registrar_evento("login_exitoso", request, usuario_id=str(usuario.pk))
    return usuario, tokens.emitir_par(usuario)


# --- Renovación (sección 4) -----------------------------------------------------------


def renovar(request, refresh_texto: str) -> dict:
    """Rota el refresh: el anterior entra a la blacklist y se emite un par nuevo con los
    claims recalculados (un cambio de rol o la verificación se reflejan aquí)."""
    try:
        refresh = RefreshToken(refresh_texto)  # firma, vencimiento, tipo y blacklist
    except TokenError as error:
        registrar_evento("renovacion_rechazada", request, motivo="refresh_invalido")
        raise _refresh_invalido() from error

    with transaction.atomic():
        try:
            usuario = Usuario.objects.select_for_update().filter(pk=refresh.get("user_id")).first()
        except DjangoValidationError:  # user_id que no es UUID (token de antes del cambio)
            usuario = None
        if (
            usuario is None
            or not usuario.is_active
            or refresh.get("token_version") != usuario.token_version
        ):
            registrar_evento("renovacion_rechazada", request, motivo="sesion_cerrada")
            raise _refresh_invalido()
        # Dos renovaciones con el mismo refresh: solo una lo mete a la blacklist.
        _, nuevo_en_blacklist = refresh.blacklist()
        if not nuevo_en_blacklist:
            registrar_evento("renovacion_rechazada", request, motivo="refresh_reusado")
            raise _refresh_invalido()
        return tokens.emitir_par(usuario)


# --- Logout (sección 5) ---------------------------------------------------------------


def _claims_del_refresh(refresh_texto: str) -> dict:
    """Valida firma, emisor y tipo, sin exigir que siga vigente."""
    jwt_conf = settings.SIMPLE_JWT
    try:
        claims = jwt.decode(
            refresh_texto,
            jwt_conf["VERIFYING_KEY"],
            algorithms=[jwt_conf["ALGORITHM"]],
            issuer=jwt_conf["ISSUER"],
            options={"verify_exp": False, "require": ["exp", "jti", "user_id"]},
        )
    except jwt.PyJWTError as error:
        raise ErrorDeNegocio(
            "refresh_invalido", "El refresh no es válido.", status.HTTP_400_BAD_REQUEST
        ) from error
    if claims.get("token_type") != "refresh":
        raise ErrorDeNegocio(
            "refresh_invalido", "El refresh no es válido.", status.HTTP_400_BAD_REQUEST
        )
    return claims


def cerrar_sesion(request, refresh_texto: str) -> None:
    """Mete el refresh a la blacklist. Si ya estaba o ya venció, no es error. El access
    sigue sirviendo hasta que vence (máximo 15 minutos)."""
    claims = _claims_del_refresh(refresh_texto)
    if claims["user_id"] != str(usuario_id(request)):
        registrar_evento("acceso_denegado", request, estado=403, error="refresh_ajeno")
        raise ErrorDeNegocio(
            "sin_permiso", "Ese refresh no es de tu sesión.", status.HTTP_403_FORBIDDEN
        )
    RefreshToken(refresh_texto, verify=False).blacklist()
    registrar_evento("logout", request)


def cerrar_todas_las_sesiones(request) -> None:
    """Sube token_version: ningún refresh emitido antes vuelve a renovar."""
    with transaction.atomic():
        Usuario.objects.filter(pk=usuario_id(request)).update(token_version=F("token_version") + 1)
        publicar_al_confirmar("sesiones_cerradas", {"usuario_id": str(usuario_id(request))})
    registrar_evento("logout_todo", request)


# --- Verificación de correo (sección 2) -----------------------------------------------


def verificar_correo(token: str) -> bool:
    """Marca el correo como verificado. Devuelve True si ya lo estaba."""
    try:
        pk = tokens.leer_token_de_verificacion(token)
    except signing.SignatureExpired as error:
        raise ErrorDeNegocio(
            "token_expirado",
            "El enlace de verificación ya venció. Pide uno nuevo.",
            status.HTTP_400_BAD_REQUEST,
        ) from error
    except signing.BadSignature as error:
        raise _enlace_de_verificacion_invalido() from error
    usuario = Usuario.objects.filter(pk=pk, is_active=True).first()
    if usuario is None:
        raise _enlace_de_verificacion_invalido()
    if usuario.email_verificado:
        return True
    with transaction.atomic():
        usuario.email_verificado = True
        usuario.save(update_fields=["email_verificado"])
        publicar_al_confirmar("correo_verificado", {"usuario_id": str(usuario.pk), "via": "enlace"})
    return False


def _enlace_de_verificacion_invalido() -> ErrorDeNegocio:
    return ErrorDeNegocio(
        "token_invalido", "El enlace de verificación no es válido.", status.HTTP_400_BAD_REQUEST
    )


def reenviar_verificacion(request, email: str) -> None:
    """Siempre responde igual; solo envía si la cuenta existe, está activa y sin verificar."""
    email = normalizar_email(email)
    usuario = Usuario.objects.filter(
        email__iexact=email, is_active=True, email_verificado=False
    ).first()
    registrar_evento("verificacion_reenviada", request, email=email, se_envio=usuario is not None)
    if usuario is not None:
        with transaction.atomic():
            _solicitar_correo(usuario, "verificacion")


# --- Recuperación de contraseña (sección 6) -------------------------------------------


def solicitar_recuperacion(request, email: str) -> None:
    """Siempre responde igual; solo envía si la cuenta existe y está activa."""
    email = normalizar_email(email)
    usuario = Usuario.objects.filter(email__iexact=email, is_active=True).first()
    registrar_evento(
        "recuperacion_solicitada", request, email=email, cuenta_existe=usuario is not None
    )
    # Con un correo que no existe no se publica nada; la respuesta es la misma y, como el
    # correo ya no se envía dentro de la petición, también tarda lo mismo (riesgo B5).
    if usuario is not None:
        with transaction.atomic():
            _solicitar_correo(usuario, "recuperacion")


def restablecer_password(request, uid: str, token: str, password: str, confirmacion: str) -> None:
    usuario = tokens.usuario_del_enlace(uid, token)
    if usuario is None:
        registrar_evento("restablecimiento_rechazado", request)
        raise ErrorDeNegocio(
            "enlace_invalido",
            "El enlace no es válido o ya expiró. Solicita uno nuevo.",
            status.HTTP_400_BAD_REQUEST,
        )
    validar_password_nueva(password, confirmacion, usuario)
    with transaction.atomic():
        estaba_verificado = usuario.email_verificado
        usuario.set_password(password)
        usuario.token_version += 1  # cierra las sesiones abiertas
        usuario.email_verificado = True  # abrir el enlace prueba que el correo es suyo
        usuario.save(update_fields=["password", "token_version", "email_verificado"])
        _solicitar_correo(usuario, "aviso_password")
        publicar_al_confirmar(
            "password_cambiada", {"usuario_id": str(usuario.pk), "motivo": "recuperacion"}
        )
        if not estaba_verificado:
            publicar_al_confirmar(
                "correo_verificado", {"usuario_id": str(usuario.pk), "via": "recuperacion"}
            )
    registrar_evento("password_restablecida", request, usuario_id=str(usuario.pk))


# --- Cambio de contraseña (sección 7) -------------------------------------------------


def cambiar_password(request, usuario: Usuario, actual: str, nueva: str, confirmacion: str) -> dict:
    """Cambia la contraseña, cierra las demás sesiones y devuelve un par nuevo para este
    dispositivo."""
    if not usuario.check_password(actual):
        registrar_evento("cambio_password_rechazado", request, motivo="password_actual")
        raise ErrorDeNegocio(
            "password_actual_incorrecta",
            "La contraseña actual no es correcta.",
            status.HTTP_400_BAD_REQUEST,
        )
    if usuario.check_password(nueva):
        raise ErrorDeNegocio(
            "password_repetida",
            "La nueva contraseña debe ser distinta de la actual.",
            status.HTTP_400_BAD_REQUEST,
        )
    validar_password_nueva(nueva, confirmacion, usuario)
    with transaction.atomic():
        usuario.set_password(nueva)
        usuario.token_version += 1
        usuario.save(update_fields=["password", "token_version"])
        _solicitar_correo(usuario, "aviso_password")
        publicar_al_confirmar(
            "password_cambiada", {"usuario_id": str(usuario.pk), "motivo": "cambio"}
        )
    registrar_evento("password_cambiada", request)
    return tokens.emitir_par(usuario)


# --- Roles (sección 8) ----------------------------------------------------------------


def cambiar_rol(request, usuario_pk, rol_nuevo: str) -> Usuario:
    """Cambia el rol y guarda quién y cuándo en CambioRol. Un administrador no puede
    quitarse su propio rol. El rol nuevo llega al token en la siguiente renovación."""
    id_admin = usuario_id(request)
    with transaction.atomic():
        usuario = Usuario.objects.select_for_update().filter(pk=usuario_pk).first()
        if usuario is None:
            raise exceptions.NotFound()
        if usuario.pk == id_admin and rol_nuevo != Usuario.Rol.ADMINISTRADOR:
            raise ErrorDeNegocio(
                "auto_degradacion",
                "No puedes quitarte tu propio rol de administrador.",
                status.HTTP_409_CONFLICT,
            )
        if usuario.rol == rol_nuevo:
            return usuario
        anterior = usuario.rol
        usuario.rol = rol_nuevo
        usuario.save(update_fields=["rol"])
        CambioRol.objects.create(
            usuario=usuario,
            rol_anterior=anterior,
            rol_nuevo=rol_nuevo,
            cambiado_por=Usuario.objects.filter(pk=id_admin).first(),
        )
        publicar_al_confirmar(
            "rol_cambiado",
            {
                "usuario_id": str(usuario.pk),
                "rol_anterior": anterior,
                "rol_nuevo": rol_nuevo,
                "cambiado_por": str(id_admin),
            },
        )
    registrar_evento(
        "rol_cambiado",
        request,
        usuario_afectado=str(usuario.pk),
        anterior=anterior,
        nuevo=rol_nuevo,
    )
    return usuario
