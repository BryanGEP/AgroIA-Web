"""svc-ia instala solo el núcleo de comun: los eventos funcionan sin Django ni DRF."""

import importlib.util
import uuid

import fakeredis

from agroia_comun.eventos import Consumidor, publicar


def test_django_no_esta_instalado_en_svc_ia():
    assert importlib.util.find_spec("django") is None
    assert importlib.util.find_spec("rest_framework") is None
    assert importlib.util.find_spec("django_filters") is None


def test_publica_y_consume_sin_django():
    redis = fakeredis.FakeRedis(decode_responses=True)
    recibidos = []
    datos = {"usuario_id": str(uuid.uuid4()), "rol": "cliente"}

    publicar("usuario_registrado", datos, origen="svc-ia", cliente=redis)
    consumidor = Consumidor(
        "svc-ia", {"usuario_registrado": recibidos.append}, cliente=redis, bloqueo_ms=10
    )
    consumidor.preparar()
    consumidor.una_vuelta()

    assert [s.datos for s in recibidos] == [datos]
