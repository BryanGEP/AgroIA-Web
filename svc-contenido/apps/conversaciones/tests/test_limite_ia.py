"""Límite de solicitudes a la IA por usuario (config/limites.py): preguntar, reintentar y
solicitar un diagnóstico comparten 10 por minuto y 30 por hora; los GET no cuentan."""

import pytest
from django.core.management import CommandError, call_command

from config import limites
from tests.datos import imagen

POR_MINUTO = 10
POR_HORA = 30


def url(conversacion_id: str, accion: str = "") -> str:
    return f"/api/v1/conversaciones/{conversacion_id}/{accion}"


def nueva(api) -> str:
    return api.post("/api/v1/conversaciones/", {"titulo": "Riego"}, format="json").json()["id"]


def preguntar(api, conversacion: str, texto: str = "¿Cada cuándo riego?"):
    return api.post(url(conversacion, "preguntar/"), {"texto": texto}, format="json")


@pytest.fixture
def reloj(monkeypatch):
    """Controla el reloj de los dos límites para probar las ventanas sin esperar."""
    ahora = [997_200.0]  # justo al empezar una hora de reloj
    monkeypatch.setattr(limites.LimiteIa, "timer", staticmethod(lambda: ahora[0]))
    return ahora


def test_al_pasar_el_limite_por_minuto_responde_429_con_el_formato_comun(cliente):
    conversacion = nueva(cliente)
    for _ in range(POR_MINUTO):
        # La primera queda pendiente y las demás responden 409: también cuentan, porque el
        # límite se revisa antes de la vista.
        assert preguntar(cliente, conversacion).status_code in (202, 409)

    respuesta = preguntar(cliente, conversacion, "Esta ya no entra")

    assert respuesta.status_code == 429
    cuerpo = respuesta.json()
    assert cuerpo["error"] == "demasiados_intentos"
    assert "Intenta de nuevo en" in cuerpo["detalle"]
    assert int(respuesta["Retry-After"]) > 0
    # Rechazada antes de la vista: no se guardó la pregunta.
    textos = [m["texto"] for m in cliente.get(url(conversacion)).json()["mensajes"]]
    assert "Esta ya no entra" not in textos


def test_el_limite_es_por_usuario(cliente, otro_cliente):
    conversacion = nueva(cliente)
    for _ in range(POR_MINUTO):
        preguntar(cliente, conversacion)
    assert preguntar(cliente, conversacion).status_code == 429

    assert preguntar(otro_cliente, nueva(otro_cliente)).status_code == 202


def test_los_get_del_polling_no_cuentan(cliente):
    conversacion = nueva(cliente)
    for _ in range(100):
        assert cliente.get(url(conversacion, "solicitud/")).status_code in (200, 404)
        cliente.get(url(conversacion))

    assert preguntar(cliente, conversacion).status_code == 202


def test_preguntar_reintentar_y_diagnosticar_comparten_el_limite(cliente):
    conversacion = nueva(cliente)
    for _ in range(POR_MINUTO - 2):
        preguntar(cliente, conversacion)
    assert cliente.post(url(conversacion, "reintentar/")).status_code == 409  # cuenta
    foto = cliente.post("/api/v1/diagnosticos/solicitar/", {"imagen": imagen()},
                        format="multipart")  # fmt: skip
    assert foto.status_code == 202  # la décima

    assert cliente.post(url(conversacion, "reintentar/")).status_code == 429
    otra = cliente.post("/api/v1/diagnosticos/solicitar/", {"imagen": imagen()},
                        format="multipart")  # fmt: skip
    assert otra.status_code == 429 and otra.json()["error"] == "demasiados_intentos"


def test_la_ventana_de_un_minuto_se_libera_y_la_de_una_hora_no(cliente, reloj):
    conversacion = nueva(cliente)
    # Los rechazados (uno por minuto) no gastan el presupuesto de la hora: entran 30.
    for minuto in range(POR_HORA // POR_MINUTO):
        reloj[0] += 61 * (minuto > 0)
        for _ in range(POR_MINUTO):
            assert preguntar(cliente, conversacion).status_code != 429
        assert preguntar(cliente, conversacion).status_code == 429  # el de un minuto

    reloj[0] += 61  # ya pasó el minuto, pero van 30 en la hora
    assert preguntar(cliente, conversacion).status_code == 429
    reloj[0] += 3600
    assert preguntar(cliente, conversacion).status_code != 429


def test_reiniciar_limites_vacia_los_contadores(cliente, settings, capsys):
    conversacion = nueva(cliente)
    for _ in range(POR_MINUTO):
        preguntar(cliente, conversacion)
    assert preguntar(cliente, conversacion).status_code == 429
    settings.DEBUG = True

    call_command("reiniciar_limites")

    assert "Contadores del límite de la IA borrados: 2." in capsys.readouterr().out
    assert preguntar(cliente, conversacion).status_code != 429


def test_reiniciar_limites_no_corre_sin_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DJANGO_DEBUG=True"):
        call_command("reiniciar_limites")


def test_peticiones_simultaneas_del_mismo_usuario_no_pasan_del_limite():
    """20 hilos a la vez: entran exactamente 10. Con el historial de DRF («leer, agregar y
    guardar») las peticiones simultáneas se pisaban y entraban más."""
    import threading
    from types import SimpleNamespace

    usuario = SimpleNamespace(pk="8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d", is_authenticated=True)
    peticion = SimpleNamespace(user=usuario)
    permitidas = []
    salida = threading.Barrier(20)

    def una():
        salida.wait()
        permitidas.append(limites.LimiteIa().allow_request(peticion, None))

    hilos = [threading.Thread(target=una) for _ in range(20)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert permitidas.count(True) == POR_MINUTO
