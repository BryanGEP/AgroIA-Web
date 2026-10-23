"""Rutas del servicio: /salud/, /api/docs/, /api/v1/ y el admin de Django."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import salud

urlpatterns = [
    path("salud/", salud, name="salud"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.usuarios.urls")),
    path("admin/", admin.site.urls),
]
