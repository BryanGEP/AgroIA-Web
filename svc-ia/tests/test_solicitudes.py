"""GET /solicitudes/<id>/: en la Entrega 2 siempre `listo`, guardadas en memoria."""

import httpx

from app.agente import ClienteAgente, obtener_agente
from app.main import app
from app.seguridad import Usuario
from app.solicitudes import RegistroSolicitudes


def preguntar(cliente_http, encabezados) -> str:
    def dependencia():
        transporte = httpx.MockTransport(
            lambda p: httpx.Response(200, json={"response": "Hola, productor.", "session_id": "x"})
        )
        with httpx.Client(base_url="http://agente", transport=transporte) as http:
            yield ClienteAgente(http)

    app.dependency_overrides[obtener_agente] = dependencia
    return cliente_http.post(
        "/agente/preguntar/", json={"pregunta": "Hola"}, headers=encabezados
    ).json()["id"]


def test_el_dueno_consulta_su_solicitud(cliente_http, como_cliente):
    id_solicitud = preguntar(cliente_http, como_cliente)

    respuesta = cliente_http.get(f"/solicitudes/{id_solicitud}/", headers=como_cliente)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == id_solicitud
    assert cuerpo["estado"] == "listo"
    assert cuerpo["tipo"] == "agente"
    assert cuerpo["resultado"] == {"respuesta": "Hola, productor.", "fuentes": []}
    assert "usuario_id" not in cuerpo


def test_otro_usuario_no_la_ve_pero_el_admin_si(
    cliente_http, como_cliente, como_otro_cliente, como_admin
):
    id_solicitud = preguntar(cliente_http, como_cliente)
    url = f"/solicitudes/{id_solicitud}/"

    assert cliente_http.get(url, headers=como_otro_cliente).status_code == 404
    assert cliente_http.get(url, headers=como_admin).status_code == 200


def test_solicitud_inexistente_404(cliente_http, como_cliente):
    respuesta = cliente_http.get("/solicitudes/no-existe/", headers=como_cliente)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"


def test_401_y_403(cliente_http, como_cliente, sin_rol):
    id_solicitud = preguntar(cliente_http, como_cliente)

    assert cliente_http.get(f"/solicitudes/{id_solicitud}/").status_code == 401
    assert cliente_http.get(f"/solicitudes/{id_solicitud}/", headers=sin_rol).status_code == 403


def test_el_registro_guarda_solo_las_ultimas():
    registro = RegistroSolicitudes(maximo=3)
    usuario = Usuario(id=10, rol="cliente", email_verificado=True)

    ids = [registro.guardar("agente", usuario, {"n": i})["id"] for i in range(5)]

    assert registro.obtener(ids[0], usuario) is None
    assert registro.obtener(ids[1], usuario) is None
    assert registro.obtener(ids[4], usuario)["resultado"] == {"n": 4}
