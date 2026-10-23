"""POST /agente/preguntar/: traducción al API del agente, simulado con httpx.MockTransport."""

import json

import httpx
import pytest

from app.agente import MAX_HISTORIAL, ClienteAgente, construir_mensaje, obtener_agente
from app.main import app

URL = "/agente/preguntar/"


def agente_simulado(manejador):
    """Sustituye la dependencia del agente por uno que responde con `manejador`."""
    peticiones: list[httpx.Request] = []

    def registrar(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return manejador(peticion)

    def dependencia():
        with httpx.Client(
            base_url="http://agente-de-prueba:8000", transport=httpx.MockTransport(registrar)
        ) as http:
            yield ClienteAgente(http)

    app.dependency_overrides[obtener_agente] = dependencia
    return peticiones


def responde(texto: str):
    return lambda peticion: httpx.Response(200, json={"response": texto, "session_id": "x"})


def test_pregunta_correcta(cliente_http, como_cliente):
    peticiones = agente_simulado(responde("Riega cada 3 a 5 días."))

    respuesta = cliente_http.post(
        URL, json={"pregunta": "¿Cada cuándo riego?"}, headers=como_cliente
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "listo"
    assert cuerpo["respuesta"] == "Riega cada 3 a 5 días."
    assert cuerpo["fuentes"] == []
    assert len(cuerpo["id"]) == 32
    enviado = json.loads(peticiones[0].content)
    assert peticiones[0].url.path == "/chat"
    assert enviado["message"] == "¿Cada cuándo riego?"
    assert len(enviado["session_id"]) == 32


def test_cada_peticion_usa_una_sesion_nueva(cliente_http, como_cliente):
    peticiones = agente_simulado(responde("ok"))

    cliente_http.post(URL, json={"pregunta": "uno"}, headers=como_cliente)
    cliente_http.post(URL, json={"pregunta": "dos"}, headers=como_cliente)

    sesiones = {json.loads(p.content)["session_id"] for p in peticiones}
    assert len(sesiones) == 2


def test_el_historial_viaja_como_contexto(cliente_http, como_cliente):
    peticiones = agente_simulado(responde("Cada 15 días."))
    historial = [
        {"rol": "usuario", "texto": "Tengo manchas negras en el fruto."},
        {"rol": "agente", "texto": "Parece antracnosis."},
    ]

    cliente_http.post(
        URL, json={"pregunta": "¿Cada cuándo aplico?", "historial": historial}, headers=como_cliente
    )

    mensaje = json.loads(peticiones[0].content)["message"]
    assert "Productor: Tengo manchas negras en el fruto." in mensaje
    assert "AgroIA: Parece antracnosis." in mensaje
    assert mensaje.endswith("Pregunta actual: ¿Cada cuándo aplico?")


def test_solo_se_envian_las_ultimas_10_entradas():
    historial = [{"rol": "usuario", "texto": f"mensaje {i}"} for i in range(15)]

    mensaje = construir_mensaje("¿Y ahora?", historial)

    assert "mensaje 4" not in mensaje
    assert "mensaje 5" in mensaje and "mensaje 14" in mensaje
    assert mensaje.count("Productor:") == MAX_HISTORIAL


def test_sin_historial_se_envia_solo_la_pregunta():
    assert construir_mensaje("Hola", []) == "Hola"


@pytest.mark.parametrize(
    "manejador",
    [
        pytest.param(
            lambda p: httpx.Response(503, json={"detail": "El servicio de IA no está disponible"}),
            id="agente-503",
        ),
        pytest.param(lambda p: httpx.Response(500, text="Internal Server Error"), id="agente-500"),
        pytest.param(lambda p: httpx.Response(200, text="<html>no es json</html>"), id="no-json"),
        pytest.param(lambda p: httpx.Response(200, json={"response": ""}), id="respuesta-vacia"),
        pytest.param(lambda p: httpx.Response(200, json={"otra": "cosa"}), id="sin-response"),
    ],
)
def test_error_del_agente_503(cliente_http, como_cliente, manejador):
    agente_simulado(manejador)

    respuesta = cliente_http.post(URL, json={"pregunta": "Hola"}, headers=como_cliente)

    assert respuesta.status_code == 503
    assert respuesta.json()["error"] == "agente_no_disponible"


@pytest.mark.parametrize(
    "excepcion",
    [httpx.ReadTimeout("lento"), httpx.ConnectTimeout("lento"), httpx.ConnectError("caído")],
    ids=["timeout-lectura", "timeout-conexion", "sin-conexion"],
)
def test_timeout_o_agente_caido_503(cliente_http, como_cliente, excepcion):
    def falla(peticion):
        raise excepcion

    agente_simulado(falla)

    respuesta = cliente_http.post(URL, json={"pregunta": "Hola"}, headers=como_cliente)

    assert respuesta.status_code == 503
    assert respuesta.json()["error"] == "agente_no_disponible"


def test_si_falla_no_se_registra_la_solicitud(cliente_http, como_cliente):
    from app.solicitudes import registro

    agente_simulado(lambda p: httpx.Response(500))

    cliente_http.post(URL, json={"pregunta": "Hola"}, headers=como_cliente)

    assert registro._datos == {}


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"pregunta": ""}, "pregunta"),
        ({"pregunta": "   "}, "pregunta"),
        ({}, "pregunta"),
        ({"pregunta": "x", "historial": [{"rol": "sistema", "texto": "x"}]}, "historial.0.rol"),
        ({"pregunta": "x" * 4001}, "pregunta"),
    ],
)
def test_validacion_400(cliente_http, como_cliente, cuerpo, campo):
    agente_simulado(responde("no debería llamarse"))

    respuesta = cliente_http.post(URL, json=cuerpo, headers=como_cliente)

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert campo in respuesta.json()["campos"]


def test_401_y_403(cliente_http, sin_rol):
    peticiones = agente_simulado(responde("no debería llamarse"))

    assert cliente_http.post(URL, json={"pregunta": "Hola"}).status_code == 401
    assert cliente_http.post(URL, json={"pregunta": "Hola"}, headers=sin_rol).status_code == 403
    assert peticiones == []
