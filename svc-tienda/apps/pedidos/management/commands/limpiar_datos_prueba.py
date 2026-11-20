"""Borra los datos que dejan las pruebas (Postman, la matriz de accesos). Solo en desarrollo.

    docker compose exec svc-tienda python manage.py limpiar_datos_prueba --usuarios <id,id,...>

Borra:
- Los productos y categorías que crean las pruebas: slug con sufijo de timestamp
  (`fosfito-de-potasio-1-l-1795210684`, `herbicidas-1795210684`, de Postman) o de la matriz
  (`matriz-<8 hexadecimales>`). Antes, los pedidos y carritos que los contengan.
- Los pedidos y carritos de los usuarios de `--usuarios`: las cuentas de demostración y los
  usuarios de prueba. svc-tienda no lee la base de usuarios; esos ids los imprime
  `limpiar_datos_prueba --listar-ids` en svc-usuarios.

Nunca toca el catálogo de demostración (los slugs de `cargar_datos_demo`). El stock que
gastaron las compras de prueba lo restablece `cargar_datos_demo`.

Se puede correr varias veces; al final dice cuánto borró.
"""

import re
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.catalogo.management.commands.cargar_datos_demo import CATEGORIAS, PRODUCTOS
from apps.catalogo.models import Categoria, Producto
from apps.pedidos.models import Carrito, ItemCarrito, Pedido

SLUG_DE_PRUEBA = re.compile(r"(-\d{10,}|^matriz-[0-9a-f]{8})$")
SLUGS_DEMO = {c[0] for c in CATEGORIAS} | {p[0] for p in PRODUCTOS}


def de_prueba(modelo) -> list[int]:
    """Ids con slug de prueba. Filtra en Python con la expresión completa."""
    filas = modelo.objects.filter(Q(slug__regex=r"-[0-9]{10,}$") | Q(slug__startswith="matriz-"))
    return [f.pk for f in filas if SLUG_DE_PRUEBA.search(f.slug) and f.slug not in SLUGS_DEMO]


def leer_usuarios(texto: str) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(parte) for parte in re.split(r"[,\s]+", texto.strip()) if parte]
    except ValueError as error:
        raise CommandError(f"--usuarios debe ser una lista de UUID: {error}") from error


class Command(BaseCommand):
    help = "Borra productos, categorías, pedidos y carritos de prueba (solo con DJANGO_DEBUG=True)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--usuarios",
            default="",
            help="Ids de las cuentas demo y de prueba, separados por comas "
            "(los da `limpiar_datos_prueba --listar-ids` en svc-usuarios).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "limpiar_datos_prueba solo corre con DJANGO_DEBUG=True: borra datos y es "
                "solo para desarrollo."
            )
        usuarios = leer_usuarios(options["usuarios"])
        with transaction.atomic():
            productos = de_prueba(Producto)
            pedidos_con_productos = Pedido.objects.filter(items__producto__in=productos)
            pedidos = Pedido.objects.filter(
                Q(usuario_id__in=usuarios) | Q(pk__in=pedidos_con_productos)
            ).distinct()
            n_pedidos = pedidos.count()
            Pedido.objects.filter(pk__in=list(pedidos.values_list("pk", flat=True))).delete()
            ItemCarrito.objects.filter(producto__in=productos).delete()
            carritos = Carrito.objects.filter(usuario_id__in=usuarios)
            n_carritos = carritos.count()
            carritos.delete()
            Producto.objects.filter(pk__in=productos).delete()
            n_productos = len(productos)
            # Una categoría de prueba con productos que no son de prueba se queda.
            vacias = Categoria.objects.filter(pk__in=de_prueba(Categoria), productos__isnull=True)
            n_categorias = vacias.count()
            vacias.delete()

        self.stdout.write(
            f"Productos de prueba: {n_productos}. Categorías de prueba: {n_categorias}. "
            f"Pedidos: {n_pedidos}. Carritos: {n_carritos} "
            f"(de {len(usuarios)} usuarios demo y de prueba). Catálogo de demostración conservado."
        )
        if not usuarios:
            self.stdout.write(
                self.style.WARNING(
                    "Sin --usuarios no se borraron pedidos ni carritos de las cuentas de prueba."
                )
            )
