"""Pruebas de los endpoints de infraestructura: salud y documentación."""


def test_salud_responde_ok(client):
    respuesta = client.get("/salud/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_salud_solo_acepta_get(client):
    respuesta = client.post("/salud/")

    assert respuesta.status_code == 405


def test_esquema_openapi_se_genera(client):
    respuesta = client.get("/api/schema/")

    assert respuesta.status_code == 200
    assert b"/salud/" in respuesta.content


def test_documentacion_disponible(client):
    respuesta = client.get("/api/docs/")

    assert respuesta.status_code == 200
