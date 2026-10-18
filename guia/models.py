"""Modelos do app guia: o Guia de Negócios (docs/GUIA.md §4), diretório gratuito de serviços e comércios.

Isolado dos classificados: não usa `Anunciante` (a empresa listada não tem login); só um vínculo opcional
para quando a mesma empresa também anunciar. Nada vai ao ar sem autorização registrada (`AceitePublicacao`
da versão vigente do `TermoGuia`). CPF nunca é guardado em claro: só o HMAC (`cpf_hash`) e os 2 últimos
dígitos (`cpf_final`). Regras em `guia/services.py`.
"""

import uuid
from pathlib import PurePath

from django.conf import settings
from django.contrib.gis.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import Bairro, Cidade, MarcaDemo
from pagamentos.armazenamento import armazenamento_privado

CHAVE_CACHE_CONFIGURACAO_GUIA = "guia:configuracao"


class GrupoCategoria(models.Model):
    """Grupo de categorias (ex.: "Construção e Reforma"), para organizar a escolha e as páginas da cidade."""

    nome = models.CharField("nome", max_length=80, unique=True, help_text="Até 80 caracteres.")
    slug = models.SlugField("endereço", max_length=80, unique=True, help_text="Usado nas URLs, sem acentos.")
    ordem = models.PositiveSmallIntegerField("ordem", default=0, help_text="Menor aparece primeiro.")

    class Meta:
        verbose_name = "grupo de categorias"
        verbose_name_plural = "grupos de categorias"
        ordering = ["ordem", "nome"]

    def __str__(self) -> str:
        """Nome do grupo."""
        return self.nome


class CategoriaServico(models.Model):
    """Tipo de serviço (ex.: "Eletricista"). Carga inicial pelo `carregar_categorias_guia` (upsert por slug).

    Categoria com empresas não é apagada, só desativada. `regulamentada` (saúde, advocacia, contabilidade,
    engenharia, corretagem, personal): ficha restrita, sem frase promocional (docs/GUIA.md §5, item 4).
    """

    grupo = models.ForeignKey(
        GrupoCategoria, on_delete=models.PROTECT, related_name="categorias", verbose_name="grupo"
    )
    nome = models.CharField("nome", max_length=80, help_text="Até 80 caracteres.")
    slug = models.SlugField(
        "endereço", max_length=80, unique=True, help_text="Usado nas URLs (/guia/mt/cidade/<endereço>/)."
    )
    ordem = models.PositiveSmallIntegerField("ordem", default=0, help_text="Menor aparece primeiro no grupo.")
    ativa = models.BooleanField(
        "ativa", default=True, help_text="Desmarque para tirar das listas sem apagar."
    )
    regulamentada = models.BooleanField(
        "profissão regulamentada",
        default=False,
        help_text="Conselho de classe (CRM, OAB, CRC, CREA, CRECI, CREF...): ficha restrita, sem frase "
        "promocional e com o número de registro.",
    )
    rotulo_registro = models.CharField(
        "rótulo do registro",
        max_length=40,
        blank=True,
        help_text='Sigla do conselho mostrada antes do número, ex.: "CRM", "OAB". Só para regulamentadas.',
    )
    sinonimos = models.TextField(
        "sinônimos",
        blank=True,
        help_text="Outras palavras para achar a categoria na busca, separadas por ponto e vírgula.",
    )
    estabelecimento = models.BooleanField(
        "estabelecimento (mostra horário)",
        default=False,
        help_text="Regulamentada que é lugar aberto ao público (farmácia, clínica, hospital, veterinário): "
        'mostra horário e "aberto agora" (informação factual). Continua sem frase e sem logo.',
    )

    history = HistoricalRecords(verbose_name="histórico da categoria")

    class Meta:
        verbose_name = "categoria de serviço"
        verbose_name_plural = "categorias de serviço"
        ordering = ["grupo__ordem", "ordem", "nome"]

    def __str__(self) -> str:
        """Nome da categoria."""
        return self.nome


def caminho_logo_guia(instancia, nome_arquivo: str) -> str:
    """Logo do perfil com nome aleatório (nunca o nome enviado; docs/SEGURANCA.md)."""
    return f"guia/logos/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


def caminho_termo_assinado(instancia, nome_arquivo: str) -> str:
    """Foto do termo em papel, no storage PRIVADO e com nome aleatório."""
    return f"guia/termos/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


