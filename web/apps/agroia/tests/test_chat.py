"""Chat con AgroIA: la orquestación del gateway entre svc-contenido y svc-ia."""

import json
import logging

import httpx
import pytest

from tests.servicios_falsos import error

pytestmark = pytest.mark.django_db

CONV = "6630c1f2a4b5c6d7e8f90123"
RUTA_CONV = f"/api/v1/conversaciones/{CONV}/"
RUTA_MENSAJES = f"{RUTA_CONV}mensajes/"
HISTORIAL = [
    {"rol": "usuario", "texto": "Tengo manchas negras.", "fuentes": []},
    {"rol": "agente", "texto": "Parece antracnosis.", "fuentes": ["Manual"]},
]
FUENTES = ["Marroquín-Pimentel (1999)", "SENASICA (2020)"]


def conversacion(mensajes=HISTORIAL):
    return {"id": CONV, "titulo": "Manchas", "mensajes": list(mensajes)}


def preparar(servicios, mensajes=HISTORIAL, agente=None, guardar=None):
    servicios.responder(
        "GET",
        "svc-contenido",
        "/api/v1/conversaciones/",
        httpx.Response(200, json={"count": 1, "results": [conversacion()]}),
    )
    servicios.responder(
        "GET", "svc-contenido", RUTA_CONV, httpx.Response(200, json=conversacion(mensajes))
    )
    servicios.responder(
        "POST", "svc-contenido", RUTA_MENSAJES, guardar or httpx.Response(201, json={})
    )
    servicios.responder(
        "POST",
        "svc-ia",
        "/agente/preguntar/",
        agente
        or httpx.Response(
            200,
            json={
                "id": "x",
                "estado": "listo",
                "respuesta": "Aplica un fungicida cúprico.",
                "fuentes": FUENTES,
            },
        ),
    )


def preguntar(client, texto="¿Cada cuándo aplico?"):
    return client.post(f"/agroia/{CONV}/preguntar/", {"pregunta": texto}, HTTP_HX_REQUEST="true")


def test_chat_pide_sesion(client):
    assert client.get("/agroia/")["Location"].startswith("/iniciar-sesion/?next=")


def test_pantalla_con_conversaciones_y_mensajes(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)

    html = client.get(f"/agroia/{CONV}/").content.decode()

    assert "Mis conversaciones" in html and "Parece antracnosis." in html
    assert "Fuentes" in html and "Manual" in html
    assert "AgroIA está escribiendo" in html  # el indicador de carga


def test_orquestacion_guarda_pregunta_pide_respuesta_y_guarda_respuesta(
    client, servicios, con_sesion
):
    con_sesion()
    preparar(servicios)

    respuesta = preguntar(client)

    html = respuesta.content.decode()
    assert "Aplica un fungicida cúprico." in html
    assert "Marroquín-Pimentel (1999)" in html  # fuentes bajo la respuesta
    orden = [(p.url.host, p.method, p.url.path) for p in servicios.peticiones]
    assert orden == [
        ("svc-contenido", "GET", RUTA_CONV),
        ("svc-contenido", "POST", RUTA_MENSAJES),
        ("svc-ia", "POST", "/agente/preguntar/"),
        ("svc-contenido", "POST", RUTA_MENSAJES),
    ]
    usuario, agente = [servicios.cuerpo(p) for p in servicios.de("svc-contenido", RUTA_MENSAJES)]
    assert usuario == {"rol": "usuario", "texto": "¿Cada cuándo aplico?"}
    assert agente == {"rol": "agente", "texto": "Aplica un fungicida cúprico.", "fuentes": FUENTES}
    # svc-ia recibe el historial anterior a la pregunta, sin las fuentes.
    assert servicios.cuerpo(servicios.de("svc-ia")[0]) == {
        "pregunta": "¿Cada cuándo aplico?",
        "historial": [
            {"rol": "usuario", "texto": "Tengo manchas negras."},
            {"rol": "agente", "texto": "Parece antracnosis."},
        ],
    }


def test_agente_caido_deja_la_pregunta_guardada_y_ofrece_reintentar(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, agente=error(503, "agente_no_disponible", "El agente no está disponible."))

    html = preguntar(client).content.decode()

    assert "AgroIA no pudo responder en este momento" in html
    assert "Reintentar" in html and 'id="reintentar" hx-swap-oob="true"' in html
    assert len(servicios.de("svc-contenido", RUTA_MENSAJES)) == 1  # solo la pregunta
    assert "El agente no está disponible." not in html  # sin detalles técnicos


