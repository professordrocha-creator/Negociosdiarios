"""Formulários do app guia: cadastro assistido no admin (celular), aceite público e aceite em papel.

Validação de formato aqui; regras (máximo de categorias, regulamentada sem frase, CPF só em resumo) vêm de
`guia/services.py`. Todo campo tem help_text; limites vêm da `ConfiguracaoGuia`/`Configuracao`.
"""

from django import forms
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from anunciantes.validators import normalizar_cnpj, normalizar_whatsapp
from anuncios.localizacao import longe_da_cidade
from core.models import Bairro, Cidade
from guia import services
from guia.models import CategoriaServico, ContatoConvite, GrupoCategoria, PerfilGuia


class MapaPonto(forms.HiddenInput):
    """Campo escondido da latitude com o mapa ao lado (static/js/mapa-ponto.js, Leaflet servido pelo site).

    Não conta como "escondido" para o admin, senão a linha inteira (com o mapa) some da tela.
    """

    template_name = (
        "guia/widgets/mapa_ponto.html"  # na pasta do app: o renderizador de formulários não lê templates/
    )

    @property
    def is_hidden(self) -> bool:
        """Mostra a linha (o mapa) no admin."""
        return False


def _horario(dia: str) -> forms.CharField:
    """Campo de horário de um dia da semana."""
    return forms.CharField(
        label=dia,
        required=False,
        max_length=60,
        help_text="Ex.: 8:00-12:00, 14:00-18:00. Em branco = fechado (ou sem horário cadastrado).",
    )


