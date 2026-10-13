"""Formulários do app privacidade: aceite da versão nova, senha de novo e a confirmação da exclusão."""

from django import forms

PALAVRA_DE_CONFIRMACAO = "EXCLUIR"


class AceiteForm(forms.Form):
    """Aceite das versões novas dos documentos (caixa sem marcação prévia)."""

    aceito = forms.BooleanField(
        label="Li e aceito as versões atualizadas",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={
            "required": "Para continuar usando o painel, é preciso aceitar as versões atualizadas."
        },
    )


class SenhaForm(forms.Form):
    """Pede a senha de novo antes de uma ação sensível (baixar os dados, excluir a conta)."""

    senha = forms.CharField(
        label="Sua senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
        help_text="Por segurança, confirme que é você.",
    )

    def __init__(self, *args, usuario=None, **kwargs):
        """`usuario` = quem está logado (a senha é conferida contra ele)."""
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_senha(self) -> str:
        """Senha certa da conta logada."""
        senha = self.cleaned_data["senha"]
        if not self.usuario or not self.usuario.check_password(senha):
            raise forms.ValidationError("Senha incorreta.")
        return senha


class ExcluirContaForm(SenhaForm):
    """Exclusão da conta: senha e a palavra EXCLUIR digitada (para não acontecer por engano)."""

    confirmacao = forms.CharField(
        label=f'Digite "{PALAVRA_DE_CONFIRMACAO}" para confirmar',
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        help_text="A exclusão não pode ser desfeita.",
    )

    def clean_confirmacao(self) -> str:
        """Só a palavra exata (sem diferença de maiúsculas e espaços nas pontas)."""
        valor = self.cleaned_data["confirmacao"].strip()
        if valor.upper() != PALAVRA_DE_CONFIRMACAO:
            raise forms.ValidationError(f"Digite {PALAVRA_DE_CONFIRMACAO} para confirmar.")
        return valor
