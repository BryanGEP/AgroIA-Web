"""Pruebas de los endpoints de infraestructura: salud y documentación."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_salud_responde_ok():
    respuesta = client.get("/salud/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_salud_solo_acepta_get():
    respuesta = client.post("/salud/")

    assert respuesta.status_code == 405


def test_documentacion_disponible():
    assert client.get("/api/docs/").status_code == 200
    assert "/salud/" in client.get("/api/schema/").json()["paths"]