class PerfilGuiaAdminForm(forms.ModelForm):
    """Cadastro assistido: o que a equipe preenche no celular. Documento e responsável são privados."""

    # Declarados (e não gerados pelo admin): select simples, que o mapa acompanha, e lista só do que vale.
    categorias = forms.ModelMultipleChoiceField(
        queryset=CategoriaServico.objects.none(),
        label="Categorias",
        required=False,  # rascunho pode ficar sem; publicar exige ao menos 1 (services.pendencias)
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    cidade = forms.ModelChoiceField(
        queryset=Cidade.objects.none(), label="Cidade", help_text="Só as cidades liberadas no site."
    )
    bairro = forms.ModelChoiceField(
        queryset=Bairro.objects.none(),
        label="Bairro",
        required=False,
        help_text="Opcional. Só bairros da cidade escolhida.",
    )
    # Aceitam pontuação (o banco guarda só dígitos / E.164): limite maior que o da coluna.
    cnpj = forms.CharField(
        label="CNPJ",
        required=False,
        max_length=18,
        help_text="Empresa: obrigatório, pontuação opcional. Nunca aparece no site.",
    )
    whatsapp = forms.CharField(
        label="WhatsApp",
        required=False,
        max_length=20,
        help_text="Com DDD, ex.: (65) 99999-0000. O número não aparece em texto no site: só o botão.",
    )
    telefone = forms.CharField(
        label="Telefone",
        required=False,
        max_length=20,
        help_text="Opcional, com DDD. Precisa de WhatsApp ou telefone para publicar.",
    )
    cpf = forms.CharField(
        label="CPF do autônomo",
        required=False,
        max_length=14,
        help_text="Só para autônomo, opcional. Não é guardado: fica só um resumo (acha cadastro repetido) "
        "e os 2 últimos dígitos. Em branco = mantém o que já estava.",
    )
    latitude = forms.FloatField(
        required=False, min_value=-90, max_value=90, label="Ponto no mapa", widget=MapaPonto
    )
    longitude = forms.FloatField(required=False, min_value=-180, max_value=180, widget=forms.HiddenInput)
    logo_envio = forms.FileField(
        label="Logo",
        required=False,
        help_text="Opcional. JPG, PNG, WebP ou HEIC; recortada em quadrado pelo centro, sem os dados da foto "
        "(GPS). Não aparece em profissão regulamentada.",
    )
    horario_seg = _horario("Segunda")
    horario_ter = _horario("Terça")
    horario_qua = _horario("Quarta")
    horario_qui = _horario("Quinta")
    horario_sex = _horario("Sexta")
    horario_sab = _horario("Sábado")
    horario_dom = _horario("Domingo")

    class Meta:
        model = PerfilGuia
        fields = [
            "tipo",
            "nome_publico",
            "categorias",
            "frase",
            "whatsapp",
            "telefone",
            "cidade",
            "bairro",
            "atendimento",
            "endereco",
            "area_atendimento",
            "cnpj",
            "cnpj_verificado_em",
            "registro_profissional",
            "responsavel_nome",
            "responsavel_contato",
            "anunciante",
            "anotacoes",
        ]
        widgets = {
            "atendimento": forms.RadioSelect,
            "tipo": forms.RadioSelect,
            "anotacoes": forms.Textarea(attrs={"rows": 3}),
            "frase": forms.TextInput,
        }
        help_texts = {
            "tipo": "Empresa tem CNPJ. Profissional regulamentado (CRM, OAB, CRC...) tem ficha restrita.",
            "nome_publico": "Como o cliente conhece o negócio. Até 120 caracteres.",
            "atendimento": 'Quem atende em casa ou na casa do cliente usa "a domicílio" '
            "(o endereço nunca aparece).",
            "endereco": "Endereço COMERCIAL (rua, número). Nunca o endereço de casa.",
            "area_atendimento": 'Para quem atende a domicílio, ex.: "Tangará da Serra e região". '
            "Até 160 caracteres.",
            "cnpj_verificado_em": "Data em que a equipe conferiu a situação ATIVA na Receita. "
            "Preenchida, a ficha "
            'mostra o selo "CNPJ verificado".',
            "registro_profissional": 'Regulamentado: aparece na ficha, ex.: "CRM-MT 1234".',
            "responsavel_nome": "Quem autoriza a publicação. Privado.",
            "responsavel_contato": "E-mail ou telefone de quem autoriza (e-mail recebe a confirmação). "
            "Privado.",
            "anunciante": "Opcional: se a mesma empresa também anuncia imóveis ou veículos no site.",
            "anotacoes": "Só para a equipe. Não escreva CPF nem dados que a ficha não usa.",
        }

    def __init__(self, *args, **kwargs):
        """Só cidades liberadas e categorias ativas (com as já escolhidas), categorias por grupo e valores
        iniciais do mapa, dos horários e do final do CPF."""
        super().__init__(*args, **kwargs)
        config = services.configuracao_guia()
        instancia = self.instance
        cidades = Cidade.objects.filter(liberada=True, uf__liberado=True)
        if instancia.cidade_id:
            cidades = cidades | Cidade.objects.filter(pk=instancia.cidade_id)
        self.fields["cidade"].queryset = cidades.select_related("uf").distinct().order_by("nome")
        self.fields["bairro"].queryset = Bairro.objects.filter(ativo=True, cidade__in=cidades).select_related(
            "cidade"
        )
        categorias = CategoriaServico.objects.filter(ativa=True)
        if instancia.pk:
            categorias = categorias | instancia.categorias.all()
        categorias = categorias.select_related("grupo").distinct()
        self.fields["categorias"].queryset = categorias
        self.fields["categorias"].help_text = (
            f"Até {config.max_categorias}. No celular, toque para abrir a lista; no computador, Ctrl+clique "
            "marca mais de uma. Categoria com * é regulamentada."
        )
        self.fields["categorias"].widget.choices = [
            (
                grupo.nome,
                [
                    (c.pk, f"{c.nome}{' *' if c.regulamentada else ''}")
                    for c in categorias
                    if c.grupo_id == grupo.pk
                ],
            )
            for grupo in GrupoCategoria.objects.filter(pk__in={c.grupo_id for c in categorias})
        ]
        frase = self.fields["frase"]
        frase.widget.attrs["maxlength"] = config.limite_frase  # o limite em si é validado por erro_da_frase
        frase.help_text = (
            f"Até {config.limite_frase} caracteres, texto puro (sem links). "
            "Profissão regulamentada não tem frase."
        )
        if instancia.ponto is not None:
            self.initial["latitude"], self.initial["longitude"] = instancia.ponto.y, instancia.ponto.x
        for chave, _ in services.DIAS_DA_SEMANA:
            self.initial[f"horario_{chave}"] = services.formatar_horario(
                (instancia.horarios or {}).get(chave)
            )
        if instancia.cpf_final:
            self.fields["cpf"].widget.attrs["placeholder"] = (
                f"já informado: ***.***.***-{instancia.cpf_final}"
            )

    def clean_whatsapp(self) -> str:
        """E.164 (+55...)."""
        valor = self.cleaned_data["whatsapp"]
        return normalizar_whatsapp(valor) if valor else ""

    def clean_telefone(self) -> str:
        """E.164 (+55...), fixo ou celular."""
        valor = self.cleaned_data["telefone"]
        if not valor:
            return ""
        try:
            return normalizar_whatsapp(valor)
        except ValidationError as erro:
            raise ValidationError("Telefone inválido. Informe DDD e número, ex.: (65) 3333-0000.") from erro

    def clean_cnpj(self) -> str:
        """Só dígitos, validado."""
        valor = self.cleaned_data["cnpj"]
        return normalizar_cnpj(valor) if valor else ""

    def clean_cpf(self) -> str:
        """Só dígitos, validado (vira resumo no `save`)."""
        valor = self.cleaned_data["cpf"]
        return services.normalizar_cpf(valor) if valor else ""

    def clean_frase(self) -> str:
        """Texto puro, sem links, até o limite."""
        frase = " ".join(self.cleaned_data["frase"].split())
        erro = services.erro_da_frase(frase)
        if erro:
            raise ValidationError(erro)
        return frase

    def clean_logo_envio(self):
        """Valida e já gera o WebP (sem EXIF) do logo enviado."""
        arquivo = self.cleaned_data.get("logo_envio")
        return services.logo_processada(arquivo) if arquivo else None

    def clean(self) -> dict:
        """Categorias (máximo, regulamentada sem frase), documento por tipo, local por modo e horários."""
        dados = super().clean()
        tipo = dados.get("tipo")
        for campo, erro in services.validar_categorias(
            list(dados.get("categorias") or []), dados.get("frase", ""), tipo
        ).items():
            self.add_error(campo, erro)
        if tipo == PerfilGuia.Tipo.EMPRESA and not dados.get("cnpj") and "cnpj" not in self.errors:
            self.add_error("cnpj", "Empresa: informe o CNPJ (ou escolha autônomo).")
        cidade, bairro = dados.get("cidade"), dados.get("bairro")
        if bairro and cidade and bairro.cidade_id != cidade.pk:
            self.add_error("bairro", "Este bairro é de outra cidade.")
        lat, lng = dados.get("latitude"), dados.get("longitude")
        if dados.get("atendimento") == PerfilGuia.Atendimento.ENDERECO:
            if (lat is None) != (lng is None):
                self.add_error("latitude", "Marque o ponto de novo no mapa.")
            elif lat is not None and cidade and longe_da_cidade(lat, lng, cidade):
                self.add_error("latitude", f"O ponto marcado está longe de {cidade.nome}. Confira o mapa.")
        horarios = {}
        for chave, _ in services.DIAS_DA_SEMANA:
            try:
                intervalos = services.interpretar_horario(dados.get(f"horario_{chave}", ""))
            except ValidationError as erro:
                self.add_error(f"horario_{chave}", erro)
                continue
            if intervalos:
                horarios[chave] = intervalos
        self._horarios = horarios
        return dados

    def save(self, commit: bool = True) -> PerfilGuia:
        """Passa mapa, horários, CPF (só o resumo) e logo ao perfil. A domicílio: sem endereço nem ponto."""
        perfil = self.instance
        dados = self.cleaned_data
        if dados["atendimento"] == PerfilGuia.Atendimento.DOMICILIO:
            perfil.endereco, perfil.ponto = "", None  # dado mínimo: nada de endereço de casa guardado
        else:
            perfil.area_atendimento = ""
            lat, lng = dados.get("latitude"), dados.get("longitude")
            perfil.ponto = Point(lng, lat, srid=4326) if lat is not None else None
        perfil.horarios = self._horarios
        if dados.get("cpf"):
            services.definir_cpf(perfil, dados["cpf"])
        if perfil.tipo != PerfilGuia.Tipo.AUTONOMO:
            perfil.cpf_hash, perfil.cpf_final = "", ""
        if dados.get("logo_envio"):
            if perfil.logo:
                perfil.logo.delete(save=False)
            perfil.logo.save("logo.webp", dados["logo_envio"], save=False)
        return super().save(commit)


class AceiteForm(forms.Form):
    """Página pública de aceite: nome digitado e a caixa "Autorizo a publicação" (com campo-armadilha)."""

    nome = forms.CharField(
        label="Seu nome completo",
        max_length=120,
        min_length=5,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
        help_text="Digite o nome de quem é responsável pelo negócio. Até 120 caracteres.",
    )
    autorizo = forms.BooleanField(
        label="Autorizo a publicação, como mostrado na prévia, nos termos acima.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={"required": "Marque a caixa para autorizar."},
    )
    # Campo-armadilha: invisível para pessoas (CSS), robôs costumam preencher.
    site_empresa = forms.CharField(
        required=False,
        label="Deixe em branco",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    def clean_nome(self) -> str:
        """Nome e sobrenome (ao menos duas palavras)."""
        nome = " ".join(self.cleaned_data["nome"].split())
        if len(nome.split(" ")) < 2:
            raise ValidationError("Digite o nome completo (nome e sobrenome).")
        return nome


class AceitePresencialForm(forms.Form):
    """Plano B no admin: foto do termo assinado (storage privado) e o nome de quem assinou."""

    nome = forms.CharField(
        label="Nome de quem assinou",
        max_length=120,
        help_text="Como está escrito no termo em papel.",
    )
    foto = forms.FileField(
        label="Foto do termo assinado",
        help_text="JPG, PNG, WebP ou HEIC. Fica em área privada (nunca no site), sem os dados da foto (GPS).",
    )
    confirmo = forms.BooleanField(
        label="Conferi: o termo está assinado e a prévia da ficha confere com o que a pessoa autorizou.",
    )


class RevogarForm(forms.Form):
    """Revogação do aceite pelo admin (pedido do titular): o perfil sai do ar na hora."""

    motivo = forms.CharField(
        label="Motivo / como o pedido chegou",
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=500,
        help_text="Ex.: pediu por WhatsApp em 18/10. Fica no registro interno. Até 500 caracteres.",
    )


class PedidoForm(forms.Form):
    """ "Esta é minha empresa" (sem login): tipo, descrição e contato para a resposta, com campo-armadilha."""

    tipo = forms.ChoiceField(
        label="O que você quer?",
        choices=[
            ("alterar", "Alterar dados da ficha"),
            ("remover", "Remover a ficha do guia (revoga a autorização)"),
            ("outro", "Outro assunto"),
        ],
        widget=forms.RadioSelect,
    )
    descricao = forms.CharField(
        label="Explique o pedido",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control", "maxlength": 1000}),
        help_text="Até 1.000 caracteres. Ex.: o horário de sábado mudou para 8h às 12h.",
    )
    contato = forms.CharField(
        label="Seu e-mail ou telefone para a resposta",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "email"}),
        help_text="Só para responder este pedido. Até 200 caracteres.",
    )
    # Campo-armadilha: invisível para pessoas (CSS), robôs costumam preencher.
    site_empresa = forms.CharField(
        required=False,
        label="Deixe em branco",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )


class PausarLoteForm(forms.Form):
    """Pausar em lote no admin: cidade e/ou categoria e o motivo (opcional)."""

    cidade = forms.ModelChoiceField(
        queryset=Cidade.objects.filter(liberada=True).order_by("nome"),
        required=False,
        label="Cidade",
        help_text="Em branco = todas.",
    )
    categoria = forms.ModelChoiceField(
        queryset=CategoriaServico.objects.filter(ativa=True).order_by("nome"),
        required=False,
        label="Categoria",
        help_text="Em branco = todas.",
    )
    motivo = forms.CharField(
        label="Motivo",
        required=False,
        max_length=200,
        help_text="Fica no histórico de cada perfil. Até 200 caracteres.",
    )

    def clean(self) -> dict:
        """Escolha ao menos a cidade ou a categoria (nunca pausa o guia inteiro por engano)."""
        dados = super().clean()
        if not dados.get("cidade") and not dados.get("categoria"):
            raise ValidationError("Escolha a cidade, a categoria ou as duas.")
        return dados


class ImportarConvitesForm(forms.Form):
    """Importar a lista de convites: arquivo CSV (primeiro passo) e o texto já lido (passo de confirmação)."""

    LIMITE_BYTES = 1024 * 1024

    arquivo = forms.FileField(
        label="Arquivo CSV",
        required=False,
        help_text="Colunas: nome, whatsapp, cidade, categoria (separadas por vírgula ou ponto e vírgula). "
        "Até 1 MB "
        "e 2.000 linhas.",
    )
    texto = forms.CharField(required=False, widget=forms.HiddenInput)
    origem = forms.ChoiceField(label="Origem", choices=ContatoConvite.Origem.choices, initial="lista_antiga")

    def clean(self) -> dict:
        """Lê o arquivo (UTF-8 ou Latin-1, o do Excel) ou usa o texto da prévia."""
        dados = super().clean()
        arquivo = dados.get("arquivo")
        if arquivo:
            if arquivo.size > self.LIMITE_BYTES:
                raise ValidationError("O arquivo pode ter até 1 MB.")
            bruto = arquivo.read()
            try:
                dados["texto"] = bruto.decode("utf-8-sig")
            except UnicodeDecodeError:
                dados["texto"] = bruto.decode("latin-1")
        if not dados.get("texto"):
            raise ValidationError("Escolha o arquivo CSV.")
        return dados


