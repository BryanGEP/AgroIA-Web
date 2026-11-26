from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agroia_comun.permisos import (
    CorreoVerificado,
    EsAdministrador,
    EsCliente,
    EsDuenoOAdmin,
    es_administrador,
    usuario_id,
)
from apps.pedidos import servicios
from apps.pedidos.filters import PedidoFilter
from apps.pedidos.models import ItemCarrito, Pedido
from apps.pedidos.serializers import (
    AgregarItemSerializer,
    CambiarCantidadSerializer,
    CambiarEstadoSerializer,
    CarritoSerializer,
    CrearPedidoSerializer,
    FiltroResumenSerializer,
    PedidoSerializer,
    ResumenSerializer,
)

SIN_TOKEN = {401: OpenApiResponse(description="Sin token o token inválido.")}
SIN_ROL = {403: OpenApiResponse(description="El token no trae un rol válido.")}
INVALIDO = {400: OpenApiResponse(description="Datos inválidos (`validacion`, con `campos`).")}
NO_ENCONTRADO = {404: OpenApiResponse(description="No existe o no es tuyo.")}
STOCK = {
    409: OpenApiResponse(
        description="`stock_insuficiente` o `producto_no_disponible`.",
        examples=[
            OpenApiExample(
                "Sin stock",
                value={
                    "error": "stock_insuficiente",
                    "detalle": "No hay suficiente stock de «Urea 46%»: pediste 3 y quedan 1.",
                },
            )
        ],
    )
}
TRANSICION = {
    409: OpenApiResponse(
        description="`transicion_invalida`.",
        examples=[
            OpenApiExample(
                "Transición inválida",
                value={
                    "error": "transicion_invalida",
                    "detalle": "Un pedido pendiente no puede pasar a «entregado».",
                },
            )
        ],
    )
}


def _carrito(request) -> dict:
    carrito = servicios.obtener_carrito(usuario_id(request))
    return CarritoSerializer(carrito, context={"request": request}).data


class _DeUsuario:
    """Carrito: cualquier usuario autenticado con rol válido, sobre su propio carrito."""

    permission_classes = [IsAuthenticated, EsDuenoOAdmin]


