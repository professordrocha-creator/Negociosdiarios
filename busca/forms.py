"""Formulários de filtro da busca (GET). Um valor inválido na URL é ignorado, nunca dá erro na tela.

A ordem dos campos é a ordem dos parâmetros na URL canônica (`Filtros.querystring`). Opções que
dependem dos anúncios no ar (bairros, marcas, modelos) vêm prontas de `busca.services`.
"""

from __future__ import annotations

from django import forms

from anuncios.forms import CampoInteiro, CampoValor
from anuncios.models import DetalheImovel, DetalheVeiculo
from catalogo.models import TipoVeiculo

ORDENS = [("recentes", "Mais recentes"), ("menor_preco", "Menor preço"), ("maior_preco", "Maior preço")]
MINIMOS = [("", "Qualquer"), ("1", "1+"), ("2", "2+"), ("3", "3+"), ("4", "4+")]

# Parâmetros que não mudam o conteúdo (ficam fora do canonical) e o de texto (sempre noindex).
SO_APRESENTACAO = {"ordem", "pagina"}


class VariasEscolhas(forms.MultipleChoiceField):
    """Várias escolhas em que um valor desconhecido na URL é só descartado (os outros valem)."""

    def clean(self, value) -> list[str]:
        """Mantém só os valores válidos, sem repetir."""
        validos = {str(chave) for chave, _ in self.choices}
        vistos: list[str] = []
        for item in value or []:
            if str(item) in validos and str(item) not in vistos:
                vistos.append(str(item))
        return vistos


class CampoArea(forms.CharField):
    """Retângulo do mapa ("Buscar nesta área"): "oeste,sul,leste,norte" em graus, 5 casas (~1 m)."""

    def clean(self, value) -> str:
        """Vazio ou um retângulo válido (coordenadas no lugar e com tamanho); senão, inválido."""
        value = super().clean(value)
        if not value:
            return ""
        try:
            oeste, sul, leste, norte = (float(v) for v in value.split(","))
        except ValueError as erro:
            raise forms.ValidationError("Área do mapa inválida.") from erro
        if not (-180 <= oeste < leste <= 180 and -90 <= sul < norte <= 90):
            raise forms.ValidationError("Área do mapa inválida.")
        return ",".join(f"{v:.5f}" for v in (oeste, sul, leste, norte))


class FiltrosBase(forms.Form):
    """Campos comuns: texto, preço, área do mapa, ordem, página. Tudo opcional."""

    q = forms.CharField(label="Buscar", required=False, max_length=100)
    preco_min = CampoValor(label="Preço mínimo", required=False, max_digits=12, decimal_places=2, min_value=0)
    preco_max = CampoValor(label="Preço máximo", required=False, max_digits=12, decimal_places=2, min_value=0)
    area = CampoArea(required=False, max_length=80, widget=forms.HiddenInput)
    ordem = forms.ChoiceField(label="Ordenar", choices=ORDENS, required=False)
    pagina = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, opcoes: dict | None = None, **kwargs):
        """`opcoes`: escolhas que dependem do banco ({"bairro": [...], "marca": [...], "modelo": [...]})."""
        super().__init__(*args, **kwargs)
        for nome, escolhas in (opcoes or {}).items():
            if nome in self.fields:
                self.fields[nome].choices = [("", "Todos")] + list(escolhas)
        for nome, rotulo in (("preco_min", "Mín."), ("preco_max", "Máx.")):
            self.fields[nome].widget.attrs.update(
                {
                    "inputmode": "numeric",
                    "placeholder": rotulo,
                    "class": "form-control",
                    "aria-label": self.fields[nome].label,
                }
            )

    def filtros(self) -> dict:
        """Só os valores válidos e preenchidos, na ordem dos campos (o resto é ignorado)."""
        self.is_valid()
        limpos = getattr(self, "cleaned_data", {})
        resultado = {}
        for nome in self.fields:
            if nome in self.errors:
                continue
            valor = limpos.get(nome)
            if valor in (None, "", [], ()):
                continue
            if nome == "q":
                valor = " ".join(valor.split())
                if not valor:
                    continue
            resultado[nome] = valor
        if resultado.get("ordem") == "recentes":
            resultado.pop("ordem")  # padrão: não vai para a URL
        if resultado.get("pagina") == 1:
            resultado.pop("pagina")
        return resultado


class FiltrosImovel(FiltrosBase):
    """Imóvel: negócio, tipo, bairro, preço, quartos, vagas e área."""

    field_order = [
        "q",
        "modalidade",
        "tipo",
        "bairro",
        "preco_min",
        "preco_max",
        "quartos",
        "vagas",
        "area_min",
        "area_max",
        "area",
        "ordem",
        "pagina",
    ]

    modalidade = forms.ChoiceField(
        label="Negócio", choices=[("", "Todos"), *DetalheImovel.Modalidade.choices], required=False
    )
    tipo = VariasEscolhas(label="Tipo", choices=DetalheImovel.Tipo.choices, required=False)
    bairro = forms.ChoiceField(label="Bairro", choices=[("", "Todos")], required=False)
    quartos = forms.ChoiceField(label="Quartos", choices=MINIMOS, required=False)
    vagas = forms.ChoiceField(label="Vagas", choices=MINIMOS, required=False)
    area_min = CampoValor(
        label="Área mínima (m²)", required=False, max_digits=12, decimal_places=2, min_value=0
    )
    area_max = CampoValor(
        label="Área máxima (m²)", required=False, max_digits=12, decimal_places=2, min_value=0
    )


class FiltrosVeiculo(FiltrosBase):
    """Veículo: tipo, marca, modelo, ano, preço, km, câmbio e combustível."""

    field_order = [
        "q",
        "tipo",
        "marca",
        "modelo",
        "ano_min",
        "ano_max",
        "preco_min",
        "preco_max",
        "km_max",
        "cambio",
        "combustivel",
        "area",
        "ordem",
        "pagina",
    ]

    tipo = VariasEscolhas(label="Tipo", choices=TipoVeiculo.choices, required=False)
    marca = forms.ChoiceField(label="Marca", choices=[("", "Todas")], required=False)
    modelo = forms.ChoiceField(label="Modelo", choices=[("", "Todos")], required=False)
    ano_min = forms.IntegerField(label="Ano de", required=False, min_value=1950, max_value=2100)
    ano_max = forms.IntegerField(label="Ano até", required=False, min_value=1950, max_value=2100)
    km_max = CampoInteiro(label="Km até", required=False, min_value=0)
    cambio = VariasEscolhas(label="Câmbio", choices=DetalheVeiculo.Cambio.choices, required=False)
    combustivel = VariasEscolhas(
        label="Combustível", choices=DetalheVeiculo.Combustivel.choices, required=False
    )


FORMULARIOS = {"imoveis": FiltrosImovel, "veiculos": FiltrosVeiculo}
