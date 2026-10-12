"""Formulários do app pagamentos: "Já paguei" (painel) e confirmação de pagamento (admin)."""

from django import forms

from core.services import configuracao
from pagamentos.models import Fatura


class ComprovanteForm(forms.Form):
    """Envio do comprovante pelo anunciante. A validação do arquivo fica em `services.comprovante_limpo`."""

    comprovante = forms.FileField(
        label="Comprovante",
        widget=forms.ClearableFileInput(
            attrs={"accept": "application/pdf,image/jpeg,image/png,image/webp", "class": "form-control"}
        ),
    )
    recado = forms.CharField(
        label="Recado para a equipe (opcional)",
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": 300}),
        help_text="Até 300 caracteres. Ex.: paguei pelo Pix da conta da empresa.",
    )

    def __init__(self, *args, **kwargs):
        """Texto de ajuda com o limite atual (Configuracao, editável no admin)."""
        super().__init__(*args, **kwargs)
        limite = configuracao().limite_comprovante_kb
        self.fields[
            "comprovante"
        ].help_text = (
            f"PDF do banco ou foto/print do comprovante (JPG, PNG ou WebP), até {limite // 1024} MB."
        )


class ConfirmarPagamentoForm(forms.Form):
    """Tela intermediária da ação "Confirmar pagamento" no admin."""

    forma = forms.ChoiceField(
        label="Forma de pagamento", choices=Fatura.Forma.choices, initial=Fatura.Forma.PIX
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 2, "cols": 60}),
        help_text="Opcional. Ex.: conferido no extrato de 12/10. Fica na fatura e no histórico da assinatura",
    )
