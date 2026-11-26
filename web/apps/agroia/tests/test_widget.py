"""Widget flotante de AgroIA: el visitante ve la invitación sin llamar a servicios; el usuario
pregunta con el mismo flujo asíncrono de /agroia/; dónde no aparece; la conversación del
widget en la sesión; las preguntas sugeridas por sección; Permissions-Policy."""

from datetime import UTC, datetime

import httpx
import pytest

from apps.agroia import servicios as servicios_agroia
from tests.servicios_falsos import error

pytestmark = pytest.mark.django_db

CONV = "6630c1f2a4b5c6d7e8f90123"
OTRA = "6630c1f2a4b5c6d7e8f90999"
RUTA_CREAR = "/api/v1/conversaciones/"
SID = "5b8e2f1c-3d4a-4e6b-9c7d-1a2b3c4d5e6f"


def ruta_conv(conversacion: str, accion: str = "") -> str:
    return f"/api/v1/conversaciones/{conversacion}/{accion}"


def solicitud(estado="pendiente", codigo=None, **extra) -> dict:
    return {"id": SID, "estado": estado, "codigo": codigo,
            "creada_en": datetime.now(UTC).isoformat(), **extra}  # fmt: skip


def abrir(client, pagina="http://testserver/aviso-de-privacidad/", **datos):
    return client.get("/agroia/widget/", datos, HTTP_HX_REQUEST="true",
                      HTTP_HX_CURRENT_URL=pagina)  # fmt: skip


def preguntar(client, texto="¿Cada cuánto riego?"):
    return client.post("/agroia/widget/preguntar/", {"pregunta": texto}, HTTP_HX_REQUEST="true")


def crear_conversacion(servicios, conversacion=CONV):
    servicios.responder("POST", "svc-contenido", RUTA_CREAR,
                        httpx.Response(201, json={"id": conversacion, "titulo": "x"}))  # fmt: skip


# --- Visitante -------------------------------------------------------------------------------


def test_el_visitante_ve_el_saludo_y_la_invitacion_sin_llamar_a_servicios(client, servicios):
    respuesta = abrir(client, "http://testserver/catalogo/?q=fungicida")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "¡Hola! Soy AgroIA 🥑" in html
    assert "Tu asistente para el cultivo del aguacate. Pregúntame lo que quieras." in html
    assert 'href="/iniciar-sesion/?next=/catalogo/%3Fq%3Dfungicida"' in html
    assert 'href="/registro/?next=/catalogo/%3Fq%3Dfungicida"' in html
    assert "<textarea" not in html  # sin campo de pregunta
    assert "AgroIA es orientativo y no sustituye el diagnóstico de un profesional." in html
    assert servicios.peticiones == []


def test_el_regreso_del_visitante_solo_es_a_este_sitio(client, servicios):
    html = abrir(client, "https://otro-sitio.example/robar").content.decode()
    assert 'href="/iniciar-sesion/?next=/"' in html


def test_el_registro_lleva_el_regreso_hasta_el_enlace_para_iniciar_sesion(client):
    html = client.get("/registro/", {"next": "/catalogo/"}).content.decode()
    assert '<input type="hidden" name="next" value="/catalogo/">' in html
    html = client.get("/registro/", {"next": "https://otro-sitio.example/"}).content.decode()
    assert 'name="next"' not in html


def test_el_contenido_del_widget_sin_htmx_lleva_al_chat(client):
    assert client.get("/agroia/widget/")["Location"] == "/agroia/"


def test_el_visitante_no_puede_preguntar(client, servicios):
    respuesta = preguntar(client)
    assert respuesta.status_code == 204 and respuesta["HX-Redirect"].startswith("/iniciar-sesion/")
    assert servicios.peticiones == []


# --- Dónde aparece y carga diferida ----------------------------------------------------------


