"""Librería de eventos (agroia_comun.eventos) con Redis simulado (fakeredis)."""

import json
import logging
import subprocess
import sys
import time
import uuid

import fakeredis
import pytest
import redis

from agroia_comun.eventos import Consumidor, ErrorEvento, Sobre, operacion, publicar
from agroia_comun.eventos.catalogo import (
    CATALOGO,
    STREAM_FALLIDOS,
    STREAM_USUARIOS,
    TipoEvento,
    obtener_tipo,
    registrar_tipo,
)
from agroia_comun.eventos.en_django import correlacion_de

USUARIO = str(uuid.uuid4())
DATOS = {"usuario_id": USUARIO, "rol": "cliente"}
STREAM_PRUEBA = "agroia:eventos:prueba"


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def tipo_con_pregunta():
    """Un tipo de prueba con un campo que nunca se registra (como la pregunta de la fase 3)."""
    tipo = registrar_tipo(
        TipoEvento(
            nombre="prueba_pregunta",
            version=1,
            stream=STREAM_PRUEBA,
            campos={"usuario_id": "uuid", "pregunta": "texto"},
            no_registrables=frozenset({"pregunta"}),
        )
    )
    yield tipo
    CATALOGO.pop("prueba_pregunta")


def lineas(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "eventos"]


def consumidor(r, manejadores, **opciones) -> Consumidor:
    opciones = {"max_reintentos": 2, "espera_base": 0.02, "bloqueo_ms": 10, **opciones}
    c = Consumidor("svc-prueba", manejadores, cliente=r, **opciones)
    c.preparar()
    return c


def esperar(segundos: float) -> None:
    time.sleep(segundos + 0.02)


# --- catálogo y sobre --------------------------------------------------------------------


def test_usuario_registrado_esta_en_el_catalogo():
    tipo = obtener_tipo("usuario_registrado")
    assert tipo.stream == STREAM_USUARIOS
    assert tipo.version == 1
    tipo.validar_datos(DATOS)


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        ({**DATOS, "email": "ana@example.com"}, "no permitidos"),
        ({"usuario_id": USUARIO}, "faltan"),
        ({"usuario_id": "10", "rol": "cliente"}, "uuid"),
        ({"usuario_id": USUARIO, "rol": 3}, "texto"),
    ],
)
def test_rechaza_datos_que_no_cumplen_el_catalogo(r, datos, mensaje):
    with pytest.raises(ErrorEvento, match=mensaje):
        publicar("usuario_registrado", datos, origen="svc-usuarios", cliente=r)
    assert not r.exists(STREAM_USUARIOS)


def test_rechaza_un_tipo_desconocido(r):
    with pytest.raises(ErrorEvento, match="desconocido"):
        publicar("algo_que_no_existe", {}, origen="svc-usuarios", cliente=r)


# --- publicar ----------------------------------------------------------------------------


