"""Formulários do app contas (por enquanto, só os usados no admin)."""

from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from contas.models import Usuario


class UsuarioCriacaoAdminForm(AdminUserCreationForm):
    """Criação de usuário no admin: e-mail e nome no lugar do username."""

    class Meta:
        model = Usuario
        fields = ("email", "nome")


class UsuarioAlteracaoAdminForm(UserChangeForm):
    """Edição de usuário no admin (a senha só muda pelo formulário próprio do Django)."""

    class Meta:
        model = Usuario
        fields = "__all__"
