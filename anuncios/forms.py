"""Formulários do painel de anúncios: dados do imóvel, localização e fotos (uma etapa cada).

Limites (caracteres, nº e tamanho de fotos) vêm da Configuracao e aparecem no help_text.
Valores em reais e áreas aceitam o jeito brasileiro de digitar ("420.000,00").
"""

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator
from django.utils import timezone

from anuncios.localizacao import longe_da_cidade
from anuncios.models import DetalheImovel, DetalheVeiculo
from anuncios.services import LADO_MAXIMO_NO_NAVEGADOR
from catalogo import services as catalogo
from catalogo.models import Marca, Modelo, TipoVeiculo, Versao
from core import imagens
from core.models import Bairro, Cidade
from core.services import configuracao


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
        aplicar_limites_de_texto(self, 'Ex.: "Casa 3 quartos com área gourmet".')
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


def aplicar_limites_de_texto(form: forms.Form, exemplo_titulo: str) -> None:
    """Título e descrição com os limites da Configuracao (validação, maxlength e help_text)."""
    config = configuracao()
    form.fields["titulo"].validators += [
        MinLengthValidator(
            config.titulo_min_caracteres,
            message="O título precisa ter pelo menos %(limit_value)d caracteres.",
        ),
        MaxLengthValidator(
            config.titulo_max_caracteres,
            message="O título pode ter no máximo %(limit_value)d caracteres.",
        ),
    ]
    form.fields["titulo"].widget.attrs["maxlength"] = config.titulo_max_caracteres
    form.fields["titulo"].help_text = (
        f"De {config.titulo_min_caracteres} a {config.titulo_max_caracteres} caracteres. " + exemplo_titulo
    )
    form.fields["descricao"].validators.append(
        MaxLengthValidator(
            config.descricao_max_caracteres,
            message="A descrição pode ter no máximo %(limit_value)d caracteres.",
        )
    )
    form.fields["descricao"].widget.attrs["maxlength"] = config.descricao_max_caracteres
    form.fields["descricao"].help_text = (
        f"Até {config.descricao_max_caracteres} caracteres, texto simples. "
        "Não coloque telefone nem link: o contato é pelo botão do WhatsApp."
    )


class CampoInteiro(forms.IntegerField):
    """IntegerField que aceita "98.000" (ponto de milhar)."""

    widget = forms.TextInput

    def to_python(self, value):
        """Converte antes das validações de mínimo e máximo."""
        if value in self.empty_values:
            return None
        valor = ler_valor(value)
        if valor is None or valor != valor.to_integral_value():
            raise ValidationError("Digite um número inteiro, como 98.000.")
        return int(valor)


class ModeloField(forms.ModelChoiceField):
    """Modelo mostrado só pelo nome (a marca já está no select anterior)."""

    def label_from_instance(self, modelo: Modelo) -> str:
        """Ex.: 'Hilux'."""
        return modelo.nome


class VersaoField(forms.ModelChoiceField):
    """Versão mostrada só pelo nome (marca e modelo já estão nos selects anteriores)."""

    def label_from_instance(self, versao: Versao) -> str:
        """Ex.: 'CD SRV 4x4 2.8 Diesel Aut.'."""
        return versao.nome


