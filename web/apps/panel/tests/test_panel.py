"""Panel de administración: acceso por rol, productos, pedidos y usuarios."""

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.servicios_falsos import USUARIO_ID, error

pytestmark = pytest.mark.django_db

CATEGORIAS = {
    "count": 1,
    "results": [
        {"id": 1, "nombre": "Fungicidas", "slug": "fungicidas", "descripcion": "", "activa": True}
    ],
}
PRODUCTO = {
    "id": 3,
    "nombre": "Caldo bordelés",
    "slug": "caldo",
    "categoria": "fungicidas",
    "descripcion": "",
    "precio": "250.00",
    "stock": 10,
    "unidad": "kg",
    "imagen": None,
    "ficha_tecnica": {"cobre": "25%"},
    "activo": True,
    "disponible": True,
}
PEDIDO = {
    "id": 12,
    "estado": "pagado",
    "direccion_envio": {
        "calle": "Hidalgo",
        "numero": "1",
        "colonia": "Centro",
        "municipio": "Jiquilpan",
        "estado": "Michoacán",
        "codigo_postal": "59510",
    },
    "items": [],
    "subtotal": "900.00",
    "envio": "0.00",
    "total": "900.00",
    "metodo_pago": "tarjeta",
    "creado_en": "2026-11-20T10:00:00-06:00",
    "transiciones_permitidas": ["enviado", "cancelado"],
}
OTRO = "d1e2f3a4-0000-4000-8000-000000000099"


def productos(servicios):
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/categorias/", httpx.Response(200, json=CATEGORIAS)
    )
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/productos/",
        httpx.Response(
            200, json={"count": 1, "next": None, "previous": None, "results": [PRODUCTO]}
        ),
    )


@pytest.mark.parametrize(
    "ruta", ["/administracion/productos/", "/administracion/pedidos/", "/administracion/usuarios/"]
)
def test_un_cliente_recibe_no_tienes_permiso(client, servicios, con_sesion, tienda_falsa, ruta):
    con_sesion(rol="cliente")

    respuesta = client.get(ruta, follow=True)

    assert respuesta.redirect_chain == [("/", 302)]
    assert "No tienes permiso" in respuesta.content.decode()
    assert servicios.peticiones == []


def test_sin_sesion_va_al_login(client):
    assert client.get("/administracion/productos/")["Location"].startswith("/iniciar-sesion/?next=")


def test_el_menu_muestra_administracion_solo_al_administrador(client, con_sesion):
    con_sesion(rol="cliente")
    assert "Administración" not in client.get("/aviso-de-privacidad/").content.decode()

    con_sesion(rol="administrador")
    assert 'href="/administracion/"' in client.get("/aviso-de-privacidad/").content.decode()


def test_listado_de_productos_con_filtros(client, servicios, con_sesion):
    tokens = con_sesion(rol="administrador")
    productos(servicios)

    html = client.get(
        "/administracion/productos/?q=caldo&categoria=fungicidas&activo=false"
    ).content.decode()

    assert "Caldo bordelés" in html and "Desactivar" in html
    peticion = next(iter(servicios.de("svc-tienda", "/api/v1/productos/")))
    assert dict(peticion.url.params) == {
        "q": "caldo",
        "categoria": "fungicidas",
        "activo": "false",
        "page": "1",
    }
    assert peticion.headers["authorization"] == f"Bearer {tokens['access']}"


