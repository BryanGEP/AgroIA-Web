from django.urls import path

from apps.diagnostico import views

app_name = "diagnostico"

urlpatterns = [
    path("diagnostico/", views.inicio, name="inicio"),
    path("diagnostico/historial/", views.historial, name="historial"),
    path("diagnostico/<str:diagnostico_id>/", views.detalle, name="detalle"),
    path("diagnostico/<str:diagnostico_id>/imagen/", views.imagen, name="imagen"),
    path("diagnostico/<str:diagnostico_id>/estado/", views.estado, name="estado"),
]
