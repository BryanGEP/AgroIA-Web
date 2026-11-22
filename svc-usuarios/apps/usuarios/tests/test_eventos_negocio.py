"""Eventos de negocio de svc-usuarios: se publican al confirmar, una vez, sin datos
sensibles, con la correlación de la petición; nada si la transacción falla."""

import json
import uuid

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from agroia_comun.eventos.catalogo import STREAM_CORREOS, STREAM_USUARIOS
from apps.usuarios import servicios, tokens
from apps.usuarios.models import Usuario
from apps.usuarios.tests.factories import PASSWORD_DE_PRUEBA
from tests.datos import ADMIN_ID, CLIENTE_ID
from tests.tokens import api_con, token

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/"
NUEVA = "Hass-Mendez-2026"


def publicados(redis, stream=STREAM_USUARIOS) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis.xrange(stream)]


def tipos(redis, stream=STREAM_USUARIOS) -> list[str]:
    return [s["tipo"] for s in publicados(redis, stream)]


def correos(redis) -> list[dict]:
    return [s["datos"] for s in publicados(redis, STREAM_CORREOS)]


@pytest.fixture
def capturar(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


# --- correo_verificado --------------------------------------------------------------------


def test_verificar_el_correo_publica_correo_verificado(usuario_cliente, redis_de_eventos, capturar):
    usuario_cliente.email_verificado = False
    usuario_cliente.save()
    enlace = tokens.token_de_verificacion(usuario_cliente)
    correlacion = str(uuid.uuid4())

    with capturar():
        respuesta = APIClient().post(
            f"{AUTH}verificar-correo/", {"token": enlace}, format="json",
            HTTP_X_CORRELACION_ID=correlacion,
        )  # fmt: skip

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "correo_verificado"
    assert sobre["datos"] == {"usuario_id": str(CLIENTE_ID), "via": "enlace"}
    assert sobre["correlacion_id"] == correlacion
    assert enlace not in json.dumps(sobre)


def test_verificar_un_correo_ya_verificado_no_publica(usuario_cliente, redis_de_eventos, capturar):
    usuario_cliente.email_verificado = True
    usuario_cliente.save()

    with capturar():
        APIClient().post(
            f"{AUTH}verificar-correo/",
            {"token": tokens.token_de_verificacion(usuario_cliente)},
            format="json",
        )

    assert publicados(redis_de_eventos) == []


# --- rol_cambiado -------------------------------------------------------------------------


def test_cambiar_el_rol_publica_rol_cambiado(usuario_cliente, admin, redis_de_eventos, capturar):
    with capturar():
        respuesta = admin.patch(
            f"/api/v1/usuarios/{CLIENTE_ID}/rol/", {"rol": "administrador"}, format="json"
        )

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "rol_cambiado"
    assert sobre["datos"] == {
        "usuario_id": str(CLIENTE_ID),
        "rol_anterior": "cliente",
        "rol_nuevo": "administrador",
        "cambiado_por": str(ADMIN_ID),
    }
    assert sobre["origen"] == "svc-usuarios"


def test_el_mismo_rol_no_publica(usuario_cliente, admin, redis_de_eventos, capturar):
    with capturar():
        admin.patch(f"/api/v1/usuarios/{CLIENTE_ID}/rol/", {"rol": "cliente"}, format="json")

    assert publicados(redis_de_eventos) == []


def test_si_la_transaccion_falla_no_publica_el_cambio_de_rol(
    usuario_cliente, usuario_admin, redis_de_eventos, capturar
):
    with capturar() as pendientes, pytest.raises(RuntimeError), transaction.atomic():
        servicios.cambiar_rol(api_request(ADMIN_ID), CLIENTE_ID, "administrador")
        raise RuntimeError("falla después del cambio")

    assert pendientes == []
    assert publicados(redis_de_eventos) == []
    assert Usuario.objects.get(pk=CLIENTE_ID).rol == "cliente"


def api_request(usuario):
    """Una petición de DRF autenticada, para llamar a servicios directamente."""
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from agroia_comun.autenticacion import AutenticacionJWT

    crudo = APIRequestFactory().get(
        "/", HTTP_AUTHORIZATION=f"Bearer {token(usuario, rol='administrador')}"
    )
    return Request(crudo, authenticators=[AutenticacionJWT()])


# --- contraseña, sesiones y correos -------------------------------------------------------


def test_cambiar_la_contrasena_publica_password_cambiada_y_pide_el_aviso(
    usuario_cliente, redis_de_eventos, capturar
):
    cliente = api_con(token(CLIENTE_ID))
    with capturar():
        respuesta = cliente.post(
            f"{AUTH}cambiar-password/",
            {"password_actual": PASSWORD_DE_PRUEBA, "password_nueva": NUEVA,
             "password_confirmacion": NUEVA},
            format="json",
        )  # fmt: skip

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "password_cambiada"
    assert sobre["datos"] == {"usuario_id": str(CLIENTE_ID), "motivo": "cambio"}
    assert correos(redis_de_eventos) == [
        {"usuario_id": str(CLIENTE_ID), "tipo_correo": "aviso_password"}
    ]
    assert NUEVA not in json.dumps(publicados(redis_de_eventos))


def test_restablecer_publica_password_cambiada_correo_verificado_y_el_aviso(
    usuario_cliente, redis_de_eventos, capturar
):
    usuario_cliente.email_verificado = False
    usuario_cliente.save()
    uid, enlace = tokens.uid_de(usuario_cliente), tokens.token_de_recuperacion(usuario_cliente)

    with capturar():
        respuesta = APIClient().post(
            f"{AUTH}restablecer/",
            {"uid": uid, "token": enlace, "password": NUEVA, "password_confirmacion": NUEVA},
            format="json",
        )

    assert respuesta.status_code == 200
    assert tipos(redis_de_eventos) == ["password_cambiada", "correo_verificado"]
    assert publicados(redis_de_eventos)[0]["datos"]["motivo"] == "recuperacion"
    assert publicados(redis_de_eventos)[1]["datos"]["via"] == "recuperacion"
    assert [c["tipo_correo"] for c in correos(redis_de_eventos)] == ["aviso_password"]
    assert enlace not in redis_de_eventos.xrange(STREAM_USUARIOS).__repr__()


def test_cerrar_todas_las_sesiones_publica_sesiones_cerradas(
    usuario_cliente, redis_de_eventos, capturar
):
    with capturar():
        respuesta = api_con(token(CLIENTE_ID)).post(f"{AUTH}logout-todo/")

    assert respuesta.status_code == 200
    [sobre] = publicados(redis_de_eventos)
    assert sobre["tipo"] == "sesiones_cerradas"
    assert sobre["datos"] == {"usuario_id": str(CLIENTE_ID)}


# --- correo_solicitado --------------------------------------------------------------------


def test_recuperar_pide_el_correo_sin_token(usuario_cliente, redis_de_eventos, capturar):
    with capturar():
        APIClient().post(f"{AUTH}recuperar/", {"email": "cliente@example.com"}, format="json")

    [sobre] = publicados(redis_de_eventos, STREAM_CORREOS)
    assert sobre["tipo"] == "correo_solicitado"
    assert sobre["datos"] == {"usuario_id": str(CLIENTE_ID), "tipo_correo": "recuperacion"}


def test_recuperar_con_un_correo_inexistente_no_publica_y_responde_igual(
    usuario_cliente, redis_de_eventos, capturar
):
    with capturar():
        real = APIClient().post(f"{AUTH}recuperar/", {"email": "cliente@example.com"},
                                format="json")  # fmt: skip
    with capturar():
        falso = APIClient().post(f"{AUTH}recuperar/", {"email": "nadie@example.com"},
                                 format="json")  # fmt: skip

    assert real.status_code == falso.status_code == 200
    assert real.json() == falso.json()
    assert len(publicados(redis_de_eventos, STREAM_CORREOS)) == 1  # solo el real


def test_el_registro_pide_el_correo_de_verificacion(redis_de_eventos, capturar):
    from tests.datos import REGISTRO

    with capturar():
        APIClient().post(f"{AUTH}registro/", REGISTRO, format="json")

    usuario = Usuario.objects.get(email=REGISTRO["email"])
    assert correos(redis_de_eventos) == [
        {"usuario_id": str(usuario.pk), "tipo_correo": "verificacion"}
    ]
