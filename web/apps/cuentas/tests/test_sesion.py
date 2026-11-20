"""Sesión del gateway (sección 11): tokens en web_db, renovación automática y decoradores."""

import httpx
import pytest
from clientes.api import SesionApi, SesionExpirada
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import include, path

from apps.cuentas.decoradores import login_requerido, rol_requerido
from tests.servicios_falsos import error, par, token

pytestmark = pytest.mark.django_db

PERFIL = {
    "id": "c1e2a3b4-0000-4000-8000-000000000010",
    "email": "juan@example.com",
    "nombre": "Juan",
    "apellidos": "",
    "telefono": "",
    "email_verificado": True,
}


def responder_perfil(servicios, respuesta=None):
    servicios.responder(
        "GET", "svc-usuarios", "/api/v1/usuarios/yo/", respuesta or httpx.Response(200, json=PERFIL)
    )
    servicios.responder(
        "GET",
        "svc-usuarios",
        "/api/v1/usuarios/yo/direcciones/",
        httpx.Response(200, json={"count": 0, "results": []}),
    )


def peticion_con_sesion(datos: dict) -> object:
    sesion = SessionStore()
    for clave, valor in datos.items():
        sesion[clave] = valor
    sesion.save()
    request = RequestFactory().get("/mi-cuenta/", REMOTE_ADDR="190.1.2.3")
    request.session = sesion
    return request


# --- Renovación automática ------------------------------------------------------------------


def test_access_vencido_se_renueva_sin_que_el_usuario_lo_note(client, servicios, con_sesion):
    viejos = con_sesion()
    nuevos = par()
    llamadas = []

    def perfil(peticion):
        llamadas.append(peticion.headers["authorization"])
        if peticion.headers["authorization"] == f"Bearer {viejos['access']}":
            return error(401, "token_invalido")
        return httpx.Response(200, json=PERFIL)

    responder_perfil(servicios, perfil)
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", httpx.Response(200, json=nuevos)
    )

    respuesta = client.get("/mi-cuenta/")

    assert respuesta.status_code == 200
    assert llamadas == [f"Bearer {viejos['access']}", f"Bearer {nuevos['access']}"]
    (renovacion,) = servicios.de("svc-usuarios", "/api/v1/auth/token/renovar/")
    assert servicios.cuerpo(renovacion) == {"refresh": viejos["refresh"]}
    assert client.session["access"] == nuevos["access"]
    assert client.session["refresh"] == nuevos["refresh"]


def test_la_renovacion_actualiza_rol_y_verificacion_del_menu(servicios):
    request = peticion_con_sesion(
        {
            "access": "a",
            "refresh": "r",
            "usuario": {"id": "x", "nombre": "Juan", "rol": "cliente", "email_verificado": False},
        }
    )
    nuevo = {"access": token(rol="administrador", verificado=True), "refresh": "r2"}
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", httpx.Response(200, json=nuevo)
    )

    SesionApi(request).renovar()

    assert request.session["usuario"]["rol"] == "administrador"
    assert request.session["usuario"]["email_verificado"] is True
    assert request.session["usuario"]["nombre"] == "Juan"


def test_refresh_vencido_manda_al_login_con_next_y_mensaje(client, servicios, con_sesion):
    con_sesion()
    responder_perfil(servicios, error(401, "token_invalido"))
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", error(401, "refresh_invalido")
    )

    respuesta = client.get("/mi-cuenta/", follow=True)

    assert respuesta.redirect_chain[0] == ("/iniciar-sesion/?next=%2Fmi-cuenta%2F", 302)
    assert "Tu sesión expiró" in respuesta.content.decode()
    assert "access" not in client.session  # la sesión se vació


def test_sesion_expirada_en_htmx_usa_hx_redirect(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/usuarios/yo/direcciones/", error(401, "token_invalido")
    )
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", error(401, "refresh_invalido")
    )
    datos = {
        "calle": "Hidalgo",
        "numero": "1",
        "colonia": "Centro",
        "municipio": "Jiquilpan",
        "estado": "Michoacán",
        "codigo_postal": "59510",
    }

    respuesta = client.post("/mi-cuenta/direcciones/", datos, HTTP_HX_REQUEST="true")

    assert respuesta.status_code == 204
    assert respuesta["HX-Redirect"].startswith("/iniciar-sesion/?next=")


