from django.contrib import admin

from apps.catalogo.models import Categoria, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "slug", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]
    prepopulated_fields = {"slug": ["nombre"]}


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "precio", "stock", "unidad", "activo", "creado_en"]
    list_filter = ["activo", "categoria", "unidad"]
    list_editable = ["precio", "stock", "activo"]
    search_fields = ["nombre", "descripcion"]
    prepopulated_fields = {"slug": ["nombre"]}
    readonly_fields = ["creado_en"]
