"""Admin do app anuncios: todos os anúncios (consulta) e a fila de moderação (aprovar/recusar).

A equipe não edita o conteúdo do anúncio (é do anunciante): aprova, recusa com motivo ou,
na lista geral, consulta e vê o histórico. Nada é apagado aqui.
"""

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join
from simple_history.admin import SimpleHistoryAdmin

from anuncios import services
from anuncios.models import Anuncio, AnuncioEmModeracao, DetalheImovel, DetalheVeiculo
from core.admin_acoes import tela_motivo


def _miniatura(anuncio: Anuncio) -> str:
    """Capa pequena na lista (URL do storage, escapada pelo format_html)."""
    capa = anuncio.capa
    if not capa:
        return "—"
    return format_html('<img class="nd-adm-mini" src="{}" alt="">', capa.miniatura.url)


class DetalheImovelInline(admin.StackedInline):
    """Ficha do imóvel dentro do anúncio (só leitura)."""

    model = DetalheImovel
    can_delete = False
    extra = 0
    fields = (
        "tipo",
        "modalidade",
        "quartos",
        "banheiros",
        "vagas",
        "area_total",
        "area_construida",
        "iptu",
        "endereco",
        "exibir_localizacao",
        "coordenadas",
    )
    readonly_fields = fields

    @admin.display(description="ponto no mapa (lat, long)")
    def coordenadas(self, imovel: DetalheImovel) -> str:
        """Latitude e longitude do ponto exato (privado: só a equipe vê)."""
        return f"{imovel.ponto.y:.5f}, {imovel.ponto.x:.5f}" if imovel.ponto else "—"

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        """A ficha nasce com o anúncio."""
        return False


