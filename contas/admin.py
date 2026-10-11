"""Admin do usuário: mesmo comportamento do admin padrão do Django, adaptado ao login por e-mail."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from contas.forms import UsuarioAlteracaoAdminForm, UsuarioCriacaoAdminForm
from contas.models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Lista, busca e edita usuários. Permissões vêm dos grupos (docs/ADMINISTRACAO.md)."""

    form = UsuarioAlteracaoAdminForm
    add_form = UsuarioCriacaoAdminForm

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("nome",)}),
        ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "criado_em")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nome", "usable_password", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("last_login", "criado_em")
    list_display = ("email", "nome", "is_staff", "is_active", "criado_em")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "nome")
    ordering = ("email",)
