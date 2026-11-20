from django.urls import path

from apps.panel import views

app_name = "panel"

urlpatterns = [
    path("administracion/", views.inicio, name="inicio"),
    path("administracion/productos/", views.productos, name="productos"),
    path("administracion/productos/nuevo/", views.producto, name="producto_nuevo"),
    path("administracion/productos/<slug:slug>/", views.producto, name="producto"),
    path(
        "administracion/productos/<slug:slug>/desactivar/",
        views.desactivar_producto,
        name="desactivar_producto",
    ),
    path("administracion/categorias/", views.categorias, name="categorias"),
    path("administracion/categorias/nueva/", views.categoria, name="categoria_nueva"),
    path("administracion/categorias/<slug:slug>/", views.categoria, name="categoria"),
    path(
        "administracion/categorias/<slug:slug>/desactivar/",
        views.desactivar_categoria,
        name="desactivar_categoria",
    ),
    path("administracion/pedidos/", views.pedidos, name="pedidos"),
    path("administracion/pedidos/<int:pedido_id>/", views.pedido, name="pedido"),
    path("administracion/pedidos/<int:pedido_id>/estado/", views.cambiar_estado, name="estado"),
    path("administracion/usuarios/", views.usuarios, name="usuarios"),
    path("administracion/usuarios/<uuid:usuario_id>/rol/", views.cambiar_rol, name="rol"),
]
