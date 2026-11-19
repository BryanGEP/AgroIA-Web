"""Borra los carritos y pedidos de prueba antes de pasar usuario_id a UUID (0003).

Eran datos de prueba con ids enteros que ya no corresponden a ningún usuario (en la
Entrega 3 el id de svc-usuarios pasó a UUID). El catálogo no se toca. Va en su propia
migración porque PostgreSQL no permite alterar la tabla en la misma transacción en que se
borraron filas con llaves foráneas diferidas.
"""

from django.db import migrations


def borrar_carritos_y_pedidos(apps, schema_editor):
    for modelo in ("ItemCarrito", "Carrito", "ItemPedido", "Pedido"):
        apps.get_model("pedidos", modelo).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(borrar_carritos_y_pedidos, migrations.RunPython.noop),
    ]
