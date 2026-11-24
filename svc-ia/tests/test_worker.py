"""Worker de svc-ia (app.worker) con el agente simulado y Redis simulado."""

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

import fakeredis
import httpx
import pytest

from agroia_comun.eventos import Consumidor, Sobre, conexion, publicar
from agroia_comun.eventos.catalogo import STREAM_FALLIDOS, STREAM_IA_RESULTADOS
from agroia_comun.eventos.consumidor import Ocupado
from app import worker
from app.agente import ClienteAgente
from app.config import Settings, settings, validar
from app.vision import ClasificadorDePrueba

PREGUNTA = "¿Qué hago con las manchas negras en mis aguacates de Ziracuaretiro?"
RESPUESTA = "Parece antracnosis: aplica un fungicida cúprico cada 21 días."
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def redis():
    servidor = fakeredis.FakeServer()
    texto = fakeredis.FakeRedis(server=servidor, decode_responses=True)
    conexion.usar(texto, binario=fakeredis.FakeRedis(server=servidor))
    yield texto
    conexion.usar(None)


class AgenteFalso:
    """Responde con lo que se le indique; cuenta las llamadas."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.llamadas += 1
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


@pytest.fixture
def agente(monkeypatch):
    def usar(*respuestas) -> AgenteFalso:
        falso = AgenteFalso(*respuestas)
        monkeypatch.setattr(
            worker,
            "agente",
            lambda: ClienteAgente(httpx.Client(base_url="http://agente",
                                               transport=httpx.MockTransport(falso))),
        )  # fmt: skip
        return falso

    return usar


def bien() -> httpx.Response:
    return httpx.Response(200, json={"response": RESPUESTA, "fuentes": ["Manual del aguacate"]})


def pregunta(vence_en: datetime | None = None) -> Sobre:
    vence = vence_en or datetime.now(UTC) + timedelta(minutes=3)
    return publicar(
        "ia_pregunta_solicitada",
        {
            "solicitud_id": str(uuid.uuid4()),
            "usuario_id": str(uuid.uuid4()),
            "conversacion_id": "6afe7fe1ae4b683f2b9e996f",
            "pregunta": PREGUNTA,
            "historial": [{"rol": "usuario", "texto": "Hola"}],
            "vence_en": vence.isoformat(),
        },
        origen="svc-contenido",
    )


def resultados(redis) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis.xrange(STREAM_IA_RESULTADOS)]


def consumidor(redis, **opciones) -> Consumidor:
    c = Consumidor(
        worker.GRUPO, worker.MANEJADORES, al_agotar=worker.AL_AGOTAR, cliente=redis,
        bloqueo_ms=10, latido=0.01, espera_base=0.02, **opciones,
    )  # fmt: skip
    c.preparar()
    return c


# --- Pregunta -------------------------------------------------------------------------------


def test_una_respuesta_correcta_publica_ia_respuesta_generada(redis, agente):
    falso = agente(bien())
    sobre = pregunta()

    worker.responder(sobre)

    [resultado] = resultados(redis)
    assert resultado["tipo"] == "ia_respuesta_generada"
    assert resultado["datos"]["respuesta"] == RESPUESTA
    assert resultado["datos"]["fuentes"] == ["Manual del aguacate"]
    assert resultado["datos"]["solicitud_id"] == sobre.datos["solicitud_id"]
    assert falso.llamadas == 1
    assert redis.get(worker.llave_de_candado(sobre.datos["solicitud_id"])) == "hecho"


def test_la_respuesta_hereda_la_correlacion_de_la_solicitud(redis, agente):
    agente(bien())
    sobre = pregunta()

    consumidor(redis).una_vuelta()

    assert resultados(redis)[0]["correlacion_id"] == sobre.correlacion_id


def test_la_misma_solicitud_dos_veces_llama_una_sola_vez_al_agente(redis, agente):
    falso = agente(bien())
    sobre = pregunta()

    worker.responder(sobre)
    worker.responder(sobre)

    assert falso.llamadas == 1
    assert len(resultados(redis)) == 1


def test_si_otro_la_esta_procesando_lanza_ocupado(redis, agente):
    agente(bien())
    sobre = pregunta()
    redis.set(worker.llave_de_candado(sobre.datos["solicitud_id"]), "procesando")

    with pytest.raises(Ocupado):
        worker.responder(sobre)


@pytest.mark.parametrize(
    "falla",
    [
        httpx.Response(503, json={"detail": "El servicio de IA no está disponible"}),
        httpx.Response(429, json={"detail": "rate limit"}),
        httpx.ReadTimeout("tardó"),
        httpx.ConnectError("sin conexión"),
    ],
    ids=["503", "429", "timeout", "sin-conexion"],
)
def test_un_error_que_se_reintenta_lanza_y_suelta_el_candado(redis, agente, falla):
    agente(falla)
    sobre = pregunta()

    with pytest.raises(Exception):  # noqa: B017 - el tipo depende del caso
        worker.responder(sobre)

    assert resultados(redis) == []
    assert redis.get(worker.llave_de_candado(sobre.datos["solicitud_id"])) is None


@pytest.mark.parametrize(
    "falla",
    [httpx.Response(422, json={"detail": "inválida"}), httpx.Response(200, json={"response": ""})],
    ids=["422", "respuesta-vacia"],
)
def test_un_error_que_no_se_reintenta_publica_la_fallida_al_momento(redis, agente, falla):
    falso = agente(falla)
    pregunta()

    consumidor(redis).una_vuelta()

    [resultado] = resultados(redis)
    assert resultado["tipo"] == "ia_respuesta_fallida"
    assert resultado["datos"]["codigo"] == "pregunta_invalida"
    assert falso.llamadas == 1


def test_al_agotar_los_reintentos_publica_agente_no_disponible(redis, agente, caplog):
    caplog.set_level(logging.INFO)
    falso = agente(httpx.Response(503, json={}))
    pregunta()
    c = consumidor(redis, max_reintentos=2)

    for fallos in range(3):
        time.sleep(c.espera(fallos) + 0.02)
        c.una_vuelta()

    assert falso.llamadas == 3
    [resultado] = resultados(redis)
    assert resultado["tipo"] == "ia_respuesta_fallida"
    assert resultado["datos"]["codigo"] == "agente_no_disponible"
    [(_, fallido)] = redis.xrange(STREAM_FALLIDOS)
    assert fallido["datos_omitidos"] == "historial,pregunta"
    assert "Ziracuaretiro" not in json.dumps(fallido)
    assert "Ziracuaretiro" not in caplog.text


def test_un_error_y_luego_bien_responde_en_el_reintento(redis, agente):
    falso = agente(httpx.Response(503, json={}), bien())
    pregunta()
    c = consumidor(redis)

    c.una_vuelta()
    time.sleep(c.espera(1) + 0.02)
    c.una_vuelta()

    assert falso.llamadas == 2
    assert [r["tipo"] for r in resultados(redis)] == ["ia_respuesta_generada"]


def test_una_solicitud_vencida_no_llama_al_agente(redis, agente):
    falso = agente(bien())

    worker.responder(pregunta(vence_en=datetime.now(UTC) - timedelta(seconds=1)))

    assert falso.llamadas == 0
    assert resultados(redis)[0]["datos"]["codigo"] == "vencida"


def test_ni_la_pregunta_ni_la_respuesta_aparecen_en_los_logs(redis, agente, caplog):
    caplog.set_level(logging.DEBUG)
    agente(bien())
    pregunta()

    consumidor(redis).una_vuelta()

    assert "evento_procesado" in caplog.text
    assert "Ziracuaretiro" not in caplog.text and "fungicida cúprico" not in caplog.text


def test_varios_hilos_atienden_varias_preguntas_a_la_vez(redis, monkeypatch):
    """Cinco preguntas, un agente que tarda 0.3 s y 3 hilos: en fila serían 1.5 s."""

    def lento(peticion):
        time.sleep(0.3)
        return bien()

    monkeypatch.setattr(
        worker, "agente",
        lambda: ClienteAgente(httpx.Client(base_url="http://agente",
                                           transport=httpx.MockTransport(lento))),
    )  # fmt: skip
    for _ in range(5):
        pregunta()
    hilos = []

    def fabricar(sufijo):
        c = Consumidor(worker.GRUPO, worker.MANEJADORES, nombre=f"svc-ia-{sufijo}",
                       cliente=redis, bloqueo_ms=10, latido=0.05)  # fmt: skip
        hilos.append(c)
        return c

    inicio = time.monotonic()

    def vigilar():
        while len(resultados(redis)) < 5 and time.monotonic() - inicio < 5:
            time.sleep(0.02)
        for c in hilos:
            c.pedir_detener()

    import threading

    from agroia_comun.eventos.consumidor import correr_en_hilos

    threading.Thread(target=vigilar).start()
    monkeypatch.setattr("signal.signal", lambda *a: None)
    correr_en_hilos(fabricar, 3)

    assert len(resultados(redis)) == 5
    assert time.monotonic() - inicio < 1.3  # 2 rondas de 0.3 s, no 5


# --- Diagnóstico ----------------------------------------------------------------------------


def diagnostico(redis, imagen: bytes | None = PNG) -> Sobre:
    solicitud_id = str(uuid.uuid4())
    if imagen is not None:
        conexion.cliente_binario().set(worker.llave_de_imagen(solicitud_id), imagen, ex=60)
    return publicar(
        "diagnostico_solicitado",
        {
            "solicitud_id": solicitud_id,
            "diagnostico_id": "6adad34bdf98ab47ebafa190",
            "usuario_id": str(uuid.uuid4()),
            "vence_en": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
        },
        origen="svc-contenido",
    )


def test_sin_modelo_publica_modelo_no_disponible_y_borra_la_copia(redis):
    sobre = diagnostico(redis)

    worker.diagnosticar(sobre)

    [resultado] = resultados(redis)
    assert resultado["tipo"] == "diagnostico_fallido"
    assert resultado["datos"]["codigo"] == "modelo_no_disponible"
    assert (
        conexion.cliente_binario().get(worker.llave_de_imagen(sobre.datos["solicitud_id"])) is None
    )


def test_con_el_clasificador_de_prueba_publica_un_resultado_marcado(redis, monkeypatch):
    monkeypatch.setattr(worker, "obtener_clasificador", ClasificadorDePrueba)
    sobre = diagnostico(redis)

    worker.diagnosticar(sobre)

    [resultado] = resultados(redis)
    assert resultado["tipo"] == "diagnostico_generado"
    datos = resultado["datos"]
    assert datos["modelo_version"] == "prueba-no-es-un-modelo"
    assert abs(sum(datos["probabilidades"].values()) - 1) < 0.001
    assert datos["confianza"] == datos["probabilidades"][datos["clase"]]


def test_sin_la_copia_de_la_imagen_publica_imagen_no_disponible(redis):
    worker.diagnosticar(diagnostico(redis, imagen=None))
    assert resultados(redis)[0]["datos"]["codigo"] == "imagen_no_disponible"


def test_una_imagen_que_no_es_jpg_ni_png_publica_imagen_invalida(redis):
    worker.diagnosticar(diagnostico(redis, imagen=b"GIF89a" + b"0" * 20))
    assert resultados(redis)[0]["datos"]["codigo"] == "imagen_invalida"


# --- Configuración --------------------------------------------------------------------------


def test_el_clasificador_de_prueba_no_se_permite_sin_debug(monkeypatch):
    monkeypatch.setenv("IA_CLASIFICADOR_PRUEBA", "1")
    monkeypatch.setenv("DEBUG", "False")
    with pytest.raises(RuntimeError, match="DEBUG=True"):
        validar(Settings())


def test_sin_la_variable_no_hay_clasificador(monkeypatch):
    from app.vision import obtener_clasificador

    monkeypatch.setattr(settings, "clasificador_prueba", False)
    assert obtener_clasificador() is None
    monkeypatch.setattr(settings, "clasificador_prueba", True)
    monkeypatch.setattr(settings, "debug", False)
    assert obtener_clasificador() is None  # aun con la variable, sin DEBUG no
    monkeypatch.setattr(settings, "debug", True)
    assert isinstance(obtener_clasificador(), ClasificadorDePrueba)


# --- Correlación en la API ------------------------------------------------------------------


def test_la_api_devuelve_la_correlacion_validada(cliente_http):
    valor = str(uuid.uuid4())
    assert (
        cliente_http.get("/salud/", headers={"X-Correlacion-Id": valor}).headers["X-Correlacion-Id"]
        == valor
    )
    otra = cliente_http.get("/salud/", headers={"X-Correlacion-Id": "no-es-uuid"})
    assert uuid.UUID(otra.headers["X-Correlacion-Id"])