def test_agente_lento_tambien_ofrece_reintentar(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)
    servicios.lentos.add("svc-ia")

    assert "Reintentar" in preguntar(client).content.decode()


def test_reintentar_no_vuelve_a_guardar_la_pregunta(client, servicios, con_sesion):
    con_sesion()
    pendiente = [*HISTORIAL, {"rol": "usuario", "texto": "¿Y la dosis?", "fuentes": []}]
    preparar(servicios, mensajes=pendiente)

    html = client.post(f"/agroia/{CONV}/reintentar/", HTTP_HX_REQUEST="true").content.decode()

    assert "Aplica un fungicida cúprico." in html
    (guardado,) = servicios.de("svc-contenido", RUTA_MENSAJES)
    assert servicios.cuerpo(guardado)["rol"] == "agente"
    enviado = servicios.cuerpo(servicios.de("svc-ia")[0])
    assert enviado["pregunta"] == "¿Y la dosis?"
    assert len(enviado["historial"]) == 2  # sin la pregunta pendiente


def test_la_pantalla_muestra_reintentar_si_quedo_una_pregunta_sin_respuesta(
    client, servicios, con_sesion
):
    con_sesion()
    preparar(servicios, mensajes=[{"rol": "usuario", "texto": "¿Y la dosis?", "fuentes": []}])

    assert (
        "Tu última pregunta no tiene respuesta todavía"
        in client.get(f"/agroia/{CONV}/").content.decode()
    )


def test_si_falla_guardar_la_respuesta_se_muestra_igual_y_queda_en_el_log(
    client, servicios, con_sesion, caplog
):
    con_sesion()
    caplog.set_level(logging.INFO, logger="seguridad")
    llamadas = []

    def guardar(peticion):
        llamadas.append(peticion)
        if len(llamadas) == 2:  # la respuesta del agente
            raise httpx.ConnectError("svc-contenido caído")
        return httpx.Response(201, json={})

    preparar(servicios, guardar=guardar)

    html = preguntar(client).content.decode()

    assert "Aplica un fungicida cúprico." in html
    assert "No pudimos guardar esta respuesta en tu historial." in html
    eventos = [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]
    assert eventos[-1]["evento"] == "respuesta_no_guardada"
    assert eventos[-1]["conversacion"] == CONV
    assert "Aplica un fungicida" not in caplog.text  # el texto no va al log


def test_conversacion_llena_no_llama_al_agente_y_ofrece_una_nueva(client, servicios, con_sesion):
    con_sesion()
    preparar(
        servicios, guardar=error(409, "conversacion_llena", "La conversación llegó al límite.")
    )

    html = preguntar(client).content.decode()

    assert "llegó a su límite de mensajes" in html and "Iniciar una conversación nueva" in html
    assert servicios.de("svc-ia") == []


def test_nueva_conversacion_con_la_primera_pregunta(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, mensajes=[])
    servicios.responder(
        "POST",
        "svc-contenido",
        "/api/v1/conversaciones/",
        httpx.Response(201, json={"id": CONV, "titulo": "x"}),
    )

    respuesta = client.post("/agroia/nueva/", {"pregunta": "¿Qué es la roña?"})

    assert respuesta["Location"] == f"/agroia/{CONV}/"
    crear = servicios.de("svc-contenido", "/api/v1/conversaciones/")
    assert servicios.cuerpo(next(p for p in crear if p.method == "POST")) == {
        "titulo": "¿Qué es la roña?"
    }
    assert servicios.de("svc-ia")


def test_pregunta_vacia(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)

    html = preguntar(client, "   ").content.decode()

    assert "Escribe una pregunta." in html
    assert servicios.peticiones == []


def test_borrar_conversacion(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("DELETE", "svc-contenido", RUTA_CONV, httpx.Response(204))

    respuesta = client.post(f"/agroia/{CONV}/borrar/")

    assert respuesta["Location"] == "/agroia/"


def test_conversacion_ajena_404(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_CONV, error(404, "no_encontrado"))

    assert client.get(f"/agroia/{CONV}/").status_code == 404
