"""Admin do app guia (docs/GUIA.md §8): cadastro assistido pensado para o celular, convite pelo WhatsApp,
aceite em papel, publicação (só com aceite), revogação e o termo com aviso de rascunho jurídico.

Grupo "Guia" cadastra e publica; Moderador resolve os pedidos dos titulares; Financeiro e Comercial não veem
nada do guia (permissões em guia/migrations/0002). Regras em `guia/services.py`; aqui só se orquestra.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from simple_history.admin import SimpleHistoryAdmin

from core.admin_acoes import tela_motivo
from core.services import textos_ajuda
from guia import services
from guia.forms import (
    AceitePresencialForm,
    ImportarConvitesForm,
    PausarLoteForm,
    PerfilGuiaAdminForm,
    RevogarForm,
)
from guia.models import (
    AceitePublicacao,
    CategoriaServico,
    ConfiguracaoGuia,
    ContatoConvite,
    ConviteAceite,
    GrupoCategoria,
    PedidoDoPerfil,
    PerfilGuia,
    TermoGuia,
)

AVISO_RASCUNHO_TERMO = (
    "Termo do guia em RASCUNHO: revisão jurídica pendente (o advogado revisa na Sprint 9). "
    "O público não vê este aviso."
)


@admin.register(GrupoCategoria)
class GrupoCategoriaAdmin(admin.ModelAdmin):
    """Grupos de categorias (ordem das páginas da cidade)."""

    list_display = ("nome", "ordem", "total_categorias")
    list_editable = ("ordem",)
    prepopulated_fields = {"slug": ("nome",)}

    def get_queryset(self, request: HttpRequest) -> QuerySet[GrupoCategoria]:
        """Com a contagem de categorias."""
        return super().get_queryset(request).annotate(n=Count("categorias"))

    @admin.display(description="categorias", ordering="n")
    def total_categorias(self, grupo: GrupoCategoria) -> int:
        """Quantas categorias o grupo tem."""
        return grupo.n

    def has_delete_permission(self, request: HttpRequest, obj: GrupoCategoria | None = None) -> bool:
        """Grupo com categorias não se apaga (a chave é protegida); vazio, só o Administrador."""
        if obj is not None and obj.categorias.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(CategoriaServico)
class CategoriaServicoAdmin(SimpleHistoryAdmin):
    """Categorias: editáveis; com empresas, não se apagam (só desativar)."""

    list_display = ("nome", "grupo", "ativa", "regulamentada", "rotulo_registro", "total_perfis")
    list_filter = ("grupo", "ativa", "regulamentada")
    search_fields = ("nome", "slug", "sinonimos")
    prepopulated_fields = {"slug": ("nome",)}
    actions = ["desativar"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[CategoriaServico]:
        """Com a contagem de perfis."""
        return super().get_queryset(request).select_related("grupo").annotate(n=Count("perfis"))

    @admin.display(description="perfis", ordering="n")
    def total_perfis(self, categoria: CategoriaServico) -> int:
        """Quantos perfis usam a categoria."""
        return categoria.n

    def has_delete_permission(self, request: HttpRequest, obj: CategoriaServico | None = None) -> bool:
        """Nunca pela lista (em lote); na ficha, só sem perfis. Com perfis: desative."""
        if obj is None or obj.perfis.exists():
            return False
        return super().has_delete_permission(request, obj)

    @admin.action(description="Desativar (some das listas, nada é apagado)", permissions=["change"])
    def desativar(self, request: HttpRequest, queryset: QuerySet[CategoriaServico]) -> None:
        """Tira as categorias das listas sem apagar."""
        total = queryset.update(ativa=False)
        self.message_user(request, f"{total} categoria(s) desativada(s).", messages.SUCCESS)


class SoLeitura:
    """Inline só de leitura (o registro nasce pelos serviços, nunca à mão)."""

    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        """Nada se cria à mão."""
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Nada se edita à mão."""
        return False


class AceiteInline(SoLeitura, admin.TabularInline):
    """Registros de aceite do perfil (prova do consentimento), com a foto do termo e a revogação."""

    model = AceitePublicacao
    verbose_name_plural = "aceites (prova da autorização)"
    fields = (
        "termo",
        "canal",
        "nome_digitado",
        "aceito_em",
        "ip_truncado",
        "agente_resumido",
        "foto",
        "situacao",
    )
    readonly_fields = fields

    @admin.display(description="foto do termo")
    def foto(self, aceite: AceitePublicacao) -> str:
        """Link para a foto (área privada; abre só pelo admin)."""
        if not aceite.foto_termo:
            return "—"
        return format_html('<a href="{}">ver foto</a>', reverse("admin:guia_aceite_foto", args=[aceite.pk]))

    @admin.display(description="situação")
    def situacao(self, aceite: AceitePublicacao) -> str:
        """Válido (com o link de revogar) ou a data da revogação."""
        if aceite.revogado_em:
            return f"Revogado em {aceite.revogado_em:%d/%m/%Y}"
        return format_html(
            'Válido · <a href="{}">revogar</a>', reverse("admin:guia_aceite_revogar", args=[aceite.pk])
        )


class ConviteInline(SoLeitura, admin.TabularInline):
    """Convites enviados (o token nunca aparece aqui)."""

    model = ConviteAceite
    verbose_name_plural = "convites de aceite"
    fields = ("canal", "criado_em", "expira_em", "usado_em", "criado_por")
    readonly_fields = fields


