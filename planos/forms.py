"""Formulários do app planos."""

from django import forms

from planos.models import Periodicidade, Plano


class PedidoPlanoForm(forms.Form):
    """Painel › Meu plano: escolher o plano e a periodicidade (o pedido vai para a equipe)."""

    plano = forms.ModelChoiceField(
        label="Plano", queryset=Plano.objects.none(), widget=forms.RadioSelect, empty_label=None
    )
    periodicidade = forms.ChoiceField(
        label="Pagamento",
        choices=Periodicidade.choices,
        widget=forms.RadioSelect,
        initial=Periodicidade.MENSAL,
    )

    def __init__(self, *args, planos=None, **kwargs):
        """Só planos à venda."""
        super().__init__(*args, **kwargs)
        self.fields["plano"].queryset = planos if planos is not None else Plano.objects.filter(ativo=True)
