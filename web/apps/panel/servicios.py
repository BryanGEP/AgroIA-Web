"""Panel de administración: llama a svc-tienda y svc-usuarios con el token del administrador.

Las reglas las aplica cada servicio (roles, transiciones de pedido, auto-degradación); el
panel solo muestra lo que ellos permiten, por ejemplo `transiciones_permitidas` del pedido.
"""

from clientes.tienda import reescribir_imagen
from django.http import HttpRequest

from apps.cuentas.servicios import con_sesion

ESTADOS = [
    ("pendiente", "Pendiente de pago"),
    ("pagado", "Pagado"),
    ("enviado", "Enviado"),
    ("entregado", "Entregado"),
    ("cancelado", "Cancelado"),
]
UNIDADES = [("pieza", "Pieza"), ("kg", "Kilogramo"), ("litro", "Litro"), ("costal", "Costal")]


def _limpios(filtros: dict) -> dict:
    return {clave: valor for clave, valor in filtros.items() if valor not in ("", None)}


# --- Productos y categorías ---------------------------------------------------------------


def productos(request: HttpRequest, filtros: dict) -> dict:
    """Incluye los inactivos: svc-tienda los muestra al administrador."""
    datos = con_sesion(request, "tienda", "GET", "productos/", params=_limpios(filtros))
    datos["results"] = [reescribir_imagen(p) for p in datos.get("results", [])]
    return datos


def producto(request: HttpRequest, slug: str) -> dict:
    return reescribir_imagen(con_sesion(request, "tienda", "GET", f"productos/{slug}/"))


def guardar_producto(request: HttpRequest, slug: str | None, datos: dict, imagen=None) -> dict:
    """Los datos van en JSON (la ficha técnica es un objeto). La imagen, si hay, en un
    segundo PATCH multipart: un JSONField no se lee bien dentro de un formulario."""
    if slug:
        producto_guardado = con_sesion(request, "tienda", "PATCH", f"productos/{slug}/", json=datos)
    else:
        producto_guardado = con_sesion(request, "tienda", "POST", "productos/", json=datos)
    if imagen is not None:
        producto_guardado = con_sesion(
            request,
            "tienda",
            "PATCH",
            f"productos/{producto_guardado['slug']}/",
            files={"imagen": (imagen.name, imagen.read(), imagen.content_type)},
        )
    return producto_guardado


def desactivar_producto(request: HttpRequest, slug: str) -> None:
    con_sesion(request, "tienda", "DELETE", f"productos/{slug}/")


def categorias(request: HttpRequest) -> list[dict]:
    datos = con_sesion(request, "tienda", "GET", "categorias/")
    return datos.get("results", []) if isinstance(datos, dict) else datos


def categoria(request: HttpRequest, slug: str) -> dict:
    return con_sesion(request, "tienda", "GET", f"categorias/{slug}/")


def guardar_categoria(request: HttpRequest, slug: str | None, datos: dict) -> dict:
    if slug:
        return con_sesion(request, "tienda", "PATCH", f"categorias/{slug}/", json=datos)
    return con_sesion(request, "tienda", "POST", "categorias/", json=datos)


def desactivar_categoria(request: HttpRequest, slug: str) -> None:
    con_sesion(request, "tienda", "DELETE", f"categorias/{slug}/")


# --- Pedidos ------------------------------------------------------------------------------


def pedidos(request: HttpRequest, filtros: dict) -> dict:
    return con_sesion(request, "tienda", "GET", "pedidos/", params=_limpios(filtros))


def pedido(request: HttpRequest, pedido_id: int) -> dict:
    return con_sesion(request, "tienda", "GET", f"pedidos/{pedido_id}/")


def cambiar_estado(request: HttpRequest, pedido_id: int, estado: str) -> dict:
    """svc-tienda valida la transición y devuelve las nuevas transiciones permitidas."""
    return con_sesion(
        request, "tienda", "PATCH", f"pedidos/{pedido_id}/estado/", json={"estado": estado}
    )


# --- Usuarios -----------------------------------------------------------------------------


def usuarios(request: HttpRequest, filtros: dict) -> dict:
    return con_sesion(request, "usuarios", "GET", "usuarios/", params=_limpios(filtros))


def cambiar_rol(request: HttpRequest, usuario_id: str, rol: str) -> dict:
    return con_sesion(
        request, "usuarios", "PATCH", f"usuarios/{usuario_id}/rol/", json={"rol": rol}
    )