class CarritoView(_DeUsuario, APIView):
    @extend_schema(
        summary="Ver mi carrito",
        description=(
            "Se crea vacío la primera vez. Los totales se estiman con los precios actuales."
        ),
        responses={200: CarritoSerializer, **SIN_TOKEN, **SIN_ROL},
    )
    def get(self, request):
        return Response(_carrito(request))

    @extend_schema(
        summary="Vaciar mi carrito",
        responses={204: None, **SIN_TOKEN, **SIN_ROL},
    )
    def delete(self, request):
        servicios.vaciar_carrito(usuario_id(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ItemsCarritoView(_DeUsuario, APIView):
    @extend_schema(
        summary="Agregar al carrito",
        description=(
            "Si el producto ya está en el carrito, suma la cantidad. Valida que el total no "
            "supere el stock disponible. El carrito no aparta stock: se descuenta al crear "
            "el pedido."
        ),
        request=AgregarItemSerializer,
        responses={201: CarritoSerializer, **INVALIDO, **SIN_TOKEN, **SIN_ROL, **STOCK},
    )
    def post(self, request):
        datos = AgregarItemSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.agregar_al_carrito(
            usuario_id(request), datos.validated_data["producto"], datos.validated_data["cantidad"]
        )
        return Response(_carrito(request), status=status.HTTP_201_CREATED)


class ItemCarritoView(_DeUsuario, APIView):
    def _item(self, request, pk: int) -> ItemCarrito:
        return get_object_or_404(
            ItemCarrito.objects.select_related("producto__categoria", "carrito"),
            pk=pk,
            carrito__usuario_id=usuario_id(request),
        )

    @extend_schema(
        summary="Cambiar cantidad de un item",
        request=CambiarCantidadSerializer,
        responses={
            200: CarritoSerializer,
            **INVALIDO,
            **SIN_TOKEN,
            **SIN_ROL,
            **NO_ENCONTRADO,
            **STOCK,
        },
    )
    def patch(self, request, pk: int):
        item = self._item(request, pk)
        datos = CambiarCantidadSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.cambiar_cantidad(item, datos.validated_data["cantidad"])
        return Response(_carrito(request))

    @extend_schema(
        summary="Quitar un item",
        responses={204: None, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    )
    def delete(self, request, pk: int):
        servicios.quitar_item(self._item(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="Listar pedidos",
        description=(
            "El cliente ve solo los suyos; el administrador ve todos. Filtro `estado`. "
            "Paginado de 20 en 20."
        ),
        responses={200: PedidoSerializer(many=True), **INVALIDO, **SIN_TOKEN, **SIN_ROL},
    ),
    retrieve=extend_schema(
        summary="Ver un pedido",
        description="Dueño o administrador. Si el pedido es de otro cliente responde 404.",
        responses={200: PedidoSerializer, **SIN_TOKEN, **SIN_ROL, **NO_ENCONTRADO},
    ),
)
class PedidoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PedidoSerializer
    filterset_class = PedidoFilter
    ordering_fields = ["creado_en", "total"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # al generar el esquema OpenAPI
            return Pedido.objects.none()
        pedidos = Pedido.objects.prefetch_related("items__producto")
        # Pagar es solo del dueño, aunque sea administrador.
        if self.action != "pagar" and es_administrador(self.request):
            return pedidos
        return pedidos.filter(usuario_id=usuario_id(self.request))

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), EsCliente(), CorreoVerificado()]
        if self.action == "pagar":
            return [IsAuthenticated(), EsCliente()]
        if self.action == "cambiar_estado":
            return [IsAuthenticated(), EsAdministrador()]
        return [IsAuthenticated(), EsDuenoOAdmin()]

    @extend_schema(
        summary="Crear pedido desde el carrito",
        description=(
            "Cliente con correo verificado. Convierte el carrito en pedido en una sola "
            "transacción: valida y descuenta stock, copia nombre y precio de cada producto y la "
            "dirección, calcula subtotal, envío (gratis si el subtotal supera "
            "`ENVIO_GRATIS_DESDE`) y total, y vacía el carrito. El pedido queda `pendiente`."
        ),
        request=CrearPedidoSerializer,
        responses={
            201: PedidoSerializer,
            400: OpenApiResponse(description="Datos inválidos o `carrito_vacio`."),
            **SIN_TOKEN,
            403: OpenApiResponse(description="No es cliente o no ha verificado su correo."),
            **STOCK,
        },
    )
    def create(self, request):
        datos = CrearPedidoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        pedido = servicios.crear_pedido_desde_carrito(
            usuario_id(request),
            dict(datos.validated_data["direccion_envio"]),
            datos.validated_data["metodo_pago"],
        )
        return Response(
            PedidoSerializer(pedido, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Pagar pedido (pago simulado)",
        description=(
            "Solo el cliente dueño. Pasa el pedido de `pendiente` a `pagado` sin cobrar nada; "
            "la respuesta trae `pago_simulado: true`."
        ),
        request=None,
        responses={
            200: PedidoSerializer,
            **SIN_TOKEN,
            403: OpenApiResponse(description="No es cliente."),
            **NO_ENCONTRADO,
            **TRANSICION,
        },
    )
    @action(detail=True, methods=["post"])
    def pagar(self, request, pk=None):
        pedido = servicios.pagar_pedido(self.get_object())
        return Response(PedidoSerializer(pedido, context={"request": request}).data)

    @extend_schema(
        summary="Cambiar estado del pedido",
        description=(
            "Solo administrador. Transiciones válidas: pendiente → pagado → enviado → entregado, "
            "y cancelado desde pendiente o pagado. Al cancelar se devuelve el stock."
        ),
        request=CambiarEstadoSerializer,
        responses={
            200: PedidoSerializer,
            **INVALIDO,
            **SIN_TOKEN,
            403: OpenApiResponse(description="No es administrador."),
            **NO_ENCONTRADO,
            **TRANSICION,
        },
    )
    @action(detail=True, methods=["patch"], url_path="estado")
    def cambiar_estado(self, request, pk=None):
        pedido = self.get_object()
        datos = CambiarEstadoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        pedido = servicios.cambiar_estado(
            pedido, datos.validated_data["estado"], usuario_id(request)
        )
        return Response(PedidoSerializer(pedido, context={"request": request}).data)


class ResumenView(APIView):
    """Números del inicio del panel de administración."""

    permission_classes = [IsAuthenticated, EsAdministrador]

    @extend_schema(
        summary="Resumen para el panel",
        description=(
            "Solo administrador. Pedidos pendientes y pagados por enviar; ventas (pedidos "
            "pagados, enviados o entregados) de hoy, de los últimos 7 días y del mes, contadas "
            "por `pagado_en` (o `creado_en` en los pagados antes de que existiera ese campo); "
            "productos activos con stock bajo (`0 < stock <= umbral`) y agotados, hasta 10 de "
            "cada uno; y los últimos 5 pedidos. Los días son de America/Mexico_City."
        ),
        parameters=[FiltroResumenSerializer],
        responses={
            200: ResumenSerializer,
            **INVALIDO,
            **SIN_TOKEN,
            403: OpenApiResponse(description="El usuario no es administrador."),
        },
        examples=[
            OpenApiExample(
                "Resumen",
                response_only=True,
                value={
                    "fecha": "2026-11-26",
                    "pedidos": {"pendientes": 3, "por_enviar": 2},
                    "ventas": {
                        "hoy": {"total": "1600.00", "pedidos": 1},
                        "ultimos_7_dias": {"total": "5210.00", "pedidos": 4},
                        "mes": {"total": "9870.50", "pedidos": 9},
                        "respaldo": {"pedidos_sin_pagado_en": 2, "primer_pagado_en": "2026-11-26"},
                    },
                    "stock": {
                        "umbral": 5,
                        "bajo": {
                            "total": 1,
                            "productos": [{"slug": "urea-46", "nombre": "Urea 46%", "stock": 3}],
                        },
                        "agotados": {"total": 0, "productos": []},
                    },
                    "ultimos_pedidos": [
                        {
                            "id": 94,
                            "estado": "pendiente",
                            "total": "1600.00",
                            "creado_en": "2026-11-26T10:12:00-06:00",
                            "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
                        }
                    ],
                },
            )
        ],
    )
    def get(self, request):
        filtros = FiltroResumenSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(servicios.resumen(filtros.validated_data["umbral"]))
