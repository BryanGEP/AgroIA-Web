"""Endpoints de categorías y productos: caso correcto, validación, 401 y 403."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.catalogo.models import Categoria, Producto
from apps.catalogo.tests.factories import CategoriaFactory, ProductoFactory

pytestmark = pytest.mark.django_db

CATEGORIAS = "/api/v1/categorias/"
PRODUCTOS = "/api/v1/productos/"


def png(nombre: str = "foto.png") -> SimpleUploadedFile:
    contenido = BytesIO()
    Image.new("RGB", (10, 10), "green").save(contenido, format="PNG")
    return SimpleUploadedFile(nombre, contenido.getvalue(), content_type="image/png")


def slugs(respuesta) -> list[str]:
    return [p["slug"] for p in respuesta.json()["results"]]


# --- Categorías ---------------------------------------------------------------


def test_listar_categorias_es_publico_y_oculta_inactivas(anonimo):
    CategoriaFactory(slug="fungicidas")
    CategoriaFactory(slug="vieja", activa=False)

    respuesta = anonimo.get(CATEGORIAS)

    assert respuesta.status_code == 200
    assert [c["slug"] for c in respuesta.json()["results"]] == ["fungicidas"]


def test_admin_ve_categorias_inactivas(admin):
    CategoriaFactory()
    CategoriaFactory(activa=False)

    assert admin.get(CATEGORIAS).json()["count"] == 2


def test_crear_categoria_genera_slug(admin):
    respuesta = admin.post(CATEGORIAS, {"nombre": "Nutrición foliar"}, format="json")

    assert respuesta.status_code == 201
    assert respuesta.json()["slug"] == "nutricion-foliar"


def test_crear_categoria_sin_nombre_falla(admin):
    respuesta = admin.post(CATEGORIAS, {"descripcion": "sin nombre"}, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert "nombre" in respuesta.json()["campos"]


def test_crear_categoria_sin_token_401(anonimo):
    respuesta = anonimo.post(CATEGORIAS, {"nombre": "Riego"}, format="json")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "no_autenticado"


def test_crear_categoria_como_cliente_403(cliente):
    respuesta = cliente.post(CATEGORIAS, {"nombre": "Riego"}, format="json")

    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "sin_permiso"


def test_editar_categoria(admin, anonimo, cliente):
    categoria = CategoriaFactory(slug="riego")
    url = f"{CATEGORIAS}riego/"

    assert admin.patch(url, {"descripcion": "Goteo"}, format="json").status_code == 200
    categoria.refresh_from_db()
    assert categoria.descripcion == "Goteo"
    assert admin.patch(url, {"nombre": ""}, format="json").status_code == 400
    assert anonimo.patch(url, {"descripcion": "x"}, format="json").status_code == 401
    assert cliente.patch(url, {"descripcion": "x"}, format="json").status_code == 403


def test_borrar_categoria_es_logico(admin, anonimo, cliente):
    categoria = CategoriaFactory(slug="riego")
    url = f"{CATEGORIAS}riego/"

    assert anonimo.delete(url).status_code == 401
    assert cliente.delete(url).status_code == 403
    assert admin.delete(url).status_code == 204
    categoria.refresh_from_db()
    assert categoria.activa is False
    assert anonimo.get(url).status_code == 404


def test_put_no_esta_permitido(admin):
    CategoriaFactory(slug="riego")

    respuesta = admin.put(f"{CATEGORIAS}riego/", {"nombre": "Riego"}, format="json")

    assert respuesta.status_code == 405
    assert respuesta.json()["error"] == "metodo_no_permitido"


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_no_revisa_el_rol_de_admin(anonimo):
    respuesta = anonimo.post(CATEGORIAS, {"nombre": "Herramientas"}, format="json")

    assert respuesta.status_code == 201


# --- Productos: listado y detalle ---------------------------------------------


def test_listar_productos_es_publico_y_solo_activos(anonimo):
    ProductoFactory(slug="visible")
    ProductoFactory(slug="inactivo", activo=False)
    ProductoFactory(slug="de-categoria-inactiva", categoria=CategoriaFactory(activa=False))

    respuesta = anonimo.get(PRODUCTOS)

    assert respuesta.status_code == 200
    assert slugs(respuesta) == ["visible"]
    producto = respuesta.json()["results"][0]
    assert producto["precio"] == "100.00"
    assert producto["disponible"] is True


def test_listado_paginado_de_20(anonimo):
    ProductoFactory.create_batch(25)

    primera = anonimo.get(PRODUCTOS).json()
    segunda = anonimo.get(PRODUCTOS, {"page": 2}).json()

    assert primera["count"] == 25
    assert len(primera["results"]) == 20
    assert len(segunda["results"]) == 5


def test_filtros_de_productos(anonimo):
    fungicidas = CategoriaFactory(slug="fungicidas")
    ProductoFactory(slug="cobre", categoria=fungicidas, precio=Decimal("180.00"), stock=0)
    ProductoFactory(slug="azufre", categoria=fungicidas, precio=Decimal("90.00"))
    ProductoFactory(slug="tijera", precio=Decimal("350.00"))

    assert sorted(slugs(anonimo.get(PRODUCTOS, {"categoria": "fungicidas"}))) == [
        "azufre",
        "cobre",
    ]
    assert slugs(anonimo.get(PRODUCTOS, {"precio_min": "100", "precio_max": "200"})) == ["cobre"]
    assert sorted(slugs(anonimo.get(PRODUCTOS, {"disponible": "true"}))) == ["azufre", "tijera"]
    assert slugs(anonimo.get(PRODUCTOS, {"disponible": "false"})) == ["cobre"]


def test_busqueda_en_nombre_y_descripcion(anonimo):
    ProductoFactory(slug="a", nombre="Caldo bordelés", descripcion="Fungicida cúprico")
    ProductoFactory(slug="b", nombre="Tijera", descripcion="Para poda de ramas")
    ProductoFactory(slug="c", nombre="Urea", descripcion="Fertilizante nitrogenado")

    assert slugs(anonimo.get(PRODUCTOS, {"q": "bordel"})) == ["a"]
    assert slugs(anonimo.get(PRODUCTOS, {"q": "PODA"})) == ["b"]


def test_ordenamiento(anonimo):
    ProductoFactory(slug="caro", nombre="Bomba", precio=Decimal("900.00"))
    ProductoFactory(slug="barato", nombre="Azufre", precio=Decimal("50.00"))

    assert slugs(anonimo.get(PRODUCTOS, {"ordering": "precio"})) == ["barato", "caro"]
    assert slugs(anonimo.get(PRODUCTOS, {"ordering": "-precio"})) == ["caro", "barato"]
    assert slugs(anonimo.get(PRODUCTOS, {"ordering": "nombre"})) == ["barato", "caro"]
    assert slugs(anonimo.get(PRODUCTOS))[0] == "barato"  # por defecto, el más reciente


def test_filtro_con_valor_invalido_falla(anonimo):
    respuesta = anonimo.get(PRODUCTOS, {"precio_min": "barato"})

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert "precio_min" in respuesta.json()["campos"]


def test_detalle_por_slug(anonimo):
    ProductoFactory(slug="caldo-bordeles", ficha_tecnica={"dosis": "2 kg/ha"})

    respuesta = anonimo.get(f"{PRODUCTOS}caldo-bordeles/")

    assert respuesta.status_code == 200
    assert respuesta.json()["ficha_tecnica"] == {"dosis": "2 kg/ha"}


def test_producto_inactivo_no_existe_para_el_publico(anonimo, cliente, admin):
    ProductoFactory(slug="retirado", activo=False)
    url = f"{PRODUCTOS}retirado/"

    assert anonimo.get(url).status_code == 404
    assert anonimo.get(url).json()["error"] == "no_encontrado"
    assert cliente.get(url).status_code == 404
    assert admin.get(url).status_code == 200


def test_admin_filtra_por_activo(admin):
    ProductoFactory(slug="activo")
    ProductoFactory(slug="inactivo", activo=False)

    assert slugs(admin.get(PRODUCTOS, {"activo": "false"})) == ["inactivo"]


# --- Productos: escritura -----------------------------------------------------


def datos_producto(**cambios) -> dict:
    datos = {
        "nombre": "Oxicloruro de cobre 50% PH",
        "categoria": CategoriaFactory(slug="fungicidas").slug,
        "descripcion": "Fungicida preventivo.",
        "precio": "245.50",
        "stock": 30,
        "unidad": "kg",
        "ficha_tecnica": {"ingrediente_activo": "Oxicloruro de cobre", "dosis": "2-3 kg/ha"},
    }
    datos.update(cambios)
    return datos


def test_crear_producto(admin):
    respuesta = admin.post(PRODUCTOS, datos_producto(), format="json")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["slug"] == "oxicloruro-de-cobre-50-ph"
    assert cuerpo["precio"] == "245.50"
    assert cuerpo["categoria"] == "fungicidas"
    assert Producto.objects.get().precio == Decimal("245.50")


def test_crear_producto_con_imagen(admin):
    datos = datos_producto(ficha_tecnica='{"dosis": "2 kg/ha"}')
    datos["imagen"] = png()

    respuesta = admin.post(PRODUCTOS, datos, format="multipart")

    assert respuesta.status_code == 201, respuesta.json()
    assert respuesta.json()["imagen"].endswith(".png")
    assert Producto.objects.get().ficha_tecnica == {"dosis": "2 kg/ha"}


def test_imagen_con_formato_no_permitido_falla(admin):
    datos = datos_producto()
    datos.pop("ficha_tecnica")
    datos["imagen"] = SimpleUploadedFile("ficha.txt", b"texto", content_type="text/plain")

    respuesta = admin.post(PRODUCTOS, datos, format="multipart")

    assert respuesta.status_code == 400
    assert "imagen" in respuesta.json()["campos"]


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("precio", "-5.00"),
        ("precio", "0"),
        ("stock", -1),
        ("unidad", "tonelada"),
        ("categoria", "no-existe"),
        ("ficha_tecnica", ["no", "es", "objeto"]),
    ],
)
def test_crear_producto_con_datos_invalidos(admin, campo, valor):
    respuesta = admin.post(PRODUCTOS, datos_producto(**{campo: valor}), format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_crear_producto_sin_token_401(anonimo):
    assert anonimo.post(PRODUCTOS, datos_producto(), format="json").status_code == 401


def test_crear_producto_como_cliente_403(cliente):
    assert cliente.post(PRODUCTOS, datos_producto(), format="json").status_code == 403


def test_editar_producto(admin, anonimo, cliente):
    producto = ProductoFactory(slug="urea")
    url = f"{PRODUCTOS}urea/"

    respuesta = admin.patch(url, {"precio": "520.00", "stock": 8}, format="json")
    assert respuesta.status_code == 200
    producto.refresh_from_db()
    assert (producto.precio, producto.stock) == (Decimal("520.00"), 8)
    assert admin.patch(url, {"stock": -3}, format="json").status_code == 400
    assert anonimo.patch(url, {"stock": 1}, format="json").status_code == 401
    assert cliente.patch(url, {"stock": 1}, format="json").status_code == 403


def test_borrar_producto_es_logico(admin, anonimo, cliente):
    producto = ProductoFactory(slug="urea")
    url = f"{PRODUCTOS}urea/"

    assert anonimo.delete(url).status_code == 401
    assert cliente.delete(url).status_code == 403
    assert admin.delete(url).status_code == 204
    producto.refresh_from_db()
    assert producto.activo is False
    assert Producto.objects.filter(pk=producto.pk).exists()
    assert Categoria.objects.exists()
