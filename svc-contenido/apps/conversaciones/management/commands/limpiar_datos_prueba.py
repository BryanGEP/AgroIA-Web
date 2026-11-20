"""Borra lo que dejan las pruebas (Postman, la matriz de accesos). Solo en desarrollo.

    docker compose exec svc-contenido python manage.py limpiar_datos_prueba --usuarios <id,id,...>

Borra las conversaciones, los diagnósticos (con su foto en `default_storage`) y los eventos
de bitácora de los usuarios de `--usuarios`: las cuentas de demostración y los usuarios
de prueba. svc-contenido no lee la base de usuarios; esos ids los imprime
`limpiar_datos_prueba --listar-ids` en svc-usuarios.

También borra los eventos de bitácora con `usuario_id` 00000000-0000-0000-0000-00000000000a:
la colección de Postman mandaba `"usuario_id": 10` hasta el cierre de la Entrega 3, y DRF
lo convertía en ese UUID. Hoy manda el id del cliente demo.

No toca nada de otros usuarios ni la base de conocimiento del agente (vive en agente-db).
Se puede correr varias veces; al final dice cuánto borró.
"""

import re
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.bitacora import servicios as bitacora
from apps.conversaciones import servicios as conversaciones
from apps.diagnosticos import servicios as diagnosticos
from config import mongo

ID_EJEMPLO_POSTMAN = str(uuid.UUID(int=10))


def leer_usuarios(texto: str) -> list[str]:
    try:
        return [str(uuid.UUID(parte)) for parte in re.split(r"[,\s]+", texto.strip()) if parte]
    except ValueError as error:
        raise CommandError(f"--usuarios debe ser una lista de UUID: {error}") from error


class Command(BaseCommand):
    help = "Borra conversaciones, diagnósticos y bitácora de prueba (solo con DJANGO_DEBUG=True)."

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
        de_ellos = {"usuario_id": {"$in": usuarios}}

        n_conversaciones = (
            mongo.coleccion(conversaciones.COLECCION).delete_many(de_ellos).deleted_count
        )

        coleccion = mongo.coleccion(diagnosticos.COLECCION)
        n_diagnosticos = n_fotos = 0
        for diagnostico in coleccion.find(de_ellos, {"imagen": 1}):
            # Primero el documento: si falla, la foto sigue teniendo dueño.
            coleccion.delete_one({"_id": diagnostico["_id"]})
            n_diagnosticos += 1
            if diagnostico.get("imagen") and default_storage.exists(diagnostico["imagen"]):
                default_storage.delete(diagnostico["imagen"])
                n_fotos += 1

        n_eventos = (
            mongo.coleccion(bitacora.COLECCION)
            .delete_many({"usuario_id": {"$in": [*usuarios, ID_EJEMPLO_POSTMAN]}})
            .deleted_count
        )

        self.stdout.write(
            f"Conversaciones: {n_conversaciones}. Diagnósticos: {n_diagnosticos} "
            f"({n_fotos} fotos). Eventos de bitácora: {n_eventos} "
            f"(de {len(usuarios)} usuarios demo y de prueba)."
        )
        if not usuarios:
            self.stdout.write(
                self.style.WARNING(
                    "Sin --usuarios solo se borran los eventos de ejemplo de Postman."
                )
            )
