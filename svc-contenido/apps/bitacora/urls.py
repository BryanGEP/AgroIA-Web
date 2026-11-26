from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.bitacora.views import BitacoraViewSet, EstadoEventosView

router = DefaultRouter()
router.register("bitacora", BitacoraViewSet, basename="bitacora")

urlpatterns = [
    path("eventos/estado/", EstadoEventosView.as_view(), name="estado-eventos"),
    *router.urls,
]