def test_la_pagina_trae_solo_la_burbuja_y_el_panel_vacio(client, servicios):
    html = client.get("/aviso-de-privacidad/").content.decode()

    assert 'x-data="widgetAgroia"' in html
    assert (
        'aria-label="Abrir el chat de AgroIA"' in html
        and 'aria-controls="widget-agroia-panel"' in html
    )
    assert 'hx-get="/agroia/widget/" hx-trigger="cargar"' in html  # carga diferida
    assert 'data-pendiente=""' in html
    assert "Iniciar sesión</a>" not in html.split('id="widget-agroia-contenido"')[1]
    assert servicios.peticiones == []


@pytest.mark.parametrize(
    "ruta",
    ["/iniciar-sesion/", "/registro/", "/recuperar/", "/reenviar-verificacion/",
     "/una-ruta-que-no-existe/"],
)  # fmt: skip
def test_no_aparece_en_las_pantallas_de_acceso_ni_en_un_404(client, ruta):
    assert "widgetAgroia" not in client.get(ruta).content.decode()


def test_no_aparece_en_el_chat_completo(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_CREAR,
                        httpx.Response(200, json={"count": 0, "results": []}))  # fmt: skip
    assert "widgetAgroia" not in client.get("/agroia/").content.decode()


def test_no_aparece_en_el_panel_de_administracion(client, servicios, con_sesion):
    con_sesion("administrador")
    html = client.get("/administracion/").content.decode()
    assert "widgetAgroia" not in html


def test_no_aparece_en_una_pagina_que_fallo(client, servicios):
    servicios.caidos.add("svc-tienda")
    respuesta = client.get("/catalogo/")
    assert respuesta.status_code == 503 and "widgetAgroia" not in respuesta.content.decode()


def test_permissions_policy_solo_permite_el_microfono_a_este_sitio(client):
    politica = client.get("/aviso-de-privacidad/")["Permissions-Policy"]
    assert "microphone=(self)" in politica and "camera=()" in politica


# --- Usuario: preguntar con el flujo asíncrono -----------------------------------------------


def test_el_usuario_sin_conversacion_ve_el_saludo_las_sugerencias_y_el_campo(
    client, servicios, con_sesion
):
    con_sesion()

    html = abrir(client).content.decode()

    assert "¡Hola! Soy AgroIA 🥑" in html
    assert 'id="widget-pregunta"' in html and 'name="pregunta"' in html
    assert 'placeholder="Escribe tu pregunta sobre el aguacate…"' in html
    for sugerencia in servicios_agroia.SUGERENCIAS_GENERALES:
        assert f'value="{sugerencia}"' in html
    assert 'href="/agroia/"' in html and "Ver historial completo" in html
    assert 'x-data="microfono"' in html  # el botón solo se muestra si el navegador tiene la API
    assert servicios.peticiones == []  # todavía no hay conversación que pedir


def test_la_primera_pregunta_crea_la_conversacion_y_espera_la_respuesta(
    client, servicios, con_sesion
):
    con_sesion()
    crear_conversacion(servicios)
    servicios.responder("POST", "svc-contenido", ruta_conv(CONV, "preguntar/"),
                        httpx.Response(202, json=solicitud()))  # fmt: skip

    html = preguntar(client).content.decode()

    assert servicios.cuerpo(servicios.de("svc-contenido", RUTA_CREAR)[0]) == {
        "titulo": "¿Cada cuánto riego?"
    }
    assert servicios.de("svc-ia") == []
    assert "¿Cada cuánto riego?" in html and "AgroIA está escribiendo" in html
    assert f'hx-get="/agroia/{CONV}/solicitud/"' in html and 'hx-trigger="load delay:2s"' in html
    assert '<div id="widget-sugerencias" hx-swap-oob="delete"></div>' in html
    sesion = client.session
    assert sesion[servicios_agroia.SESION_CONVERSACION] == CONV
    assert sesion[servicios_agroia.SESION_PENDIENTE] is True
    # En la página siguiente, el widget sabe que hay algo pendiente (sin pedir nada).
    servicios.peticiones.clear()
    pagina = client.get("/aviso-de-privacidad/").content.decode()
    assert 'data-pendiente="true"' in pagina and servicios.peticiones == []