class PerfilGuia(MarcaDemo):
    """Empresa, autônomo ou profissional listado no guia (sem login; cadastrado pela equipe).

    Só sai do servidor o `ponto_publico`: o endereço comercial (quem atende em endereço) ou o centro da
    cidade (quem atende a domicílio; nunca endereço residencial). Documento (CNPJ, final do CPF) e os dados
    do responsável são privados: nunca aparecem no site.
    """

    class Tipo(models.TextChoices):
        EMPRESA = "empresa", "Empresa (com CNPJ)"
        AUTONOMO = "autonomo", "Profissional autônomo"
        REGULAMENTADO = "profissional_regulamentado", "Profissional regulamentado (conselho de classe)"

    class Atendimento(models.TextChoices):
        ENDERECO = "atende_em_endereco", "Tem endereço (atende no local)"
        DOMICILIO = "atende_a_domicilio", "Atende a domicílio (sem endereço)"

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        AGUARDANDO_ACEITE = "aguardando_aceite", "Aguardando aceite"
        PUBLICADO = "publicado", "Publicado"
        PAUSADO = "pausado", "Pausado"
        REMOVIDO = "removido", "Removido"

    class Origem(models.TextChoices):
        CADASTRO_ASSISTIDO = "cadastro_assistido", "Cadastro assistido (equipe)"
        AUTOCADASTRO = "autocadastro", "Autocadastro"
        LISTA_ANTIGA = "lista_antiga", "Lista do projeto antigo"

    nome_publico = models.CharField("nome público", max_length=120)
    slug = models.SlugField("endereço da ficha", max_length=140, unique=True, editable=False)
    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices, default=Tipo.EMPRESA)
    frase = models.CharField("frase de apresentação", max_length=255, blank=True)

    # Documento: privado, nunca exibido.
    cnpj = models.CharField("CNPJ", max_length=14, blank=True, db_index=True)
    cnpj_verificado_em = models.DateField("CNPJ conferido em", null=True, blank=True)
    cpf_hash = models.CharField(
        "resumo do CPF (HMAC)", max_length=64, blank=True, db_index=True, editable=False
    )
    cpf_final = models.CharField("final do CPF", max_length=2, blank=True, editable=False)
    registro_profissional = models.CharField("registro profissional", max_length=40, blank=True)

    responsavel_nome = models.CharField("nome do responsável", max_length=120)
    responsavel_contato = models.CharField("contato do responsável", max_length=120, blank=True)
    anotacoes = models.TextField("anotações internas", blank=True)

    whatsapp = models.CharField("WhatsApp", max_length=16, blank=True, db_index=True)
    telefone = models.CharField("telefone", max_length=16, blank=True)

    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name="perfis_guia", verbose_name="cidade"
    )
    bairro = models.ForeignKey(
        Bairro, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="bairro"
    )
    atendimento = models.CharField(
        "como atende", max_length=20, choices=Atendimento.choices, default=Atendimento.ENDERECO
    )
    endereco = models.CharField("endereço comercial", max_length=200, blank=True)
    ponto = models.PointField("ponto no mapa", srid=4326, null=True, blank=True)
    area_atendimento = models.CharField("área de atendimento", max_length=160, blank=True)
    ponto_publico = models.PointField("ponto público", srid=4326, null=True, blank=True, editable=False)

    horarios = models.JSONField(
        "horários",
        default=dict,
        blank=True,
        help_text='Ex.: {"seg": [["08:00", "18:00"]]}. Vazio = sem horário.',
    )
    fuso = models.CharField("fuso horário", max_length=40, default="America/Cuiaba")
    logo = models.FileField("logo (400 px)", upload_to=caminho_logo_guia, blank=True, editable=False)

    categorias = models.ManyToManyField(
        CategoriaServico, related_name="perfis", blank=True, verbose_name="categorias"
    )
    status = models.CharField(
        "situação", max_length=20, choices=Status.choices, default=Status.RASCUNHO, db_index=True
    )
    origem = models.CharField(
        "origem", max_length=20, choices=Origem.choices, default=Origem.CADASTRO_ASSISTIDO
    )
    anunciante = models.ForeignKey(
        "anunciantes.Anunciante",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfis_guia",
        verbose_name="também anuncia como",
    )
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        verbose_name="cadastrado por",
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True, editable=False)
    removido_em = models.DateTimeField(
        "removido em",
        null=True,
        blank=True,
        editable=False,
        help_text="Contatos e logo apagados nesta data; o resto sai na limpeza depois do prazo de prova.",
    )

    history = HistoricalRecords(verbose_name="histórico do perfil")

    class Meta:
        verbose_name = "perfil do guia"
        verbose_name_plural = "perfis do guia"
        ordering = ["nome_publico"]
        indexes = [models.Index(fields=["cidade", "status"], name="guia_perfil_cidade_status_idx")]

    def __str__(self) -> str:
        """Ex.: 'Vidraçaria Boa Vista (Tangará da Serra/MT)'."""
        return f"{self.nome_publico} ({self.cidade})" if self.cidade_id else self.nome_publico

    def clean(self) -> None:
        """Telefones em E.164, CNPJ só dígitos e frase sem links nem HTML (texto puro, docs/GUIA.md §10)."""
        from anunciantes.validators import normalizar_cnpj, normalizar_whatsapp
        from guia.services import erro_da_frase

        erros: dict[str, list[str]] = {}
        for campo in ("whatsapp", "telefone"):
            valor = getattr(self, campo)
            if valor:
                try:
                    setattr(self, campo, normalizar_whatsapp(valor))
                except ValidationError as erro:
                    erros[campo] = [m.replace("WhatsApp", campo.capitalize()) for m in erro.messages]
        if self.cnpj:
            try:
                self.cnpj = normalizar_cnpj(self.cnpj)
            except ValidationError as erro:
                erros["cnpj"] = erro.messages
        mensagem = erro_da_frase(self.frase)
        if mensagem:
            erros["frase"] = [mensagem]
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs) -> None:
        """Gera o slug (nome + cidade, único); recalcula o ponto público e o fuso (do estado) ao gravar."""
        from guia.services import fuso_da_uf, ponto_publico_de, slug_do_perfil

        if not self.slug:
            self.slug = slug_do_perfil(self)
        self.ponto_publico = ponto_publico_de(self)
        if self.cidade_id:
            self.fuso = fuso_da_uf(self.cidade.uf_id)  # "aberto agora" no fuso do estado da cidade
        super().save(*args, **kwargs)

    @property
    def regulamentado(self) -> bool:
        """Ficha restrita: tipo regulamentado ou alguma categoria regulamentada (já gravada)."""
        if self.tipo == self.Tipo.REGULAMENTADO:
            return True
        return bool(self.pk) and self.categorias.filter(regulamentada=True).exists()

    @property
    def mostra_horario(self) -> bool:
        """Horário e "aberto agora" na ficha: todos, menos o profissional regulamentado individual (médico,
        dentista, advogado...). Estabelecimento regulado (farmácia, clínica, hospital, veterinário) mostra."""
        if not self.regulamentado:
            return True
        return bool(self.pk) and self.categorias.filter(regulamentada=True, estabelecimento=True).exists()