class DetalheVeiculoInline(admin.StackedInline):
    """Ficha do veículo dentro do anúncio (só leitura)."""

    model = DetalheVeiculo
    can_delete = False
    extra = 0
    fields = (
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
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        """A ficha nasce com o anúncio."""
        return False


class BaseAnuncioAdmin(admin.ModelAdmin):
    """Comum às duas telas: só leitura (o conteúdo é do anunciante), sem criar nem apagar."""

    class Media:
        css = {"all": ("css/admin-nd.css",)}

    list_select_related = ("anunciante", "cidade", "bairro")
    search_fields = ("codigo", "titulo", "anunciante__nome_publico")
    inlines = [DetalheImovelInline, DetalheVeiculoInline]

    def get_inlines(self, request: HttpRequest, obj: Anuncio | None = None):
        """Só a ficha da categoria do anúncio."""
        if obj is None:
            return self.inlines
        return [DetalheVeiculoInline] if obj.e_veiculo else [DetalheImovelInline]

    readonly_fields = (
        "codigo",
        "anunciante",
        "categoria",
        "titulo",
        "descricao",
        "preco",
        "cidade",
        "bairro",
        "situacao",
        "pausado_por",
        "motivo_moderacao",
        "moderado_por",
        "publicado_em",
        "expira_em",
        "destaque_ate",
        "criado_em",
        "atualizado_em",
        "demo",
        "fotos_grandes",
    )
    fields = readonly_fields

    @admin.display(description="capa")
    def capa_mini(self, anuncio: Anuncio) -> str:
        """Miniatura da capa na lista."""
        return _miniatura(anuncio)

    @admin.display(description="fotos")
    def fotos_grandes(self, anuncio: Anuncio) -> str:
        """Todas as fotos em tamanho grande (1600 px, reduzidas na tela) para conferir o conteúdo."""
        prontas = [foto for foto in anuncio.fotos.all() if foto.imagem]
        if not prontas:
            return "Sem fotos prontas."
        return format_html_join(
            "",
            '<a href="{}" target="_blank" rel="noopener">'
            '<img class="nd-adm-foto" src="{}" alt="Foto {}"></a>',
            ((foto.imagem.url, foto.imagem.url, i + 1) for i, foto in enumerate(prontas)),
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Anúncios nascem no painel do anunciante."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Exclusão é lógica (situação "excluído"), nunca pelo admin."""
        return False


@admin.register(Anuncio)
class AnuncioAdmin(SimpleHistoryAdmin, BaseAnuncioAdmin):
    """Todos os anúncios: filtro por situação, categoria, cidade e demo.

    O conteúdo é do anunciante (só leitura). A equipe com permissão de alterar anúncios (Administrador e
    Moderador) edita só o "destaque até" (seção Destaques da home) e usa as ações Pausar, Reativar e Remover,
    com motivo, histórico e e-mail ao anunciante (`anuncios.services.acao_da_equipe`).
    """

    list_display = (
        "codigo", "capa_mini", "titulo", "anunciante", "cidade", "situacao", "expira_em", "destaque_ate",
        "demo",
    )  # fmt: skip
    list_filter = ("situacao", "categoria", "cidade", "demo")
    # Tudo continua só leitura, menos o "destaque até".
    readonly_fields = tuple(campo for campo in BaseAnuncioAdmin.readonly_fields if campo != "destaque_ate")
    fields = BaseAnuncioAdmin.readonly_fields
    actions = ["pausar_acao", "reativar_acao", "remover_acao"]

    def _acao(
        self, request: HttpRequest, queryset: QuerySet[Anuncio], acao: str, titulo: str, obrigatorio: bool
    ):
        """Tela intermediária com o motivo (a mesma das outras decisões) e a ação em cada anúncio."""
        return tela_motivo(
            self,
            request,
            queryset,
            f"{acao}_acao",
            titulo,
            obrigatorio,
            lambda anuncio, por, motivo: services.acao_da_equipe(anuncio, por, acao, motivo),
            "{n} anúncio(s) "
            + {"pausar": "pausado(s)", "reativar": "reativado(s)", "remover": "removido(s)"}[acao]
            + "; anunciantes avisados por e-mail.",
        )

    @admin.action(description="Pausar (motivo obrigatório; avisa o anunciante)", permissions=["change"])
    def pausar_acao(self, request: HttpRequest, queryset: QuerySet[Anuncio]):
        """Publicado → pausado pela equipe; o anunciante corrige e reativa no painel."""
        return self._acao(request, queryset, "pausar", "Pausar anúncios", True)

    @admin.action(
        description="Reativar (só os pausados pela equipe; respeita o plano)", permissions=["change"]
    )
    def reativar_acao(self, request: HttpRequest, queryset: QuerySet[Anuncio]):
        """Volta ao ar o que a equipe pausou, se couber no plano da loja."""
        return self._acao(request, queryset, "reativar", "Reativar anúncios", False)

    @admin.action(description="Remover do site (motivo obrigatório; nada é apagado)", permissions=["change"])
    def remover_acao(self, request: HttpRequest, queryset: QuerySet[Anuncio]):
        """Exclusão lógica: some do site e do painel; o registro e o histórico ficam."""
        return self._acao(request, queryset, "remover", "Remover anúncios do site", True)


@admin.register(AnuncioEmModeracao)
class ModeracaoAdmin(BaseAnuncioAdmin):
    """Fila de moderação: só "em análise", mais antigos primeiro, com as ações Aprovar e Recusar."""

    list_display = ("codigo", "capa_mini", "titulo", "anunciante", "cidade", "atualizado_em")
    ordering = ("atualizado_em",)
    actions = ["aprovar_selecionados", "recusar_selecionados"]

    @staticmethod
    def _concretos(queryset: QuerySet) -> QuerySet[Anuncio]:
        """Os mesmos anúncios como `Anuncio` (o histórico só é gravado para o modelo concreto)."""
        return Anuncio.objects.filter(pk__in=queryset.values("pk")).select_related("anunciante__usuario")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Anuncio]:
        """Só anúncios aguardando análise."""
        return (
            super()
            .get_queryset(request)
            .filter(situacao=Anuncio.Situacao.EM_MODERACAO)
            .prefetch_related("fotos")
        )

    @admin.action(description="Aprovar selecionados (publica e avisa por e-mail)", permissions=["change"])
    def aprovar_selecionados(self, request: HttpRequest, queryset: QuerySet[Anuncio]):
        """Publica cada anúncio e avisa o anunciante."""
        feitos = 0
        for anuncio in self._concretos(queryset):
            try:
                services.aprovar(anuncio, request.user)
                feitos += 1
            except ValueError as erro:
                self.message_user(request, str(erro), messages.WARNING)
        self.message_user(
            request, f"{feitos} anúncio(s) aprovado(s); anunciantes avisados.", messages.SUCCESS
        )

    @admin.action(description="Recusar selecionados (motivo enviado por e-mail)", permissions=["change"])
    def recusar_selecionados(self, request: HttpRequest, queryset: QuerySet[Anuncio]):
        """Pede o motivo e devolve para rascunho."""
        return tela_motivo(
            self,
            request,
            self._concretos(queryset),
            "recusar_selecionados",
            "Recusar anúncios",
            True,
            services.recusar,
            "{n} anúncio(s) recusado(s); anunciantes avisados.",
        )
