import factory

from apps.usuarios.models import Direccion, Usuario

PASSWORD_DE_PRUEBA = "Aguacate-Hass-2026"


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario

    email = factory.Sequence(lambda n: f"usuario{n}@example.com")
    nombre = factory.Sequence(lambda n: f"Usuario {n}")
    apellidos = "Pérez"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Crea con create_user para que la contraseña quede con hash."""
        password = kwargs.pop("password", PASSWORD_DE_PRUEBA)
        return model_class.objects.create_user(*args, password=password, **kwargs)


class DireccionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Direccion

    usuario = factory.SubFactory(UsuarioFactory)
    alias = factory.Sequence(lambda n: f"Dirección {n}")
    calle = "Av. Lázaro Cárdenas"
    numero = "120"
    colonia = "Centro"
    municipio = "Jiquilpan"
    estado = "Michoacán"
    codigo_postal = "59510"
