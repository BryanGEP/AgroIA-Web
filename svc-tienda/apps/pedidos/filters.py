import django_filters

from apps.pedidos.models import Pedido


class PedidoFilter(django_filters.FilterSet):
    estado = django_filters.ChoiceFilter(choices=Pedido.Estado.choices)

    class Meta:
        model = Pedido
        fields = ["estado"]