class FilaFilter(admin.SimpleListFilter):
    """Visões da fila do guia (docs/GUIA.md §8): aguardando aceite (com link vencido destacado), publicados,
    pausados, cadastro repetido e removidos."""

    title = "fila"
    parameter_name = "fila"

    def lookups(self, request, model_admin):
        """Opções do filtro."""
        return [
            ("aguardando", "Aguardando aceite"),
            ("link_vencido", "Aguardando aceite, com link vencido"),
            ("publicados", "Publicados"),
            ("pausados", "Pausados"),
            ("duplicidade", "Possível cadastro repetido"),
            ("removidos", "Removidos"),
        ]

    def queryset(self, request, queryset):
        """Aplica a visão escolhida."""
        from django.db.models import Exists, OuterRef
        from django.utils import timezone

        Status = PerfilGuia.Status
        valor = self.value()
        if valor == "aguardando":
            return queryset.filter(status=Status.AGUARDANDO_ACEITE)
        if valor == "link_vencido":
            valido = ConviteAceite.objects.filter(
                perfil=OuterRef("pk"), usado_em__isnull=True, expira_em__gt=timezone.now()
            )
            return queryset.filter(status=Status.AGUARDANDO_ACEITE).exclude(Exists(valido))
        if valor == "publicados":
            return queryset.filter(status=Status.PUBLICADO)
        if valor == "pausados":
            return queryset.filter(status=Status.PAUSADO)
        if valor == "duplicidade":
            return queryset.filter(pk__in=services.perfis_com_duplicidade().values("pk"))
        if valor == "removidos":
            return queryset.filter(status=Status.REMOVIDO)
        return queryset


