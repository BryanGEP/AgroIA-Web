"""Pantallas de cuenta: página completa, errores por campo, bloqueo y límite de intentos."""

import httpx
import pytest

from tests.servicios_falsos import USUARIO_ID, error, par

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
CREDENCIALES = {"email": "juan@example.com", "password": "Aguacate-Hass-2026"}


def login_correcto(servicios, verificado=True):
    tokens = par(verificado=verificado)
    usuario = {"id": USUARIO_ID, "nombre": "Juan", "rol": "cliente", "email_verificado": verificado}
    servicios.responder(
        "POST", "svc-usuarios", LOGIN, httpx.Response(200, json={**tokens, "usuario": usuario})
    )
    return tokens


# --- Iniciar sesión -------------------------------------------------------------------------


def test_pagina_de_inicio_de_sesion(client):
    html = client.get("/iniciar-sesion/").content.decode()

    assert '<label for="id_email"' in html and '<label for="id_password"' in html
    assert "csrfmiddlewaretoken" in html
    assert 'href="/recuperar/"' in html and 'href="/registro/"' in html


def test_login_guarda_la_sesion_y_vuelve_a_next(client, servicios):
    tokens = login_correcto(servicios)
    client.get("/iniciar-sesion/")
    llave_anterior = client.session.session_key

    respuesta = client.post("/iniciar-sesion/", {**CREDENCIALES, "next": "/catalogo/"})

    assert respuesta.status_code == 302 and respuesta["Location"] == "/catalogo/"
    assert client.session["access"] == tokens["access"]
    assert client.session["usuario"]["nombre"] == "Juan"
    assert client.session.session_key != llave_anterior  # cycle_key()
    cookie = client.cookies["sessionid"]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"


def test_el_login_manda_la_ip_real_del_navegador_a_svc_usuarios(client, servicios):
    # El bloqueo de axes y el límite por IP de svc-usuarios cuentan por esta IP.
    login_correcto(servicios)

    client.post(
        "/iniciar-sesion/", CREDENCIALES, REMOTE_ADDR="190.10.20.30", HTTP_X_FORWARDED_FOR="1.1.1.1"
    )

    (peticion,) = servicios.de("svc-usuarios", LOGIN)
    assert peticion.headers["x-forwarded-for"] == "190.10.20.30"
    assert servicios.cuerpo(peticion) == CREDENCIALES


def test_next_a_otro_sitio_se_ignora(client, servicios):
    login_correcto(servicios)

    respuesta = client.post("/iniciar-sesion/", {**CREDENCIALES, "next": "https://otro.example/"})

    assert respuesta["Location"] == "/"


def test_credenciales_invalidas(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        LOGIN,
        error(401, "credenciales_invalidas", "Correo o contraseña incorrectos."),
    )

    respuesta = client.post("/iniciar-sesion/", CREDENCIALES)

    assert respuesta.status_code == 200
    assert "Correo o contraseña incorrectos." in respuesta.content.decode()
    assert "access" not in client.session


def test_cuenta_bloqueada(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        LOGIN,
        error(
            403,
            "cuenta_bloqueada_temporalmente",
            "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos o restablece tu "
            "contraseña.",
        ),
    )

    html = client.post("/iniciar-sesion/", CREDENCIALES).content.decode()

    assert "Intenta de nuevo en 15 minutos" in html


def test_demasiados_intentos_dice_cuanto_esperar(client, servicios):
    servicios.responder(
        "POST", "svc-usuarios", LOGIN, error(429, "demasiados_intentos", **{"Retry-After": "42"})
    )

    html = client.post("/iniciar-sesion/", CREDENCIALES).content.decode()

    assert "Hiciste demasiados intentos. Espera 42 segundos" in html


def test_servicio_caido(client, servicios):
    servicios.caidos.add("svc-usuarios")

    html = client.post("/iniciar-sesion/", CREDENCIALES).content.decode()

    assert "no está disponible" in html


