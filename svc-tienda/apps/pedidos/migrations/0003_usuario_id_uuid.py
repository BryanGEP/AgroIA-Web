"""usuario_id pasa de entero a UUID (Entrega 3: el id de svc-usuarios ahora es UUID).

La 0002 ya borró los carritos y pedidos de prueba. PostgreSQL no puede convertir bigint a uuid con ALTER COLUMN, por eso la columna se quita
y se vuelve a crear.
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0002_borrar_carritos_y_pedidos"),
    ]

    operations = [
        migrations.RemoveIndex(model_name="pedido", name="pedido_usuario_fecha"),
        migrations.RemoveField(model_name="carrito", name="usuario_id"),
        migrations.RemoveField(model_name="pedido", name="usuario_id"),
        migrations.AddField(
            model_name="carrito",
            name="usuario_id",
            field=models.UUIDField(default=uuid.uuid4, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pedido",
            name="usuario_id",
            field=models.UUIDField(default=uuid.uuid4),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="pedido",
            index=models.Index(fields=["usuario_id", "-creado_en"], name="pedido_usuario_fecha"),
        ),
    ]
