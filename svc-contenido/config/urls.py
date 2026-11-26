"""Rutas del servicio: /salud/, /api/docs/ y /api/v1/.

Las fotos de diagnóstico no se sirven como archivos estáticos (ni con DEBUG=True): son datos
personales. Solo salen por GET /api/v1/diagnosticos/<id>/imagen/, para el dueño o un
administrador.
"""

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
