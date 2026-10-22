"""Permisos de DRF por rol, leídos del token (no de la base).

Roles: `cliente` y `administrador`. Sin token, DRF responde 401; con token pero sin
permiso, 403. Con AUTH_ACTIVA=False estas clases no revisan el rol, pero `IsAuthenticated`
sigue pidiendo token donde el endpoint necesita saber quién es el usuario.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

CLIENTE = "cliente"
ADMINISTRADOR = "administrador"
ROLES = (CLIENTE, ADMINISTRADOR)


def _claims(request: Request) -> dict:
    token = getattr(request.user, "token", None)
    return token.payload if token is not None else {}


def esta_autenticado(request: Request) -> bool:
    return bool(request.user and request.user.is_authenticated)


def usuario_id(request: Request) -> int:
    """Id del usuario del token (svc-usuarios). Solo llamar con el usuario autenticado."""
    return int(request.user.id)


def rol_de(request: Request) -> str | None:
    return _claims(request).get("rol")


def es_administrador(request: Request) -> bool:
    return esta_autenticado(request) and rol_de(request) == ADMINISTRADOR


def correo_verificado(request: Request) -> bool:
    return _claims(request).get("email_verificado") is True


def _auth_activa() -> bool:
    return getattr(settings, "AUTH_ACTIVA", True)


class _PermisoPorRol(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not _auth_activa():
            return True
        return esta_autenticado(request) and self.cumple(request)

    def cumple(self, request: Request) -> bool:
        raise NotImplementedError


class EsAdministrador(_PermisoPorRol):
    message = "Solo un administrador puede hacer esta acción."

    def cumple(self, request):
        return rol_de(request) == ADMINISTRADOR


class EsCliente(_PermisoPorRol):
    message = "Esta acción es solo para clientes."

    def cumple(self, request):
        return rol_de(request) == CLIENTE


class CorreoVerificado(_PermisoPorRol):
    message = "Verifica tu correo para poder hacer esta acción."

    def cumple(self, request):
        return correo_verificado(request)


class EsDuenoOAdmin(_PermisoPorRol):
    """Pide un rol válido; a nivel objeto, solo el dueño (`obj.usuario_id`) o un administrador."""

    message = "No tienes permiso para ver este recurso."

    def cumple(self, request):
        return rol_de(request) in ROLES

    def has_object_permission(self, request, view, obj) -> bool:
        if not _auth_activa():
            return True
        return rol_de(request) == ADMINISTRADOR or obj.usuario_id == usuario_id(request)
