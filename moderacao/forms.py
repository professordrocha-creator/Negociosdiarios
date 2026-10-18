"""Formulários do app moderacao: denúncia pública (com honeypot) e a decisão da equipe no admin."""

from django import forms

from moderacao.models import Denuncia


class DenunciaForm(forms.Form):
    """Denúncia sem login: anúncio (código), motivo, detalhes e e-mail opcionais e um campo-armadilha."""

    anuncio = forms.CharField(
        label="Código do anúncio",
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ND-IM-00012"}),
        help_text="Está na página do anúncio (ex.: ND-IM-00012 ou ND-VE-00034).",
    )
    motivo = forms.ChoiceField(
        label="O que está errado?", choices=Denuncia.Motivo.choices, widget=forms.RadioSelect
    )
    texto = forms.CharField(
        label="Detalhes (opcional)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control", "maxlength": 1000}),
        help_text="Até 1.000 caracteres. Não escreva dados de outras pessoas (CPF, telefone).",
    )
    email = forms.EmailField(
        label="Seu e-mail (opcional)",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
        help_text="Só se quiser retorno. Nunca é mostrado ao anunciante.",
    )
    # Campo-armadilha: invisível para pessoas (CSS), robôs costumam preencher.
    site_empresa = forms.CharField(
        required=False,
        label="Deixe em branco",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    def clean_anuncio(self) -> str:
        """Código em maiúsculas, sem espaços."""
        return self.cleaned_data["anuncio"].strip().upper()


class DecisaoForm(forms.Form):
    """Tela intermediária de "Aceitar" no admin: o que fazer com o anúncio e o motivo (vai ao anunciante)."""

    acao = forms.ChoiceField(
        label="O que fazer com o anúncio",
        choices=[
            ("pausar", "Pausar (o anunciante corrige e reativa)"),
            ("remover", "Remover (sai do ar de vez)"),
        ],
        widget=forms.RadioSelect,
        initial="pausar",
    )
    motivo = forms.CharField(
        label="Motivo",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
        help_text="Vai por e-mail ao anunciante. Não cite quem denunciou.",
    )
