"""Rutas del servicio: /salud/, /api/docs/ y, desde la fase 1, /api/v1/."""

from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import salud

urlpatterns = [
    path("salud/", salud, name="salud"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("admin/", admin.site.urls),
    # path("api/v1/", include(...)),  # fase 1 en adelante
]
