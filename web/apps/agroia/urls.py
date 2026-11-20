from django.urls import path

from apps.agroia import views

app_name = "agroia"

urlpatterns = [
    path("agroia/", views.inicio, name="inicio"),
    path("agroia/nueva/", views.nueva, name="nueva"),
    path("agroia/<str:conversacion_id>/", views.ver, name="ver"),
    path("agroia/<str:conversacion_id>/preguntar/", views.preguntar, name="preguntar"),
    path("agroia/<str:conversacion_id>/reintentar/", views.reintentar, name="reintentar"),
    path("agroia/<str:conversacion_id>/borrar/", views.borrar, name="borrar"),
]
