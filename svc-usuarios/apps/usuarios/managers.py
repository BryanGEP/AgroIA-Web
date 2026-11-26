from django.contrib.auth.base_user import BaseUserManager


def normalizar_email(email: str) -> str:
    """Quita espacios y pasa todo el correo a minúsculas."""
    return email.strip().lower()


class UsuarioManager(BaseUserManager):
    """Usuarios identificados por correo (no hay `username`)."""

    use_in_migrations = True

    def _crear(self, email: str, password: str | None, **campos):
        if not email:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(email=normalizar_email(email), **campos)
        usuario.set_password(password)  # hash; con None queda sin contraseña utilizable
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email: str, password: str | None = None, **campos):
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        campos.setdefault("rol", "cliente")
        return self._crear(email, password, **campos)

    def create_superuser(self, email: str, password: str | None = None, **campos):
        campos.setdefault("is_staff", True)
        campos.setdefault("is_superuser", True)
        campos.setdefault("rol", "administrador")
        campos.setdefault("email_verificado", True)
        if campos["is_staff"] is not True or campos["is_superuser"] is not True:
            raise ValueError("Un superusuario necesita is_staff=True e is_superuser=True.")
        return self._crear(email, password, **campos)
