"""Crea los índices de MongoDB de svc-contenido. Se puede correr varias veces.

    docker compose exec svc-contenido python manage.py crear_indices

El contenedor lo corre al arrancar, antes del servidor.
"""

from django.core.management.base import BaseCommand

from apps.bitacora import servicios as bitacora
from apps.conversaciones import servicios as conversaciones
from apps.diagnosticos import servicios as diagnosticos
from config import mongo


class Command(BaseCommand):
    help = "Crea los índices de conversaciones, diagnósticos y bitácora (idempotente)."

    def handle(self, *args, **options):
        for modulo in (conversaciones, diagnosticos, bitacora):
            coleccion = mongo.coleccion(modulo.COLECCION)
            for claves in modulo.INDICES:
                nombre = coleccion.create_index(claves)
                self.stdout.write(f"{modulo.COLECCION}: {nombre}")
        self.stdout.write(self.style.SUCCESS("Índices listos."))