class TermoGuia(MarcaDemo):
    """Termo de autorização de publicação, com versão (mesmo padrão dos Termos de Uso).

    Vale a versão com o `vigente_desde` mais recente que já começou. Em vigor, o texto fica travado (é o
    que as pessoas aceitaram): para mudar, crie uma versão nova. `rascunho_juridico` fica ligado até o
    advogado revisar (aviso no admin).
    """

    versao = models.CharField("versão", max_length=40, unique=True, help_text='Ex.: "2026-10".')
    texto = models.TextField(
        "texto",
        help_text="Texto puro. Título: linha começando com ## . Item de lista: linha começando com - . "
        "Parágrafos separados por linha em branco. Variáveis: {nome_guia}, {versao}, {vigente_desde}, "
        "{empresa}, {documento}, {cidade_sede}, {email_encarregado}.",
    )
    vigente_desde = models.DateField(
        "em vigor desde", help_text="A partir desta data, os novos aceites usam esta versão."
    )
    rascunho_juridico = models.BooleanField(
        "rascunho: revisão jurídica pendente",
        default=True,
        help_text="Aviso só para a equipe (no admin). Desmarque quando o advogado aprovar o texto.",
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)

    history = HistoricalRecords(verbose_name="histórico do termo")

    class Meta:
        verbose_name = "termo do guia"
        verbose_name_plural = "termos do guia (autorização de publicação)"
        ordering = ["-vigente_desde", "-pk"]

    def __str__(self) -> str:
        """Ex.: 'Termo do guia v2026-10'."""
        return f"Termo do guia v{self.versao}"

    def em_vigor(self, hoje=None) -> bool:
        """Vigência já começou (o texto fica travado)."""
        return self.vigente_desde <= (hoje or timezone.localdate())