def test_la_segunda_pregunta_usa_la_misma_conversacion(client, servicios, con_sesion):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = CONV
    sesion.save()
    servicios.responder("POST", "svc-contenido", ruta_conv(CONV, "preguntar/"),
                        httpx.Response(202, json=solicitud()))  # fmt: skip

    preguntar(client)

    assert servicios.de("svc-contenido", RUTA_CREAR) == []


def test_si_la_conversacion_se_borro_empieza_otra(client, servicios, con_sesion):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = OTRA
    sesion.save()
    servicios.responder(
        "POST", "svc-contenido", ruta_conv(OTRA, "preguntar/"), error(404, "no_encontrado")
    )
    crear_conversacion(servicios)
    servicios.responder("POST", "svc-contenido", ruta_conv(CONV, "preguntar/"),
                        httpx.Response(202, json=solicitud()))  # fmt: skip

    html = preguntar(client).content.decode()

    assert "AgroIA está escribiendo" in html
    assert client.session[servicios_agroia.SESION_CONVERSACION] == CONV


def test_muchas_preguntas_seguidas_no_dejan_una_conversacion_vacia(client, servicios, con_sesion):
    con_sesion()
    crear_conversacion(servicios)
    servicios.responder("POST", "svc-contenido", ruta_conv(CONV, "preguntar/"),
                        error(429, "demasiados_intentos", "x",
                              **{"Retry-After": "30"}))  # fmt: skip
    servicios.responder("DELETE", "svc-contenido", ruta_conv(CONV), httpx.Response(204))

    respuesta = preguntar(client)

    html = respuesta.content.decode()
    assert "Hiciste muchas preguntas seguidas. Espera 30 segundos" in html
    assert respuesta["X-Conservar-Pregunta"] == "1"
    assert [p.method for p in servicios.de("svc-contenido", ruta_conv(CONV))] == ["DELETE"]
    assert servicios_agroia.SESION_CONVERSACION not in client.session
    assert "widget-sugerencias" not in html  # las sugerencias siguen


def test_una_conversacion_llena_ofrece_empezar_otra_en_el_widget(client, servicios, con_sesion):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = CONV
    sesion.save()
    servicios.responder("POST", "svc-contenido", ruta_conv(CONV, "preguntar/"),
                        error(409, "conversacion_llena", "Llena."))  # fmt: skip

    html = preguntar(client).content.decode()

    assert (
        'hx-post="/agroia/widget/reiniciar/"' in html and "Empezar una conversación nueva" in html
    )


def test_al_abrir_con_una_conversacion_muestra_sus_mensajes_y_sigue_esperando(
    client, servicios, con_sesion
):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = CONV
    sesion.save()
    servicios.responder("GET", "svc-contenido", ruta_conv(CONV), httpx.Response(200, json={
        "id": CONV, "titulo": "Riego",
        "mensajes": [{"rol": "usuario", "texto": "¿Cada cuánto riego?", "fuentes": []}],
        "solicitud": solicitud()}))  # fmt: skip

    html = abrir(client).content.decode()

    assert "¿Cada cuánto riego?" in html
    assert f'hx-get="/agroia/{CONV}/solicitud/"' in html  # el polling sigue
    assert "widget-sugerencias" not in html
    assert client.session[servicios_agroia.SESION_PENDIENTE] is True


def test_al_llegar_la_respuesta_se_quita_la_marca_y_se_avisa_al_widget(
    client, servicios, con_sesion
):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = CONV
    sesion[servicios_agroia.SESION_PENDIENTE] = True
    sesion.save()
    servicios.responder("GET", "svc-contenido", ruta_conv(CONV, "solicitud/"), httpx.Response(
        200, json=solicitud("listo", respuesta="Riega cada **7 días**.",
                            fuentes=["Manual"])))  # fmt: skip

    respuesta = client.get(f"/agroia/{CONV}/solicitud/", HTTP_HX_REQUEST="true")

    assert respuesta["HX-Trigger"] == "agroia-respuesta"
    assert "<strong>7 días</strong>" in respuesta.content.decode()
    assert servicios_agroia.SESION_PENDIENTE not in client.session