def test_listado_de_productos_con_htmx_devuelve_la_tabla(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    productos(servicios)

    html = client.get("/administracion/productos/", HTTP_HX_REQUEST="true").content.decode()

    assert 'id="tabla-productos"' in html and "<html" not in html


def test_editar_producto_con_ficha_e_imagen(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    productos(servicios)
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/caldo/", httpx.Response(200, json=PRODUCTO)
    )
    servicios.responder(
        "PATCH", "svc-tienda", "/api/v1/productos/caldo/", httpx.Response(200, json=PRODUCTO)
    )
    imagen = SimpleUploadedFile("caldo.png", b"\x89PNG\r\n\x1a\nxx", content_type="image/png")

    respuesta = client.post(
        "/administracion/productos/caldo/",
        {
            "nombre": "Caldo bordelés",
            "categoria": "fungicidas",
            "precio": "260.50",
            "stock": "8",
            "unidad": "kg",
            "descripcion": "",
            "ficha_tecnica": '{"cobre": "25%", "cal": "10%"}',
            "activo": "on",
            "imagen": imagen,
        },
    )

    assert respuesta.status_code == 302
    datos, archivo = servicios.de("svc-tienda", "/api/v1/productos/caldo/")[1:]
    assert servicios.cuerpo(datos)["ficha_tecnica"] == {"cobre": "25%", "cal": "10%"}
    assert servicios.cuerpo(datos)["precio"] == "260.50"
    assert b'filename="caldo.png"' in archivo.content


def test_ficha_tecnica_que_no_es_json_no_llega_a_la_api(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    productos(servicios)

    respuesta = client.post(
        "/administracion/productos/nuevo/",
        {
            "nombre": "X",
            "categoria": "fungicidas",
            "precio": "1",
            "stock": "1",
            "unidad": "kg",
            "ficha_tecnica": "{no es json",
        },
    )

    assert respuesta.status_code == 400
    assert "No es JSON válido" in respuesta.content.decode()
    assert not [p for p in servicios.peticiones if p.method == "POST"]


def test_desactivar_producto(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder("DELETE", "svc-tienda", "/api/v1/productos/caldo/", httpx.Response(204))

    assert (
        client.post("/administracion/productos/caldo/desactivar/")["Location"]
        == "/administracion/productos/"
    )
    assert servicios.de("svc-tienda", "/api/v1/productos/caldo/")


def test_el_pedido_muestra_solo_las_transiciones_permitidas(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/12/", httpx.Response(200, json=PEDIDO)
    )

    html = client.get("/administracion/pedidos/12/").content.decode()

    assert 'value="enviado"' in html and 'value="cancelado"' in html
    assert 'value="entregado"' not in html and 'value="pendiente"' not in html


def test_cambiar_estado_con_htmx(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "PATCH",
        "svc-tienda",
        "/api/v1/pedidos/12/estado/",
        httpx.Response(
            200, json={**PEDIDO, "estado": "enviado", "transiciones_permitidas": ["entregado"]}
        ),
    )

    html = client.post(
        "/administracion/pedidos/12/estado/", {"estado": "enviado"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    assert "Estado actualizado." in html and 'value="entregado"' in html
    assert servicios.cuerpo(servicios.de("svc-tienda")[0]) == {"estado": "enviado"}


def test_transicion_invalida_muestra_el_mensaje_del_servicio(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "PATCH",
        "svc-tienda",
        "/api/v1/pedidos/12/estado/",
        error(409, "transicion_invalida", "Un pedido pagado no puede pasar a «entregado»."),
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/12/", httpx.Response(200, json=PEDIDO)
    )

    html = client.post(
        "/administracion/pedidos/12/estado/", {"estado": "entregado"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    assert "no puede pasar a «entregado»" in html


def test_pedidos_filtrados_por_estado(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/pedidos/",
        httpx.Response(200, json={"count": 1, "next": None, "previous": None, "results": [PEDIDO]}),
    )

    html = client.get("/administracion/pedidos/?estado=pagado").content.decode()

    assert "#12" in html
    assert servicios.de("svc-tienda")[0].url.params["estado"] == "pagado"


def test_usuarios_y_cambio_de_rol(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "GET",
        "svc-usuarios",
        "/api/v1/usuarios/",
        httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": USUARIO_ID,
                        "email": "yo@x.mx",
                        "nombre": "Admin",
                        "apellidos": "",
                        "rol": "administrador",
                        "email_verificado": True,
                    },
                    {
                        "id": OTRO,
                        "email": "ana@x.mx",
                        "nombre": "Ana",
                        "apellidos": "",
                        "rol": "cliente",
                        "email_verificado": False,
                    },
                ],
            },
        ),
    )
    servicios.responder(
        "PATCH", "svc-usuarios", f"/api/v1/usuarios/{OTRO}/rol/", httpx.Response(200, json={})
    )

    html = client.get("/administracion/usuarios/?rol=cliente").content.decode()
    respuesta = client.post(
        f"/administracion/usuarios/{OTRO}/rol/", {"rol": "administrador"}, follow=True
    )

    assert "(tú)" in html and f'action="/administracion/usuarios/{OTRO}/rol/"' in html
    assert (
        f'action="/administracion/usuarios/{USUARIO_ID}/rol/"' not in html
    )  # sin botón para sí mismo
    assert "Cambiamos el rol" in respuesta.content.decode()


def test_auto_degradacion_muestra_el_mensaje(client, servicios, con_sesion):
    con_sesion(rol="administrador")
    servicios.responder(
        "PATCH",
        "svc-usuarios",
        f"/api/v1/usuarios/{USUARIO_ID}/rol/",
        error(409, "auto_degradacion", "No puedes quitarte tu propio rol de administrador."),
    )
    servicios.responder(
        "GET",
        "svc-usuarios",
        "/api/v1/usuarios/",
        httpx.Response(200, json={"count": 0, "results": []}),
    )

    respuesta = client.post(
        f"/administracion/usuarios/{USUARIO_ID}/rol/", {"rol": "cliente"}, follow=True
    )

    assert "No puedes quitarte tu propio rol de administrador." in respuesta.content.decode()
