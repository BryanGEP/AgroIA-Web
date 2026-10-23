"""Pruebas de los endpoints de infraestructura: salud y documentación."""


def test_salud_responde_ok(cliente_http):
    respuesta = cliente_http.get("/salud/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_salud_solo_acepta_get(cliente_http):
    respuesta = cliente_http.post("/salud/")

    assert respuesta.status_code == 405
    assert respuesta.json()["error"] == "metodo_no_permitido"


def test_documentacion_disponible(cliente_http):
    assert cliente_http.get("/api/docs/").status_code == 200
    esquema = cliente_http.get("/api/schema/").json()
    assert {
        "/salud/",
        "/agente/preguntar/",
        "/diagnostico/",
        "/solicitudes/{id_solicitud}/",
    } <= set(esquema["paths"])
    assert esquema["components"]["securitySchemes"]["jwtAuth"]["scheme"] == "bearer"
    assert "422" not in esquema["paths"]["/agente/preguntar/"]["post"]["responses"]


def test_ruta_inexistente_404(cliente_http):
    respuesta = cliente_http.get("/no-existe/")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"