@admin.register(PerfilGuia)
class PerfilGuiaAdmin(SimpleHistoryAdmin):
    """Cadastro assistido (uma coluna, celular) com o painel de publicação no topo da ficha."""

    form = PerfilGuiaAdminForm
    change_form_template = "admin/guia/perfilguia/change_form.html"
    change_list_template = "admin/guia/perfilguia/change_list.html"
    list_display = (
        "nome_publico",
        "cidade",
        "status",
        "link_de_aceite",
        "lista_categorias",
        "atualizado_em",
        "demo",
    )
    list_filter = (FilaFilter, "status", "tipo", "origem", "cidade", "categorias", "demo")
    actions = ["pausar_selecionados", "reativar_selecionados", "remover_selecionados", "exportar_csv"]
    search_fields = ("nome_publico", "slug")
    list_select_related = ("cidade",)
    inlines = [AceiteInline, ConviteInline]
    readonly_fields = (
        "status",
        "origem",
        "slug",
        "final_do_cpf",
        "logo_atual",
        "cadastrado_por",
        "publicado_em",
    )
    fieldsets = (
        (
            "1. Quem é",
            {"fields": ("tipo", "nome_publico", "categorias", "frase", "logo_atual", "logo_envio")},
        ),
        ("2. Contato (aparece no site por botões)", {"fields": ("whatsapp", "telefone")}),
        (
            "3. Onde atende",
            {
                "fields": (
                    "cidade",
                    "bairro",
                    "atendimento",
                    "endereco",
                    "latitude",
                    "longitude",
                    "area_atendimento",
                )
            },
        ),
        (
            "4. Horário",
            {
                "description": "Um campo por dia. Em branco = sem horário naquele dia.",
                "fields": tuple(f"horario_{dia}" for dia, _ in services.DIAS_DA_SEMANA),
            },
        ),
        (
            "5. Documento e responsável (privado, nunca no site)",
            {
                "fields": (
                    "cnpj",
                    "cnpj_verificado_em",
                    "cpf",
                    "final_do_cpf",
                    "registro_profissional",
                    "responsavel_nome",
                    "responsavel_contato",
                )
            },
        ),
        (
            "6. Interno",
            {
                "fields": (
                    "status",
                    "origem",
                    "slug",
                    "anunciante",
                    "anotacoes",
                    "cadastrado_por",
                    "publicado_em",
                )
            },
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[PerfilGuia]:
        """Com as categorias (lista)."""
        return super().get_queryset(request).prefetch_related("categorias")

    @admin.display(description="link de aceite")
    def link_de_aceite(self, perfil: PerfilGuia) -> str:
        """Aguardando aceite: até quando vale o link, ou "VENCIDO" (reenviar pela ficha)."""
        from django.utils import timezone

        if perfil.status != PerfilGuia.Status.AGUARDANDO_ACEITE:
            return "—"
        convite = (
            perfil.convites.filter(usado_em__isnull=True, expira_em__gt=timezone.now())
            .order_by("-expira_em")
            .first()
        )
        if convite is None:
            return format_html('<b class="nd-guia-vencido">VENCIDO</b> · reenviar na ficha')
        return f"vale até {timezone.localtime(convite.expira_em):%d/%m}"

    @admin.action(description="Pausar os selecionados (com confirmação)", permissions=["change"])
    def pausar_selecionados(self, request: HttpRequest, queryset: QuerySet[PerfilGuia]):
        """Tela de confirmação com o motivo; pausa só os publicados (nada é apagado)."""
        return tela_motivo(
            self,
            request,
            queryset,
            "pausar_selecionados",
            "Pausar perfis",
            False,
            lambda perfil, por, motivo: services.pausar_em_lote(
                [perfil], motivo or "Pausado em lote pela equipe."
            ),
            "{n} perfil(is) processado(s); os publicados foram pausados.",
        )

    @admin.action(description="Reativar os selecionados (só com aceite vigente)", permissions=["change"])
    def reativar_selecionados(self, request: HttpRequest, queryset: QuerySet[PerfilGuia]) -> None:
        """Volta ao ar os pausados que cumprem os requisitos; avisa os que não puderam."""
        total, falhas = services.reativar_em_lote(queryset)
        self.message_user(request, f"{total} perfil(is) reativado(s).", messages.SUCCESS)
        for falha in falhas[:10]:
            self.message_user(request, falha, messages.WARNING)

    @admin.action(description="Remover (pedido do titular: apaga contatos e logo)", permissions=["change"])
    def remover_selecionados(self, request: HttpRequest, queryset: QuerySet[PerfilGuia]):
        """Confirmação com motivo obrigatório; despublica e apaga contatos e logo (fica o aceite)."""
        return tela_motivo(
            self,
            request,
            queryset.exclude(status=PerfilGuia.Status.REMOVIDO),
            "remover_selecionados",
            "Remover perfis do guia",
            True,
            lambda perfil, por, motivo: services.remover_perfil(perfil, por, motivo),
            "{n} perfil(is) removido(s): contatos e logo apagados.",
        )

    @admin.action(description="Exportar CSV dos selecionados", permissions=["view"])
    def exportar_csv(self, request: HttpRequest, queryset: QuerySet[PerfilGuia]) -> HttpResponse:
        """Planilha com os dados públicos e a situação (fórmulas neutralizadas)."""
        return _baixar_csv(services.csv_perfis(queryset), "perfis-guia.csv")

    @admin.display(description="categorias")
    def lista_categorias(self, perfil: PerfilGuia) -> str:
        """Nomes das categorias."""
        return ", ".join(c.nome for c in perfil.categorias.all())

    @admin.display(description="CPF guardado")
    def final_do_cpf(self, perfil: PerfilGuia) -> str:
        """Só o final (o CPF em claro não existe no banco)."""
        return f"***.***.***-{perfil.cpf_final}" if perfil.cpf_final else "—"

    @admin.display(description="logo atual")
    def logo_atual(self, perfil: PerfilGuia) -> str:
        """Miniatura do logo já processado."""
        if not perfil.logo:
            return "—"
        return format_html('<img src="{}" alt="" class="nd-guia-logo">', perfil.logo.url)

    def has_delete_permission(self, request: HttpRequest, obj: PerfilGuia | None = None) -> bool:
        """Nada é apagado (remoção pelo pedido do titular: etapa G3)."""
        return False

    def save_model(self, request: HttpRequest, obj: PerfilGuia, form, change: bool) -> None:
        """Grava quem cadastrou e avisa duplicidades (sem bloquear: a equipe decide)."""
        if not change:
            obj.cadastrado_por = request.user
        super().save_model(request, obj, form, change)
        for aviso in services.duplicidades(obj):
            messages.warning(request, f"Possível cadastro repetido: {aviso}")

    def render_change_form(
        self, request: HttpRequest, context: dict, add=False, change=False, form_url="", obj=None
    ):
        """Painel de publicação (pendências, duplicidade, botões) e dados do mapa e das categorias."""
        from core.models import Cidade

        cidades = Cidade.objects.filter(liberada=True, uf__liberado=True).exclude(ponto=None)
        context.update(
            {
                "ajuda_itens": textos_ajuda("guia_cadastro"),
                "centros": {str(c.pk): [c.ponto.y, c.ponto.x] for c in cidades},
                "reguladas": list(
                    CategoriaServico.objects.filter(regulamentada=True).values_list("pk", flat=True)
                ),
                "termo": services.termo_vigente(),
            }
        )
        if obj is not None:
            faltas = services.pendencias(obj)
            context.update(
                {
                    "pendencias": faltas,
                    "pendencias_convite": services.pendencias(obj, exigir_aceite=False),
                    "duplicidades": services.duplicidades(obj),
                    "aceite": services.aceite_vigente(obj),
                    "pode_mudar": self.has_change_permission(request, obj),
                }
            )
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_urls(self):
        """Ações da ficha: convite pelo WhatsApp, aceite em papel, publicar, pausar e revogar aceite."""
        protegida = self.admin_site.admin_view
        return [
            path("<int:pk>/convite/", protegida(self.convite_view), name="guia_perfil_convite"),
            path(
                "<int:pk>/aceite-presencial/", protegida(self.presencial_view), name="guia_perfil_presencial"
            ),
            path(
                "<int:pk>/publicar/", protegida(require_POST(self.publicar_view)), name="guia_perfil_publicar"
            ),
            path("<int:pk>/pausar/", protegida(require_POST(self.pausar_view)), name="guia_perfil_pausar"),
            path("aceite/<int:pk>/revogar/", protegida(self.revogar_view), name="guia_aceite_revogar"),
            path("aceite/<int:pk>/foto/", protegida(self.foto_view), name="guia_aceite_foto"),
            path("pausar-em-lote/", protegida(self.pausar_lote_view), name="guia_pausar_lote"),
            path("estatisticas/", protegida(self.estatisticas_view), name="guia_estatisticas"),
            *super().get_urls(),
        ]

    def _perfil(self, request: HttpRequest, pk: int) -> PerfilGuia:
        """Perfil para uma ação de mudança (exige a permissão de alterar perfis)."""
        perfil = get_object_or_404(PerfilGuia, pk=pk)
        if not self.has_change_permission(request, perfil):
            raise PermissionDenied
        return perfil

    def _voltar(self, perfil: PerfilGuia) -> HttpResponseRedirect:
        """Volta para a ficha do perfil."""
        return redirect("admin:guia_perfilguia_change", perfil.pk)

    def _tela(self, request: HttpRequest, perfil: PerfilGuia, template: str, **extra) -> TemplateResponse:
        """Tela intermediária do admin (mesmo cabeçalho e trilha)."""
        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": perfil,
            "perfil": perfil,
            **extra,
        }
        return TemplateResponse(request, template, contexto)

    def convite_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """POST: cria o link (vence os anteriores) e mostra a mensagem pronta com o botão que abre o wa.me.

        Sem redirecionar direto ao wa.me: a CSP (form-action) barra o redirecionamento de um POST para
        outro site, e assim a equipe ainda confere a mensagem antes de enviar.
        """
        perfil = self._perfil(request, pk)
        if request.method != "POST":
            return self._voltar(perfil)
        try:
            _, token = services.gerar_convite(perfil, request.user)
        except services.PublicacaoRecusada as erro:
            for falta in erro.pendencias:
                messages.error(request, falta)
            return self._voltar(perfil)
        link = services.link_aceite(token)
        mensagem = services.mensagem_convite(perfil, link, request.user)
        destino = perfil.whatsapp or perfil.telefone
        return self._tela(
            request,
            perfil,
            "admin/guia/perfilguia/convite.html",
            title="Enviar convite pelo WhatsApp",
            link=link,
            mensagem=mensagem,
            url_whatsapp=services.url_whatsapp(destino, mensagem),
            validade=services.configuracao_guia().dias_validade_convite,
        )

    def presencial_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Aceite em papel: foto do termo assinado (privada) + nome; publica na hora."""
        perfil = self._perfil(request, pk)
        form = AceitePresencialForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                services.registrar_aceite_presencial(
                    perfil, form.cleaned_data["foto"], form.cleaned_data["nome"], request.user
                )
            except ValidationError as erro:
                form.add_error("foto", erro)
            except services.PublicacaoRecusada as erro:
                for falta in erro.pendencias:
                    form.add_error(None, falta)
            else:
                messages.success(request, "Aceite em papel registrado. O perfil está publicado.")
                return self._voltar(perfil)
        return self._tela(
            request,
            perfil,
            "admin/guia/perfilguia/presencial.html",
            title="Registrar aceite em papel",
            form=form,
            termo=services.termo_vigente(),
            previa=services.previa(perfil),
        )

    def publicar_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Publica (ou volta ao ar) só com o aceite vigente e os requisitos; senão explica o que falta."""
        perfil = self._perfil(request, pk)
        try:
            services.publicar(perfil, motivo="Publicado pela equipe (aceite vigente).")
        except services.PublicacaoRecusada as erro:
            for falta in erro.pendencias:
                messages.error(request, falta)
        else:
            messages.success(request, "Perfil publicado.")
        return self._voltar(perfil)

    def pausar_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Tira do ar sem apagar."""
        perfil = self._perfil(request, pk)
        try:
            services.pausar(perfil)
        except ValueError as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, "Perfil pausado (fora do ar).")
        return self._voltar(perfil)

    def revogar_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Revoga um aceite (pedido do titular): despublica na hora; o registro fica como prova."""
        aceite = get_object_or_404(AceitePublicacao.objects.select_related("perfil", "termo"), pk=pk)
        self._perfil(request, aceite.perfil_id)
        form = RevogarForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                services.revogar_aceite(aceite, request.user, form.cleaned_data["motivo"])
            except ValueError as erro:
                messages.error(request, str(erro))
            else:
                messages.success(request, "Aceite revogado. O perfil saiu do ar.")
            return self._voltar(aceite.perfil)
        return self._tela(
            request,
            aceite.perfil,
            "admin/guia/perfilguia/revogar.html",
            title="Revogar aceite",
            form=form,
            aceite=aceite,
        )

    def pausar_lote_view(self, request: HttpRequest) -> HttpResponse:
        """Pausar por cidade e/ou categoria: escolhe, vê a lista e confirma (nada é apagado)."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        form = PausarLoteForm(request.POST or None)
        perfis = None
        if request.method == "POST" and form.is_valid():
            perfis = PerfilGuia.objects.filter(status=PerfilGuia.Status.PUBLICADO).select_related("cidade")
            if form.cleaned_data["cidade"]:
                perfis = perfis.filter(cidade=form.cleaned_data["cidade"])
            if form.cleaned_data["categoria"]:
                perfis = perfis.filter(categorias=form.cleaned_data["categoria"])
            if "confirmar" in request.POST:
                motivo = form.cleaned_data["motivo"] or "Pausado em lote pela equipe."
                total = services.pausar_em_lote(perfis, motivo)
                messages.success(request, f"{total} perfil(is) pausado(s).")
                return redirect("admin:guia_perfilguia_changelist")
        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Pausar em lote (cidade ou categoria)",
            "form": form,
            "perfis": perfis,
        }
        return TemplateResponse(request, "admin/guia/perfilguia/pausar_lote.html", contexto)

    def estatisticas_view(self, request: HttpRequest) -> HttpResponse:
        """Visualizações e cliques por perfil e por categoria (7 ou 30 dias); ?csv=1 baixa a tabela."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        dias = 7 if request.GET.get("dias") == "7" else 30
        if request.GET.get("csv") == "1":
            return _baixar_csv(services.csv_estatisticas(dias), f"estatisticas-guia-{dias}d.csv")
        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Estatísticas do guia",
            "dados": services.estatisticas_do_guia(dias),
            "ajuda_itens": textos_ajuda("guia_estatisticas"),
        }
        return TemplateResponse(request, "admin/guia/perfilguia/estatisticas.html", contexto)

    def foto_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Foto do termo em papel (storage privado): só para quem vê os aceites, sem cache."""
        if not request.user.has_perm("guia.view_aceitepublicacao"):
            raise PermissionDenied
        aceite = get_object_or_404(AceitePublicacao, pk=pk)
        if not aceite.foto_termo:
            raise Http404("Sem foto.")
        resposta = FileResponse(aceite.foto_termo.open("rb"), content_type="image/jpeg")
        resposta["Cache-Control"] = "private, no-store"
        resposta["X-Content-Type-Options"] = "nosniff"
        return resposta


@admin.register(TermoGuia)
class TermoGuiaAdmin(SimpleHistoryAdmin):
    """Versões do termo de autorização. Em vigor: texto travado (crie outra versão para mudar)."""

    list_display = ("__str__", "vigente_desde", "rascunho_juridico", "em_vigor_hoje", "total_aceites")
    fields = ("versao", "vigente_desde", "texto", "rascunho_juridico")

    @admin.display(description="em vigor", boolean=True)
    def em_vigor_hoje(self, termo: TermoGuia) -> bool:
        """Vigência já começou."""
        return termo.em_vigor()

    @admin.display(description="aceites")
    def total_aceites(self, termo: TermoGuia) -> int:
        """Quantos aceites usam esta versão."""
        return termo.aceites.count()

    def get_readonly_fields(self, request: HttpRequest, obj: TermoGuia | None = None) -> tuple[str, ...]:
        """Em vigor: só o aviso de revisão jurídica muda (o texto aceito não pode mudar)."""
        if obj is not None and obj.em_vigor():
            return ("versao", "vigente_desde", "texto")
        return ()

    def _avisar_rascunho(self, request: HttpRequest) -> None:
        """Aviso enquanto a versão vigente (ou alguma) estiver como rascunho jurídico."""
        vigente = services.termo_vigente()
        if (vigente is None or vigente.rascunho_juridico) or TermoGuia.objects.filter(
            rascunho_juridico=True
        ).exists():
            messages.warning(request, AVISO_RASCUNHO_TERMO)

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Lista com o aviso de rascunho."""
        if request.method == "GET":
            self._avisar_rascunho(request)
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request: HttpRequest, object_id=None, form_url="", extra_context=None):
        """Ficha com o aviso de rascunho e o lembrete de como mudar uma versão em vigor."""
        obj = self.get_object(request, object_id) if object_id else None
        if request.method == "GET":
            if obj is None or obj.rascunho_juridico:
                messages.warning(request, AVISO_RASCUNHO_TERMO)
            if obj is not None and obj.em_vigor():
                messages.info(
                    request, "Versão em vigor: o texto não muda mais. Para mudar, adicione uma versão nova."
                )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_delete_permission(self, request: HttpRequest, obj: TermoGuia | None = None) -> bool:
        """Prova do que foi aceito: nunca se apaga."""
        return False

    def save_model(self, request: HttpRequest, obj: TermoGuia, form, change: bool) -> None:
        """Versão nova que já está em vigor: cria os links de aceite dos publicados (no prazo)."""
        super().save_model(request, obj, form, change)
        if services.termo_vigente() == obj:
            total = services.convidar_para_termo_novo()
            if total:
                messages.info(
                    request,
                    f"{total} perfil(is) publicado(s) ganharam o link para aceitar a v{obj.versao} até "
                    f'{services.prazo_do_termo(obj):%d/%m/%Y}. Veja em "Quem falta aceitar".',
                )

    def get_urls(self):
        """Painel "quem falta aceitar a versão vigente"."""
        return [
            path("pendentes/", self.admin_site.admin_view(self.pendentes_view), name="guia_termo_pendentes"),
            *super().get_urls(),
        ]

    def pendentes_view(self, request: HttpRequest) -> HttpResponse:
        """Publicados sem aceite da versão vigente, com os dias que faltam e o link para reenviar."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        termo = services.termo_vigente()
        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Quem falta aceitar o termo vigente",
            "termo": termo,
            "prazo": services.prazo_do_termo(termo) if termo else None,
            "pendentes": services.pendentes_do_termo(),
            "ajuda_itens": textos_ajuda("guia_termo_pendentes"),
        }
        return TemplateResponse(request, "admin/guia/termoguia/pendentes.html", contexto)


class VencidoFilter(admin.SimpleListFilter):
    """Pedidos em aberto com o prazo (15 dias) já passado."""

    title = "prazo"
    parameter_name = "prazo"

    def lookups(self, request, model_admin):
        """Opções do filtro."""
        return [("vencido", "Prazo vencido"), ("no_prazo", "Em aberto, no prazo")]

    def queryset(self, request, queryset):
        """Aplica o filtro."""
        from django.utils import timezone

        abertos = queryset.filter(
            status__in=(PedidoDoPerfil.Status.ABERTO, PedidoDoPerfil.Status.EM_ANDAMENTO)
        )
        if self.value() == "vencido":
            return abertos.filter(prazo_ate__lt=timezone.localdate())
        if self.value() == "no_prazo":
            return abertos.filter(prazo_ate__gte=timezone.localdate())
        return queryset


@admin.register(PedidoDoPerfil)
class PedidoDoPerfilAdmin(SimpleHistoryAdmin):
    """Pedidos dos titulares do guia ("Esta é minha empresa", e-mail, WhatsApp), com prazo de 15 dias e marca
    de vencido. A equipe registra os que chegam por e-mail; pedido de remoção pelo contato cadastrado pode ser
    atendido na hora (ação "Atender: remover"), com a confirmação por e-mail depois."""

    list_display = ("criado_em", "tipo", "perfil", "origem", "status", "prazo_ate", "vencido", "demo")
    list_filter = (VencidoFilter, "status", "tipo", "origem", "demo")
    search_fields = ("perfil__nome_publico", "contato", "descricao")
    list_select_related = ("perfil", "perfil__cidade")
    autocomplete_fields = ("perfil",)
    actions = ["atender_removendo", "marcar_atendido", "recusar"]

    def get_fields(self, request: HttpRequest, obj: PedidoDoPerfil | None = None) -> tuple[str, ...]:
        """Novo (registrado pela equipe): perfil, tipo, origem, descrição e contato. Existente: tudo."""
        if obj is None:
            return ("perfil", "tipo", "origem", "descricao", "contato")
        return ("perfil", "tipo", "origem", "descricao", "contato", "criado_em", "prazo_ate", "status",
                "resposta", "decidido_por", "decidido_em", "demo")  # fmt: skip

    def get_readonly_fields(self, request: HttpRequest, obj: PedidoDoPerfil | None = None) -> tuple[str, ...]:
        """O que o titular pediu não se edita depois de registrado."""
        if obj is None:
            return ()
        return ("perfil", "tipo", "origem", "descricao", "contato", "criado_em", "decidido_por",
                "decidido_em", "demo")  # fmt: skip

    @admin.display(description="vencido", boolean=True)
    def vencido(self, pedido: PedidoDoPerfil) -> bool:
        """Em aberto e com o prazo passado."""
        return services.pedido_vencido(pedido)

    def has_delete_permission(self, request: HttpRequest, obj: PedidoDoPerfil | None = None) -> bool:
        """Registro do atendimento: não se apaga."""
        return False

    def save_model(self, request: HttpRequest, obj: PedidoDoPerfil, form, change: bool) -> None:
        """Ao fechar o pedido, grava quem decidiu e quando."""
        from django.utils import timezone

        if (
            obj.status in (PedidoDoPerfil.Status.ATENDIDO, PedidoDoPerfil.Status.RECUSADO)
            and not obj.decidido_em
        ):
            obj.decidido_por, obj.decidido_em = request.user, timezone.now()
        super().save_model(request, obj, form, change)

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Lembra os pedidos dos titulares do resto do site (privacidade), que ficam na outra fila."""
        if request.method == "GET":
            _avisar_outra_fila(request, "privacidade")
        return super().changelist_view(request, extra_context)

    @admin.action(description="Atender: remover o perfil (apaga contatos e logo; confirma por e-mail)",
                  permissions=["change"])  # fmt: skip
    def atender_removendo(self, request: HttpRequest, queryset: QuerySet[PedidoDoPerfil]):
        """Confirmação com o que foi feito; remove o perfil de cada pedido em aberto e fecha o pedido."""
        return tela_motivo(
            self,
            request,
            queryset.filter(status__in=(PedidoDoPerfil.Status.ABERTO, PedidoDoPerfil.Status.EM_ANDAMENTO)),
            "atender_removendo",
            "Atender pedidos removendo os perfis",
            False,
            lambda pedido, por, motivo: services.remover_perfil(pedido.perfil, por, motivo, pedido=pedido),
            "{n} pedido(s) atendido(s); perfis removidos.",
        )

    @admin.action(description="Marcar como atendido (com o que foi feito)", permissions=["change"])
    def marcar_atendido(self, request: HttpRequest, queryset: QuerySet[PedidoDoPerfil]):
        """Fecha os pedidos com a resposta."""
        return tela_motivo(
            self,
            request,
            queryset,
            "marcar_atendido",
            "Marcar pedidos como atendidos",
            True,
            lambda pedido, por, motivo: services.responder_pedido(
                pedido, por, PedidoDoPerfil.Status.ATENDIDO, motivo
            ),
            "{n} pedido(s) atendido(s).",
        )

    @admin.action(description="Recusar (com o motivo)", permissions=["change"])
    def recusar(self, request: HttpRequest, queryset: QuerySet[PedidoDoPerfil]):
        """Fecha os pedidos como recusados, com o motivo."""
        return tela_motivo(
            self,
            request,
            queryset,
            "recusar",
            "Recusar pedidos",
            True,
            lambda pedido, por, motivo: services.responder_pedido(
                pedido, por, PedidoDoPerfil.Status.RECUSADO, motivo
            ),
            "{n} pedido(s) recusado(s).",
        )


