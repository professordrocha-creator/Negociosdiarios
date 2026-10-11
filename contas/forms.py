"""Formulários do app contas (por enquanto, só os usados no admin)."""

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AdminUserCreationForm, AuthenticationForm, UserChangeForm

from anunciantes.services import MENSAGENS_SEM_ACESSO, motivo_sem_painel
from contas.models import Usuario


class EntrarForm(AuthenticationForm):
    """Login do cliente em /entrar/: e-mail e senha, só para anunciante ativo (nunca equipe).

    A senha é conferida primeiro (com o bloqueio do django-axes); só depois vem a regra de
    quem pode entrar, com uma mensagem que diz o que fazer.
    """

    def __init__(self, *args, **kwargs):
        """Rótulos e atributos de navegador (preenchimento automático) dos campos."""
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "email", "inputmode": "email", "autofocus": True}
        )
        self.fields["password"].label = "Senha"
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "current-password"}
        )

    def confirm_login_allowed(self, user) -> None:
        """Recusa equipe, quem não tem loja e loja pendente ou suspensa."""
        super().confirm_login_allowed(user)
        motivo = motivo_sem_painel(user)
        if motivo:
            raise forms.ValidationError(MENSAGENS_SEM_ACESSO[motivo], code=motivo)


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
