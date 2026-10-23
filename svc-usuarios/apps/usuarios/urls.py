from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.usuarios.views import DireccionViewSet, PerfilView, RegistroView, UsuarioViewSet

router = DefaultRouter()
router.register("usuarios/yo/direcciones", DireccionViewSet, basename="direccion")
router.register("usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("auth/registro/", RegistroView.as_view(), name="registro"),
    path("usuarios/yo/", PerfilView.as_view(), name="perfil"),
    *router.urls,
]
