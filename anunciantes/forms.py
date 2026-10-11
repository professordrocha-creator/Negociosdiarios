"""Formulários do app anunciantes."""

from django import forms


class MotivoStatusForm(forms.Form):
    """Motivo da aprovação/suspensão no admin (fica no cadastro e no histórico)."""

    motivo = forms.CharField(
        label="Motivo",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
        help_text="Até 500 caracteres. Fica registrado no cadastro e no histórico do anunciante.",
    )

    def __init__(self, *args, obrigatorio: bool = True, **kwargs):
        """Na suspensão o motivo é obrigatório; na aprovação, opcional ("Documento conferido.")."""
        super().__init__(*args, **kwargs)
        self.fields["motivo"].required = obrigatorio