class DadosVeiculoForm(forms.Form):
    """Etapa 1 do veículo: catálogo FIPE (tipo → marca → modelo → versão), ficha, preço, cidade e texto.

    Os selects do catálogo são encadeados: as opções de cada um dependem do anterior (lidas de
    `self.data` ou do `initial`). Com JavaScript o HTMX troca o bloco ao mudar um select
    (`anuncios:catalogo`); sem JavaScript, o botão "Atualizar listas" reenvia o formulário.
    """

    tipo_veiculo = forms.ChoiceField(label="Tipo", choices=[("", "Escolha…"), *TipoVeiculo.choices])
    marca = forms.ModelChoiceField(label="Marca", queryset=Marca.objects.none(), empty_label="Escolha…")
    modelo = ModeloField(label="Modelo", queryset=Modelo.objects.none(), empty_label="Escolha…")
    versao = VersaoField(label="Versão", queryset=Versao.objects.none(), empty_label="Escolha…")
    ano_fabricacao = forms.IntegerField(label="Ano de fabricação", min_value=1950)
    ano_modelo = forms.IntegerField(label="Ano do modelo", min_value=1950)
    quilometragem = CampoInteiro(label="Quilometragem (km)", min_value=0, max_value=3_000_000)
    combustivel = forms.ChoiceField(label="Combustível", choices=DetalheVeiculo.Combustivel.choices)
    cambio = forms.ChoiceField(label="Câmbio", choices=DetalheVeiculo.Cambio.choices)
    cor = forms.ChoiceField(label="Cor", choices=DetalheVeiculo.Cor.choices)
    portas = forms.TypedChoiceField(
        label="Portas",
        choices=[("", "—"), *DetalheVeiculo.PORTAS],
        coerce=int,
        empty_value=None,
        required=False,
    )
    final_placa = forms.RegexField(
        label="Final da placa",
        regex=r"^\d$",
        required=False,
        max_length=1,
        error_messages={"invalid": "Só o último dígito da placa (0 a 9)."},
        help_text="Opcional: só o último dígito. Nunca a placa inteira.",
    )
    opcionais = forms.MultipleChoiceField(
        label="Opcionais",
        choices=DetalheVeiculo.Opcional.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    preco = CampoValor(label="Preço (R$)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    cidade = forms.ModelChoiceField(label="Cidade", queryset=Cidade.objects.none(), empty_label=None)
    titulo = forms.CharField(label="Título", required=False)
    descricao = forms.CharField(label="Descrição", widget=forms.Textarea(attrs={"rows": 8}), required=False)

    CAMPOS_CATALOGO = ("tipo_veiculo", "marca", "modelo", "versao")
    CAMPOS_ANUNCIO = ("titulo", "descricao", "preco", "cidade")
    CAMPOS_FICHA = (
        "versao",
        "ano_fabricacao",
        "ano_modelo",
        "quilometragem",
        "combustivel",
        "cambio",
        "cor",
        "portas",
        "final_placa",
        "opcionais",
    )

    def __init__(self, *args, **kwargs):
        """Opções encadeadas do catálogo, cidades liberadas, limites de texto e classes do Bootstrap."""
        super().__init__(*args, **kwargs)
        aplicar_limites_de_texto(self, "Deixe em branco para usar marca, modelo, versão e ano.")
        ano_max = timezone.localdate().year + 1
        self.fields["ano_fabricacao"].max_value = ano_max
        self.fields["ano_modelo"].max_value = ano_max + 1
        self.fields["ano_fabricacao"].validators.append(MaxValueValidator(ano_max))
        self.fields["ano_modelo"].validators.append(MaxValueValidator(ano_max + 1))
        self.fields["cidade"].queryset = Cidade.objects.filter(liberada=True, uf__liberado=True).order_by(
            "nome"
        )
        tipo, marca, modelo = (self._valor(campo) for campo in ("tipo_veiculo", "marca", "modelo"))
        self.fields["marca"].queryset = catalogo.marcas_do_tipo(tipo)
        self.fields["modelo"].queryset = catalogo.modelos_da_marca(marca, tipo)
        self.fields["versao"].queryset = catalogo.versoes_do_modelo(modelo)
        for nome, campo in self.fields.items():
            if nome == "opcionais":
                continue
            eh_select = isinstance(campo.widget, forms.Select)
            campo.widget.attrs.setdefault("class", "form-select" if eh_select else "form-control")
        self.fields["preco"].widget.attrs["inputmode"] = "decimal"
        self.fields["quilometragem"].widget.attrs["inputmode"] = "numeric"

    def _valor(self, campo: str) -> str:
        """Valor atual do campo: o enviado (data) ou o inicial (initial), como texto."""
        if self.is_bound:
            return str(self.data.get(self.add_prefix(campo), "") or "")
        valor = self.initial.get(campo, "")
        return str(getattr(valor, "pk", valor) or "")

    def clean(self) -> dict:
        """Coerência do catálogo (versão do modelo, modelo da marca e do tipo) e dos anos."""
        dados = super().clean()
        tipo, marca, modelo, versao = (dados.get(c) for c in self.CAMPOS_CATALOGO)
        if versao and modelo and versao.modelo_id != modelo.pk:
            self.add_error("versao", "Esta versão não é do modelo escolhido.")
        if modelo and (marca and modelo.marca_id != marca.pk or tipo and modelo.tipo != tipo):
            self.add_error("modelo", "Este modelo não é da marca e do tipo escolhidos.")
        fabricacao, ano_modelo = dados.get("ano_fabricacao"), dados.get("ano_modelo")
        if fabricacao and ano_modelo and not (fabricacao <= ano_modelo <= fabricacao + 1):
            self.add_error("ano_modelo", "O ano do modelo é o mesmo da fabricação ou o seguinte.")
        return dados

    def dados_anuncio(self) -> dict:
        """Só os campos do Anuncio."""
        return {campo: self.cleaned_data[campo] for campo in self.CAMPOS_ANUNCIO}

    def dados_ficha(self) -> dict:
        """Só os campos do DetalheVeiculo."""
        return {campo: self.cleaned_data[campo] for campo in self.CAMPOS_FICHA}

    @classmethod
    def inicial(cls, anuncio) -> dict:
        """Valores atuais do anúncio para editar (o catálogo vem da versão gravada)."""
        veiculo = anuncio.veiculo
        modelo = veiculo.versao.modelo
        return {
            **{campo: getattr(anuncio, campo) for campo in cls.CAMPOS_ANUNCIO},
            **{campo: getattr(veiculo, campo) for campo in cls.CAMPOS_FICHA},
            "tipo_veiculo": modelo.tipo,
            "marca": modelo.marca_id,
            "modelo": modelo.pk,
            "versao": veiculo.versao_id,
            "cidade": anuncio.cidade_id,
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
        elif lat is not None and longe_da_cidade(lat, lng, cidade):
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
    """Etapa 3 — fotos: várias de uma vez, cada uma validada (tipo real, tamanho, dimensões mínimas).

    O mínimo aceito é baixo (só recusa ícone/miniatura); foto pequena passa e o painel avisa. Fotos
    grandes do celular são reduzidas no navegador antes do envio (`data-reduzir-fotos`).
    """

    fotos = VariasFotosField(
        label="Adicionar fotos",
        widget=VariosArquivos(
            attrs={
                "accept": "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif",
                "class": "form-control",
                "data-reduzir-fotos": "",  # static/js/reduzir-fotos.js reduz antes de enviar
            }
        ),
        error_messages={"required": "Escolha pelo menos uma foto."},
    )

    def __init__(self, *args, vagas: int = 10, **kwargs):
        """`vagas` = quantas fotos ainda cabem no anúncio."""
        super().__init__(*args, **kwargs)
        self.vagas = vagas
        config = configuracao()
        self.fields["fotos"].widget.attrs["data-lado-maximo"] = LADO_MAXIMO_NO_NAVEGADOR
        self.fields["fotos"].help_text = (
            "Escolha as fotos do celular ou do computador (JPG, PNG, WebP ou HEIC do iPhone): o site "
            "ajusta o tamanho sozinho. Prefira fotos deitadas. "
            f"Até {config.max_fotos_anuncio} fotos (ainda cabem {vagas}), "
            f"até {config.limite_foto_anuncio_kb // 1024} MB cada. "
            "Não fotografe pessoas, documentos nem placas de carro."
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
                    imagens.FORMATOS_FOTO_ANUNCIO,
                )
            except ValidationError as erro:
                erros.append(f"{arquivo.name[:60]}: {' '.join(erro.messages)}")
        if erros:
            raise ValidationError(erros)
        return arquivos
