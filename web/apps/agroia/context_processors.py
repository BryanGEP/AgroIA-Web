"""`widget_agroia` en todas las plantillas: si base.html muestra el widget flotante en esta
página y si hay una pregunta del widget pendiente (para seguir el polling al cambiar de
página sin pedir nada a svc-contenido).

No aparece en /agroia/ (ahí está el chat completo), en las pantallas de acceso ni en el
panel de administración. Las páginas de error lo quitan con el bloque `widget_agroia`.
"""

from apps.agroia import servicios


def widget_agroia(request) -> dict:
    coincidencia = getattr(request, "resolver_match", None)
    app = getattr(coincidencia, "app_name", None)
    vista = getattr(coincidencia, "url_name", None)
    sesion = getattr(request, "session", None)
    con_sesion = bool(sesion is not None and sesion.get("access"))
    return {
        "widget_agroia": {
            "mostrar": servicios.mostrar_widget(app, vista),
            "con_sesion": con_sesion,
            "pendiente": bool(con_sesion and sesion.get(servicios.SESION_PENDIENTE)),
        }
    }
