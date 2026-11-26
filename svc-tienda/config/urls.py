"""Rutas del servicio: /salud/, /api/docs/ y /api/v1/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import salud

urlpatterns = [
    path("salud/", salud, name="salud"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.catalogo.urls")),
    path("api/v1/", include("apps.pedidos.urls")),
    path("admin/", admin.site.urls),
]

# En desarrollo svc-tienda sirve las imágenes subidas; después las servirá el gateway.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
