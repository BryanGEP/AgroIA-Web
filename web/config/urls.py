"""Rutas del gateway: páginas, catálogo, /salud/ y /api/docs/."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import salud

urlpatterns = [
    path("", include("apps.paginas.urls")),
    path("", include("apps.catalogo.urls")),
    path("salud/", salud, name="salud"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

handler404 = "apps.paginas.views.no_encontrado"
handler500 = "apps.paginas.views.error_servidor"