def test_reiniciar_empieza_otra_sin_borrar_la_anterior(client, servicios, con_sesion):
    con_sesion()
    sesion = client.session
    sesion[servicios_agroia.SESION_CONVERSACION] = CONV
    sesion[servicios_agroia.SESION_PENDIENTE] = True
    sesion.save()

    html = client.post("/agroia/widget/reiniciar/", HTTP_HX_REQUEST="true",
                       HTTP_HX_CURRENT_URL="http://testserver/").content.decode()  # fmt: skip

    assert "¡Hola! Soy AgroIA 🥑" in html and "Empezaste una conversación nueva." in html
    assert servicios_agroia.SESION_CONVERSACION not in client.session
    assert servicios_agroia.SESION_PENDIENTE not in client.session
    assert servicios.peticiones == []  # la anterior no se borra: sigue en /agroia/


# --- Preguntas sugeridas por sección ---------------------------------------------------------


@pytest.mark.parametrize(
    "pagina, seccion",
    [
        ("http://testserver/diagnostico/", "diagnostico"),
        ("http://testserver/catalogo/", "catalogo"),
        ("http://testserver/carrito/", "tienda"),
    ],
)
def test_las_sugerencias_cambian_con_la_seccion(client, con_sesion, pagina, seccion):
    con_sesion()
    html = abrir(client, pagina).content.decode()
    for sugerencia in servicios_agroia.SUGERENCIAS[seccion]:
        assert f'value="{sugerencia}"' in html


def test_en_un_producto_las_sugerencias_llevan_su_nombre(client, con_sesion):
    con_sesion()
    html = abrir(client, "http://testserver/catalogo/oxicloruro/",
                 producto="Oxicloruro de cobre 1 kg").content.decode()  # fmt: skip
    assert 'value="¿Cómo y cuándo se aplica Oxicloruro de cobre 1 kg?"' in html


def test_el_nombre_del_producto_se_recorta_y_se_escapa(client, con_sesion):
    """Viene de un campo que el navegador puede cambiar."""
    con_sesion()
    malicioso = '<script>alert("x")</script><img src=x onerror=alert(1)>' + "a" * 200

    html = abrir(
        client, "http://testserver/catalogo/oxicloruro/", producto=malicioso
    ).content.decode()

    assert "<script>alert" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert servicios_agroia.nombre_de_producto(malicioso) == malicioso[:80]
    assert len(servicios_agroia.nombre_de_producto(malicioso)) == servicios_agroia.LARGO_PRODUCTO


def test_la_pagina_del_producto_manda_su_nombre_al_widget(client, tienda_falsa):
    html = client.get("/catalogo/caldo-bordeles/").content.decode()

    assert '<input type="hidden" name="producto" value="Caldo bordelés 1 kg">' in html


# --- «Copiar» en las respuestas (también en /agroia/) ----------------------------------------


def test_cada_respuesta_trae_copiar_y_la_pregunta_no(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_CREAR,
                        httpx.Response(200, json={"count": 0, "results": []}))  # fmt: skip
    servicios.responder("GET", "svc-contenido", ruta_conv(CONV), httpx.Response(200, json={
        "id": CONV, "titulo": "Riego", "solicitud": None, "mensajes": [
            {"rol": "usuario", "texto": "¿Riego?", "fuentes": []},
            {"rol": "agente", "texto": "Cada 7 días.", "fuentes": []}]}))  # fmt: skip

    html = client.get(f"/agroia/{CONV}/").content.decode()

    assert html.count('x-data="copiar"') == 1
    assert 'aria-label="Copiar la respuesta"' in html and 'x-ref="respuesta"' in html


def test_htmx_no_asienta_estilos_en_linea(client):
    """Al reemplazar el panel, HTMX copiaba `style` del campo viejo al nuevo (mismo id) y la
    CSP lo bloqueaba. `style` no está en attributesToSettle."""
    html = client.get("/aviso-de-privacidad/").content.decode()
    assert '"attributesToSettle": ["class", "width", "height"]' in html