def test_renueva_una_sola_vez(servicios):
    request = peticion_con_sesion({"access": "a", "refresh": "r", "usuario": {}})
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", error(401, "token_invalido"))
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", httpx.Response(200, json=par())
    )

    with pytest.raises(SesionExpirada):
        SesionApi(request).llamar("tienda", "GET", "carrito/")

    assert len(servicios.de("svc-usuarios", "/api/v1/auth/token/renovar/")) == 1
    assert len(servicios.de("svc-tienda")) == 2


def test_dos_peticiones_a_la_vez_no_cierran_la_sesion(servicios):
    # Otra petición ya rotó el refresh y guardó el par nuevo en la base: se adopta.
    request = peticion_con_sesion({"access": "a", "refresh": "r-viejo", "usuario": {}})
    guardada = SessionStore(session_key=request.session.session_key)
    guardada.update({"access": "a-nuevo", "refresh": "r-nuevo", "usuario": {}})
    guardada.save()
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/token/renovar/", error(401, "refresh_invalido")
    )

    SesionApi(request).renovar()

    assert request.session["access"] == "a-nuevo"
    assert request.session["refresh"] == "r-nuevo"


def test_un_401_sin_sesion_no_intenta_renovar(servicios):
    request = peticion_con_sesion({})
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", error(401, "no_autenticado"))

    assert SesionApi(request).llamar("tienda", "GET", "carrito/").status_code == 401
    assert servicios.de("svc-usuarios") == []


def test_las_llamadas_llevan_la_ip_real_del_navegador(servicios):
    request = peticion_con_sesion({"access": "a"})
    request.META["HTTP_X_FORWARDED_FOR"] = "6.6.6.6"
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", httpx.Response(200, json={}))

    SesionApi(request).llamar("tienda", "GET", "carrito/")

    (peticion,) = servicios.de("svc-tienda")
    assert peticion.headers["x-forwarded-for"] == "190.1.2.3"
    assert peticion.headers["authorization"] == "Bearer a"


# --- Los tokens nunca llegan al navegador ------------------------------------------------


def test_el_jwt_no_aparece_en_el_html_ni_en_las_cookies(client, servicios, con_sesion):
    tokens = con_sesion()
    responder_perfil(servicios)

    respuesta = client.get("/mi-cuenta/")

    html = respuesta.content.decode()
    assert tokens["access"] not in html and tokens["refresh"] not in html
    for cookie in client.cookies.values():
        assert tokens["access"] not in cookie.value and tokens["refresh"] not in cookie.value


# --- Decoradores ------------------------------------------------------------------------


@login_requerido
def solo_con_sesion(request):
    return HttpResponse("dentro")


@rol_requerido("administrador")
def solo_administrador(request):
    return HttpResponse("panel")


urlpatterns = [
    path("privada/", solo_con_sesion),
    path("panel/", solo_administrador),
    path("", include("config.urls")),
]


@pytest.fixture
def con_vistas_de_prueba(settings):
    settings.ROOT_URLCONF = __name__


def test_login_requerido_manda_al_login(client, con_vistas_de_prueba):
    respuesta = client.get("/privada/")

    assert respuesta.status_code == 302
    assert respuesta["Location"] == "/iniciar-sesion/?next=%2Fprivada%2F"


def test_login_requerido_deja_pasar_con_sesion(client, con_sesion, con_vistas_de_prueba):
    con_sesion()

    assert client.get("/privada/").content == b"dentro"


def test_vista_de_administrador_redirige_a_un_cliente(client, con_sesion, con_vistas_de_prueba):
    con_sesion(rol="cliente")

    respuesta = client.get("/panel/", follow=True)

    assert respuesta.redirect_chain == [("/", 302)]
    assert "No tienes permiso" in respuesta.content.decode()


def test_vista_de_administrador_con_administrador(client, con_sesion, con_vistas_de_prueba):
    con_sesion(rol="administrador")

    assert client.get("/panel/").content == b"panel"