def test_menu_con_sesion_y_banner_sin_verificar(client, servicios, con_sesion):
    con_sesion(verificado=False, nombre="María")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/categorias/", httpx.Response(200, json={"results": []})
    )
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/productos/",
        httpx.Response(200, json={"count": 0, "results": []}),
    )

    html = client.get("/aviso-de-privacidad/").content.decode()

    assert "María" in html and "Cerrar sesión" in html and "Mi cuenta" in html
    assert "Verifica tu correo para poder comprar" in html
    assert 'href="/iniciar-sesion/' not in html


def test_sin_banner_con_correo_verificado(client, con_sesion):
    con_sesion(verificado=True)

    assert "Verifica tu correo" not in client.get("/aviso-de-privacidad/").content.decode()


# --- Cerrar sesión ----------------------------------------------------------------------------


def test_cerrar_sesion_solo_por_post(client, servicios, con_sesion, tienda_falsa):
    tokens = con_sesion()
    servicios.responder("POST", "svc-usuarios", "/api/v1/auth/logout/", httpx.Response(205))

    assert client.get("/cerrar-sesion/").status_code == 405
    respuesta = client.post("/cerrar-sesion/", follow=True)

    assert "Cerraste sesión." in respuesta.content.decode()
    assert "access" not in client.session
    (logout,) = servicios.de("svc-usuarios", "/api/v1/auth/logout/")
    assert servicios.cuerpo(logout) == {"refresh": tokens["refresh"]}


def test_cerrar_sesion_pide_csrf(con_sesion, servicios):
    from django.test import Client

    estricto = Client(enforce_csrf_checks=True)
    assert estricto.post("/cerrar-sesion/").status_code == 403


def test_cerrar_sesion_aunque_svc_usuarios_no_responda(client, servicios, con_sesion):
    con_sesion()
    servicios.caidos.add("svc-usuarios")

    client.post("/cerrar-sesion/")

    assert "access" not in client.session


# --- Registro -------------------------------------------------------------------------------


REGISTRO = {
    "nombre": "María",
    "apellidos": "López",
    "email": "maria@example.com",
    "password": "Aguacate-Hass-2026",
    "password_confirmacion": "Aguacate-Hass-2026",
    "acepto_privacidad": "on",
}


def test_registro_correcto(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/registro/",
        httpx.Response(201, json={"id": USUARIO_ID}),
    )

    respuesta = client.post("/registro/", REGISTRO)

    assert respuesta.status_code == 201
    assert "Revisa tu correo" in respuesta.content.decode()
    (peticion,) = servicios.de("svc-usuarios")
    assert servicios.cuerpo(peticion)["acepto_privacidad"] is True


def test_registro_muestra_los_errores_de_la_api_junto_a_cada_campo(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/registro/",
        error(
            400,
            "validacion",
            "Revisa los datos enviados.",
            campos={
                "email": ["email_registrado"],
                "password": ["Esta contraseña es demasiado común."],
            },
        ),
    )

    html = client.post("/registro/", REGISTRO).content.decode()

    assert 'id="id_email-error"' in html and "Ya existe una cuenta con este correo." in html
    assert 'id="id_password-error"' in html and "Esta contraseña es demasiado común." in html
    assert 'aria-invalid="true"' in html


def test_registro_sin_aceptar_el_aviso_no_llega_a_la_api(client, servicios):
    datos = {k: v for k, v in REGISTRO.items() if k != "acepto_privacidad"}

    html = client.post("/registro/", datos).content.decode()

    assert "debes aceptar el aviso de privacidad" in html
    assert servicios.peticiones == []


# --- Correo y contraseña --------------------------------------------------------------------


VERIFICAR = "/api/v1/auth/verificar-correo/"


