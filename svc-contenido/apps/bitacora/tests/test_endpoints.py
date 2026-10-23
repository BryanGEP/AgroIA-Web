"""Endpoints de la bitácora: solo administrador, filtros por tipo y fechas."""

from datetime import UTC, datetime

import pytest

URL = "/api/v1/bitacora/"


def registrar(tipo: str, fecha: datetime, mongo_simulado) -> None:
    """Inserta un evento con una fecha fija (la API siempre usa la fecha actual)."""
    mongo_simulado["bitacora"].insert_one(
        {"tipo": tipo, "usuario_id": 10, "servicio": "svc-tienda", "datos": {}, "fecha": fecha}
    )


def test_registrar_evento(admin):
    respuesta = admin.post(
        URL,
        {
            "tipo": "pedido_creado",
            "usuario_id": 10,
            "servicio": "svc-tienda",
            "datos": {"pedido_id": 7},
        },
        format="json",
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "pedido_creado"
    assert cuerpo["datos"] == {"pedido_id": 7}
    assert "fecha" in cuerpo


def test_evento_sin_usuario(admin):
    respuesta = admin.post(URL, {"tipo": "arranque", "servicio": "svc-ia"}, format="json")

    assert respuesta.status_code == 201
    assert respuesta.json()["usuario_id"] is None
    assert respuesta.json()["datos"] == {}


@pytest.mark.parametrize(
    ("datos", "campo"),
    [
        ({"tipo": "Pedido Creado", "servicio": "svc-tienda"}, "tipo"),
        ({"tipo": "pedido_creado"}, "servicio"),
        ({"tipo": "pedido_creado", "servicio": "svc-tienda", "datos": [1, 2]}, "datos"),
    ],
)
def test_evento_invalido_400(admin, datos, campo):
    respuesta = admin.post(URL, datos, format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_registrar_401_y_403(anonimo, cliente):
    datos = {"tipo": "pedido_creado", "servicio": "svc-tienda"}

    assert anonimo.post(URL, datos, format="json").status_code == 401
    assert cliente.post(URL, datos, format="json").status_code == 403


def test_listar_con_filtros(admin, mongo_simulado):
    registrar("pedido_creado", datetime(2026, 10, 20, 15, tzinfo=UTC), mongo_simulado)
    registrar("pedido_creado", datetime(2026, 10, 22, 15, tzinfo=UTC), mongo_simulado)
    registrar("usuario_registrado", datetime(2026, 10, 22, 16, tzinfo=UTC), mongo_simulado)

    todos = admin.get(URL).json()
    por_tipo = admin.get(URL, {"tipo": "pedido_creado"}).json()
    por_fecha = admin.get(URL, {"desde": "2026-10-21", "hasta": "2026-10-22"}).json()
    combinado = admin.get(URL, {"tipo": "pedido_creado", "desde": "2026-10-21"}).json()

    assert todos["count"] == 3
    assert todos["results"][0]["tipo"] == "usuario_registrado"  # más reciente primero
    assert por_tipo["count"] == 2
    assert por_fecha["count"] == 2
    assert combinado["count"] == 1


def test_filtro_de_fecha_invalido_400(admin):
    respuesta = admin.get(URL, {"desde": "ayer"})

    assert respuesta.status_code == 400
    assert "desde" in respuesta.json()["campos"]


def test_rango_invertido_400(admin):
    respuesta = admin.get(URL, {"desde": "2026-10-22", "hasta": "2026-10-01"})

    assert respuesta.status_code == 400


def test_listar_401_y_403(anonimo, cliente):
    assert anonimo.get(URL).status_code == 401
    assert cliente.get(URL).status_code == 403