class ConviteAceite(models.Model):
    """Link de aceite enviado ao responsável (`/guia/aceite/<token>/`): uso único e com validade.

    Token de 32 bytes aleatórios (nunca o id). Gerar um convite novo vence os anteriores ainda não usados.
    """

    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "E-mail"
        PRESENCIAL = "presencial", "Presencial (termo em papel)"

    perfil = models.ForeignKey(
        PerfilGuia, on_delete=models.PROTECT, related_name="convites", verbose_name="perfil"
    )
    token = models.CharField("token", max_length=64, unique=True, editable=False)
    canal = models.CharField("canal", max_length=12, choices=Canal.choices, default=Canal.WHATSAPP)
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    expira_em = models.DateTimeField("expira em")
    usado_em = models.DateTimeField("usado em", null=True, blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="criado por",
    )

    class Meta:
        verbose_name = "convite de aceite"
        verbose_name_plural = "convites de aceite"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        """Ex.: 'Convite WhatsApp · 18/10/2026'."""
        return f"Convite {self.get_canal_display()} · {timezone.localtime(self.criado_em):%d/%m/%Y}"

    def valido(self, agora=None) -> bool:
        """Ainda não usado e dentro da validade."""
        return self.usado_em is None and (agora or timezone.now()) < self.expira_em


class AceitePublicacao(models.Model):
    """Registro da autorização: quem (nome digitado), quando, qual versão do termo, IP truncado e navegador.

    É a prova do consentimento (LGPD, art. 7º, I): guardado enquanto o perfil existir e mais o prazo de
    prova (`ConfiguracaoGuia.prazo_prova_aceite_anos`). Revogar = despublicar na hora e registrar a data.
    No aceite presencial, a foto do termo assinado fica no storage privado.
    """

    perfil = models.ForeignKey(
        PerfilGuia, on_delete=models.PROTECT, related_name="aceites", verbose_name="perfil"
    )
    termo = models.ForeignKey(
        TermoGuia, on_delete=models.PROTECT, related_name="aceites", verbose_name="versão do termo"
    )
    convite = models.ForeignKey(
        ConviteAceite,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aceites",
        verbose_name="convite",
    )
    canal = models.CharField("canal", max_length=12, choices=ConviteAceite.Canal.choices)
    nome_digitado = models.CharField("nome digitado", max_length=120)
    aceito_em = models.DateTimeField("aceito em", default=timezone.now)
    ip_truncado = models.CharField("IP (último bloco zerado)", max_length=45, blank=True)
    agente_resumido = models.CharField("navegador (resumo)", max_length=80, blank=True)
    foto_termo = models.FileField(
        "foto do termo assinado",
        upload_to=caminho_termo_assinado,
        storage=armazenamento_privado,
        blank=True,
        editable=False,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="registrado por (presencial)",
    )
    revogado_em = models.DateTimeField("revogado em", null=True, blank=True)
    revogado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="revogado por",
    )
    motivo_revogacao = models.TextField("motivo da revogação", blank=True)

    history = HistoricalRecords(verbose_name="histórico do aceite")

    class Meta:
        verbose_name = "aceite de publicação"
        verbose_name_plural = "aceites de publicação"
        ordering = ["-aceito_em"]

    def __str__(self) -> str:
        """Ex.: 'Aceite v2026-10 · 18/10/2026 14:05'."""
        return f"Aceite v{self.termo.versao} · {timezone.localtime(self.aceito_em):%d/%m/%Y %H:%M}"

    @property
    def valido(self) -> bool:
        """Não revogado."""
        return self.revogado_em is None


class EstatisticaGuiaDia(models.Model):
    """Totais do dia por perfil (sem IP nem cookie; regra anti-robô das estatísticas). Contagem: G2."""

    perfil = models.ForeignKey(
        PerfilGuia, on_delete=models.CASCADE, related_name="estatisticas", verbose_name="perfil"
    )
    dia = models.DateField("dia")
    visualizacoes = models.PositiveIntegerField("visualizações", default=0)
    cliques_whatsapp = models.PositiveIntegerField("cliques no WhatsApp", default=0)
    cliques_telefone = models.PositiveIntegerField("cliques no telefone", default=0)

    class Meta:
        verbose_name = "estatística do dia (guia)"
        verbose_name_plural = "estatísticas por dia (guia)"
        ordering = ["-dia"]
        constraints = [models.UniqueConstraint(fields=["perfil", "dia"], name="guia_estatistica_perfil_dia")]

    def __str__(self) -> str:
        """Ex.: 'Vidraçaria · 18/10/2026'."""
        return f"{self.perfil.nome_publico} · {self.dia:%d/%m/%Y}"


