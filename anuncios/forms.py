"""Formulários do painel de anúncios: dados do imóvel, localização e fotos (uma etapa cada).

Limites (caracteres, nº e tamanho de fotos) vêm da Configuracao e aparecem no help_text.
Valores em reais e áreas aceitam o jeito brasileiro de digitar ("420.000,00").
"""

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinLengthValidator

from anuncios.models import DetalheImovel
from core import imagens
from core.models import Bairro, Cidade
from core.services import configuracao

# Raio aceito entre o ponto marcado e o centro da cidade (graus; ~0,6° ≈ 65 km): pega clique errado.
DISTANCIA_MAXIMA_GRAUS = 0.6


def ler_valor(texto: str) -> Decimal | None:
    """Converte "R$ 420.000,00", "420000", "1.600" ou "64,5" em Decimal (None se vazio).

    Vírgula é sempre o decimal. Sem vírgula, ponto seguido de 3 dígitos é milhar ("1.600" = 1600).
    """
    texto = re.sub(r"[R$\s]", "", str(texto or ""))
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return Decimal(texto)
    except InvalidOperation as erro:
        raise ValidationError("Digite só números, como 420.000,00.") from erro


class CampoValor(forms.DecimalField):
    """DecimalField que entende o formato brasileiro (ver `ler_valor`)."""

    widget = forms.TextInput

    def to_python(self, value):
        """Converte antes das validações de casas decimais e mínimo."""
        if value in self.empty_values:
            return None
        return ler_valor(value)


class DadosImovelForm(forms.Form):
    """Etapa 1 — dados: título, descrição, preço e a ficha do imóvel."""

    titulo = forms.CharField(label="Título")
    tipo = forms.ChoiceField(label="Tipo de imóvel", choices=DetalheImovel.Tipo.choices)
    modalidade = forms.ChoiceField(
        label="Negócio", choices=DetalheImovel.Modalidade.choices, widget=forms.RadioSelect
    )
    preco = CampoValor(
        label="Preço (R$)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Venda: valor total. Aluguel: valor por mês.",
    )
    quartos = forms.IntegerField(label="Quartos", min_value=0, max_value=50, initial=0)
    banheiros = forms.IntegerField(label="Banheiros", min_value=0, max_value=50, initial=0)
    vagas = forms.IntegerField(label="Vagas de garagem", min_value=0, max_value=100, initial=0)
    area_total = CampoValor(
        label="Área total (m²)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1"),
        help_text="Em metros quadrados. 1 hectare = 10.000 m².",
    )
    area_construida = CampoValor(
        label="Área construída (m²)", max_digits=10, decimal_places=2, required=False
    )
    iptu = CampoValor(label="IPTU por ano (R$)", max_digits=10, decimal_places=2, required=False)
    descricao = forms.CharField(label="Descrição", widget=forms.Textarea(attrs={"rows": 8}), required=False)

    CAMPOS_ANUNCIO = ("titulo", "descricao", "preco")
    CAMPOS_FICHA = (
        "tipo",
        "modalidade",
        "quartos",
        "banheiros",
        "vagas",
        "area_total",
        "area_construida",
        "iptu",
    )

    def __init__(self, *args, **kwargs):
        """Limites de texto da Configuracao (no help_text e no navegador) e classes do Bootstrap."""
        super().__init__(*args, **kwargs)
        config = configuracao()
        self.fields["titulo"].validators += [
            MinLengthValidator(
                config.titulo_min_caracteres,
                message="O título precisa ter pelo menos %(limit_value)d caracteres.",
            ),
            MaxLengthValidator(
                config.titulo_max_caracteres,
                message="O título pode ter no máximo %(limit_value)d caracteres.",
            ),
        ]
        self.fields["titulo"].widget.attrs["maxlength"] = config.titulo_max_caracteres
        self.fields["titulo"].help_text = (
            f"De {config.titulo_min_caracteres} a {config.titulo_max_caracteres} caracteres. "
            'Ex.: "Casa 3 quartos com área gourmet".'
        )
        self.fields["descricao"].validators.append(
            MaxLengthValidator(
                config.descricao_max_caracteres,
                message="A descrição pode ter no máximo %(limit_value)d caracteres.",
            )
        )
        self.fields["descricao"].widget.attrs["maxlength"] = config.descricao_max_caracteres
        self.fields["descricao"].help_text = (
            f"Até {config.descricao_max_caracteres} caracteres, texto simples. "
            "Não coloque telefone nem link: o contato é pelo botão do WhatsApp."
        )
        for nome, campo in self.fields.items():
            if nome == "modalidade":
                continue
            campo.widget.attrs.setdefault("class", "form-select" if nome == "tipo" else "form-control")
        for nome in ("preco", "area_total", "area_construida", "iptu"):
            self.fields[nome].widget.attrs["inputmode"] = "decimal"

    def clean(self) -> dict:
        """Área construída não passa da área total."""
        dados = super().clean()
        total, construida = dados.get("area_total"), dados.get("area_construida")
        if total and construida and construida > total:
            self.add_error("area_construida", "A área construída não pode ser maior que a área total.")
        return dados

    def dados_anuncio(self) -> dict:
        """Só os campos do Anuncio."""
        return {campo: self.cleaned_data[campo] for campo in self.CAMPOS_ANUNCIO}

    def dados_ficha(self) -> dict:
        """Só os campos do DetalheImovel."""
        return {campo: self.cleaned_data[campo] for campo in self.CAMPOS_FICHA}

    @classmethod
    def inicial(cls, anuncio) -> dict:
        """Valores atuais do anúncio para editar."""
        imovel = anuncio.imovel
        return {
            **{campo: getattr(anuncio, campo) for campo in cls.CAMPOS_ANUNCIO},
            **{campo: getattr(imovel, campo) for campo in cls.CAMPOS_FICHA},
        }


