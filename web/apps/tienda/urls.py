from django.urls import path

from apps.tienda import views

app_name = "tienda"

urlpatterns = [
    path("carrito/", views.carrito, name="carrito"),
    path("carrito/agregar/<slug:slug>/", views.agregar, name="agregar"),
    path("carrito/items/<int:item_id>/cantidad/", views.cambiar, name="cambiar"),
    path("carrito/items/<int:item_id>/quitar/", views.quitar, name="quitar"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/direccion/", views.checkout_direccion, name="checkout_direccion"),
    path("mis-pedidos/", views.mis_pedidos, name="mis_pedidos"),
    path("mis-pedidos/<int:pedido_id>/", views.pedido, name="pedido"),
    path("mis-pedidos/<int:pedido_id>/pagar/", views.pagar, name="pagar"),
]
