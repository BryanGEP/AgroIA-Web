from django.urls import path

from apps.catalogo import views

app_name = "catalogo"

urlpatterns = [
    path("catalogo/", views.lista, name="lista"),
    path("catalogo/<slug:slug>/", views.detalle, name="detalle"),
    path("media/tienda/<path:ruta>", views.imagen, name="imagen"),
]
