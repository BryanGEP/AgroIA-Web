from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.pedidos.views import CarritoView, ItemCarritoView, ItemsCarritoView, PedidoViewSet

router = DefaultRouter()
router.register("pedidos", PedidoViewSet, basename="pedido")

urlpatterns = [
    path("carrito/", CarritoView.as_view(), name="carrito"),
    path("carrito/items/", ItemsCarritoView.as_view(), name="carrito-items"),
    path("carrito/items/<int:pk>/", ItemCarritoView.as_view(), name="carrito-item"),
    *router.urls,
]
