"""Crea las cuentas de demostración que usa la colección de Postman. Solo en desarrollo.

    docker compose exec svc-usuarios python manage.py cargar_usuarios_demo

Las tres cuentas comparten la contraseña CONTRASENA_DEMO, que está en el repositorio a
propósito (docs/postman/AgroIA-Web.postman_environment.json). Por eso el comando se niega
a correr con DJANGO_DEBUG=False: estas cuentas nunca deben existir fuera de desarrollo.
Es idempotente: si ya existen, vuelve a dejar su rol, verificación y contraseña.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.usuarios.models import Usuario

CONTRASENA_DEMO = "solo-demo-no-usar-en-produccion"

CUENTAS = [
    {
        "email": "cliente@demo.agroia.test",
        "nombre": "Cliente Demo",
        "rol": "cliente",
        "email_verificado": True,
    },
    {
        "email": "sin-verificar@demo.agroia.test",
        "nombre": "Cliente Sin Verificar",
        "rol": "cliente",
        "email_verificado": False,
    },
    {
        "email": "admin@demo.agroia.test",
        "nombre": "Admin Demo",
        "rol": "administrador",
        "email_verificado": True,
    },
]


class Command(BaseCommand):
    help = "Crea las cuentas de demostración de Postman (solo con DJANGO_DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "cargar_usuarios_demo solo corre con DJANGO_DEBUG=True: sus cuentas tienen una "
                "contraseña pública y no deben existir fuera de desarrollo."
            )
        with transaction.atomic():
            for datos in CUENTAS:
                usuario = Usuario.objects.filter(email=datos["email"]).first()
                creado = usuario is None
                if creado:
                    usuario = Usuario.objects.create_user(
                        email=datos["email"], password=CONTRASENA_DEMO, nombre=datos["nombre"]
                    )
                else:
                    usuario.set_password(CONTRASENA_DEMO)
                usuario.nombre = datos["nombre"]
                usuario.rol = datos["rol"]
                usuario.email_verificado = datos["email_verificado"]
                usuario.is_active = True
                usuario.tiene_2fa = False
                usuario.save()
                accion = "creada" if creado else "actualizada"
                self.stdout.write(f"{datos['email']} ({datos['rol']}): {accion}")
        self.stdout.write(
            self.style.WARNING(
                "Cuentas de demostración listas. No deben existir fuera de desarrollo."
            )
        )