def test_publica_el_sobre_completo(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    correlacion = str(uuid.uuid4())

    sobre = publicar(
        "usuario_registrado", DATOS, origen="svc-usuarios", correlacion_id=correlacion, cliente=r
    )

    [(_, campos)] = r.xrange(STREAM_USUARIOS)
    guardado = json.loads(campos["sobre"])
    assert guardado == {
        "id": sobre.id,
        "tipo": "usuario_registrado",
        "version": 1,
        "fecha": sobre.fecha,
        "origen": "svc-usuarios",
        "correlacion_id": correlacion,
        "datos": DATOS,
    }
    [linea] = lineas(caplog)
    assert linea["evento"] == "evento_publicado"
    assert linea["evento_id"] == sobre.id
    assert "datos" not in linea and USUARIO not in json.dumps(linea)


@pytest.mark.parametrize("valor", [None, "", "no-es-uuid", "1; DROP", "x" * 500])
def test_correlacion_invalida_se_reemplaza_por_una_nueva(r, valor):
    sobre = publicar(
        "usuario_registrado", DATOS, origen="svc-usuarios", correlacion_id=valor, cliente=r
    )
    assert uuid.UUID(sobre.correlacion_id)
    assert sobre.correlacion_id != valor


def test_correlacion_de_la_peticion():
    class Peticion:
        headers = {"X-Correlacion-Id": "8D3F6C2A-1B4E-4F7A-9C5D-2E6F8A0B1C3D"}

    assert correlacion_de(Peticion()) == "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d"
    Peticion.headers = {"X-Correlacion-Id": "<script>"}
    assert uuid.UUID(correlacion_de(Peticion()))


class RedisCaido(fakeredis.FakeRedis):
    def xadd(self, *args, **kwargs):
        raise redis.ConnectionError("Error 111 connecting to redis:6379. Connection refused.")


def test_con_redis_caido_no_lanza_y_registra_evento_no_publicado(caplog):
    caplog.set_level(logging.INFO, logger="eventos")

    resultado = publicar("usuario_registrado", DATOS, origen="svc-usuarios", cliente=RedisCaido())

    assert resultado is None
    [linea] = lineas(caplog)
    assert linea["evento"] == "evento_no_publicado"
    assert linea["tipo"] == "usuario_registrado"
    assert "Connection refused" in linea["motivo"]
    assert linea["datos"] == DATOS  # para poder republicarlo a mano


def test_los_campos_no_registrables_no_llegan_a_ningun_log(r, caplog, tipo_con_pregunta):
    caplog.set_level(logging.INFO, logger="eventos")
    secreto = "¿Cómo curo la roña de mi huerta en Tancítaro?"
    datos = {"usuario_id": USUARIO, "pregunta": secreto}

    sobre = publicar("prueba_pregunta", datos, origen="web", cliente=r)
    publicar("prueba_pregunta", datos, origen="web", cliente=RedisCaido())
    consumidor(r, {"prueba_pregunta": lambda s: None}).una_vuelta()

    assert json.loads(r.xrange(STREAM_PRUEBA)[0][1]["sobre"])["datos"]["pregunta"] == secreto
    eventos = [x["evento"] for x in lineas(caplog)]
    assert eventos == ["evento_publicado", "evento_no_publicado", "evento_procesado"]
    assert secreto not in caplog.text
    no_publicado = lineas(caplog)[1]
    assert no_publicado["datos"] == {"usuario_id": USUARIO}
    assert sobre.datos["pregunta"] == secreto


# --- consumir ----------------------------------------------------------------------------


def publicar_uno(r, datos=DATOS) -> Sobre:
    return publicar("usuario_registrado", datos, origen="svc-usuarios", cliente=r)


def pendientes(r) -> int:
    return r.xpending(STREAM_USUARIOS, "svc-prueba")["pending"]


def test_procesa_confirma_y_marca(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    recibidos = []
    sobre = publicar_uno(r)

    assert consumidor(r, {"usuario_registrado": recibidos.append}).una_vuelta() == 1

    assert [s.id for s in recibidos] == [sobre.id]
    assert recibidos[0].datos == DATOS
    assert pendientes(r) == 0
    assert r.exists(f"agroia:procesados:svc-prueba:{sobre.id}")
    assert 0 < r.ttl(f"agroia:procesados:svc-prueba:{sobre.id}") <= 7 * 24 * 3600
    assert lineas(caplog)[-1]["evento"] == "evento_procesado"


def test_procesa_lo_publicado_antes_de_que_existiera_el_grupo(r):
    publicar_uno(r)
    recibidos = []

    consumidor(r, {"usuario_registrado": recibidos.append}).una_vuelta()

    assert len(recibidos) == 1


def test_el_mismo_evento_dos_veces_se_aplica_una(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    recibidos = []
    sobre = publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": recibidos.append})
    c.una_vuelta()

    r.xadd(STREAM_USUARIOS, {"sobre": sobre.a_json()})  # el mismo sobre llega otra vez
    c.una_vuelta()

    assert len(recibidos) == 1
    assert lineas(caplog)[-1]["evento"] == "evento_duplicado"
    assert pendientes(r) == 0


def test_otros_tipos_del_stream_se_ignoran(r):
    sobre = Sobre(
        id=str(uuid.uuid4()), tipo="rol_cambiado", version=1, fecha="2026-11-22T00:00:00+00:00",
        origen="svc-usuarios", correlacion_id=str(uuid.uuid4()), datos={},
    )  # fmt: skip
    r.xadd(STREAM_USUARIOS, {"sobre": sobre.a_json()})
    recibidos = []

    consumidor(r, {"usuario_registrado": recibidos.append}).una_vuelta()

    assert recibidos == []
    assert pendientes(r) == 0


class Falla:
    """Manejador que falla las primeras `veces` y luego guarda el evento."""

    def __init__(self, veces: int):
        self.veces = veces
        self.llamadas = 0
        self.guardados: list[str] = []

    def __call__(self, sobre: Sobre):
        self.llamadas += 1
        if self.llamadas <= self.veces:
            raise RuntimeError(f"falla {self.llamadas}")
        self.guardados.append(sobre.id)


def test_si_el_manejador_falla_no_marca_y_reintenta_con_espera_creciente(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    sobre = publicar_uno(r)
    manejador = Falla(veces=2)
    c = consumidor(r, {"usuario_registrado": manejador}, max_reintentos=3, espera_base=0.1)

    c.una_vuelta()  # 1.er intento: falla
    assert pendientes(r) == 1
    assert not r.exists(c.clave_procesado(sobre.id))

    c.una_vuelta()  # todavía no pasa la espera (0.1 s): no reintenta
    assert manejador.llamadas == 1

    esperar(c.espera(1))
    c.una_vuelta()  # 2.º intento: falla otra vez; ahora espera el doble
    assert manejador.llamadas == 2
    esperar(c.espera(1))
    c.una_vuelta()
    assert manejador.llamadas == 2  # 0.12 s no bastan: la espera ya es de 0.2 s

    esperar(c.espera(2))
    c.una_vuelta()  # 3.er intento: bien
    assert manejador.guardados == [sobre.id]
    assert pendientes(r) == 0
    assert r.exists(c.clave_procesado(sobre.id))
    reintentos = [x for x in lineas(caplog) if x["evento"] == "evento_reintentado"]
    assert [x["intento"] for x in reintentos] == [1, 2]
    assert [x["siguiente_en_segundos"] for x in reintentos] == [0.1, 0.2]
    assert "falla 1" in reintentos[0]["motivo"]


def test_al_agotar_los_reintentos_va_a_fallidos_con_el_motivo(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    sobre = publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": Falla(veces=99)}, max_reintentos=2)

    for entrega in range(1, 4):  # 1 intento + 2 reintentos
        esperar(c.espera(entrega))
        c.una_vuelta()

    assert pendientes(r) == 0
    [(_, fallido)] = r.xrange(STREAM_FALLIDOS)
    assert json.loads(fallido["sobre"])["id"] == sobre.id
    assert fallido["grupo"] == "svc-prueba"
    assert fallido["stream"] == STREAM_USUARIOS
    assert fallido["intentos"] == "3"
    assert "falla 3" in fallido["motivo"]
    assert not r.exists(c.clave_procesado(sobre.id))
    assert lineas(caplog)[-1]["evento"] == "evento_fallido"


def test_un_sobre_ilegible_va_directo_a_fallidos(r):
    r.xadd(STREAM_USUARIOS, {"sobre": "{no es json"})

    consumidor(r, {"usuario_registrado": Falla(0)}).una_vuelta()

    [(_, fallido)] = r.xrange(STREAM_FALLIDOS)
    assert fallido["intentos"] == "1"
    assert "Sobre inválido" in fallido["motivo"]


def test_una_version_mas_nueva_que_la_del_catalogo_va_a_fallidos(r):
    sobre = Sobre(
        id=str(uuid.uuid4()), tipo="usuario_registrado", version=2,
        fecha="2026-11-22T00:00:00+00:00", origen="svc-usuarios",
        correlacion_id=str(uuid.uuid4()), datos=DATOS,
    )  # fmt: skip
    r.xadd(STREAM_USUARIOS, {"sobre": sobre.a_json()})
    manejador = Falla(0)

    consumidor(r, {"usuario_registrado": manejador}).una_vuelta()

    assert manejador.llamadas == 0
    [(_, fallido)] = r.xrange(STREAM_FALLIDOS)
    assert "Versión 2 no soportada" in fallido["motivo"]


def test_recupera_lo_que_dejo_colgado_un_consumidor_caido(r):
    sobre = publicar_uno(r)
    caido = consumidor(r, {"usuario_registrado": Falla(0)}, nombre="caido")
    caido.lectura.xreadgroup("svc-prueba", "caido", {STREAM_USUARIOS: ">"}, count=1)
    # «caido» murió con el mensaje leído y sin confirmar.
    manejador = Falla(0)
    vivo = consumidor(r, {"usuario_registrado": manejador}, nombre="vivo")

    vivo.una_vuelta()
    assert manejador.guardados == []  # todavía no pasa la espera

    esperar(vivo.espera(1))
    vivo.una_vuelta()
    assert manejador.guardados == [sobre.id]
    assert pendientes(r) == 0


def test_si_muere_entre_el_manejador_y_la_marca_lo_cubre_el_manejador_idempotente(r):
    """El manejador terminó bien, pero el proceso murió antes de marcar y confirmar: el
    evento se vuelve a entregar y se llama otra vez al manejador, que no lo duplica."""
    bitacora: dict[str, dict] = {}

    def guardar(sobre: Sobre):  # idempotente, como el índice único de evento_id
        bitacora.setdefault(sobre.id, sobre.datos)

    llamadas = []
    sobre = publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": lambda s: (llamadas.append(1), guardar(s))})
    original = r.pipeline

    def pipeline_que_muere(*args, **kwargs):
        r.pipeline = original
        raise SystemExit("el proceso murió")

    r.pipeline = pipeline_que_muere
    with pytest.raises(SystemExit):
        c.una_vuelta()
    assert pendientes(r) == 1 and not r.exists(c.clave_procesado(sobre.id))

    esperar(c.espera(1))
    c.una_vuelta()

    assert len(llamadas) == 2
    assert list(bitacora) == [sobre.id]
    assert pendientes(r) == 0


def test_al_recibir_sigterm_termina_el_mensaje_en_curso_y_sale(r, caplog):
    caplog.set_level(logging.INFO, logger="eventos")
    primero, segundo = publicar_uno(r), publicar_uno(r)
    terminados = []
    procesos: list[Consumidor] = []

    def lento(sobre: Sobre):
        procesos[0].pedir_detener()  # llega SIGTERM a la mitad del manejador
        time.sleep(0.05)
        terminados.append(sobre.id)

    procesos.append(consumidor(r, {"usuario_registrado": lento}))
    procesos[0].correr()

    assert terminados == [primero.id]  # el que estaba en curso terminó
    assert pendientes(r) == 0  # y quedó confirmado; el segundo ni se leyó
    info = r.xinfo_groups(STREAM_USUARIOS)[0]
    assert info["lag"] == 1
    eventos = [x["evento"] for x in lineas(caplog)]
    assert eventos[-1] == "consumidor_detenido"
    procesados = [x["evento_id"] for x in lineas(caplog) if x["evento"] == "evento_procesado"]
    assert procesados == [primero.id]
    assert segundo.id not in procesados


def test_sin_redis_el_consumidor_espera_y_no_se_cae(caplog):
    caplog.set_level(logging.INFO, logger="eventos")

    class SinRedis(fakeredis.FakeRedis):
        def xgroup_create(self, *a, **k):
            raise redis.ConnectionError("Connection refused")

    c = Consumidor("svc-prueba", {"usuario_registrado": print}, cliente=SinRedis())
    c._dormir = lambda segundos: c.pedir_detener()

    c.correr()

    sin_redis = [x for x in lineas(caplog) if x["evento"] == "consumidor_sin_redis"]
    assert sin_redis and sin_redis[0]["reintento_en_segundos"] == 2.0


def test_los_clientes_de_redis_tienen_timeout(monkeypatch):
    from agroia_comun.eventos import conexion

    monkeypatch.setattr(conexion, "_clientes", {})
    normal = conexion.cliente().connection_pool.connection_kwargs
    lectura = conexion.cliente_de_lectura().connection_pool.connection_kwargs
    assert normal["socket_timeout"] == conexion.TIMEOUT
    assert normal["socket_connect_timeout"] == conexion.TIMEOUT
    assert lectura["socket_timeout"] > conexion.BLOQUEO_MS / 1000
    assert conexion.cliente().connection_pool.connection_kwargs["db"] == 1


# --- operación ---------------------------------------------------------------------------


def test_estado_muestra_pendientes_y_fallidos(r):
    publicar_uno(r)
    publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": Falla(99)}, max_reintentos=0)
    c.una_vuelta()  # el primero va a fallidos (sin reintentos)
    r.xreadgroup("svc-prueba", "otro", {STREAM_USUARIOS: ">"}, count=1)  # el segundo, colgado

    datos = operacion.estado(r)

    [usuarios] = [s for s in datos["streams"] if s["stream"] == STREAM_USUARIOS]
    assert usuarios["largo"] == 2
    [grupo] = usuarios["grupos"]
    assert grupo["grupo"] == "svc-prueba" and grupo["pendientes"] == 1
    assert datos["fallidos"]["total"] == 1
    assert datos["fallidos"]["ultimos"][0]["tipo"] == "usuario_registrado"


def test_reprocesar_conserva_el_id_y_los_que_ya_lo_procesaron_lo_saltan(r):
    sobre = publicar_uno(r)
    otro_grupo = []
    otro = Consumidor(
        "svc-otro", {"usuario_registrado": otro_grupo.append}, cliente=r, bloqueo_ms=10
    )
    otro.preparar()
    otro.una_vuelta()  # el otro grupo lo procesa bien
    manejador = Falla(veces=1)
    c = consumidor(r, {"usuario_registrado": manejador}, max_reintentos=0)
    c.una_vuelta()  # en este grupo falla y va a fallidos
    [(id_fallido, _)] = r.xrange(STREAM_FALLIDOS)

    resultado = operacion.reprocesar(r, ids=[id_fallido])

    assert resultado["republicados"][0]["evento_id"] == sobre.id
    assert r.xlen(STREAM_FALLIDOS) == 0
    c.una_vuelta()
    otro.una_vuelta()
    assert manejador.guardados == [sobre.id]  # este grupo sí lo aplica ahora
    assert len(otro_grupo) == 1  # el otro lo saltó: mismo id, ya procesado


def test_reprocesar_pide_id_o_todos(r):
    with pytest.raises(ErrorEvento):
        operacion.reprocesar(r)


def test_el_stream_de_fallidos_no_se_recorta(r, monkeypatch):
    from agroia_comun.eventos import catalogo
    from agroia_comun.eventos import consumidor as modulo

    monkeypatch.setattr(catalogo, "MAXLEN", 2)
    monkeypatch.setattr("agroia_comun.eventos.productor.MAXLEN", 2)
    c = consumidor(r, {"usuario_registrado": Falla(99)}, max_reintentos=0)
    for _ in range(5):
        publicar_uno(r)
        c.una_vuelta()
    assert modulo.STREAM_FALLIDOS == STREAM_FALLIDOS
    assert r.xlen(STREAM_FALLIDOS) == 5


# --- núcleo sin Django -------------------------------------------------------------------


def test_el_nucleo_no_importa_django():
    codigo = (
        "import sys, agroia_comun.eventos, agroia_comun.eventos.operacion, "
        "agroia_comun.eventos.__main__, agroia_comun.tokens; "
        "assert not [m for m in sys.modules if m == 'django' or m.startswith('django.')], 'django'"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr
