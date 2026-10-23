from django.urls import path

from apps.paginas import views

app_name = "paginas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("aviso-de-privacidad/", views.aviso_privacidad, name="aviso_privacidad"),
]