@admin.register(ContatoConvite)
class ContatoConviteAdmin(SimpleHistoryAdmin):
    """Lista de convites (docs/GUIA.md §9): importar CSV com prévia, convidar um por vez pelo WhatsApp, marcar
    "recusou"/"não contatar" (bloqueia o número) e criar o perfil de quem aceitou. Sem página pública."""

    change_list_template = "admin/guia/contatoconvite/change_list.html"
    list_display = (
        "nome",
        "whatsapp_legivel",
        "cidade",
        "categoria",
        "origem",
        "situacao",
        "convidado_em",
        "acoes",
        "demo",
    )
    list_filter = ("situacao", "origem", "cidade", "demo")
    search_fields = ("nome", "whatsapp")
    list_select_related = ("cidade", "categoria", "perfil")
    fields = (
        "nome",
        "whatsapp",
        "cidade",
        "categoria",
        "origem",
        "situacao",
        "convidado_em",
        "perfil",
        "observacao",
        "responsavel_nome",
        "autorizou_contato_em",
    )
    readonly_fields = ("convidado_em", "perfil", "autorizou_contato_em")
    actions = ["criar_ficha", "marcar_contatado", "marcar_recusou", "marcar_nao_contatar", "marcar_novo"]

    @admin.display(description="WhatsApp", ordering="whatsapp")
    def whatsapp_legivel(self, contato: ContatoConvite) -> str:
        """(65) 99999-0000."""
        return services.telefone_legivel(contato.whatsapp)

    @admin.display(description="ações")
    def acoes(self, contato: ContatoConvite) -> str:
        """Convidar (um por vez) e criar o perfil; nada para número bloqueado."""
        if contato.bloqueado:
            return "bloqueado"
        if contato.perfil_id:
            return format_html(
                '<a href="{}">abrir perfil</a>',
                reverse("admin:guia_perfilguia_change", args=[contato.perfil_id]),
            )
        return format_html(
            '<a href="{}">convidar</a> · <a href="{}">criar perfil</a>',
            reverse("admin:guia_contato_convidar", args=[contato.pk]),
            reverse("admin:guia_contato_criar_perfil", args=[contato.pk]),
        )

    def save_model(self, request: HttpRequest, obj: ContatoConvite, form, change: bool) -> None:
        """WhatsApp em E.164 (o modelo guarda já normalizado)."""
        from anunciantes.validators import normalizar_whatsapp

        obj.whatsapp = normalizar_whatsapp(obj.whatsapp)
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request: HttpRequest, obj: ContatoConvite | None = None) -> bool:
        """A lista "não contatar" não pode sumir (é o que impede novo convite)."""
        return False

    def _marcar(self, request, queryset, situacao: str, texto: str) -> None:
        """Marca a situação dos selecionados."""
        for contato in queryset:
            services.marcar_contato(contato, situacao)
        self.message_user(request, texto.format(n=queryset.count()), messages.SUCCESS)

    @admin.action(description="Marcar: recusou (bloqueia novos convites)", permissions=["change"])
    def marcar_recusou(self, request: HttpRequest, queryset: QuerySet[ContatoConvite]) -> None:
        """Recusou o convite."""
        self._marcar(
            request, queryset, ContatoConvite.Situacao.RECUSOU, "{n} contato(s) marcado(s): recusou."
        )

    @admin.action(description="Marcar: não contatar (bloqueia novos convites)", permissions=["change"])
    def marcar_nao_contatar(self, request: HttpRequest, queryset: QuerySet[ContatoConvite]) -> None:
        """Pediu para não ser contatado."""
        self._marcar(
            request,
            queryset,
            ContatoConvite.Situacao.NAO_CONTATAR,
            "{n} contato(s) marcado(s): não contatar.",
        )

    @admin.action(description='Voltar para "novo"', permissions=["change"])
    def marcar_novo(self, request: HttpRequest, queryset: QuerySet[ContatoConvite]) -> None:
        """Desfaz uma marcação feita por engano."""
        self._marcar(request, queryset, ContatoConvite.Situacao.NOVO, "{n} contato(s) de volta para novo.")

    @admin.action(description="Marcar como contatado (já falei com a pessoa)", permissions=["change"])
    def marcar_contatado(self, request: HttpRequest, queryset: QuerySet[ContatoConvite]) -> None:
        """Interessado (ou contato) com quem a equipe já falou: situação "contatado", com a data."""
        for contato in queryset:
            services.marcar_contatado(contato)
        self.message_user(
            request, f"{queryset.count()} contato(s) marcado(s) como contatado.", messages.SUCCESS
        )

    @admin.action(description="Criar ficha a partir deste contato (marque um)", permissions=["change"])
    def criar_ficha(self, request: HttpRequest, queryset: QuerySet[ContatoConvite]):
        """Cria o rascunho do perfil com os dados do contato e abre o cadastro assistido para completar.

        Um por vez (a equipe completa e manda o link de aceite de cada ficha). Número bloqueado não vira
        ficha."""
        if not request.user.has_perm("guia.add_perfilguia"):
            raise PermissionDenied
        if queryset.count() != 1:
            self.message_user(
                request, "Marque um contato só: a ficha abre para você completar.", messages.WARNING
            )
            return None
        try:
            perfil = services.criar_perfil_do_contato(queryset.get(), request.user)
        except ValueError as erro:
            self.message_user(request, str(erro), messages.ERROR)
            return None
        self.message_user(request, "Ficha criada como rascunho. Complete os dados e envie o link de aceite.")
        return redirect("admin:guia_perfilguia_change", perfil.pk)

    def get_urls(self):
        """Importar CSV, convidar e criar perfil."""
        protegida = self.admin_site.admin_view
        return [
            path("importar/", protegida(self.importar_view), name="guia_contato_importar"),
            path("<int:pk>/convidar/", protegida(self.convidar_view), name="guia_contato_convidar"),
            path("<int:pk>/perfil/", protegida(self.criar_perfil_view), name="guia_contato_criar_perfil"),
            *super().get_urls(),
        ]

    def _contexto(self, request: HttpRequest, titulo: str, **extra) -> dict:
        """Cabeçalho e trilha do admin."""
        return {**self.admin_site.each_context(request), "opts": self.model._meta, "title": titulo, **extra}

    def importar_view(self, request: HttpRequest) -> HttpResponse:
        """CSV → prévia (linhas válidas, erros e ignoradas por número de linha) → importar só as válidas."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = ImportarConvitesForm(request.POST or None, request.FILES or None)
        previa, texto = None, ""
        if request.method == "POST" and form.is_valid():
            texto = form.cleaned_data["texto"]
            try:
                if "importar" in request.POST:
                    total = services.importar_convites(texto, form.cleaned_data["origem"])
                    messages.success(request, f"{total} contato(s) importado(s).")
                    return redirect("admin:guia_contatoconvite_changelist")
                previa = services.ler_csv_convites(texto)
            except ValueError as erro:
                form.add_error(None, str(erro))
        contexto = self._contexto(
            request,
            "Importar lista de convites",
            form=form,
            previa=previa,
            texto=texto,
            ajuda_itens=textos_ajuda("guia_importar"),
        )
        return TemplateResponse(request, "admin/guia/contatoconvite/importar.html", contexto)

    def convidar_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """GET: a mensagem e o botão. POST: marca "convidado" (com a data) e mostra o botão do wa.me."""
        contato = get_object_or_404(ContatoConvite, pk=pk)
        if not self.has_change_permission(request, contato):
            raise PermissionDenied
        url = ""
        if request.method == "POST":
            try:
                url = services.convidar_contato(contato, request.user)
            except ValueError as erro:
                messages.error(request, str(erro))
                return redirect("admin:guia_contatoconvite_changelist")
        contexto = self._contexto(
            request,
            "Convidar pelo WhatsApp",
            contato=contato,
            mensagem=services.mensagem_convite_contato(contato, request.user),
            url_whatsapp=url,
            bloqueado=contato.bloqueado or services.numero_bloqueado(contato.whatsapp),
        )
        return TemplateResponse(request, "admin/guia/contatoconvite/convidar.html", contexto)

    def criar_perfil_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Quem disse "sim": cria o rascunho do perfil (origem lista antiga) e abre a ficha para completar."""
        contato = get_object_or_404(ContatoConvite, pk=pk)
        if not (
            self.has_change_permission(request, contato) and request.user.has_perm("guia.add_perfilguia")
        ):
            raise PermissionDenied
        if request.method != "POST":
            contexto = self._contexto(request, "Criar perfil a partir do contato", contato=contato)
            return TemplateResponse(request, "admin/guia/contatoconvite/criar_perfil.html", contexto)
        try:
            perfil = services.criar_perfil_do_contato(contato, request.user)
        except ValueError as erro:
            messages.error(request, str(erro))
            return redirect("admin:guia_contatoconvite_changelist")
        messages.success(request, "Perfil criado como rascunho. Complete os dados e envie o link de aceite.")
        return redirect("admin:guia_perfilguia_change", perfil.pk)


