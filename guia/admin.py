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

from core.services import textos_ajuda
from guia import services
from guia.forms import AceitePresencialForm, PerfilGuiaAdminForm, RevogarForm
from guia.models import (
    AceitePublicacao,
    CategoriaServico,
    ConfiguracaoGuia,
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


@admin.register(PerfilGuia)
class PerfilGuiaAdmin(SimpleHistoryAdmin):
    """Cadastro assistido (uma coluna, celular) com o painel de publicação no topo da ficha."""

    form = PerfilGuiaAdminForm
    change_form_template = "admin/guia/perfilguia/change_form.html"
    list_display = ("nome_publico", "cidade", "status", "lista_categorias", "atualizado_em", "demo")
    list_filter = ("status", "tipo", "origem", "cidade", "categorias", "demo")
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


@admin.register(PedidoDoPerfil)
class PedidoDoPerfilAdmin(SimpleHistoryAdmin):
    """Pedidos dos titulares do guia (alterar, remover, outro), com prazo. O formulário público vem na G3."""

    list_display = ("criado_em", "tipo", "perfil", "status", "prazo_ate", "demo")
    list_filter = ("status", "tipo", "demo")
    search_fields = ("perfil__nome_publico", "contato", "descricao")
    list_select_related = ("perfil", "perfil__cidade")
    fields = ("perfil", "tipo", "descricao", "contato", "criado_em", "prazo_ate", "status", "resposta",
              "decidido_por", "decidido_em", "demo")  # fmt: skip
    readonly_fields = (
        "perfil",
        "tipo",
        "descricao",
        "contato",
        "criado_em",
        "decidido_por",
        "decidido_em",
        "demo",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Pedidos chegam pela ficha pública (G3)."""
        return False

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
