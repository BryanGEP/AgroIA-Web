"""Autenticación: login, renovación, logout, verificación, recuperación, cambio de
contraseña y de rol (secciones 2 a 8 de docs/requerimientos-autenticacion.md)."""

import json
import logging
import re
import uuid
from datetime import timedelta
from unittest import mock

import jwt
import pytest
from django.conf import settings
from django.core import mail
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.usuarios import tokens
from apps.usuarios.models import CambioRol, Usuario
from apps.usuarios.tests.factories import PASSWORD_DE_PRUEBA, UsuarioFactory
from tests.datos import ADMIN_ID, CLIENTE_ID, REGISTRO
from tests.tokens import api_con

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/"
NUEVA = "Hass-Mendez-2026"


def claims(token: str) -> dict:
    return jwt.decode(
        token, settings.LLAVE_PUBLICA_PRUEBAS, algorithms=["RS256"], issuer="agroia-usuarios"
    )


def login(email="cliente@example.com", password=PASSWORD_DE_PRUEBA, **extra):
    return APIClient().post(
        f"{AUTH}login/", {"email": email, "password": password}, format="json", **extra
    )


def renovar(refresh: str):
    return APIClient().post(f"{AUTH}token/renovar/", {"refresh": refresh}, format="json")


def par(**login_extra) -> dict:
    respuesta = login(**login_extra)
    assert respuesta.status_code == 200, respuesta.json()
    return respuesta.json()


def enlace_del_correo(correo) -> str:
    return re.search(r"http://localhost:8000/\S+", correo.body).group(0)


def eventos(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]


# --- Login (sección 3) -----------------------------------------------------------------


def test_login_correcto_devuelve_ambos_tokens_con_los_claims(usuario_cliente):
    respuesta = login()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["usuario"] == {
        "id": str(CLIENTE_ID),
        "nombre": "Juan",
        "rol": "cliente",
        "email_verificado": False,
    }
    acceso, renovacion = claims(cuerpo["access"]), claims(cuerpo["refresh"])
    assert acceso["token_type"] == "access" and renovacion["token_type"] == "refresh"
    for c in (acceso, renovacion):
        assert c["user_id"] == str(CLIENTE_ID)
        assert c["rol"] == "cliente"
        assert c["email_verificado"] is False
        assert c["token_version"] == 0
        assert c["iss"] == "agroia-usuarios"
        assert c["jti"]
        # Sin datos personales en el token.
        assert "email" not in c and "telefono" not in c and "nombre" not in c
    assert acceso["exp"] - acceso["iat"] == 15 * 60
    assert renovacion["exp"] - renovacion["iat"] == 7 * 24 * 60 * 60
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.last_login is not None


def test_el_access_sirve_en_los_endpoints_protegidos(usuario_cliente):
    acceso = par()["access"]

    assert api_con(acceso).get("/api/v1/usuarios/yo/").status_code == 200


def test_el_correo_se_normaliza_en_el_login(usuario_cliente):
    assert login(email="  CLIENTE@Example.com ").status_code == 200


def test_contrasena_incorrecta_y_correo_inexistente_responden_igual(usuario_cliente):
    incorrecta = login(password="No-Es-La-2026")
    inexistente = login(email="nadie@example.com")

    assert incorrecta.status_code == inexistente.status_code == 401
    assert (
        incorrecta.json()
        == inexistente.json()
        == {
            "error": "credenciales_invalidas",
            "detalle": "Correo o contraseña incorrectos.",
        }
    )


def test_cuenta_desactivada_rechazada_con_el_mismo_mensaje(usuario_cliente):
    usuario_cliente.is_active = False
    usuario_cliente.save()

    respuesta = login()

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "credenciales_invalidas"