class PedidoDoPerfil(MarcaDemo):
    """Pedido de alteração, remoção ou outro do titular: pela ficha pública ("Esta é minha empresa") ou
    registrado pela equipe (e-mail, WhatsApp). Prazo padrão: recebido + `Configuracao.prazo_titular_dias`
    (15 dias), como os pedidos de `privacidade`. Guardado pelo prazo de prova depois de decidido.
    """

    class Origem(models.TextChoices):
        FICHA = "ficha", "Formulário da ficha"
        EMAIL = "email", "E-mail"
        OUTRO = "outro", "Outro canal (WhatsApp, telefone...)"

    class Tipo(models.TextChoices):
        ALTERAR = "alterar", "Alterar dados"
        REMOVER = "remover", "Remover da lista"
        OUTRO = "outro", "Outro"

    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        ATENDIDO = "atendido", "Atendido"
        RECUSADO = "recusado", "Recusado"

    perfil = models.ForeignKey(
        PerfilGuia, on_delete=models.PROTECT, related_name="pedidos", verbose_name="perfil"
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    origem = models.CharField("origem", max_length=8, choices=Origem.choices, default=Origem.FICHA)
    descricao = models.TextField("o que foi pedido", max_length=1000, blank=True)
    contato = models.CharField("contato para resposta", max_length=200, blank=True)
    criado_em = models.DateTimeField("recebido em", default=timezone.now, editable=False)
    prazo_ate = models.DateField("prazo", blank=True)
    status = models.CharField(
        "situação", max_length=14, choices=Status.choices, default=Status.ABERTO, db_index=True
    )
    resposta = models.TextField("resposta / o que foi feito", blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="decidido por",
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)

    history = HistoricalRecords(verbose_name="histórico do pedido")

    class Meta:
        verbose_name = "pedido do perfil (titular)"
        verbose_name_plural = "pedidos dos perfis (titulares)"
        ordering = ["status", "prazo_ate"]

    def __str__(self) -> str:
        """Ex.: 'Remover da lista · Vidraçaria Boa Vista'."""
        return f"{self.get_tipo_display()} · {self.perfil.nome_publico}"

    def save(self, *args, **kwargs) -> None:
        """Prazo padrão: data do recebimento + o prazo dos titulares da Configuracao."""
        if not self.prazo_ate:
            from datetime import timedelta

            from core.services import configuracao

            recebido = timezone.localtime(self.criado_em).date()
            self.prazo_ate = recebido + timedelta(days=configuracao().prazo_titular_dias)
        super().save(*args, **kwargs)


class ConfiguracaoGuia(models.Model):
    """Ajustes do guia, editáveis no admin (registro único, sempre o id 1; lido com cache).

    Os limites da logo vêm da `Configuracao` do site (os mesmos do logo da loja).
    """

    ID_UNICO = 1

    ativo = models.BooleanField(
        "guia no ar",
        default=False,
        help_text="Liga e desliga a aba inteira no site (as páginas públicas chegam na etapa G2). "
        "O link de aceite funciona mesmo desligado.",
    )
    nome_guia = models.CharField(
        "nome da aba",
        max_length=40,
        default="Guia de Negócios",
        help_text="Aparece no menu, nas páginas e no termo.",
    )
    max_categorias = models.PositiveSmallIntegerField(
        "máximo de categorias por perfil",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    limite_frase = models.PositiveSmallIntegerField(
        "limite da frase (caracteres)",
        default=160,
        validators=[MinValueValidator(20), MaxValueValidator(255)],
    )
    dias_validade_convite = models.PositiveSmallIntegerField(
        "validade do link de aceite (dias)", default=15, validators=[MinValueValidator(1)]
    )
    dias_aceite_termo_novo = models.PositiveSmallIntegerField(
        "prazo para aceitar um termo novo (dias)",
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Contado do início da vigência. Sem aceite no prazo, o perfil é pausado (nunca apagado).",
    )
    pedidos_por_hora = models.PositiveSmallIntegerField(
        'pedidos "Esta é minha empresa" por hora (por visitante)',
        default=5,
        validators=[MinValueValidator(1)],
    )
    minimo_empresas_indexar = models.PositiveSmallIntegerField(
        "mínimo de empresas para o Google indexar",
        default=3,
        help_text="Cidade + categoria com menos empresas fica fora do Google (página fina). Usado na G2.",
    )
    prazo_prova_aceite_anos = models.PositiveSmallIntegerField(
        "guarda do aceite após a remoção (anos)",
        default=5,
        help_text="Prazo de prova do consentimento. Decisão a validar com o advogado.",
    )
    tentativas_aceite_por_hora = models.PositiveSmallIntegerField(
        "tentativas de aceite por hora (por visitante)", default=10, validators=[MinValueValidator(1)]
    )
    contatos_por_hora = models.PositiveSmallIntegerField(
        "contatos revelados por hora (por visitante)",
        default=30,
        validators=[MinValueValidator(1)],
        help_text='Cliques em WhatsApp e "Ver telefone" por visitante por hora (contra robôs coletores).',
    )
    limite_foto_termo_kb = models.PositiveIntegerField(
        "limite da foto do termo em papel (KB)", default=10240, validators=[MinValueValidator(100)]
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico da configuração do guia")

    class Meta:
        verbose_name = "configuração do guia"
        verbose_name_plural = "configuração do guia"

    def __str__(self) -> str:
        """Nome fixo no admin."""
        return "Configuração do guia"

    def save(self, *args, **kwargs) -> None:
        """Sempre o registro 1 (registro único); limpa o cache."""
        self.pk = self.ID_UNICO
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_CONFIGURACAO_GUIA)

    def delete(self, *args, **kwargs):
        """O registro único nunca é apagado."""
        raise PermissionError("A configuração do guia não pode ser apagada.")


class ContatoConvite(MarcaDemo):
    """Contato da lista de convites (projeto antigo, indicação): só para a equipe convidar, um por vez.

    Sem página pública. "Recusou" e "não contatar" bloqueiam novos convites para o número (também no convite
    de aceite de um perfil). Quem aceita vira `PerfilGuia` com origem `lista_antiga` (docs/GUIA.md §9).
    """

    class Origem(models.TextChoices):
        LISTA_ANTIGA = "lista_antiga", "Lista do projeto antigo"
        INDICACAO = "indicacao", "Indicação"
        OUTRO = "outro", "Outro"

    class Situacao(models.TextChoices):
        NOVO = "novo", "Novo"
        CONVIDADO = "convidado", "Convidado"
        ACEITOU = "aceitou", "Aceitou"
        RECUSOU = "recusou", "Recusou"
        NAO_CONTATAR = "nao_contatar", "Não contatar"

    BLOQUEADOS = (Situacao.RECUSOU, Situacao.NAO_CONTATAR)

    nome = models.CharField("nome", max_length=120)
    whatsapp = models.CharField(
        "WhatsApp", max_length=16, db_index=True, help_text="Com DDD; guardado em E.164."
    )
    cidade = models.ForeignKey(Cidade, on_delete=models.PROTECT, related_name="+", verbose_name="cidade")
    categoria = models.ForeignKey(
        CategoriaServico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="categoria",
    )
    origem = models.CharField("origem", max_length=14, choices=Origem.choices, default=Origem.LISTA_ANTIGA)
    situacao = models.CharField(
        "situação", max_length=14, choices=Situacao.choices, default=Situacao.NOVO, db_index=True
    )
    convidado_em = models.DateTimeField("convidado em", null=True, blank=True)
    perfil = models.ForeignKey(
        PerfilGuia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contatos_convite",
        verbose_name="perfil criado",
    )
    observacao = models.CharField("observação", max_length=200, blank=True)
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)

    history = HistoricalRecords(verbose_name="histórico do contato")

    class Meta:
        verbose_name = "contato para convite"
        verbose_name_plural = "lista de convites"
        ordering = ["situacao", "nome"]

    def __str__(self) -> str:
        """Ex.: 'João Eletricista (Tangará da Serra/MT)'."""
        return f"{self.nome} ({self.cidade})"

    @property
    def bloqueado(self) -> bool:
        """Recusou ou pediu para não ser contatado."""
        return self.situacao in self.BLOQUEADOS
