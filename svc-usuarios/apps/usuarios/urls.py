from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.usuarios import views

router = DefaultRouter()
router.register("usuarios/yo/direcciones", views.DireccionViewSet, basename="direccion")
router.register("usuarios", views.UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("auth/registro/", views.RegistroView.as_view(), name="registro"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/token/renovar/", views.RenovarView.as_view(), name="renovar"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/logout-todo/", views.LogoutTodoView.as_view(), name="logout-todo"),
    path("auth/verificar-correo/", views.VerificarCorreoView.as_view(), name="verificar-correo"),
    path(
        "auth/reenviar-verificacion/",
        views.ReenviarVerificacionView.as_view(),
        name="reenviar-verificacion",
    ),
    path("auth/recuperar/", views.RecuperarView.as_view(), name="recuperar"),
    path("auth/restablecer/", views.RestablecerView.as_view(), name="restablecer"),
    path("auth/cambiar-password/", views.CambiarPasswordView.as_view(), name="cambiar-password"),
    path("usuarios/yo/", views.PerfilView.as_view(), name="perfil"),
    *router.urls,
]
