"""`usuario` y `carrito_cantidad` en todas las plantillas: el menú y el banner de correo sin
verificar.

Solo id, nombre, rol y email_verificado; los tokens nunca llegan a las plantillas.
"""


def usuario(request) -> dict:
    sesion = getattr(request, "session", None)
    if sesion is None:
        return {"usuario": None, "carrito_cantidad": 0}
    return {
        "usuario": sesion.get("usuario") or None,
        # Se guarda en la sesión al iniciar sesión y con cada cambio del carrito.
        "carrito_cantidad": sesion.get("carrito_cantidad", 0),
    }
