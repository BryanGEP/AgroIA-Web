from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.usuarios.models import CambioRol, Direccion, Usuario


class DireccionInline(admin.TabularInline):
    model = Direccion
    extra = 0


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin de Django para usuarios identificados por correo (sin username)."""

    ordering = ["-date_joined"]
    list_display = ["email", "nombre", "apellidos", "rol", "email_verificado", "is_active"]
    list_filter = ["rol", "email_verificado", "is_active", "is_staff"]
    search_fields = ["email", "nombre", "apellidos"]
    readonly_fields = ["date_joined", "last_login", "acepto_privacidad_en", "version_privacidad"]
    inlines = [DireccionInline]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Datos personales", {"fields": ["nombre", "apellidos", "telefono"]}),
        (
            "Rol y verificación",
            {"fields": ["rol", "email_verificado", "tiene_2fa", "token_version"]},
        ),
        ("Aviso de privacidad", {"fields": ["acepto_privacidad_en", "version_privacidad"]}),
        ("Acceso al admin de Django", {"fields": ["is_active", "is_staff", "is_superuser"]}),
        ("Fechas", {"fields": ["date_joined", "last_login"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "nombre", "password1", "password2"]}),
    ]
    filter_horizontal = []


@admin.register(Direccion)
class DireccionAdmin(admin.ModelAdmin):
    list_display = ["usuario", "alias", "municipio", "estado", "codigo_postal", "predeterminada"]
    list_filter = ["estado", "predeterminada"]
    search_fields = ["usuario__email", "alias", "calle", "colonia", "municipio"]


@admin.register(CambioRol)
class CambioRolAdmin(admin.ModelAdmin):
    """Historial de cambios de rol: solo lectura."""

    list_display = ["usuario", "rol_anterior", "rol_nuevo", "cambiado_por", "cambiado_en"]
    list_filter = ["rol_nuevo"]
    search_fields = ["usuario__email", "cambiado_por__email"]
    readonly_fields = ["usuario", "rol_anterior", "rol_nuevo", "cambiado_por", "cambiado_en"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