@pytest.mark.parametrize(
    ("respuesta", "estado", "texto"),
    [
        (httpx.Response(200, json={"mensaje": "Correo verificado."}), 200, "Ya puedes comprar"),
        (
            httpx.Response(200, json={"mensaje": "Tu correo ya estaba verificado."}),
            200,
            "ya estaba verificado",
        ),
        (error(400, "token_expirado"), 400, "El enlace ya venció"),
        (error(400, "token_invalido"), 400, "El enlace no es válido"),
    ],
)
def test_verificar_correo_desde_el_enlace(client, servicios, respuesta, estado, texto):
    servicios.responder("POST", "svc-usuarios", VERIFICAR, respuesta)

    pagina = client.get("/verificar-correo/", {"token": "abc:123:firma"})

    assert pagina.status_code == estado
    assert texto in pagina.content.decode()
    assert servicios.cuerpo(servicios.de("svc-usuarios", VERIFICAR)[0]) == {
        "token": "abc:123:firma"
    }


def test_verificar_con_sesion_renueva_para_quitar_el_banner(client, servicios, con_sesion):
    con_sesion(verificado=False)
    servicios.responder(
        "POST",
        "svc-usuarios",
        VERIFICAR,
        httpx.Response(200, json={"mensaje": "Correo verificado."}),
    )
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/token/renovar/",
        httpx.Response(200, json=par(verificado=True)),
    )

    html = client.get("/verificar-correo/", {"token": "t"}).content.decode()

    assert client.session["usuario"]["email_verificado"] is True
    assert "Verifica tu correo para poder comprar" not in html


@pytest.mark.parametrize(
    ("ruta", "destino"),
    [
        ("/recuperar/", "/api/v1/auth/recuperar/"),
        ("/reenviar-verificacion/", "/api/v1/auth/reenviar-verificacion/"),
    ],
)
def test_formularios_de_correo_muestran_el_mensaje_generico(client, servicios, ruta, destino):
    servicios.responder(
        "POST",
        "svc-usuarios",
        destino,
        httpx.Response(
            200, json={"mensaje": "Si el correo está registrado, te enviamos un enlace."}
        ),
    )

    respuesta = client.post(ruta, {"email": "a@b.mx"}, follow=True)

    assert "Si el correo está registrado" in respuesta.content.decode()


def test_restablecer_contrasena(client, servicios):
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/restablecer/", httpx.Response(200, json={})
    )

    respuesta = client.post(
        "/restablecer/MTA/abc-123/",
        {"password": "Hass-Mendez-2026", "password_confirmacion": "Hass-Mendez-2026"},
    )

    assert respuesta.status_code == 302 and respuesta["Location"] == "/iniciar-sesion/"
    enviado = servicios.cuerpo(servicios.de("svc-usuarios")[0])
    assert enviado["uid"] == "MTA" and enviado["token"] == "abc-123"


def test_restablecer_con_enlace_vencido(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/restablecer/",
        error(400, "enlace_invalido", "El enlace no es válido o ya expiró. Solicita uno nuevo."),
    )

    respuesta = client.post(
        "/restablecer/MTA/x/", {"password": "a" * 10, "password_confirmacion": "a" * 10}
    )

    assert respuesta.status_code == 400
    assert 'href="/recuperar/"' in respuesta.content.decode()


def test_cambiar_contrasena_guarda_el_par_nuevo(client, servicios, con_sesion):
    con_sesion()
    nuevos = par()
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/cambiar-password/", httpx.Response(200, json=nuevos)
    )

    respuesta = client.post(
        "/mi-cuenta/contrasena/",
        {
            "password_actual": "a",
            "password_nueva": "Hass-Mendez-2026",
            "password_confirmacion": "Hass-Mendez-2026",
        },
    )

    assert respuesta.status_code == 302
    assert client.session["access"] == nuevos["access"]


def test_cambiar_contrasena_con_la_actual_incorrecta(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/cambiar-password/",
        error(400, "password_actual_incorrecta", "La contraseña actual no es correcta."),
    )

    html = client.post(
        "/mi-cuenta/contrasena/",
        {"password_actual": "a", "password_nueva": "b" * 10, "password_confirmacion": "b" * 10},
    ).content.decode()

    assert "La contraseña actual no es correcta." in html


# --- Mi cuenta ------------------------------------------------------------------------------


