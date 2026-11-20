from django.urls import path

from apps.proxy import views

app_name = "proxy"

urlpatterns = [
    path("api/<str:servicio>/<path:ruta>", views.reenviar, name="reenviar"),
]
