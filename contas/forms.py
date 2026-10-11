"""Formulários do app contas (por enquanto, só os usados no admin)."""

from django import forms
from django.conf import settings
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


class CodigoAcessoForm(forms.Form):
    """Tela "Confirme que é você" do admin: um campo só, para o código recebido por e-mail."""

    codigo = forms.CharField(
        label="Código",
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "autofocus": True}),
    )

    def __init__(self, *args, **kwargs):
        """Monta o texto de ajuda com a validade configurada (nunca fixa no código)."""
        super().__init__(*args, **kwargs)
        self.fields["codigo"].help_text = (
            f"6 dígitos enviados ao seu e-mail. Vale {settings.ADMIN_CODIGO_MINUTOS} minutos e uma vez só. "
            "Se recebeu um código de emergência do servidor, digite-o aqui."
        )
