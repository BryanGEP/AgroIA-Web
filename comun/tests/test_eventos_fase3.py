"""Librería de eventos, fase 3: latido (nadie reclama lo que se sigue procesando), Ocupado,
espera desde el fallo, al_agotar, política por stream, fallidos sin datos sensibles,
retención por tiempo, hilos y limpieza de consumidores viejos."""

import json
import threading
import time
import uuid

import fakeredis
import pytest

from agroia_comun.eventos import Consumidor, Sobre, operacion, publicar
from agroia_comun.eventos.catalogo import (
    STREAM_FALLIDOS,
    STREAM_IA_RESULTADOS,
    STREAM_IA_SOLICITUDES,
    STREAM_USUARIOS,
    politica,
)
from agroia_comun.eventos.consumidor import Ocupado, correr_en_hilos

USUARIO = str(uuid.uuid4())
DATOS = {"usuario_id": USUARIO, "rol": "cliente"}


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def publicar_uno(r) -> Sobre:
    return publicar("usuario_registrado", DATOS, origen="svc-usuarios", cliente=r)


def pregunta(r, **cambios) -> Sobre:
    datos = {
        "solicitud_id": str(uuid.uuid4()),
        "usuario_id": USUARIO,
        "conversacion_id": "abc123",
        "pregunta": "¿Cómo curo la roña de mi huerta en Tancítaro?",
        "historial": [{"rol": "usuario", "texto": "Hola, tengo 40 árboles en Uruapan"}],
        "vence_en": "2026-11-22T20:00:00+00:00",
        **cambios,
    }
    return publicar("ia_pregunta_solicitada", datos, origen="svc-contenido", cliente=r)


def consumidor(r, manejadores, **opciones) -> Consumidor:
    opciones = {"max_reintentos": 2, "espera_base": 0.05, "bloqueo_ms": 10, "latido": 0.02,
                **opciones}  # fmt: skip
    c = Consumidor("svc-prueba", manejadores, cliente=r, **opciones)
    c.preparar()
    return c


def pendientes(r, stream=STREAM_USUARIOS) -> int:
    return r.xpending(stream, "svc-prueba")["pending"]


# --- El latido: nadie reclama lo que se sigue procesando ---------------------------------


def test_un_manejador_lento_con_dos_hilos_se_procesa_una_vez_sin_intentos_de_mas(r, caplog):
    """El manejador tarda diez veces la espera de reintento. Mientras tanto otro hilo del
    mismo grupo revisa los pendientes una y otra vez: no lo reclama, porque el latido lo
    mantiene reciente. Al final se procesó una vez, sin fallos ni reintentos."""
    caplog.set_level("INFO", logger="eventos")
    llamadas = []

    def lento(sobre):
        llamadas.append(threading.current_thread().name)
        time.sleep(0.6)  # la espera de reintento es de 0.06 s (3 latidos)

    sobre = publicar_uno(r)
    uno = consumidor(r, {"usuario_registrado": lento}, nombre="hilo-1")
    dos = consumidor(r, {"usuario_registrado": lento}, nombre="hilo-2")
    trabajando = threading.Thread(target=uno.una_vuelta, name="hilo-1")
    trabajando.start()
    time.sleep(0.05)
    fin = time.monotonic() + 0.7
    while time.monotonic() < fin:  # el otro hilo insiste mientras el primero trabaja
        dos.reclamar_pendientes()
        time.sleep(0.02)
    trabajando.join()

    assert llamadas == ["hilo-1"]
    assert pendientes(r) == 0
    assert r.exists(uno.clave_procesado(sobre.id))
    lineas = [json.loads(x.getMessage()) for x in caplog.records if x.name == "eventos"]
    eventos = [linea["evento"] for linea in lineas]
    assert "evento_reintentado" not in eventos and "evento_fallido" not in eventos
    assert eventos.count("evento_procesado") == 1
    [procesado] = [linea for linea in lineas if linea["evento"] == "evento_procesado"]
    # Redis lo entregó una sola vez: el latido renueva con JUSTID, que no suma entregas.
    assert procesado["entregas"] == 1 and procesado["intento"] == 1
    assert procesado["consumidor"] == "hilo-1" and procesado["duracion_ms"] >= 600