class BairroField(forms.ModelChoiceField):
    """Bairro mostrado como "Bairro (Cidade)", agrupado no seletor pela cidade."""

    def label_from_instance(self, bairro: Bairro) -> str:
        """Nome com a cidade, para não confundir bairros homônimos."""
        return f"{bairro.nome} ({bairro.cidade.nome})"


class LocalizacaoForm(forms.Form):
    """Etapa 2 — localização: cidade, bairro, endereço privado, ponto no mapa e o que o público vê."""

    cidade = forms.ModelChoiceField(label="Cidade", queryset=Cidade.objects.none(), empty_label=None)
    bairro = BairroField(
        label="Bairro",
        queryset=Bairro.objects.none(),
        required=False,
        help_text="Não achou o bairro? Fale com a gente para cadastrarmos.",
    )
    endereco = forms.CharField(
        label="Endereço (privado)",
        max_length=200,
        required=False,
        help_text="Nunca aparece no site. Ajuda a equipe a conferir o anúncio.",
    )
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput, min_value=-90, max_value=90)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput, min_value=-180, max_value=180)
    exibir_localizacao = forms.ChoiceField(
        label="O que o visitante vê no mapa",
        choices=DetalheImovel.ExibirLocalizacao.choices,
        widget=forms.RadioSelect,
        initial=DetalheImovel.ExibirLocalizacao.APROXIMADA,
        help_text="Recomendado: aproximada. Exata só se o dono do imóvel concordar.",
    )

    def __init__(self, *args, **kwargs):
        """Só cidades liberadas e bairros ativos delas (CLAUDE.md, regras de telas)."""
        super().__init__(*args, **kwargs)
        self.fields["cidade"].queryset = Cidade.objects.filter(liberada=True, uf__liberado=True).order_by(
            "nome"
        )
        self.fields["bairro"].queryset = (
            Bairro.objects.filter(ativo=True, cidade__liberada=True)
            .select_related("cidade")
            .order_by("cidade__nome", "nome")
        )
        for nome in ("cidade", "bairro"):
            self.fields[nome].widget.attrs["class"] = "form-select"
        self.fields["endereco"].widget.attrs["class"] = "form-control"

    def clean(self) -> dict:
        """Bairro da cidade escolhida; ponto perto da cidade; "só o bairro" exige bairro."""
        dados = super().clean()
        cidade, bairro = dados.get("cidade"), dados.get("bairro")
        if cidade and bairro and bairro.cidade_id != cidade.pk:
            self.add_error("bairro", f"Este bairro não é de {cidade.nome}.")
        lat, lng = dados.get("latitude"), dados.get("longitude")
        if (lat is None) != (lng is None):
            self.add_error(None, "Marque o ponto de novo no mapa.")
        elif lat is not None and cidade and cidade.ponto:
            if (
                abs(lat - cidade.ponto.y) > DISTANCIA_MAXIMA_GRAUS
                or abs(lng - cidade.ponto.x) > DISTANCIA_MAXIMA_GRAUS
            ):
                self.add_error(None, f"O ponto marcado está longe de {cidade.nome}. Confira o mapa.")
        exibir = dados.get("exibir_localizacao")
        if exibir == DetalheImovel.ExibirLocalizacao.SO_BAIRRO and not bairro:
            self.add_error("bairro", 'Para mostrar "só o bairro", escolha o bairro.')
        return dados

    @classmethod
    def inicial(cls, anuncio) -> dict:
        """Valores atuais do anúncio para editar."""
        imovel = anuncio.imovel
        return {
            "cidade": anuncio.cidade_id,
            "bairro": anuncio.bairro_id,
            "endereco": imovel.endereco,
            "latitude": imovel.ponto.y if imovel.ponto else None,
            "longitude": imovel.ponto.x if imovel.ponto else None,
            "exibir_localizacao": imovel.exibir_localizacao,
        }


