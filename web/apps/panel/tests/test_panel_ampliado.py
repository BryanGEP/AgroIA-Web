"""Panel ampliado: resumen, bitácora, estado de los eventos, detalle de usuario, filtros nuevos
y confirmaciones. Los servicios están simulados (tests/servicios_falsos.py)."""

import httpx
import pytest
from django.test import override_settings

from apps.panel.bitacora import resumir
from tests.servicios_falsos import USUARIO_ID, error

pytestmark = pytest.mark.django_db

OTRO = "d1e2f3a4-0000-4000-8000-000000000099"
CORRELACION = "5b1f3c2a-0000-4000-8000-0000000000aa"
RESUMEN = {
    "fecha": "2026-11-26",
    "pedidos": {"pendientes": 3, "por_enviar": 2},
    "ventas": {
        "hoy": {"total": "1600.00", "pedidos": 1},
        "ultimos_7_dias": {"total": "5210.00", "pedidos": 4},
        "mes": {"total": "9870.50", "pedidos": 9},
        "respaldo": {"pedidos_sin_pagado_en": 2, "primer_pagado_en": "2026-11-26"},
    },
    "stock": {
        "umbral": 5,
        "bajo": {"total": 1, "productos": [{"slug": "urea", "nombre": "Urea 46%", "stock": 3}]},
        "agotados": {"total": 1,
                     "productos": [{"slug": "caldo", "nombre": "Caldo bordelés", "stock": 0}]},
    },
    "ultimos_pedidos": [
        {"id": 94, "estado": "pendiente", "total": "1600.00",
         "creado_en": "2026-11-26T10:12:00-06:00", "usuario_id": OTRO}
    ],
}  # fmt: skip
ANA = {
    "id": OTRO,
    "email": "ana@x.mx",
    "nombre": "Ana",
    "apellidos": "Ruiz",
    "telefono": "",
    "rol": "cliente",
    "email_verificado": False,
    "is_active": True,
    "date_joined": "2026-11-25T09:00:00-06:00",
}
PAGINA_VACIA = {"count": 0, "next": None, "previous": None, "results": []}
EVENTO_ESTADO = {
    "id": "1",
    "tipo": "pedido_estado_cambiado",
    "usuario_id": OTRO,
    "servicio": "svc-tienda",
    "datos": {"pedido_id": 12, "estado_anterior": "pendiente", "estado_nuevo": "pagado",
              "total": "900.00", "cambiado_por": OTRO},
    "fecha": "2026-11-26T10:00:00-06:00",
    "evento_id": "e1",
    "correlacion_id": CORRELACION,
}  # fmt: skip
PEDIDO = {
    "id": 12,
    "usuario_id": OTRO,
    "estado": "pagado",
    "direccion_envio": {"calle": "Hidalgo", "numero": "1", "colonia": "Centro",
                        "municipio": "Jiquilpan", "estado": "Michoacán", "codigo_postal": "59510"},
    "items": [],
    "subtotal": "900.00",
    "envio": "0.00",
    "total": "900.00",
    "metodo_pago": "tarjeta",
    "creado_en": "2026-11-20T10:00:00-06:00",
    "pagado_en": "2026-11-20T10:05:00-06:00",
    "transiciones_permitidas": ["enviado", "cancelado"],
}  # fmt: skip


def pagina(*resultados) -> dict:
    return {"count": len(resultados), "next": None, "previous": None, "results": list(resultados)}


def usuarios_con(servicios, *usuarios):
    servicios.responder(
        "GET", "svc-usuarios", "/api/v1/usuarios/", httpx.Response(200, json=pagina(*usuarios))
    )


# --- Acceso ---------------------------------------------------------------------------------

RUTAS_NUEVAS = [
    "/administracion/",
    "/administracion/bitacora/",
    "/administracion/eventos/",
    f"/administracion/usuarios/{OTRO}/",
]


@pytest.mark.parametrize("ruta", RUTAS_NUEVAS)
def test_sin_sesion_va_al_login(client, servicios, ruta):
    respuesta = client.get(ruta)

    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/iniciar-sesion/?next=")
    assert servicios.peticiones == []


@pytest.mark.parametrize("ruta", RUTAS_NUEVAS)
def test_un_cliente_recibe_no_tienes_permiso(client, servicios, con_sesion, tienda_falsa, ruta):
    con_sesion(rol="cliente")

    respuesta = client.get(ruta, follow=True)

    assert respuesta.redirect_chain == [("/", 302)]
    assert "No tienes permiso" in respuesta.content.decode()
    assert servicios.peticiones == []


