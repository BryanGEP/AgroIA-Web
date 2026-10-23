"""Endpoints de registro, perfil, direcciones y listado del administrador."""

import pytest
from django.test import override_settings

from apps.usuarios.models import Direccion, Usuario
from apps.usuarios.tests.factories import DireccionFactory, UsuarioFactory
from tests.datos import CLIENTE_ID, DIRECCION, REGISTRO
from tests.tokens import api_con, token

pytestmark = pytest.mark.django_db

REGISTRAR = "/api/v1/auth/registro/"
YO = "/api/v1/usuarios/yo/"
DIRECCIONES = "/api/v1/usuarios/yo/direcciones/"
USUARIOS = "/api/v1/usuarios/"


# --- Registro -----------------------------------------------------------------


def test_registro_correcto(anonimo):
    respuesta = anonimo.post(REGISTRAR, REGISTRO, format="json")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"id", "email", "mensaje"}
    assert cuerpo["email"] == "maria.lopez@example.com"
    usuario = Usuario.objects.get(id=cuerpo["id"])
    assert usuario.nombre == "María"
    assert usuario.rol == "cliente"
    assert usuario.email_verificado is False
    assert usuario.version_privacidad == "2026-10"
    assert usuario.acepto_privacidad_en is not None


def test_la_contrasena_no_queda_en_texto_plano(anonimo):
    respuesta = anonimo.post(REGISTRAR, REGISTRO, format="json")

    usuario = Usuario.objects.get(id=respuesta.json()["id"])
    assert REGISTRO["password"] not in usuario.password
    assert usuario.check_password(REGISTRO["password"])
    assert "password" not in respuesta.json()