class QueroSerListadoForm(forms.Form):
    """ "Quero ser listado" (/guia/quero-ser-listado/): o mínimo para a equipe montar a ficha. Sem CPF e sem
    endereço (de casa ou não): a equipe pede o resto no contato. Campo-armadilha contra robôs."""

    nome = forms.CharField(
        label="Nome da empresa ou do serviço",
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "organization"}),
        help_text="Como os clientes conhecem você. Até 120 caracteres.",
    )
    categoria = forms.ModelChoiceField(
        queryset=CategoriaServico.objects.none(),
        label="O que você faz",
        empty_label="Escolha a categoria",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Escolha a mais próxima; a equipe ajusta depois.",
    )
    cidade = forms.ModelChoiceField(
        queryset=Cidade.objects.none(),
        label="Cidade",
        empty_label="Escolha a cidade",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Só as cidades atendidas pelo site.",
    )
    whatsapp = forms.CharField(
        label="WhatsApp para contato",
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "tel", "autocomplete": "tel"}),
        help_text="Com DDD, ex.: (65) 99999-0000.",
    )
    responsavel_nome = forms.CharField(
        label="Seu nome",
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
        help_text="Quem a equipe deve procurar. Até 120 caracteres.",
    )
    autorizo = forms.BooleanField(
        label="Autorizo o Negócios Diários a entrar em contato comigo por este número para montar a ficha.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={"required": "Marque a caixa para a equipe poder falar com você."},
    )
    # Campo-armadilha: invisível para pessoas (CSS), robôs costumam preencher.
    site_empresa = forms.CharField(
        required=False,
        label="Deixe em branco",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        """Categorias ativas (por grupo e nome) e só as cidades liberadas."""
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = CategoriaServico.objects.filter(ativa=True).order_by("nome")
        self.fields["cidade"].queryset = Cidade.objects.filter(liberada=True, uf__liberado=True).order_by(
            "nome"
        )

    def clean_whatsapp(self) -> str:
        """WhatsApp brasileiro em E.164 (+55...)."""
        return normalizar_whatsapp(self.cleaned_data["whatsapp"])