# --- Resumen --------------------------------------------------------------------------------


@override_settings(PANEL_UMBRAL_STOCK_BAJO=7)
def test_resumen_completo(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder("GET", "svc-tienda", "/api/v1/resumen/", httpx.Response(200, json=RESUMEN))
    usuarios_con(servicios, ANA)

    html = client.get("/administracion/").content.decode()

    assert (
        "Pendientes de pago" in html and 'href="/administracion/pedidos/?estado=pendiente"' in html
    )
    assert 'href="/administracion/pedidos/?estado=pagado"' in html
    assert "$1,600.00" in html and "$9,870.50" in html
    assert "Urea 46%" in html and "Caldo bordelés" in html
    assert "Pedido #94" in html and "Ana Ruiz" in html
    assert "antes del 26/11/2026" in html and "fecha de creación" in html
    assert servicios.de("svc-tienda", "/api/v1/resumen/")[0].url.params["umbral"] == "7"
    pedidas = [p.url.params for p in servicios.de("svc-usuarios", "/api/v1/usuarios/")]
    assert any("desde" in p for p in pedidas) and any(p.get("ids") == OTRO for p in pedidas)


def test_resumen_con_svc_tienda_caido_muestra_solo_sus_tarjetas_con_error(
    client, servicios, con_sesion
):
    con_sesion(rol="administrador")
    servicios.caidos.add("svc-tienda")
    usuarios_con(servicios, ANA)

    respuesta = client.get("/administracion/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "No pudimos cargar esta parte." in html
    assert "Ana Ruiz" in html  # la tarjeta de usuarios sí carga


def test_resumen_con_svc_usuarios_caido_carga_lo_de_la_tienda(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder("GET", "svc-tienda", "/api/v1/resumen/", httpx.Response(200, json=RESUMEN))
    servicios.caidos.add("svc-usuarios")

    html = client.get("/administracion/").content.decode()

    assert "$1,600.00" in html and "Pedido #94" in html
    assert html.count("No pudimos cargar esta parte.") == 1


# --- Bitácora -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evento, texto",
    [
        (EVENTO_ESTADO, "Pedido #12: pendiente → pagado"),
        ({"tipo": "rol_cambiado",
          "datos": {"rol_anterior": "cliente", "rol_nuevo": "administrador"}},
         "Rol: cliente → administrador"),
        ({"tipo": "pedido_creado", "datos": {"pedido_id": 7, "total": "840.50", "unidades": 3,
                                             "metodo_pago": "transferencia"}},
         "Pedido #7 creado por $840.50 (3 unidades) · transferencia"),
        ({"tipo": "correo_verificado", "datos": {"via": "enlace"}},
         "Correo verificado por el enlace del correo"),
        ({"tipo": "usuario_registrado", "datos": {"rol": "cliente"}}, "Cuenta nueva (cliente)"),
        ({"tipo": "sesiones_cerradas", "datos": {}}, "Cerró todas sus sesiones"),
        ({"tipo": "algo_nuevo", "datos": {"secreto": "x"}}, "Algo nuevo"),
    ],
)  # fmt: skip
def test_resumen_legible_de_cada_evento(evento, texto):
    assert resumir(evento) == texto


def test_bitacora_lista_con_filtros_y_correlacion(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-contenido", "/api/v1/bitacora/", httpx.Response(200, json=pagina(EVENTO_ESTADO))
    )
    usuarios_con(servicios, ANA)

    html = client.get(
        "/administracion/bitacora/", {"tipo": "pedido_estado_cambiado", "desde": "2026-11-01"}
    ).content.decode()

    assert "Pedido #12: pendiente → pagado" in html
    assert f'href="/administracion/bitacora/?correlacion_id={CORRELACION}"' in html
    assert 'href="/administracion/pedidos/12/"' in html and "Ana Ruiz" in html
    params = servicios.de("svc-contenido", "/api/v1/bitacora/")[0].url.params
    assert params["tipo"] == "pedido_estado_cambiado" and params["desde"] == "2026-11-01"
    assert "usuario_id" not in params  # los vacíos no se mandan


def test_bitacora_con_htmx_devuelve_solo_los_resultados(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-contenido", "/api/v1/bitacora/", httpx.Response(200, json=PAGINA_VACIA)
    )

    html = client.get("/administracion/bitacora/", HTTP_HX_REQUEST="true").content.decode()

    assert "<html" not in html and "No hay eventos con estos filtros" in html


def test_bitacora_con_filtro_invalido_muestra_el_error(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET",
        "svc-contenido",
        "/api/v1/bitacora/",
        error(400, "validacion", "Datos inválidos.", campos={"usuario_id": ["No es un UUID."]}),
    )

    respuesta = client.get("/administracion/bitacora/", {"usuario_id": "no-es-uuid"})

    assert respuesta.status_code == 200
    assert "Revisa los filtros" in respuesta.content.decode()


# --- Estado de los eventos ------------------------------------------------------------------

ESTADO = {
    "streams": [
        {
            "stream": "agroia:eventos:tienda",
            "largo": 42,
            "grupos": [
                {
                    "grupo": "svc-contenido",
                    "pendientes": 1,
                    "sin_leer": 0,
                    "consumidores": [{"nombre": "a1b2", "pendientes": 1, "inactivo_ms": 125000}],
                }
            ],
        }
    ],
    "fallidos": {
        "total": 1,
        "ultimos": [
            {"id": "1795210684000-0", "fecha": "2026-11-26T18:30:00+00:00", "tipo": "pedido_creado",
             "grupo": "svc-contenido", "stream": "agroia:eventos:tienda", "intentos": 4,
             "motivo": "ConnectionError", "datos_omitidos": None}
        ],
    },
}  # fmt: skip


def test_estado_de_los_eventos(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-contenido", "/api/v1/eventos/estado/", httpx.Response(200, json=ESTADO)
    )

    html = client.get("/administracion/eventos/").content.decode()

    assert "agroia:eventos:tienda" in html and "inactivo 2 min" in html
    assert "1795210684000-0" in html and "ConnectionError" in html
    assert "agroia_comun.eventos reprocesar --id" in html and "descartar --id" in html
    assert "solo el nombre de la excepción" in html
    assert (
        'hx-get="/administracion/eventos/"' in html
        and "hx-trigger" not in html.split("estado-eventos")[1]
    )


def test_estado_de_los_eventos_con_htmx_devuelve_solo_el_estado(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-contenido", "/api/v1/eventos/estado/", httpx.Response(200, json=ESTADO)
    )

    html = client.get("/administracion/eventos/", HTTP_HX_REQUEST="true").content.decode()

    assert html.lstrip().startswith('<div id="estado-eventos"') and "<html" not in html


def test_estado_de_los_eventos_sin_redis_muestra_el_error(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET",
        "svc-contenido",
        "/api/v1/eventos/estado/",
        error(503, "eventos_no_disponible", "No pudimos leer el estado de los eventos."),
    )

    respuesta = client.get("/administracion/eventos/")

    assert respuesta.status_code == 200
    assert "No pudimos leer el estado de los eventos." in respuesta.content.decode()


# --- Usuarios -------------------------------------------------------------------------------


def test_detalle_de_usuario_con_sus_pedidos_y_su_bitacora(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/", httpx.Response(200, json=ANA)
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/", httpx.Response(200, json=pagina(PEDIDO))
    )

    html = client.get(f"/administracion/usuarios/{OTRO}/").content.decode()

    assert "ana@x.mx" in html and "Sin verificar" in html
    assert f'href="/administracion/bitacora/?usuario_id={OTRO}"' in html
    assert "Pedido #12" in html and "Hacerlo administrador" in html
    assert servicios.de("svc-tienda", "/api/v1/pedidos/")[0].url.params["usuario_id"] == OTRO


def test_detalle_de_usuario_inexistente_404(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/", error(404, "no_encontrado")
    )

    assert client.get(f"/administracion/usuarios/{OTRO}/").status_code == 404


def test_tu_propio_detalle_no_ofrece_cambiar_el_rol(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    yo = {**ANA, "id": USUARIO_ID, "rol": "administrador"}
    servicios.responder(
        "GET", "svc-usuarios", f"/api/v1/usuarios/{USUARIO_ID}/", httpx.Response(200, json=yo)
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/", httpx.Response(200, json=PAGINA_VACIA)
    )

    html = client.get(f"/administracion/usuarios/{USUARIO_ID}/").content.decode()

    assert "No puedes cambiar tu propio rol" in html
    assert f'action="/administracion/usuarios/{USUARIO_ID}/rol/"' not in html


def test_cambiar_el_rol_desde_el_detalle_regresa_al_detalle(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "PATCH", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/rol/", httpx.Response(200, json={})
    )

    respuesta = client.post(
        f"/administracion/usuarios/{OTRO}/rol/", {"rol": "administrador", "volver": "detalle"}
    )

    assert respuesta["Location"] == f"/administracion/usuarios/{OTRO}/"


def test_usuarios_filtrados_por_verificacion(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    usuarios_con(servicios, ANA)

    client.get("/administracion/usuarios/", {"email_verificado": "false", "otro": "x"})

    params = servicios.de("svc-usuarios", "/api/v1/usuarios/")[0].url.params
    assert params["email_verificado"] == "false" and "otro" not in params


# --- Pedidos --------------------------------------------------------------------------------


def test_pedidos_por_numero_y_fechas(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/", httpx.Response(200, json=pagina(PEDIDO))
    )
    usuarios_con(servicios, ANA)

    html = client.get(
        "/administracion/pedidos/", {"id": "#12", "desde": "2026-11-01", "hasta": "2026-11-30"}
    ).content.decode()

    params = servicios.de("svc-tienda", "/api/v1/pedidos/")[0].url.params
    assert (
        params["id"] == "12" and params["desde"] == "2026-11-01" and params["hasta"] == "2026-11-30"
    )
    assert "Ana Ruiz" in html


def test_numero_de_pedido_invalido_no_llama_a_la_tienda(client, servicios, con_sesion):
    con_sesion(rol="administrador")

    html = client.get("/administracion/pedidos/", {"id": "doce"}).content.decode()

    assert "solo dígitos" in html
    assert not servicios.de("svc-tienda")


def test_detalle_de_pedido_con_cliente_y_linea_de_tiempo(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/12/", httpx.Response(200, json=PEDIDO)
    )
    servicios.responder(
        "GET", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/", httpx.Response(200, json=ANA)
    )
    servicios.responder(
        "GET", "svc-contenido", "/api/v1/bitacora/", httpx.Response(200, json=pagina(EVENTO_ESTADO))
    )

    html = client.get("/administracion/pedidos/12/").content.decode()

    assert "Ana Ruiz" in html and "Pagado" in html and "20/11/2026 10:05" in html
    assert "Pedido #12: pendiente → pagado" in html
    assert servicios.de("svc-contenido", "/api/v1/bitacora/")[0].url.params["pedido_id"] == "12"
    # Las transiciones piden confirmación con el diálogo propio, no con hx-confirm.
    assert 'x-data="confirmar"' in html and "hx-confirm" not in html
    assert "¿Marcar el pedido como enviado?" in html and "¿Cancelar este pedido?" in html


def test_detalle_de_pedido_con_contenido_caido_muestra_el_resto(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/12/", httpx.Response(200, json=PEDIDO)
    )
    servicios.responder(
        "GET", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/", httpx.Response(200, json=ANA)
    )
    servicios.caidos.add("svc-contenido")

    respuesta = client.get("/administracion/pedidos/12/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "No pudimos cargar esta parte." in html and 'value="enviado"' in html


# --- Productos ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stock, esperado",
    [("bajo", {"stock_max": "5"}), ("agotado", {"disponible": "false"}), ("otro", {})],
)
@override_settings(PANEL_UMBRAL_STOCK_BAJO=5)
def test_productos_filtrados_por_existencias(client, servicios, con_sesion, stock, esperado):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/categorias/", httpx.Response(200, json=PAGINA_VACIA)
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json=PAGINA_VACIA)
    )

    client.get("/administracion/productos/", {"stock": stock, "ordering": "stock"})

    params = dict(servicios.de("svc-tienda", "/api/v1/productos/")[0].url.params)
    assert params == {**esperado, "ordering": "stock", "page": "1"}


def test_productos_marcan_stock_bajo_y_agotado(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    base = {"categoria": "riego", "precio": "10.00", "activo": True, "imagen": None}
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/categorias/", httpx.Response(200, json=PAGINA_VACIA)
    )
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/productos/",
        httpx.Response(
            200,
            json=pagina(
                {**base, "nombre": "Poco", "slug": "poco", "stock": 2},
                {**base, "nombre": "Nada", "slug": "nada", "stock": 0},
            ),
        ),
    )

    html = client.get("/administracion/productos/").content.decode()

    assert "Stock bajo</span>" in html and "Agotado</span>" in html
    assert 'x-data="confirmar"' in html and "hx-confirm" not in html


def test_un_orden_desconocido_no_se_manda(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/categorias/", httpx.Response(200, json=PAGINA_VACIA)
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json=PAGINA_VACIA)
    )

    client.get("/administracion/productos/", {"ordering": "password"})

    assert "ordering" not in servicios.de("svc-tienda", "/api/v1/productos/")[0].url.params
