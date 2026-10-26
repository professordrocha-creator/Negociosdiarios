"""Formulários do app pagamentos: "Já paguei" (painel), confirmação de pagamento (admin) e, no lote 3B,
escolher plano e conferir os dados, a Configuração do Pix e as datas da aprovação (Cadastros aguardando)."""

from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from anunciantes.validators import normalizar_whatsapp
from core.services import configuracao
from pagamentos import pix
from pagamentos.models import ConfiguracaoPix, Fatura
from planos.forms import PedidoPlanoForm


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


# --- Lote 3B: pedido de plano com Pix ----------------------------------------------------------------


class AssinarForm(PedidoPlanoForm):
    """Escolher plano: plano, periodicidade e a conferência do nome da loja e do WhatsApp (o documento e a
    cidade já foram informados no cadastro e são conferidos pela equipe)."""

    nome_publico = forms.CharField(
        label="Nome da loja",
        max_length=80,
        help_text="Como a loja aparece no site. Até 80 caracteres.",
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": 80}),
    )
    whatsapp = forms.CharField(
        label="WhatsApp",
        max_length=20,
        help_text="Com DDD, ex.: (65) 99999-0000. É por ele que os clientes falam com você.",
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "tel", "autocomplete": "tel"}),
    )

    def clean_whatsapp(self) -> str:
        """WhatsApp em E.164."""
        return normalizar_whatsapp(self.cleaned_data["whatsapp"])


class JaPagueiForm(ComprovanteForm):
    """ "Já paguei" da tela Pagar: comprovante opcional (a equipe confere pelo identificador no extrato)."""

    def __init__(self, *args, **kwargs):
        """Comprovante opcional, com o limite atual no texto de ajuda."""
        super().__init__(*args, **kwargs)
        campo = self.fields["comprovante"]
        campo.required = False
        campo.label = "Comprovante (opcional)"
        campo.help_text = "Ajuda a conferir mais rápido. " + campo.help_text


class ConfiguracaoPixForm(forms.ModelForm):
    """Configuração do Pix no admin: confere o formato da chave e grava a versão normalizada."""

    class Meta:
        model = ConfiguracaoPix
        fields = ("pix_chave", "pix_nome", "pix_cidade", "pix_instrucao")

    def clean_pix_chave(self) -> str:
        """E-mail, CPF, CNPJ, celular (+55) ou chave aleatória; vazio = Pix desligado no site."""
        chave = self.cleaned_data["pix_chave"].strip()
        if not chave:
            return ""
        try:
            return pix.validar_chave(chave)[1]
        except ValueError as erro:
            raise forms.ValidationError(str(erro)) from erro

    def clean(self) -> dict:
        """Com chave, o nome e a cidade do recebedor também são obrigatórios (vão no código Pix)."""
        dados = super().clean()
        if dados.get("pix_chave"):
            for campo in ("pix_nome", "pix_cidade"):
                if not (dados.get(campo) or "").strip():
                    self.add_error(campo, "Obrigatório quando há chave Pix (vai dentro do código Pix).")
        return dados


class AprovarPedidoForm(forms.Form):
    """Tela "Aprovar" de Cadastros aguardando: vigência (sugerida, a equipe ajusta) e observação."""

    inicio = forms.DateField(label="Início da vigência", widget=AdminDateWidget)
    fim = forms.DateField(
        label="Fim da vigência",
        widget=AdminDateWidget,
        help_text="Até este dia (inclusive) a loja publica anúncios novos. Sugestão: início + dias de "
        "vigência do plano.",
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 2, "cols": 60}),
        help_text="Opcional. Ex.: Pix conferido no extrato de 12/10. Sem dados bancários nem CPF.",
    )

    def clean(self) -> dict:
        """O fim vem depois do início."""
        dados = super().clean()
        inicio, fim = dados.get("inicio"), dados.get("fim")
        if inicio and fim and fim <= inicio:
            self.add_error("fim", "O fim da vigência precisa ser depois do início.")
        return dados