@admin.register(ConfiguracaoGuia)
class ConfiguracaoGuiaAdmin(SimpleHistoryAdmin):
    """Configuração do guia (registro único): a lista abre direto o formulário."""

    readonly_fields = ("atualizado_em",)

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Registro único: o menu leva direto ao formulário."""
        return redirect("admin:guia_configuracaoguia_change", services.configuracao_guia().pk)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Só existe um registro (criado sozinho)."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ConfiguracaoGuia | None = None) -> bool:
        """O registro único nunca é apagado."""
        return False


def _baixar_csv(conteudo: str, nome: str) -> HttpResponse:
    """Resposta de download do CSV (sem cache)."""
    resposta = HttpResponse(conteudo, content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    resposta["Cache-Control"] = "private, no-store"
    return resposta


def _avisar_outra_fila(request: HttpRequest, qual: str) -> None:
    """Pedidos do titular ficam em duas filas (site e guia): cada uma avisa quantos há em aberto na outra."""
    from django.utils import timezone

    from privacidade.models import PedidoTitular

    if qual == "privacidade" and request.user.has_perm("privacidade.view_pedidotitular"):
        abertos = PedidoTitular.objects.filter(
            situacao__in=(PedidoTitular.Situacao.ABERTO, PedidoTitular.Situacao.EM_ANDAMENTO)
        )
        url = reverse("admin:privacidade_pedidotitular_changelist")
    elif qual == "guia" and request.user.has_perm("guia.view_pedidodoperfil"):
        abertos = PedidoDoPerfil.objects.filter(
            status__in=(PedidoDoPerfil.Status.ABERTO, PedidoDoPerfil.Status.EM_ANDAMENTO)
        )
        url = reverse("admin:guia_pedidodoperfil_changelist") + "?prazo=vencido"
    else:
        return
    total = abertos.count()
    if total:
        campo = "prazo" if qual == "privacidade" else "prazo_ate"
        vencidos = abertos.filter(**{f"{campo}__lt": timezone.localdate()}).count()
        nome = "do site (Meus dados, e-mail)" if qual == "privacidade" else "do Guia de Negócios"
        messages.info(
            request,
            format_html(
                'Pedidos dos titulares {}: {} em aberto, {} vencido(s). <a href="{}">Ver</a>',
                nome,
                total,
                vencidos,
                url,
            ),  # fmt: skip
        )
