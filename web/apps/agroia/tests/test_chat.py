"""Chat con AgroIA (asíncrono): el gateway pide la respuesta a svc-contenido, que la publica
como evento, y la pantalla consulta el estado con HTMX."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.servicios_falsos import error

pytestmark = pytest.mark.django_db

CONV = "6630c1f2a4b5c6d7e8f90123"
RUTA_CONV = f"/api/v1/conversaciones/{CONV}/"
RUTA_PREGUNTAR = f"{RUTA_CONV}preguntar/"
RUTA_REINTENTAR = f"{RUTA_CONV}reintentar/"
RUTA_SOLICITUD = f"{RUTA_CONV}solicitud/"
HISTORIAL = [
    {"rol": "usuario", "texto": "Tengo manchas negras.", "fuentes": []},
    {"rol": "agente", "texto": "Parece antracnosis.", "fuentes": ["Manual"]},
]
FUENTES = ["Marroquín-Pimentel (1999)", "SENASICA (2020)"]


def ahora(segundos_atras: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(seconds=segundos_atras)).isoformat()


def solicitud(estado="pendiente", codigo=None, segundos_atras=0, **extra) -> dict:
    return {"id": "5b8e2f1c-3d4a-4e6b-9c7d-1a2b3c4d5e6f", "estado": estado, "codigo": codigo,
            "creada_en": ahora(segundos_atras), "conversacion_id": CONV, **extra}  # fmt: skip


def conversacion(mensajes=HISTORIAL, datos_solicitud=None):
    return {"id": CONV, "titulo": "Manchas", "mensajes": list(mensajes),
            "solicitud": datos_solicitud}  # fmt: skip


def preparar(servicios, mensajes=HISTORIAL, datos_solicitud=None, preguntar_responde=None):
    servicios.responder(
        "GET",
        "svc-contenido",
        "/api/v1/conversaciones/",
        httpx.Response(200, json={"count": 1, "results": [conversacion()]}),
    )
    servicios.responder(
        "GET",
        "svc-contenido",
        RUTA_CONV,
        httpx.Response(200, json=conversacion(mensajes, datos_solicitud)),
    )
    servicios.responder(
        "POST",
        "svc-contenido",
        RUTA_PREGUNTAR,
        preguntar_responde or httpx.Response(202, json=solicitud()),
    )


def preguntar(client, texto="¿Cada cuándo aplico?"):
    return client.post(f"/agroia/{CONV}/preguntar/", {"pregunta": texto}, HTTP_HX_REQUEST="true")


def consultar(client):
    return client.get(f"/agroia/{CONV}/solicitud/", HTTP_HX_REQUEST="true")


def test_chat_pide_sesion(client):
    assert client.get("/agroia/")["Location"].startswith("/iniciar-sesion/?next=")


def test_pantalla_con_conversaciones_y_mensajes(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)

    html = client.get(f"/agroia/{CONV}/").content.decode()

    assert "Mis conversaciones" in html and "Parece antracnosis." in html
    assert "Fuentes" in html and "Manual" in html


# --- Preguntar ------------------------------------------------------------------------------


def test_preguntar_pide_la_respuesta_a_svc_contenido_y_empieza_a_consultar(
    client, servicios, con_sesion
):
    con_sesion()
    preparar(servicios)

    html = preguntar(client).content.decode()

    [pedido] = servicios.de("svc-contenido", RUTA_PREGUNTAR)
    assert servicios.cuerpo(pedido) == {"texto": "¿Cada cuándo aplico?"}
    assert servicios.de("svc-ia") == []  # el gateway ya no llama al agente
    assert "¿Cada cuándo aplico?" in html  # la burbuja de la pregunta
    assert "AgroIA está escribiendo" in html
    assert f'hx-get="/agroia/{CONV}/solicitud/"' in html
    assert 'hx-trigger="load delay:2s"' in html
    assert "<script" not in html


def test_si_no_se_pudo_enviar_muestra_reintentar(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, preguntar_responde=httpx.Response(
        202, json=solicitud("fallido", "servicio_no_disponible")))  # fmt: skip

    html = preguntar(client).content.decode()

    assert "No pudimos enviar tu pregunta" in html and "Reintentar" in html
    assert "hx-trigger" not in html


def test_conversacion_llena_ofrece_una_nueva(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, preguntar_responde=error(409, "conversacion_llena", "Llena."))

    html = preguntar(client).content.decode()

    assert "llegó a su límite de mensajes" in html and "Iniciar una conversación nueva" in html


def test_una_solicitud_en_curso_muestra_el_aviso(client, servicios, con_sesion):
    con_sesion()
    preparar(
        servicios,
        preguntar_responde=error(
            409, "solicitud_en_curso", "AgroIA todavía está respondiendo tu pregunta anterior."
        ),
    )

    html = preguntar(client).content.decode()

    assert "todavía está respondiendo" in html


def test_pregunta_vacia(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)

    html = preguntar(client, "   ").content.decode()

    assert "Escribe una pregunta." in html
    assert servicios.peticiones == []


# --- Polling ---------------------------------------------------------------------------------


def test_lista_muestra_la_respuesta_y_deja_de_consultar(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD, httpx.Response(
        200, json=solicitud("listo", respuesta="Aplica **cobre** cada 21 días.",
                            fuentes=FUENTES)))  # fmt: skip

    html = consultar(client).content.decode()

    assert "<strong>cobre</strong>" in html  # pasa por markdown_seguro
    assert "SENASICA (2020)" in html
    assert "hx-trigger" not in html and "hx-get" not in html


def test_pendiente_sigue_consultando_y_el_intervalo_crece(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD,
                        httpx.Response(200, json=solicitud(segundos_atras=5)))  # fmt: skip
    assert 'hx-trigger="load delay:2s"' in consultar(client).content.decode()

    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD,
                        httpx.Response(200, json=solicitud(segundos_atras=25)))  # fmt: skip
    assert 'hx-trigger="load delay:5s"' in consultar(client).content.decode()


@pytest.mark.parametrize(
    "codigo, texto",
    [
        ("agente_no_disponible", "AgroIA no pudo responder en este momento."),
        ("vencida", "AgroIA tardó demasiado en responder."),
    ],
)
def test_fallida_muestra_el_motivo_y_reintentar(client, servicios, con_sesion, codigo, texto):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD,
                        httpx.Response(200, json=solicitud("fallido", codigo)))  # fmt: skip

    html = consultar(client).content.decode()

    assert texto in html and "Reintentar" in html
    assert f'hx-post="/agroia/{CONV}/reintentar/"' in html
    assert "hx-trigger" not in html


def test_si_svc_contenido_no_responde_se_sigue_consultando(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD, error(503, "no_disponible"))

    assert "hx-trigger" in consultar(client).content.decode()


def test_una_espera_completa_no_recibe_429(client, servicios, con_sesion):
    """180 s de polling (cada 2 s y luego cada 5 s) son menos de 50 consultas: 90 sin 429."""
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD,
                        httpx.Response(200, json=solicitud()))  # fmt: skip

    estados = {consultar(client).status_code for _ in range(90)}

    assert estados == {200}


def test_consultar_sin_htmx_lleva_a_la_conversacion(client, servicios, con_sesion):
    con_sesion()
    respuesta = client.get(f"/agroia/{CONV}/solicitud/")
    assert respuesta["Location"] == f"/agroia/{CONV}/"


# --- Reintentar y la pantalla con una solicitud --------------------------------------------


def test_reintentar_no_repite_la_pregunta_y_vuelve_a_esperar(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("POST", "svc-contenido", RUTA_REINTENTAR,
                        httpx.Response(202, json=solicitud()))  # fmt: skip

    html = client.post(f"/agroia/{CONV}/reintentar/", HTTP_HX_REQUEST="true").content.decode()

    assert servicios.de("svc-contenido", RUTA_REINTENTAR)
    assert servicios.de("svc-contenido", f"{RUTA_CONV}mensajes/") == []
    assert "AgroIA está escribiendo" in html and "hx-trigger" in html
    assert "¿Cada cuándo aplico?" not in html


def test_la_pantalla_sigue_esperando_una_solicitud_pendiente(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, mensajes=HISTORIAL[:1], datos_solicitud=solicitud())

    html = client.get(f"/agroia/{CONV}/").content.decode()

    assert f'hx-get="/agroia/{CONV}/solicitud/"' in html
    assert '<noscript><meta http-equiv="refresh" content="5"></noscript>' in html


def test_la_pantalla_ofrece_reintentar_si_la_solicitud_fallo(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, mensajes=HISTORIAL[:1],
             datos_solicitud=solicitud("fallido", "agente_no_disponible"))  # fmt: skip

    html = client.get(f"/agroia/{CONV}/").content.decode()

    assert "AgroIA no pudo responder en este momento." in html and "Reintentar" in html
    assert "noscript" not in html


def test_la_pantalla_muestra_reintentar_si_quedo_una_pregunta_sin_respuesta(
    client, servicios, con_sesion
):
    """Conversaciones de antes de los eventos (sin solicitud)."""
    con_sesion()
    preparar(servicios, mensajes=[{"rol": "usuario", "texto": "¿Y la dosis?", "fuentes": []}])

    assert (
        "Tu última pregunta no tiene respuesta todavía"
        in client.get(f"/agroia/{CONV}/").content.decode()
    )


def test_nueva_conversacion_con_la_primera_pregunta(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, mensajes=[])
    servicios.responder(
        "POST",
        "svc-contenido",
        "/api/v1/conversaciones/",
        httpx.Response(201, json={"id": CONV, "titulo": "x"}),
    )

    respuesta = client.post("/agroia/nueva/", {"pregunta": "¿Qué es la roña?"})

    assert respuesta["Location"] == f"/agroia/{CONV}/"
    crear = servicios.de("svc-contenido", "/api/v1/conversaciones/")
    assert servicios.cuerpo(next(p for p in crear if p.method == "POST")) == {
        "titulo": "¿Qué es la roña?"
    }
    assert servicios.cuerpo(servicios.de("svc-contenido", RUTA_PREGUNTAR)[0]) == {
        "texto": "¿Qué es la roña?"
    }


def test_borrar_conversacion(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("DELETE", "svc-contenido", RUTA_CONV, httpx.Response(204))

    respuesta = client.post(f"/agroia/{CONV}/borrar/")

    assert respuesta["Location"] == "/agroia/"


def test_conversacion_ajena_404(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_CONV, error(404, "no_encontrado"))

    assert client.get(f"/agroia/{CONV}/").status_code == 404


# --- Límite de preguntas por usuario (429 de svc-contenido) ----------------------------------

DEMASIADAS = error(429, "demasiados_intentos", "Demasiados intentos.", **{"Retry-After": "42"})


def test_muchas_preguntas_seguidas_muestra_el_mensaje_y_conserva_el_texto(
    client, servicios, con_sesion
):
    con_sesion()
    preparar(servicios, preguntar_responde=DEMASIADAS)

    respuesta = preguntar(client)
    html = respuesta.content.decode()

    assert "Hiciste muchas preguntas seguidas. Espera 42 segundos" in html
    assert respuesta["X-Conservar-Pregunta"] == "1"  # el campo no se vacía
    # Solo el aviso: ni la burbuja de la pregunta (no se guardó) ni un polling nuevo.
    assert "¿Cada cuándo aplico?" not in html and "hx-trigger" not in html
    assert "demasiados_intentos" not in html


def test_el_aviso_no_corta_el_polling_de_la_pregunta_anterior(client, servicios, con_sesion):
    """La espera de la pregunta en curso es otro elemento: el aviso se agrega al final y
    la consulta del estado sigue funcionando igual."""
    con_sesion()
    preparar(servicios, preguntar_responde=DEMASIADAS)
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD,
                        httpx.Response(200, json=solicitud()))  # fmt: skip

    preguntar(client)

    assert "hx-trigger" in consultar(client).content.decode()


def test_una_respuesta_correcta_no_pide_conservar_el_texto(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios)
    assert "X-Conservar-Pregunta" not in preguntar(client)


def test_conversacion_nueva_rechazada_no_deja_una_conversacion_vacia(client, servicios, con_sesion):
    con_sesion()
    preparar(servicios, mensajes=[], preguntar_responde=DEMASIADAS)
    servicios.responder("POST", "svc-contenido", "/api/v1/conversaciones/",
                        httpx.Response(201, json={"id": CONV, "titulo": "x"}))  # fmt: skip
    servicios.responder("DELETE", "svc-contenido", RUTA_CONV, httpx.Response(204))

    respuesta = client.post("/agroia/nueva/", {"pregunta": "¿Qué es la roña?"}, follow=True)

    assert [p.method for p in servicios.de("svc-contenido", RUTA_CONV)] == ["DELETE"]
    assert "Hiciste muchas preguntas seguidas" in respuesta.content.decode()


def test_reintentar_rechazado_conserva_el_boton(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("POST", "svc-contenido", RUTA_REINTENTAR, DEMASIADAS)
    servicios.responder("GET", "svc-contenido", RUTA_SOLICITUD, httpx.Response(
        200, json=solicitud("fallido", "agente_no_disponible")))  # fmt: skip

    html = client.post(f"/agroia/{CONV}/reintentar/", HTTP_HX_REQUEST="true").content.decode()

    assert "Hiciste muchas preguntas seguidas" in html
    assert f'hx-post="/agroia/{CONV}/reintentar/"' in html and "Reintentar" in html
