import django_filters

from agroia_comun.filtros import FechaDesde, FechaHasta
from apps.pedidos.models import Pedido


class PedidoFilter(django_filters.FilterSet):
    estado = django_filters.ChoiceFilter(choices=Pedido.Estado.choices)
    id = django_filters.NumberFilter(field_name="id", help_text="Número de pedido exacto.")
    usuario_id = django_filters.UUIDFilter(help_text="Pedidos de un usuario (solo administrador).")
    desde = FechaDesde(field_name="creado_en", help_text="AAAA-MM-DD, inclusive (hora de México).")
    hasta = FechaHasta(field_name="creado_en", help_text="AAAA-MM-DD, inclusive (hora de México).")

    class Meta:
        model = Pedido
        fields = ["estado", "id", "usuario_id", "desde", "hasta"]