def test_si_el_consumidor_muere_a_la_mitad_otro_lo_reclama_tras_el_plazo(r):
    sobre = publicar_uno(r)
    muerto = consumidor(r, {"usuario_registrado": print}, nombre="muerto")
    muerto.lectura.xreadgroup("svc-prueba", "muerto", {STREAM_USUARIOS: ">"}, count=1)
    recibidos = []
    vivo = consumidor(r, {"usuario_registrado": recibidos.append}, nombre="vivo")

    vivo.reclamar_pendientes()
    assert recibidos == []  # aún no pasa el plazo sin latido (3 latidos)

    time.sleep(vivo.plazo_sin_latido + 0.02)
    vivo.reclamar_pendientes()
    assert [s.id for s in recibidos] == [sobre.id]
    assert vivo.fallos(STREAM_USUARIOS, r.xrange(STREAM_USUARIOS)[0][0]) == 0


# --- Ocupado y la espera desde el fallo -----------------------------------------------------


def test_ocupado_no_cuenta_como_fallo(r, caplog):
    caplog.set_level("INFO", logger="eventos")
    veces = []

    def ocupado_y_luego_bien(sobre):
        veces.append(1)
        if len(veces) <= 3:
            raise Ocupado("otro consumidor tiene el candado")

    publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": ocupado_y_luego_bien}, max_reintentos=1)
    id_mensaje = r.xrange(STREAM_USUARIOS)[0][0]

    c.una_vuelta()
    for _ in range(3):
        time.sleep(c.plazo_sin_latido + 0.02)
        c.una_vuelta()

    assert len(veces) == 4  # 3 veces ocupado y una bien, aunque solo admite 1 reintento
    assert pendientes(r) == 0
    assert r.xlen(STREAM_FALLIDOS) == 0
    assert c.fallos(STREAM_USUARIOS, id_mensaje) == 0
    eventos = [json.loads(x.getMessage())["evento"] for x in caplog.records if x.name == "eventos"]
    assert eventos.count("evento_ocupado") == 3 and "evento_reintentado" not in eventos


def test_la_espera_se_mide_desde_el_fallo_y_no_desde_la_entrega(r):
    """Un manejador que tarda 0.3 s y falla: si la espera contara desde la entrega, el
    reintento sería inmediato. Cuenta desde el fallo: 0.1 s después."""
    llamadas = []

    def tarda_y_falla(sobre):
        llamadas.append(time.monotonic())
        if len(llamadas) == 1:
            time.sleep(0.3)
            raise RuntimeError("falla después de trabajar")

    publicar_uno(r)
    c = consumidor(r, {"usuario_registrado": tarda_y_falla}, espera_base=0.1)
    c.una_vuelta()
    fallo = time.monotonic()

    c.reclamar_pendientes()  # justo después del fallo: no se reintenta todavía
    assert len(llamadas) == 1
    time.sleep(0.12)
    c.reclamar_pendientes()
    assert len(llamadas) == 2
    assert llamadas[1] - fallo >= 0.1


# --- al_agotar y fallidos sin datos sensibles -------------------------------------------


def test_al_agotar_se_llama_antes_de_mandar_a_fallidos(r):
    agotados = []

    def falla(sobre):
        raise TimeoutError("el agente tardó demasiado")

    sobre = pregunta(r)
    c = consumidor(
        r, {"ia_pregunta_solicitada": falla}, max_reintentos=1,
        al_agotar={"ia_pregunta_solicitada": lambda s, e: agotados.append((s.id, type(e)))},
    )  # fmt: skip
    for fallos in range(2):
        time.sleep(c.espera(fallos, STREAM_IA_SOLICITUDES) + 0.02)
        c.una_vuelta()

    assert agotados == [(sobre.id, TimeoutError)]
    assert r.xlen(STREAM_FALLIDOS) == 1


