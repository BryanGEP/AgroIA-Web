"""Lógica de negocio de usuarios: registro y direcciones."""

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.request import Request

from agroia_comun.permisos import usuario_id
from apps.usuarios.models import Direccion, Usuario


def registrar_usuario(email: str, password: str, nombre: str, apellidos: str) -> Usuario:
    """Crea la cuenta sin verificar (rol cliente) y guarda la aceptación del aviso de
    privacidad con su fecha y versión. Todo o nada."""
    with transaction.atomic():
        usuario = Usuario.objects.create_user(
            email=email,
            password=password,
            nombre=nombre,
            apellidos=apellidos,
            acepto_privacidad_en=timezone.now(),
            version_privacidad=settings.VERSION_AVISO_PRIVACIDAD,
        )
        # Entrega 3: enviar el correo de verificación solo si el usuario se guardó:
        # transaction.on_commit(lambda: enviar_verificacion(usuario))
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