class VariosArquivos(forms.ClearableFileInput):
    """Campo de arquivo que aceita várias fotos de uma vez."""

    allow_multiple_selected = True


class VariasFotosField(forms.FileField):
    """FileField que valida cada arquivo de uma lista (o FileField do Django aceita só um)."""

    def __init__(self, *args, **kwargs):
        """Usa o widget de vários arquivos."""
        kwargs.setdefault("widget", VariosArquivos())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None) -> list:
        """Lista de arquivos limpos (vazia se nada foi escolhido e o campo não é obrigatório)."""
        limpar = super().clean
        if isinstance(data, list | tuple):
            return [limpar(item, initial) for item in data]
        if data in self.empty_values:
            limpar(data, initial)  # obrigatório: levanta "escolha pelo menos uma foto"
            return []
        return [limpar(data, initial)]


class FotosForm(forms.Form):
    """Etapa 3 — fotos: várias de uma vez, cada uma validada (tipo real, tamanho, dimensões mínimas)."""

    fotos = VariasFotosField(
        label="Adicionar fotos",
        widget=VariosArquivos(attrs={"accept": "image/jpeg,image/png,image/webp", "class": "form-control"}),
        error_messages={"required": "Escolha pelo menos uma foto."},
    )

    def __init__(self, *args, vagas: int = 10, **kwargs):
        """`vagas` = quantas fotos ainda cabem no anúncio."""
        super().__init__(*args, **kwargs)
        self.vagas = vagas
        config = configuracao()
        self.fields["fotos"].help_text = (
            f"JPG, PNG ou WebP, até {config.limite_foto_anuncio_kb // 1024} MB cada, mínimo "
            f"{config.foto_min_largura_px}×{config.foto_min_altura_px} px; ideal 1600×1200 (deitada). "
            f"Até {config.max_fotos_anuncio} fotos (ainda cabem {vagas}). Não fotografe pessoas, documentos "
            "nem placas de carro."
        )

    def clean_fotos(self) -> list:
        """Valida cada arquivo e o total; devolve a lista."""
        arquivos = self.cleaned_data.get("fotos") or []
        if not arquivos:
            raise ValidationError("Escolha pelo menos uma foto.")
        if len(arquivos) > self.vagas:
            raise ValidationError(f"Ainda cabem {self.vagas} foto(s) neste anúncio. Escolha menos.")
        config = configuracao()
        erros = []
        for arquivo in arquivos:
            try:
                imagens.validar_foto(
                    arquivo,
                    config.limite_foto_anuncio_kb,
                    config.foto_min_largura_px,
                    config.foto_min_altura_px,
                )
            except ValidationError as erro:
                erros.append(f"{arquivo.name[:60]}: {' '.join(erro.messages)}")
        if erros:
            raise ValidationError(erros)
        return arquivos
