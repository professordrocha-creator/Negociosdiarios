"""Admin do usuário: mesmo comportamento do admin padrão do Django, adaptado ao login por e-mail."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import HttpRequest

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

    def get_readonly_fields(self, request: HttpRequest, obj: Usuario | None = None) -> tuple[str, ...]:
        """Só o superusuário mexe em `is_superuser` e em permissões avulsas.

        Sem isto, alguém do grupo Administrador (que pode editar usuários) poderia
        se dar superusuário e escapar dos grupos (docs/ADMINISTRACAO.md).
        """
        campos = tuple(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return campos
        return (*campos, "is_superuser", "user_permissions")

    def has_change_permission(self, request: HttpRequest, obj: Usuario | None = None) -> bool:
        """Conta de superusuário só é editada por superusuário (inclui a troca de senha dela)."""
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    list_display = ("email", "nome", "is_staff", "is_active", "criado_em")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "nome")
    ordering = ("email",)