def test_fallidos_no_guardan_los_campos_no_registrables_y_no_se_reprocesan(r, caplog):
    caplog.set_level("INFO", logger="eventos")
    sobre = pregunta(r)

    def falla(s):
        raise RuntimeError("no")

    c = consumidor(r, {"ia_pregunta_solicitada": falla}, max_reintentos=0)
    c.una_vuelta()

    [(id_fallido, fallido)] = r.xrange(STREAM_FALLIDOS)
    assert fallido["datos_omitidos"] == "historial,pregunta"
    guardado = json.loads(fallido["sobre"])
    assert set(guardado["datos"]) == {"solicitud_id", "usuario_id", "conversacion_id", "vence_en"}
    assert "Tancítaro" not in json.dumps(fallido) and "Uruapan" not in json.dumps(fallido)
    assert "Tancítaro" not in caplog.text and "Uruapan" not in caplog.text

    resultado = operacion.reprocesar(r, ids=[id_fallido])
    assert resultado["republicados"] == []
    assert "datos omitidos" in resultado["no_reprocesables"][0]["motivo"]
    assert r.xlen(STREAM_FALLIDOS) == 1  # se queda para revisarlo
    assert sobre.id == guardado["id"]


# --- Política por stream y retención ------------------------------------------------------


def test_la_ia_tiene_sus_propios_reintentos_y_retencion():
    ia = politica(STREAM_IA_SOLICITUDES)
    assert (ia.max_reintentos, ia.espera_base, ia.retencion_segundos) == (2, 5.0, 24 * 3600)
    assert politica(STREAM_IA_RESULTADOS).retencion_segundos == 24 * 3600
    general = politica(STREAM_USUARIOS)
    assert (general.max_reintentos, general.espera_base, general.retencion_segundos) == (
        5, 2.0, None,
    )  # fmt: skip


def test_la_politica_se_cambia_por_variable(monkeypatch):
    monkeypatch.setenv("EVENTOS_IA_SOLICITUDES_MAX_REINTENTOS", "1")
    monkeypatch.setenv("EVENTOS_IA_SOLICITUDES_ESPERA_BASE", "0.5")
    assert politica(STREAM_IA_SOLICITUDES).max_reintentos == 1
    assert politica(STREAM_IA_SOLICITUDES).espera_base == 0.5


def test_el_consumidor_usa_la_politica_de_cada_stream(r):
    c = Consumidor("svc-prueba", {"ia_pregunta_solicitada": print}, cliente=r, latido=0.01)
    assert c.max_reintentos(STREAM_IA_SOLICITUDES) == 2
    assert c.espera(1, STREAM_IA_SOLICITUDES) == 5.0
    assert c.espera(2, STREAM_IA_SOLICITUDES) == 10.0


def test_los_streams_de_la_ia_se_recortan_por_antiguedad(r, monkeypatch):
    viejo_ms = int((time.time() - 25 * 3600) * 1000)
    r.xadd(STREAM_IA_SOLICITUDES, {"sobre": "{}"}, id=f"{viejo_ms}-0")  # de hace 25 horas
    pregunta(r)

    ids = [i for i, _ in r.xrange(STREAM_IA_SOLICITUDES)]
    assert len(ids) == 1 and not ids[0].startswith(str(viejo_ms))


# --- Hilos y consumidores viejos ----------------------------------------------------------


def test_varios_hilos_atienden_en_paralelo(r, monkeypatch):
    for _ in range(3):
        publicar_uno(r)
    inicio = time.monotonic()
    atendidos = []

    def lento(sobre):
        time.sleep(0.4)
        atendidos.append(time.monotonic() - inicio)
        if len(atendidos) == 3:
            for c in consumidores:
                c.pedir_detener()

    consumidores: list[Consumidor] = []

    def fabricar(sufijo):
        c = Consumidor("svc-prueba", {"usuario_registrado": lento}, cliente=r,
                       nombre=f"svc-prueba-{sufijo}", bloqueo_ms=10, latido=0.05)  # fmt: skip
        consumidores.append(c)
        return c

    monkeypatch.setattr("signal.signal", lambda *a: None)  # pytest no es el hilo de Docker
    correr_en_hilos(fabricar, 3)

    assert len(atendidos) == 3
    assert max(atendidos) < 1.0  # en fila serían 1.2 s
    assert len({c.nombre for c in consumidores}) == 3