def test_el_correo_se_normaliza(anonimo):
    respuesta = anonimo.post(
        REGISTRAR, {**REGISTRO, "email": "  Maria.Lopez@Example.COM "}, format="json"
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["email"] == "maria.lopez@example.com"


def test_correo_duplicado_con_mayusculas_distintas(anonimo):
    UsuarioFactory(email="maria.lopez@example.com")

    respuesta = anonimo.post(
        REGISTRAR, {**REGISTRO, "email": "MARIA.Lopez@example.com"}, format="json"
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert respuesta.json()["campos"]["email"] == ["email_registrado"]
    assert Usuario.objects.count() == 1


def test_contrasenas_distintas(anonimo):
    respuesta = anonimo.post(
        REGISTRAR, {**REGISTRO, "password_confirmacion": "Otra-Distinta-2026"}, format="json"
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["campos"]["password_confirmacion"] == ["password_no_coincide"]


@pytest.mark.parametrize(
    "password",
    ["corta1", "12345678901", "password123", "maria.lopez@example"],
    ids=["muy-corta", "solo-numeros", "comun", "parecida-al-correo"],
)
def test_contrasena_debil(anonimo, password):
    respuesta = anonimo.post(
        REGISTRAR,
        {**REGISTRO, "password": password, "password_confirmacion": password},
        format="json",
    )

    assert respuesta.status_code == 400
    assert "password" in respuesta.json()["campos"]
    assert not Usuario.objects.exists()


def test_los_mensajes_de_contrasena_estan_en_espanol(anonimo):
    respuesta = anonimo.post(
        REGISTRAR,
        {**REGISTRO, "password": "corta1", "password_confirmacion": "corta1"},
        format="json",
    )

    assert any("contraseña" in m.lower() for m in respuesta.json()["campos"]["password"])


@pytest.mark.parametrize("valor", [False, None])
def test_sin_aceptar_privacidad(anonimo, valor):
    datos = {**REGISTRO, "acepto_privacidad": valor}

    respuesta = anonimo.post(REGISTRAR, datos, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["campos"]["acepto_privacidad"] == ["privacidad_no_aceptada"]
    assert not Usuario.objects.exists()


@pytest.mark.parametrize("campo", ["nombre", "email", "password"])
def test_campos_obligatorios(anonimo, campo):
    datos = dict(REGISTRO)
    datos.pop(campo)

    respuesta = anonimo.post(REGISTRAR, datos, format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_no_se_puede_registrar_como_administrador(anonimo):
    respuesta = anonimo.post(
        REGISTRAR, {**REGISTRO, "rol": "administrador", "email_verificado": True}, format="json"
    )

    usuario = Usuario.objects.get(id=respuesta.json()["id"])
    assert usuario.rol == "cliente"
    assert usuario.email_verificado is False


def test_el_registro_ignora_un_token_invalido(anonimo):
    anonimo.credentials(HTTP_AUTHORIZATION="Bearer token-vencido")

    assert anonimo.post(REGISTRAR, REGISTRO, format="json").status_code == 201


def test_registro_despues_de_usuarios_con_id_fijo(anonimo, usuario_admin, usuario_cliente):
    assert anonimo.post(REGISTRAR, REGISTRO, format="json").status_code == 201


# --- Perfil -------------------------------------------------------------------


def test_ver_mi_perfil(cliente, usuario_cliente):
    respuesta = cliente.get(YO)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == CLIENTE_ID
    assert cuerpo["email"] == "cliente@example.com"
    assert cuerpo["rol"] == "cliente"
    assert "password" not in cuerpo


def test_editar_mi_perfil(cliente, usuario_cliente):
    respuesta = cliente.patch(
        YO, {"nombre": "Juan Carlos", "apellidos": "Gómez", "telefono": "3531234567"}, format="json"
    )

    assert respuesta.status_code == 200
    usuario_cliente.refresh_from_db()
    assert (usuario_cliente.nombre, usuario_cliente.apellidos, usuario_cliente.telefono) == (
        "Juan Carlos",
        "Gómez",
        "3531234567",
    )


def test_email_rol_y_seguridad_son_de_solo_lectura(cliente, usuario_cliente):
    cliente.patch(
        YO,
        {
            "email": "nuevo@example.com",
            "rol": "administrador",
            "email_verificado": True,
            "token_version": 9,
            "tiene_2fa": True,
        },
        format="json",
    )

    usuario_cliente.refresh_from_db()
    assert usuario_cliente.email == "cliente@example.com"
    assert usuario_cliente.rol == "cliente"
    assert usuario_cliente.email_verificado is False
    assert usuario_cliente.token_version == 0
    assert usuario_cliente.tiene_2fa is False


@pytest.mark.parametrize(
    ("datos", "campo"), [({"telefono": "123"}, "telefono"), ({"nombre": ""}, "nombre")]
)
def test_editar_perfil_invalido(cliente, datos, campo):
    respuesta = cliente.patch(YO, datos, format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_perfil_de_un_token_sin_usuario_404(anonimo):
    respuesta = api_con(token(999)).get(YO)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"


def test_perfil_401_y_403(anonimo, sin_rol):
    assert anonimo.get(YO).status_code == 401
    assert anonimo.patch(YO, {"nombre": "x"}, format="json").status_code == 401
    assert sin_rol.get(YO).status_code == 403


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_el_perfil_sigue_pidiendo_token(anonimo):
    assert anonimo.get(YO).status_code == 401


# --- Direcciones --------------------------------------------------------------


def test_crear_direccion(cliente, usuario_cliente):
    respuesta = cliente.post(DIRECCIONES, DIRECCION, format="json")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["calle"] == "Camino a La Palma"
    assert cuerpo["predeterminada"] is True  # la primera
    assert "usuario" not in cuerpo
    assert Direccion.objects.get().usuario == usuario_cliente


def test_crear_direccion_ignora_el_usuario_del_cuerpo(cliente, usuario_cliente, usuario_otro):
    cliente.post(DIRECCIONES, {**DIRECCION, "usuario": usuario_otro.id}, format="json")

    assert Direccion.objects.get().usuario == usuario_cliente


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"codigo_postal": "123"}, "codigo_postal"),
        ({"calle": ""}, "calle"),
        ({"estado": None}, "estado"),
    ],
)
def test_crear_direccion_invalida(cliente, cambio, campo):
    respuesta = cliente.post(DIRECCIONES, {**DIRECCION, **cambio}, format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_listar_solo_mis_direcciones(cliente, usuario_cliente, usuario_otro):
    DireccionFactory(usuario=usuario_cliente, alias="Casa")
    DireccionFactory(usuario=usuario_otro, alias="Ajena")

    respuesta = cliente.get(DIRECCIONES)

    assert respuesta.status_code == 200
    assert [d["alias"] for d in respuesta.json()["results"]] == ["Casa"]


def test_una_sola_predeterminada_por_la_api(cliente, usuario_cliente):
    primera = cliente.post(DIRECCIONES, DIRECCION, format="json").json()
    segunda = cliente.post(DIRECCIONES, {**DIRECCION, "alias": "Bodega"}, format="json").json()

    respuesta = cliente.patch(
        f"{DIRECCIONES}{segunda['id']}/", {"predeterminada": True}, format="json"
    )

    assert respuesta.status_code == 200
    marcadas = Direccion.objects.filter(usuario=usuario_cliente, predeterminada=True)
    assert [d.id for d in marcadas] == [segunda["id"]]
    assert cliente.get(f"{DIRECCIONES}{primera['id']}/").json()["predeterminada"] is False


def test_editar_y_borrar_direccion(cliente, usuario_cliente):
    direccion = DireccionFactory(usuario=usuario_cliente, predeterminada=True)
    url = f"{DIRECCIONES}{direccion.id}/"

    assert (
        cliente.patch(url, {"referencias": "Junto a la bodega"}, format="json").status_code == 200
    )
    direccion.refresh_from_db()
    assert direccion.referencias == "Junto a la bodega"
    assert cliente.delete(url).status_code == 204
    assert not Direccion.objects.exists()


def test_direccion_ajena_404(cliente, usuario_otro):
    ajena = DireccionFactory(usuario=usuario_otro)
    url = f"{DIRECCIONES}{ajena.id}/"

    assert cliente.get(url).status_code == 404
    assert cliente.patch(url, {"alias": "mía"}, format="json").status_code == 404
    assert cliente.delete(url).status_code == 404
    assert Direccion.objects.filter(id=ajena.id).exists()


def test_el_admin_tampoco_ve_direcciones_ajenas(admin, usuario_otro):
    ajena = DireccionFactory(usuario=usuario_otro)

    assert admin.get(f"{DIRECCIONES}{ajena.id}/").status_code == 404
    assert admin.get(DIRECCIONES).json()["count"] == 0


def test_direcciones_401_y_403(anonimo, sin_rol, usuario_cliente):
    direccion = DireccionFactory(usuario=usuario_cliente)

    assert anonimo.get(DIRECCIONES).status_code == 401
    assert anonimo.post(DIRECCIONES, DIRECCION, format="json").status_code == 401
    assert anonimo.delete(f"{DIRECCIONES}{direccion.id}/").status_code == 401
    assert sin_rol.get(DIRECCIONES).status_code == 403
    assert sin_rol.post(DIRECCIONES, DIRECCION, format="json").status_code == 403


def test_direcciones_de_un_token_sin_usuario_404():
    assert api_con(token(999)).post(DIRECCIONES, DIRECCION, format="json").status_code == 404


# --- Listado del administrador ------------------------------------------------


def test_admin_lista_usuarios_paginado(admin):
    UsuarioFactory.create_batch(22)

    primera = admin.get(USUARIOS).json()

    assert primera["count"] == 23  # 22 + el administrador
    assert len(primera["results"]) == 20
    assert "password" not in primera["results"][0]


def test_admin_filtra_por_rol_y_busca(admin):
    UsuarioFactory(email="lucia@example.com", nombre="Lucía", apellidos="Torres")
    UsuarioFactory(email="pedro@huerta.mx", nombre="Pedro")

    administradores = admin.get(USUARIOS, {"rol": "administrador"}).json()
    por_correo = admin.get(USUARIOS, {"q": "HUERTA"}).json()
    por_nombre = admin.get(USUARIOS, {"q": "torres"}).json()

    assert [u["email"] for u in administradores["results"]] == ["admin@example.com"]
    assert [u["email"] for u in por_correo["results"]] == ["pedro@huerta.mx"]
    assert [u["email"] for u in por_nombre["results"]] == ["lucia@example.com"]


def test_filtro_de_rol_invalido_400(admin):
    respuesta = admin.get(USUARIOS, {"rol": "superusuario"})

    assert respuesta.status_code == 400
    assert "rol" in respuesta.json()["campos"]


def test_listado_401_y_403(anonimo, cliente):
    assert anonimo.get(USUARIOS).status_code == 401
    assert cliente.get(USUARIOS).status_code == 403


def test_no_hay_cambio_de_rol_por_api(admin, usuario_cliente):
    respuesta = admin.patch(f"{USUARIOS}{CLIENTE_ID}/rol/", {"rol": "administrador"}, format="json")

    assert respuesta.status_code in (404, 405)
    usuario_cliente.refresh_from_db()
    assert usuario_cliente.rol == "cliente"
