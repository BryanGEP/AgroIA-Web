"""Borra los usuarios que registran las pruebas (Postman, la matriz y los scripts de
verificación). Solo en desarrollo.

    docker compose exec svc-usuarios python manage.py limpiar_datos_prueba
    docker compose exec -T svc-usuarios python manage.py limpiar_datos_prueba --listar-ids

Un usuario de prueba tiene un correo `<palabra>.<timestamp>@example.com`, como los que
registra Postman (`maria.1795210681119@example.com`). Las cuentas de demostración
(`*@demo.agroia.test`) nunca se borran.

`--listar-ids` no borra nada: imprime en una línea los ids de las cuentas de demostración
y de los usuarios de prueba, separados por comas, para pasarlos al mismo comando de
svc-tienda y svc-contenido (`--usuarios`). Esos servicios no leen la base de usuarios, así
que primero se limpian ellos y al final svc-usuarios. Ver «Correr las pruebas de
seguridad» en el README raíz.

Se puede correr varias veces; al final dice cuánto borró.
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.usuarios.management.commands.cargar_usuarios_demo import CUENTAS
from apps.usuarios.models import Usuario

CORREO_DE_PRUEBA = re.compile(r"^[a-z][a-z0-9-]*\.\d{10,}@example\.com$")


def usuarios_de_prueba():
    """Los registrados por las pruebas. Filtra en Python con la expresión completa, no
    solo con el dominio, para no tocar una cuenta real de @example.com."""
    candidatos = Usuario.objects.filter(email__iendswith="@example.com")
    return [u for u in candidatos if CORREO_DE_PRUEBA.match(u.email)]


def cuentas_demo():
    return list(Usuario.objects.filter(email__in=[c["email"] for c in CUENTAS]))


class Command(BaseCommand):
    help = "Borra los usuarios registrados por las pruebas (solo con DJANGO_DEBUG=True)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--listar-ids",
            action="store_true",
            help="No borra: imprime los ids de las cuentas demo y de prueba, separados por comas.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "limpiar_datos_prueba solo corre con DJANGO_DEBUG=True: borra datos y es "
                "solo para desarrollo."
            )
        if options["listar_ids"]:
            ids = [str(u.pk) for u in cuentas_demo() + usuarios_de_prueba()]
            self.stdout.write(",".join(ids))
            return

        with transaction.atomic():
            ids = [u.pk for u in usuarios_de_prueba()]
            # Direcciones y cambios de rol se borran en cascada.
            borrados, _ = Usuario.objects.filter(pk__in=ids).delete()
        self.stdout.write(
            f"Usuarios de prueba borrados: {len(ids)} ({borrados} registros con sus "
            "direcciones y cambios de rol). Cuentas de demostración conservadas."
        )
