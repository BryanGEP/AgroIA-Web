from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from agroia_comun.permisos import EsAdministrador, es_administrador
from apps.catalogo import servicios
from apps.catalogo.filters import ProductoFilter
from apps.catalogo.models import Categoria, Producto
from apps.catalogo.serializers import CategoriaSerializer, ProductoSerializer

ERRORES_ADMIN = {
    400: OpenApiResponse(description="Datos inválidos (`validacion`, con `campos`)."),
    401: OpenApiResponse(description="Sin token o token inválido."),
    403: OpenApiResponse(description="El usuario no es administrador."),
}
NO_ENCONTRADO = {404: OpenApiResponse(description="No existe o no está activo.")}


class _SoloAdminEscribe:
    """Lectura pública; escritura solo para administradores."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [EsAdministrador()]


@extend_schema_view(
    list=extend_schema(
        summary="Listar categorías",
        description="Público. Solo categorías activas; el administrador ve también las inactivas.",
        auth=[],
    ),
    retrieve=extend_schema(
        summary="Ver una categoría", auth=[], responses={200: CategoriaSerializer, **NO_ENCONTRADO}
    ),
    create=extend_schema(
        summary="Crear categoría",
        description="Solo administrador. El slug se genera del nombre si no se envía.",
        responses={201: CategoriaSerializer, **ERRORES_ADMIN},
    ),
    partial_update=extend_schema(
        summary="Editar categoría",
        description="Solo administrador.",
        responses={200: CategoriaSerializer, **ERRORES_ADMIN, **NO_ENCONTRADO},
    ),
    destroy=extend_schema(
        summary="Desactivar categoría",
        description="Solo administrador. Borrado lógico: `activa=False`.",
        responses={204: None, **ERRORES_ADMIN, **NO_ENCONTRADO},
    ),
)
class CategoriaViewSet(_SoloAdminEscribe, viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    lookup_field = "slug"
    filterset_fields = ["activa"]
    ordering_fields = ["nombre"]
    ordering = ["nombre"]

    def get_queryset(self):
        return servicios.categorias_visibles(es_administrador(self.request))

    def perform_create(self, serializer):
        slug = serializer.validated_data.get("slug") or servicios.generar_slug_unico(
            Categoria, serializer.validated_data["nombre"]
        )
        serializer.save(slug=slug)

    def perform_destroy(self, instance):
        servicios.desactivar_categoria(instance)


@extend_schema_view(
    list=extend_schema(
        summary="Listar productos",
        description=(
            "Público, paginado de 20 en 20 (`?page=`). Filtros: `categoria` (slug), "
            "`precio_min`, `precio_max`, `disponible` y `q` (busca en nombre y descripción). "
            "Orden con `ordering`: `precio`, `nombre`, `creado_en` (con `-` para descendente). "
            "El público solo ve productos activos de categorías activas."
        ),
        auth=[],
    ),
    retrieve=extend_schema(
        summary="Ver un producto por slug",
        auth=[],
        responses={200: ProductoSerializer, **NO_ENCONTRADO},
    ),
    create=extend_schema(
        summary="Crear producto",
        description=(
            "Solo administrador. Acepta JSON o `multipart/form-data` para subir la imagen "
            "(JPG, PNG o WebP, máximo 5 MB). En multipart, `ficha_tecnica` va como texto JSON."
        ),
        request={
            "application/json": ProductoSerializer,
            "multipart/form-data": ProductoSerializer,
        },
        responses={201: ProductoSerializer, **ERRORES_ADMIN},
    ),
    partial_update=extend_schema(
        summary="Editar producto",
        description="Solo administrador. `activo=true` reactiva un producto desactivado.",
        request={
            "application/json": ProductoSerializer,
            "multipart/form-data": ProductoSerializer,
        },
        responses={200: ProductoSerializer, **ERRORES_ADMIN, **NO_ENCONTRADO},
    ),
    destroy=extend_schema(
        summary="Desactivar producto",
        description="Solo administrador. Borrado lógico: `activo=False`; los pedidos lo conservan.",
        responses={204: None, **ERRORES_ADMIN, **NO_ENCONTRADO},
    ),
)
class ProductoViewSet(_SoloAdminEscribe, viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    lookup_field = "slug"
    filterset_class = ProductoFilter
    ordering_fields = ["precio", "nombre", "creado_en"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        return servicios.productos_visibles(es_administrador(self.request))

    def perform_create(self, serializer):
        slug = serializer.validated_data.get("slug") or servicios.generar_slug_unico(
            Producto, serializer.validated_data["nombre"]
        )
        serializer.save(slug=slug)

    def perform_destroy(self, instance):
        servicios.desactivar_producto(instance)
