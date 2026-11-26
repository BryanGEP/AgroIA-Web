"""Promueve a administrador a un usuario que ya existe.

    docker compose exec svc-usuarios python manage.py asignar_admin <email>

No hay registro de administradores por la API. Para crear uno desde cero, usar
`python manage.py createsuperuser`, que ya lo deja con rol administrador.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.managers import normalizar_email
from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = "Asigna el rol administrador a un usuario existente, por su correo."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Correo del usuario que será administrador.")

    def handle(self, *args, **options):
        email = normalizar_email(options["email"])
        usuario = Usuario.objects.filter(email__iexact=email).first()
        if usuario is None:
            raise CommandError(
                f"No existe ningún usuario con el correo {email}. Regístralo primero con "
                "POST /api/v1/auth/registro/ o crea uno con: python manage.py createsuperuser"
            )
        if usuario.rol == Usuario.Rol.ADMINISTRADOR:
            self.stdout.write(f"{email} ya era administrador.")
            return
        usuario.rol = Usuario.Rol.ADMINISTRADOR
        usuario.save(update_fields=["rol"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{email} ahora es administrador. Necesita un token nuevo para usar el rol."
            )
        )
