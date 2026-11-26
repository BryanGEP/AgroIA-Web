from rest_framework.routers import DefaultRouter

from apps.diagnosticos.views import DiagnosticoViewSet

router = DefaultRouter()
router.register("diagnosticos", DiagnosticoViewSet, basename="diagnostico")

urlpatterns = router.urls
