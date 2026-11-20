"""Carrito, checkout y pedidos del cliente: llama a svc-tienda (y a svc-usuarios para la
dirección) con el token de la sesión.

El contador del carrito del menú vive en la sesión (`carrito_cantidad`): se recalcula al
iniciar sesión, al abrir /carrito/ y con cada cambio, para no consultar svc-tienda en cada
página.
"""

from clientes.tienda import reescribir_imagen
from django.http import HttpRequest

from apps.cuentas import servicios as cuentas
from apps.cuentas.servicios import ErrorApi, con_sesion

# Campos de la dirección de svc-usuarios que svc-tienda copia en el pedido.
CAMPOS_DIRECCION = (
    "alias",
    "calle",
    "numero",
    "colonia",
    "municipio",
    "estado",
    "codigo_postal",
    "referencias",
)
METODOS_DE_PAGO = [
    ("tarjeta", "Tarjeta"),
    ("transferencia", "Transferencia"),
    ("contra_entrega", "Contra entrega"),
]


def guardar_contador(request: HttpRequest, carrito: dict) -> None:
    request.session["carrito_cantidad"] = sum(
        item.get("cantidad", 0) for item in carrito.get("items", [])
    )


def carrito(request: HttpRequest) -> dict:
    datos = con_sesion(request, "tienda", "GET", "carrito/")
    for item in datos.get("items", []):
        if isinstance(item.get("producto"), dict):
            reescribir_imagen(item["producto"])
    guardar_contador(request, datos)
    return datos


def recalcular_contador(request: HttpRequest) -> None:
    """Al iniciar sesión: si svc-tienda no responde, el contador queda en cero."""
    try:
        carrito(request)
    except ErrorApi:
        request.session["carrito_cantidad"] = 0


def agregar(request: HttpRequest, slug: str, cantidad: int = 1) -> dict:
    con_sesion(
        request, "tienda", "POST", "carrito/items/", json={"producto": slug, "cantidad": cantidad}
    )
    return carrito(request)


def cambiar_cantidad(request: HttpRequest, item_id: int, cantidad: int) -> dict:
    con_sesion(request, "tienda", "PATCH", f"carrito/items/{item_id}/", json={"cantidad": cantidad})
    return carrito(request)


def quitar(request: HttpRequest, item_id: int) -> dict:
    con_sesion(request, "tienda", "DELETE", f"carrito/items/{item_id}/")
    return carrito(request)


def direcciones(request: HttpRequest) -> list[dict]:
    return cuentas.direcciones(request)


def crear_pedido(request: HttpRequest, direccion_id: int, metodo_pago: str) -> dict:
    """El gateway trae la dirección de svc-usuarios y la manda a svc-tienda en el cuerpo
    (`direccion_envio`): svc-tienda no consulta a svc-usuarios."""
    direccion = next((d for d in direcciones(request) if d.get("id") == direccion_id), None)
    if direccion is None:
        raise ErrorApi(
            estado=400,
            codigo="validacion",
            detalle="Revisa los datos marcados.",
            campos={"direccion": ["Elige una de tus direcciones."]},
        )
    direccion_envio = {c: direccion[c] for c in CAMPOS_DIRECCION if direccion.get(c)}
    pedido = con_sesion(
        request,
        "tienda",
        "POST",
        "pedidos/",
        json={"direccion_envio": direccion_envio, "metodo_pago": metodo_pago},
    )
    request.session["carrito_cantidad"] = 0
    return pedido


def pedidos(request: HttpRequest, pagina: int = 1) -> dict:
    return con_sesion(request, "tienda", "GET", "pedidos/", params={"page": pagina})


def pedido(request: HttpRequest, pedido_id: int) -> dict:
    return con_sesion(request, "tienda", "GET", f"pedidos/{pedido_id}/")


def pagar(request: HttpRequest, pedido_id: int) -> dict:
    return con_sesion(request, "tienda", "POST", f"pedidos/{pedido_id}/pagar/")