def test_al_arrancar_borra_los_consumidores_viejos_sin_pendientes(r, caplog):
    caplog.set_level("INFO", logger="eventos")
    publicar_uno(r)
    publicar_uno(r)
    viejo = consumidor(r, {"usuario_registrado": print}, nombre="viejo")
    viejo.lectura.xreadgroup("svc-prueba", "viejo", {STREAM_USUARIOS: ">"}, count=1)
    viejo.una_vuelta  # noqa: B018
    con_pendiente = consumidor(r, {"usuario_registrado": print}, nombre="con-pendiente")
    con_pendiente.lectura.xreadgroup("svc-prueba", "con-pendiente", {STREAM_USUARIOS: ">"})
    r.xack(STREAM_USUARIOS, "svc-prueba", r.xrange(STREAM_USUARIOS)[0][0])  # viejo terminó
    time.sleep(0.05)

    nuevo = consumidor(r, {"usuario_registrado": print}, nombre="nuevo", inactivo_para_borrar=0.01)

    nombres = {c["name"] for c in r.xinfo_consumers(STREAM_USUARIOS, "svc-prueba")}
    assert "viejo" not in nombres  # sin pendientes e inactivo
    assert "con-pendiente" in nombres  # tiene un mensaje: no se toca
    assert nuevo.nombre == "nuevo"  # aparece en el grupo en su primera lectura
    assert "consumidor_viejo_borrado" in caplog.text


# --- descartar fallidos -------------------------------------------------------------------


@pytest.fixture
def con_fallidos(r):
    from agroia_comun.eventos import conexion

    conexion.usar(r)
    for n in range(3):
        r.xadd(STREAM_FALLIDOS, {"sobre": "{}", "grupo": "svc-prueba", "motivo": f"m{n}",
                                 "intentos": "3", "datos_omitidos": "pregunta"})  # fmt: skip
    yield [i for i, _ in r.xrange(STREAM_FALLIDOS)]
    conexion.usar(None)


def test_descartar_por_id_borra_solo_esos_y_lo_registra(r, con_fallidos, caplog):
    caplog.set_level("INFO", logger="eventos")
    uno, dos, tres = con_fallidos

    resultado = operacion.descartar(r, ids=[uno, "1-0"])

    assert resultado == {"descartados": [uno], "no_encontrados": ["1-0"]}
    assert [i for i, _ in r.xrange(STREAM_FALLIDOS)] == [dos, tres]
    [linea] = [
        json.loads(x.getMessage()) for x in caplog.records if "descartados" in x.getMessage()
    ]
    assert linea["evento"] == "fallidos_descartados" and linea["ids"] == [uno]
    assert linea["descartados"] == 1


def test_descartar_pide_id_o_todos(r):
    from agroia_comun.eventos.catalogo import ErrorEvento

    with pytest.raises(ErrorEvento):
        operacion.descartar(r)


def test_descartar_todos_desde_la_linea_de_comandos_pide_confirmacion(con_fallidos, r, monkeypatch,
                                                                      capsys):  # fmt: skip
    from agroia_comun.eventos.__main__ import main

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert main(["descartar", "--todos"]) == 1
    assert r.xlen(STREAM_FALLIDOS) == 3 and "No se borró nada." in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda _: "s")
    assert main(["descartar", "--todos"]) == 0
    assert r.xlen(STREAM_FALLIDOS) == 0
    assert "Descartados: 3" in capsys.readouterr().out


def test_descartar_todos_con_si_no_pregunta(con_fallidos, r, monkeypatch):
    from agroia_comun.eventos.__main__ import main

    def no_preguntes(_):
        raise AssertionError("no debía pedir confirmación")

    monkeypatch.setattr("builtins.input", no_preguntes)
    assert main(["descartar", "--todos", "--si"]) == 0
    assert r.xlen(STREAM_FALLIDOS) == 0


def test_descartar_por_id_no_pide_confirmacion(con_fallidos, r, monkeypatch):
    from agroia_comun.eventos.__main__ import main

    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("no debía preguntar"))
    assert main(["descartar", "--id", con_fallidos[0]]) == 0
    assert r.xlen(STREAM_FALLIDOS) == 2
