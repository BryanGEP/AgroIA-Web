"""Tokens de prueba firmados con la llave temporal de settings_pruebas."""

from django.conf import settings
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token


def token(usuario_id: int, rol: str | None = "cliente", **extra) -> str:
    return firmar_token(settings.LLAVE_PRIVADA_PRUEBAS, usuario_id=usuario_id, rol=rol, **extra)


def api_con(token_jwt: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token_jwt}")
    return cliente