PERFIL = {
    "id": USUARIO_ID,
    "email": "juan@example.com",
    "nombre": "Juan",
    "apellidos": "Pérez",
    "telefono": "",
    "email_verificado": True,
}
DIRECCION = {
    "id": 3,
    "alias": "Huerta",
    "calle": "Camino a La Palma",
    "numero": "km 3",
    "colonia": "La Palma",
    "municipio": "Jiquilpan",
    "estado": "Michoacán",
    "codigo_postal": "59510",
    "referencias": "",
    "predeterminada": True,
}


def responder_mi_cuenta(servicios, direcciones=None):
    servicios.responder(
        "GET", "svc-usuarios", "/api/v1/usuarios/yo/", httpx.Response(200, json=PERFIL)
    )
    servicios.responder(
        "GET",
        "svc-usuarios",
        "/api/v1/usuarios/yo/direcciones/",
        httpx.Response(
            200,
            json={"count": 1, "results": direcciones if direcciones is not None else [DIRECCION]},
        ),
    )


def test_mi_cuenta_pide_sesion(client):
    respuesta = client.get("/mi-cuenta/")

    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/iniciar-sesion/?next=")


def test_mi_cuenta_muestra_datos_y_direcciones(client, servicios, con_sesion):
    con_sesion()
    responder_mi_cuenta(servicios)

    html = client.get("/mi-cuenta/").content.decode()

    assert "juan@example.com" in html and 'value="Pérez"' in html
    assert "Camino a La Palma" in html and "Predeterminada" in html


def test_editar_perfil_con_error_de_la_api(client, servicios, con_sesion):
    con_sesion()
    responder_mi_cuenta(servicios)
    servicios.responder(
        "PATCH",
        "svc-usuarios",
        "/api/v1/usuarios/yo/",
        error(
            400, "validacion", campos={"telefono": ["El teléfono debe tener de 10 a 15 dígitos."]}
        ),
    )

    respuesta = client.post("/mi-cuenta/", {"nombre": "Juan", "telefono": "123"})

    assert respuesta.status_code == 400
    assert 'id="id_telefono-error"' in respuesta.content.decode()


def test_agregar_direccion_con_htmx_devuelve_solo_la_lista(client, servicios, con_sesion):
    con_sesion()
    responder_mi_cuenta(servicios)
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/usuarios/yo/direcciones/",
        httpx.Response(201, json=DIRECCION),
    )
    datos = {
        k: DIRECCION[k]
        for k in ("calle", "numero", "colonia", "municipio", "estado", "codigo_postal")
    }

    respuesta = client.post("/mi-cuenta/direcciones/", datos, HTTP_HX_REQUEST="true")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert 'id="lista-direcciones"' in html and "<html" not in html


def test_agregar_direccion_con_error_muestra_el_campo(client, servicios, con_sesion):
    con_sesion()
    responder_mi_cuenta(servicios, direcciones=[])
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/usuarios/yo/direcciones/",
        error(
            400, "validacion", campos={"codigo_postal": ["El código postal debe tener 5 dígitos."]}
        ),
    )
    datos = {k: DIRECCION[k] for k in ("calle", "numero", "colonia", "municipio", "estado")}

    respuesta = client.post(
        "/mi-cuenta/direcciones/", {**datos, "codigo_postal": "595"}, HTTP_HX_REQUEST="true"
    )

    assert respuesta.status_code == 200  # HTMX 2 no reemplaza el contenido con un 4xx
    assert "El código postal debe tener 5 dígitos." in respuesta.content.decode()


def test_borrar_direccion_sin_javascript_vuelve_a_mi_cuenta(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "DELETE", "svc-usuarios", "/api/v1/usuarios/yo/direcciones/3/", httpx.Response(204)
    )

    respuesta = client.post("/mi-cuenta/direcciones/3/borrar/")

    assert respuesta.status_code == 302 and respuesta["Location"] == "/mi-cuenta/#direcciones"


def test_pantallas_sin_lenguaje_del_proyecto_escolar(client):
    for ruta in ("/iniciar-sesion/", "/registro/", "/recuperar/", "/reenviar-verificacion/"):
        html = client.get(ruta).content.decode().lower()
        assert "entrega" not in html and "fase " not in html