def test_el_access_caduca_a_los_15_minutos(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        acceso = par()["access"]
        reloj.tick(timedelta(minutes=14))
        assert api_con(acceso).get("/api/v1/usuarios/yo/").status_code == 200
        reloj.tick(timedelta(minutes=2))
        respuesta = api_con(acceso).get("/api/v1/usuarios/yo/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "token_invalido"


def test_login_sin_datos_400(usuario_cliente):
    respuesta = APIClient().post(f"{AUTH}login/", {"email": "cliente@example.com"}, format="json")

    assert respuesta.status_code == 400
    assert "password" in respuesta.json()["campos"]


def test_cuenta_con_2fa_responde_501(usuario_cliente):
    usuario_cliente.tiene_2fa = True
    usuario_cliente.save()

    respuesta = login()

    assert respuesta.status_code == 501
    assert respuesta.json()["error"] == "2fa_no_disponible"


def test_login_con_token_vencido_en_el_encabezado_igual_funciona(usuario_cliente):
    # El login no lee tokens: uno vencido no impide iniciar sesión.
    respuesta = login(HTTP_AUTHORIZATION="Bearer token-viejo")

    assert respuesta.status_code == 200


# --- Renovación (sección 4) ------------------------------------------------------------


def test_renovacion_correcta_devuelve_un_refresh_nuevo(usuario_cliente):
    anterior = par()["refresh"]

    respuesta = renovar(anterior)

    assert respuesta.status_code == 200
    nuevo = respuesta.json()
    assert set(nuevo) == {"access", "refresh"}
    assert nuevo["refresh"] != anterior
    assert claims(nuevo["access"])["user_id"] == str(CLIENTE_ID)


def test_reusar_el_refresh_anterior_falla(usuario_cliente):
    anterior = par()["refresh"]
    assert renovar(anterior).status_code == 200

    respuesta = renovar(anterior)

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "refresh_invalido"


def test_usuario_desactivado_no_renueva(usuario_cliente):
    refresh = par()["refresh"]
    usuario_cliente.is_active = False
    usuario_cliente.save()

    assert renovar(refresh).status_code == 401


def test_token_version_distinto_no_renueva(usuario_cliente):
    refresh = par()["refresh"]
    usuario_cliente.token_version += 1
    usuario_cliente.save()

    assert renovar(refresh).status_code == 401


def test_el_cambio_de_rol_y_la_verificacion_aparecen_en_el_nuevo_token(usuario_cliente):
    refresh = par()["refresh"]
    usuario_cliente.rol = "administrador"
    usuario_cliente.email_verificado = True
    usuario_cliente.save()

    nuevo = claims(renovar(refresh).json()["access"])

    assert nuevo["rol"] == "administrador"
    assert nuevo["email_verificado"] is True


def test_refresh_vencido_no_renueva(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        refresh = par()["refresh"]
        reloj.tick(timedelta(days=7, minutes=1))
        assert renovar(refresh).status_code == 401


@pytest.mark.parametrize("caso", ["access", "alterado", "basura"])
def test_renovar_con_algo_que_no_es_un_refresh_valido_falla(usuario_cliente, caso):
    tokens_ = par()
    valor = {
        "access": tokens_["access"],
        "alterado": tokens_["refresh"][:-4] + "AAAA",
        "basura": "no-es-un-jwt",
    }[caso]

    respuesta = renovar(valor)

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "refresh_invalido"


def test_renovar_sin_refresh_400(anonimo):
    assert anonimo.post(f"{AUTH}token/renovar/", {}, format="json").status_code == 400


# --- Logout (sección 5) ----------------------------------------------------------------


def test_tras_el_logout_el_refresh_no_renueva(usuario_cliente):
    tokens_ = par()

    respuesta = api_con(tokens_["access"]).post(
        f"{AUTH}logout/", {"refresh": tokens_["refresh"]}, format="json"
    )

    assert respuesta.status_code == 205
    assert renovar(tokens_["refresh"]).status_code == 401


def test_logout_repetido_no_da_error(usuario_cliente):
    tokens_ = par()
    cliente = api_con(tokens_["access"])

    cliente.post(f"{AUTH}logout/", {"refresh": tokens_["refresh"]}, format="json")
    respuesta = cliente.post(f"{AUTH}logout/", {"refresh": tokens_["refresh"]}, format="json")

    assert respuesta.status_code == 205


def test_logout_con_refresh_vencido_responde_205(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        tokens_ = par()
        reloj.tick(timedelta(days=8))
        acceso_nuevo = tokens.emitir_par(usuario_cliente)["access"]
        respuesta = api_con(acceso_nuevo).post(
            f"{AUTH}logout/", {"refresh": tokens_["refresh"]}, format="json"
        )

    assert respuesta.status_code == 205


def test_logout_con_refresh_de_otro_usuario_403(usuario_cliente, usuario_otro):
    mio = par()
    ajeno = par(email="otro@example.com")

    respuesta = api_con(mio["access"]).post(
        f"{AUTH}logout/", {"refresh": ajeno["refresh"]}, format="json"
    )

    assert respuesta.status_code == 403
    assert renovar(ajeno["refresh"]).status_code == 200  # no se cerró la sesión del otro


def test_logout_con_basura_400(usuario_cliente):
    respuesta = api_con(par()["access"]).post(
        f"{AUTH}logout/", {"refresh": "no-es-un-jwt"}, format="json"
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "refresh_invalido"


def test_logout_sin_token_401(anonimo):
    assert anonimo.post(f"{AUTH}logout/", {"refresh": "x"}, format="json").status_code == 401
    assert anonimo.post(f"{AUTH}logout-todo/").status_code == 401


def test_logout_todo_cierra_las_demas_sesiones(usuario_cliente):
    celular, laptop = par(), par()

    respuesta = api_con(laptop["access"]).post(f"{AUTH}logout-todo/")

    assert respuesta.status_code == 200
    assert renovar(celular["refresh"]).status_code == 401
    assert renovar(laptop["refresh"]).status_code == 401
    assert par()["refresh"]  # puede volver a iniciar sesión


# --- Verificación de correo (sección 2) ------------------------------------------------


def test_el_registro_envia_un_correo_de_verificacion(anonimo, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = anonimo.post(f"{AUTH}registro/", REGISTRO, format="json")

    assert respuesta.status_code == 201
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.to == ["maria.lopez@example.com"]
    assert correo.subject == "Verifica tu correo en AgroIA"
    assert "El enlace vence en 24 horas" in correo.body
    assert correo.alternatives and correo.alternatives[0][1] == "text/html"
    assert enlace_del_correo(correo).startswith("http://localhost:8000/verificar-correo/?token=")


def test_un_error_del_servidor_de_correo_no_rompe_el_registro(
    anonimo, django_capture_on_commit_callbacks
):
    with (
        mock.patch(
            "django.core.mail.EmailMultiAlternatives.send", side_effect=ConnectionError("smtp")
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        respuesta = anonimo.post(f"{AUTH}registro/", REGISTRO, format="json")

    assert respuesta.status_code == 201
    assert Usuario.objects.filter(email="maria.lopez@example.com").exists()


def verificar(token: str):
    return APIClient().post(f"{AUTH}verificar-correo/", {"token": token}, format="json")


def test_token_de_verificacion_valido(usuario_cliente):
    respuesta = verificar(tokens.token_de_verificacion(usuario_cliente))

    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "Correo verificado."}
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.email_verificado is True


def test_el_enlace_del_correo_verifica(anonimo, django_capture_on_commit_callbacks):
    from urllib.parse import parse_qs, urlparse

    with django_capture_on_commit_callbacks(execute=True):
        anonimo.post(f"{AUTH}registro/", REGISTRO, format="json")
    token = parse_qs(urlparse(enlace_del_correo(mail.outbox[0])).query)["token"][0]

    assert verificar(token).status_code == 200


def test_doble_verificacion_responde_200(usuario_cliente):
    token = tokens.token_de_verificacion(usuario_cliente)
    verificar(token)

    respuesta = verificar(token)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "Tu correo ya estaba verificado."}


def test_token_de_verificacion_alterado(usuario_cliente):
    respuesta = verificar(tokens.token_de_verificacion(usuario_cliente) + "x")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "token_invalido"


def test_token_de_verificacion_vencido(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        token = tokens.token_de_verificacion(usuario_cliente)
        reloj.tick(timedelta(hours=24, minutes=1))
        respuesta = verificar(token)

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "token_expirado"


def test_token_de_recuperacion_no_sirve_para_verificar(usuario_cliente):
    # Distinto salt: un token firmado para otra cosa no verifica el correo.
    from django.core import signing

    otro = signing.TimestampSigner(salt="otra-cosa").sign(str(usuario_cliente.pk))

    assert verificar(otro).json()["error"] == "token_invalido"


def reenviar(email: str, **extra):
    return APIClient().post(
        f"{AUTH}reenviar-verificacion/", {"email": email}, format="json", **extra
    )


def test_reenvio_con_correo_inexistente_responde_igual_que_uno_real(
    usuario_cliente, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        real = reenviar("cliente@example.com")
        inexistente = reenviar("nadie@example.com")

    assert real.status_code == inexistente.status_code == 200
    assert real.json() == inexistente.json()
    assert [c.to for c in mail.outbox] == [["cliente@example.com"]]


def test_reenvio_a_cuenta_ya_verificada_no_envia(
    usuario_cliente, django_capture_on_commit_callbacks
):
    usuario_cliente.email_verificado = True
    usuario_cliente.save()

    with django_capture_on_commit_callbacks(execute=True):
        assert reenviar("cliente@example.com").status_code == 200

    assert mail.outbox == []


# --- Recuperación de contraseña (sección 6) --------------------------------------------


def recuperar(email: str, **extra):
    return APIClient().post(f"{AUTH}recuperar/", {"email": email}, format="json", **extra)


def restablecer(uid, token, password=NUEVA, confirmacion=NUEVA):
    return APIClient().post(
        f"{AUTH}restablecer/",
        {"uid": uid, "token": token, "password": password, "password_confirmacion": confirmacion},
        format="json",
    )


def datos_del_enlace(usuario) -> tuple[str, str]:
    return tokens.uid_de(usuario), tokens.token_de_recuperacion(usuario)


def test_recuperar_con_correo_inexistente_responde_igual_que_uno_real(
    usuario_cliente, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        real = recuperar("cliente@example.com")
        inexistente = recuperar("nadie@example.com")

    assert real.status_code == inexistente.status_code == 200
    assert real.json() == inexistente.json()
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.subject == "Restablece tu contraseña de AgroIA"
    assert "Si no pediste este cambio, ignora este correo" in correo.body
    assert enlace_del_correo(correo).startswith("http://localhost:8000/restablecer/")


def test_recuperar_cuenta_desactivada_no_envia(usuario_cliente, django_capture_on_commit_callbacks):
    usuario_cliente.is_active = False
    usuario_cliente.save()

    with django_capture_on_commit_callbacks(execute=True):
        assert recuperar("cliente@example.com").status_code == 200

    assert mail.outbox == []


def test_restablecimiento_correcto(usuario_cliente, django_capture_on_commit_callbacks):
    anterior = par()["refresh"]
    usuario_cliente.refresh_from_db()  # el login cambió last_login, que firma el enlace
    uid, token = datos_del_enlace(usuario_cliente)

    with django_capture_on_commit_callbacks(execute=True):
        respuesta = restablecer(uid, token)

    assert respuesta.status_code == 200
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.check_password(NUEVA)
    assert usuario_cliente.email_verificado is True  # abrir el enlace prueba que es suyo
    assert renovar(anterior).status_code == 401  # se cerraron las sesiones
    assert login(password=NUEVA).status_code == 200
    assert [c.subject for c in mail.outbox] == ["Tu contraseña de AgroIA fue cambiada"]


def test_el_enlace_del_correo_restablece(usuario_cliente, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        recuperar("cliente@example.com")
    uid, token = enlace_del_correo(mail.outbox[0]).rstrip("/").split("/")[-2:]

    assert restablecer(uid, token).status_code == 200


def test_el_mismo_enlace_no_sirve_dos_veces(usuario_cliente):
    uid, token = datos_del_enlace(usuario_cliente)
    assert restablecer(uid, token).status_code == 200

    respuesta = restablecer(uid, token, "Otra-Distinta-2026", "Otra-Distinta-2026")

    assert respuesta.status_code == 400
    assert respuesta.json() == {
        "error": "enlace_invalido",
        "detalle": "El enlace no es válido o ya expiró. Solicita uno nuevo.",
    }


def test_enlace_vencido_falla(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        uid, token = datos_del_enlace(usuario_cliente)
        reloj.tick(timedelta(hours=1, minutes=1))
        respuesta = restablecer(uid, token)

    assert respuesta.json()["error"] == "enlace_invalido"


@pytest.mark.parametrize("uid", ["no-es-base64", "MTA", "bm8tZXMtdXVpZA"])
def test_uid_alterado_falla(usuario_cliente, uid):
    _, token = datos_del_enlace(usuario_cliente)

    assert restablecer(uid, token).json()["error"] == "enlace_invalido"


def test_restablecer_con_contrasena_debil_o_distinta(usuario_cliente):
    uid, token = datos_del_enlace(usuario_cliente)

    debil = restablecer(uid, token, "12345678", "12345678")
    distinta = restablecer(uid, token, NUEVA, "Otra-Cosa-2026")

    assert debil.status_code == 400 and "password" in debil.json()["campos"]
    assert distinta.json()["campos"] == {"password_confirmacion": ["password_no_coincide"]}
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.check_password(PASSWORD_DE_PRUEBA)


# --- Cambio de contraseña (sección 7) --------------------------------------------------


def cambiar(cliente, actual=PASSWORD_DE_PRUEBA, nueva=NUEVA, confirmacion=NUEVA):
    return cliente.post(
        f"{AUTH}cambiar-password/",
        {"password_actual": actual, "password_nueva": nueva, "password_confirmacion": confirmacion},
        format="json",
    )


def test_cambio_de_contrasena_correcto(usuario_cliente, django_capture_on_commit_callbacks):
    otro_dispositivo = par()
    este = par()

    with django_capture_on_commit_callbacks(execute=True):
        respuesta = cambiar(api_con(este["access"]))

    assert respuesta.status_code == 200
    nuevos = respuesta.json()
    assert claims(nuevos["access"])["token_version"] == 1
    # El dispositivo actual sigue con los tokens nuevos; el otro ya no renueva.
    assert api_con(nuevos["access"]).get("/api/v1/usuarios/yo/").status_code == 200
    assert renovar(nuevos["refresh"]).status_code == 200
    assert renovar(otro_dispositivo["refresh"]).status_code == 401
    assert login(password=NUEVA).status_code == 200
    assert [c.subject for c in mail.outbox] == ["Tu contraseña de AgroIA fue cambiada"]
    assert "Si no fuiste tú" in mail.outbox[0].body


def test_contrasena_actual_incorrecta(usuario_cliente):
    respuesta = cambiar(api_con(par()["access"]), actual="No-Es-La-2026")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "password_actual_incorrecta"


def test_nueva_igual_a_la_actual(usuario_cliente):
    respuesta = cambiar(
        api_con(par()["access"]), nueva=PASSWORD_DE_PRUEBA, confirmacion=PASSWORD_DE_PRUEBA
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "password_repetida"


def test_cambio_con_contrasena_debil(usuario_cliente):
    respuesta = cambiar(api_con(par()["access"]), nueva="12345678", confirmacion="12345678")

    assert respuesta.status_code == 400
    assert "password" in respuesta.json()["campos"]


def test_cambiar_contrasena_sin_token_401(anonimo):
    assert cambiar(anonimo).status_code == 401


# --- Cambio de rol (sección 8) ---------------------------------------------------------


def cambiar_rol(cliente, usuario_id, rol="administrador"):
    return cliente.patch(f"/api/v1/usuarios/{usuario_id}/rol/", {"rol": rol}, format="json")


def test_el_admin_cambia_el_rol_y_queda_registrado(admin, usuario_cliente):
    respuesta = cambiar_rol(admin, CLIENTE_ID)

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "administrador"
    cambio = CambioRol.objects.get()
    assert cambio.usuario == usuario_cliente
    assert (cambio.rol_anterior, cambio.rol_nuevo) == ("cliente", "administrador")
    assert cambio.cambiado_por_id == ADMIN_ID
    assert cambio.cambiado_en is not None


def test_mismo_rol_no_registra_cambio(admin, usuario_cliente):
    assert cambiar_rol(admin, CLIENTE_ID, "cliente").status_code == 200
    assert not CambioRol.objects.exists()


def test_el_admin_no_puede_quitarse_su_propio_rol(admin, usuario_admin):
    respuesta = cambiar_rol(admin, ADMIN_ID, "cliente")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "auto_degradacion"
    usuario_admin.refresh_from_db()
    assert usuario_admin.rol == "administrador"


def test_cambio_de_rol_validaciones(admin, usuario_cliente):
    assert cambiar_rol(admin, CLIENTE_ID, "operativo").status_code == 400
    assert cambiar_rol(admin, uuid.uuid4()).status_code == 404
    assert cambiar_rol(admin, "no-es-uuid").status_code == 404


def test_cambio_de_rol_401_y_403(anonimo, cliente, usuario_cliente):
    assert cambiar_rol(anonimo, CLIENTE_ID).status_code == 401
    assert cambiar_rol(cliente, CLIENTE_ID).status_code == 403
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.rol == "cliente"


# --- Log de seguridad ------------------------------------------------------------------


def test_eventos_de_login_sin_contrasenas_ni_tokens(usuario_cliente, caplog):
    caplog.set_level(logging.INFO, logger="seguridad")

    login(password="Mala-Contrasena-2026")
    cuerpo = login().json()

    nombres = [e["evento"] for e in eventos(caplog)]
    assert nombres == ["login_fallido", "login_exitoso"]
    assert eventos(caplog)[0]["email"] == "cliente@example.com"
    assert eventos(caplog)[1]["usuario_id"] == str(CLIENTE_ID)
    for secreto in (
        "Mala-Contrasena-2026",
        PASSWORD_DE_PRUEBA,
        cuerpo["access"],
        cuerpo["refresh"],
    ):
        assert secreto not in caplog.text


def test_eventos_de_recuperacion_cambio_de_password_y_rol(admin, usuario_cliente, caplog):
    caplog.set_level(logging.INFO, logger="seguridad")

    recuperar("cliente@example.com")
    cambiar(api_con(par()["access"]))
    cambiar_rol(admin, CLIENTE_ID)

    nombres = [e["evento"] for e in eventos(caplog)]
    assert "recuperacion_solicitada" in nombres
    assert "password_cambiada" in nombres
    assert "rol_cambiado" in nombres
    assert NUEVA not in caplog.text


def test_un_usuario_con_id_uuid():
    usuario = UsuarioFactory()

    assert isinstance(usuario.pk, uuid.UUID)


def test_si_escriben_la_contrasena_en_el_correo_no_queda_en_el_log(usuario_cliente, caplog):
    caplog.set_level(logging.INFO, logger="seguridad")

    login(email="Mi-Contrasena-Secreta-2026", password="otra-cosa")

    (evento,) = eventos(caplog)
    assert evento["evento"] == "login_fallido"
    assert evento["email"] == "email_no_valido"
    assert "Mi-Contrasena-Secreta-2026".lower() not in caplog.text.lower()
