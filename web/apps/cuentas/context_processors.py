"""`usuario` en todas las plantillas: el menú y el banner de correo sin verificar.

Solo id, nombre, rol y email_verificado; los tokens nunca llegan a las plantillas.
"""


def usuario(request) -> dict:
    datos = request.session.get("usuario") if hasattr(request, "session") else None
    return {"usuario": datos or None}
