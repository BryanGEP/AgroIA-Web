from rest_framework.routers import DefaultRouter

from apps.bitacora.views import BitacoraViewSet

router = DefaultRouter()
router.register("bitacora", BitacoraViewSet, basename="bitacora")

urlpatterns = router.urls
