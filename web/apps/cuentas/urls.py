from django.urls import path

from apps.cuentas import views

app_name = "cuentas"

urlpatterns = [
    path("iniciar-sesion/", views.iniciar_sesion, name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion, name="cerrar_sesion"),
    path("registro/", views.registro, name="registro"),
    # Los enlaces de los correos (FRONTEND_URL en svc-usuarios) llegan aquí.
    path("verificar-correo/", views.verificar_correo, name="verificar_correo"),
    path("reenviar-verificacion/", views.reenviar_verificacion, name="reenviar_verificacion"),
    path("recuperar/", views.recuperar, name="recuperar"),
    path("restablecer/<str:uid>/<str:token>/", views.restablecer, name="restablecer"),
    path("mi-cuenta/", views.mi_cuenta, name="mi_cuenta"),
    path("mi-cuenta/contrasena/", views.cambiar_password, name="cambiar_password"),
    path("mi-cuenta/direcciones/", views.agregar_direccion, name="agregar_direccion"),
    path(
        "mi-cuenta/direcciones/<int:direccion_id>/borrar/",
        views.borrar_direccion,
        name="borrar_direccion",
    ),
    path(
        "mi-cuenta/direcciones/<int:direccion_id>/predeterminada/",
        views.predeterminada,
        name="predeterminada",
    ),
]
