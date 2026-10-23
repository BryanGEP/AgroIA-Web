"""Rutas del servicio: /salud/, /api/docs/ y /api/v1/."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import salud

urlpatterns = [
    path("salud/", salud, name="salud"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.conversaciones.urls")),
    path("api/v1/", include("apps.diagnosticos.urls")),
    path("api/v1/", include("apps.bitacora.urls")),
]

# En desarrollo svc-contenido sirve las imágenes de diagnósticos; después las servirá el
# gateway y en la Entrega 5, Cloud Storage.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
