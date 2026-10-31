"""Admin do app pagamentos: faturas (painel de cobrança, confirmar/recusar/cancelar), textos dos e-mails e,
no lote 3B, "Cadastros aguardando" (aprovar numa tela só) e a "Configuração do Pix"."""

from decimal import Decimal

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db.models import Case, QuerySet, Value, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from simple_history.admin import SimpleHistoryAdmin

from core.admin_acoes import tela_motivo
from core.services import configuracao
from core.templatetags.nd import cnpj
from pagamentos.forms import AprovarPedidoForm, ConfiguracaoPixForm, ConfirmarPagamentoForm
from pagamentos.models import ConfiguracaoPix, Fatura, ModeloEmailCobranca, PedidoAguardando
from pagamentos.services import (
    aprovar_pedido_pago,
    cancelar_fatura,
    confirmar_pagamento,
    datas_sugeridas,
    gerar_pix,
    marcar_nao_pago,
    pedidos_aguardando,
    recusar_comprovante,
    recusar_pedido_pago,
    resumo_cobranca,
)
from pagamentos.views import resposta_do_comprovante
from planos.models import Assinatura


@admin.register(Fatura)
class FaturaAdmin(SimpleHistoryAdmin):
    """Faturas: filtros por situação e vencimento, painel de cobrança e as decisões da equipe.

    A situação só muda pelas ações (confirmar, recusar comprovante, cancelar) e pela rotina diária. Nada
    se apaga. O comprovante abre por uma URL do admin que confere a permissão (nunca pela mídia pública).
    """

    list_display = (
        "codigo",
        "cliente",
        "descricao",
        "valor",
        "vencimento",
        "situacao",
        "pago_em",
        "tem_comprovante",
        "demo",
    )
    list_filter = ("situacao", "vencimento", "forma", "demo")
    search_fields = (
        "codigo",
        "assinatura__anunciante__nome_publico",
        "assinatura__anunciante__usuario__email",
        "campanha__nome",
        "campanha__patrocinador__nome",
    )
    list_select_related = ("assinatura__anunciante", "campanha__patrocinador")
    date_hierarchy = "vencimento"
    change_list_template = "admin/pagamentos/fatura/change_list.html"
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "codigo",
                    "assinatura",
                    "campanha",
                    "link_de_pagamento",
                    "descricao",
                    "competencia",
                    "periodo_fim",
                    "valor",
                    "vencimento",
                )
            },
        ),
        (
            "Pagamento",
            {
                "fields": (
                    "situacao",
                    "link_boleto",
                    "ver_comprovante",
                    "comprovante_enviado_em",
                    "motivo_recusa",
                    "forma",
                    "pago_em",
                    "confirmado_por",
                )
            },
        ),
        ("Anotações", {"fields": ("observacao", "avisos_enviados", "demo", "criado_em", "atualizado_em")}),
    )
    actions = ["confirmar_pagamento_acao", "recusar_comprovante_acao", "cancelar_acao"]

    def get_readonly_fields(self, request: HttpRequest, obj: Fatura | None = None) -> list[str]:
        """Editáveis: link do boleto e observação; o valor só enquanto a fatura está aberta (desconto)."""
        editaveis = {"link_boleto", "observacao"}
        if obj is not None and obj.situacao == Fatura.Situacao.ABERTA:
            editaveis.add("valor")
        todos = [campo for _, opcoes in self.fieldsets for campo in opcoes["fields"]]
        return [campo for campo in todos if campo not in editaveis]

    def formfield_for_dbfield(self, db_field, request: HttpRequest, **kwargs):
        """Link do boleto digitado sem esquema vira https:// (o padrão do Django 6)."""
        if db_field.name == "link_boleto":
            kwargs["assume_scheme"] = "https"
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Faturas nascem da rotina diária ou do "Registrar pagamento manual" da assinatura."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Fatura | None = None) -> bool:
        """Registro financeiro: nunca se apaga (cancele, com motivo)."""
        return False

    @admin.display(description="cliente")
    def cliente(self, fatura: Fatura) -> str:
        """A loja (assinatura) ou o patrocinador (campanha de publicidade)."""
        return fatura.cliente_nome

    @admin.display(description="link de pagamento")
    def link_de_pagamento(self, fatura: Fatura) -> str:
        """Endereço completo onde o cliente paga (para mandar pelo WhatsApp a quem pedir)."""
        if not fatura.pk:
            return "—"
        url = settings.SITE_URL + fatura.link_pagamento
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    @admin.display(description="comprovante", boolean=True)
    def tem_comprovante(self, fatura: Fatura) -> bool:
        """Tem comprovante enviado."""
        return bool(fatura.comprovante)

    @admin.display(description="comprovante")
    def ver_comprovante(self, fatura: Fatura) -> str:
        """Link para abrir o comprovante (URL do admin com checagem de permissão)."""
        if not fatura.comprovante:
            return "—"
        url = reverse("admin:pagamentos_fatura_comprovante", args=[fatura.pk])
        tipo = "PDF" if fatura.comprovante_e_pdf else "imagem"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Abrir comprovante ({})</a>', url, tipo
        )

    def get_urls(self):
        """Painel de cobrança e comprovante (com permissão de ver faturas)."""
        extras = [
            path("painel/", self.admin_site.admin_view(self.painel), name="pagamentos_fatura_painel"),
            path(
                "<int:pk>/comprovante/",
                self.admin_site.admin_view(self.comprovante),
                name="pagamentos_fatura_comprovante",
            ),
        ]
        return extras + super().get_urls()

    def painel(self, request: HttpRequest) -> TemplateResponse:
        """A receber no mês, recebido no mês, vencendo em 7 dias, vencidas e aguardando confirmação."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        lista = reverse("admin:pagamentos_fatura_changelist")
        resumo = resumo_cobranca()
        cartoes = [
            ("A receber no mês", "a_receber_mes"),
            ("Recebido no mês", "recebido_mes"),
            ("Vencendo em 7 dias", "vencendo_7_dias"),
            ("Vencidas", "vencidas"),
            ("Aguardando confirmação", "aguardando"),
        ]
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Painel de cobrança",
            "opts": self.model._meta,
            "hoje": timezone.localdate(),
            "cartoes": [
                {"titulo": titulo, **resumo[chave], "url": f"{lista}?{resumo[chave]['filtro']}"}
                for titulo, chave in cartoes
            ],
        }
        return TemplateResponse(request, "admin/pagamentos/painel_cobranca.html", contexto)

    def comprovante(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Abre o comprovante para a equipe com permissão de ver faturas."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        return resposta_do_comprovante(get_object_or_404(Fatura, pk=pk))

    @admin.action(
        description="Confirmar pagamento (renova a assinatura e reativa os anúncios)", permissions=["change"]
    )
    def confirmar_pagamento_acao(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Tela intermediária com forma de pagamento e observação; depois baixa cada fatura em aberto.

        Pedido de cadastro novo (plano ainda aguardando o primeiro pagamento) fica de fora: ele é aprovado em
        "Cadastros aguardando", que aprova a loja e ativa o plano de uma vez (Parte 4)."""
        novos = queryset.filter(assinatura__situacao=Assinatura.Situacao.PENDENTE)
        if novos.exists():
            self.message_user(
                request,
                format_html(
                    '{} pedido(s) de cadastro novo ficaram de fora: aprove em <a href="{}">Cadastros '
                    "aguardando</a> (aprova a loja e ativa o plano de uma vez).",
                    novos.count(),
                    reverse("admin:pagamentos_pedidoaguardando_changelist"),
                ),
                messages.WARNING,
            )
            queryset = queryset.exclude(pk__in=novos.values("pk"))
            if not queryset.exists():
                return None
        form = ConfirmarPagamentoForm(request.POST if "aplicar" in request.POST else None)
        if "aplicar" in request.POST and form.is_valid():
            feitos = 0
            for fatura in queryset:
                try:
                    confirmar_pagamento(
                        fatura, request.user, form.cleaned_data["forma"], form.cleaned_data["observacao"]
                    )
                    feitos += 1
                except ValueError as erro:
                    self.message_user(request, str(erro), messages.WARNING)
            self.message_user(
                request, f"{feitos} pagamento(s) confirmado(s); anunciantes avisados.", messages.SUCCESS
            )
            return None
        opts = self.model._meta
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Confirmar pagamento",
            "form": form,
            "itens": [str(fatura) for fatura in queryset],
            "ids": [fatura.pk for fatura in queryset],
            "url_voltar": reverse("admin:pagamentos_fatura_changelist"),
            "acao": "confirmar_pagamento_acao",
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "opts": opts,
        }
        return TemplateResponse(request, "admin/pagamentos/confirmar_pagamento.html", contexto)

    @admin.action(description="Recusar comprovante (motivo enviado por e-mail)", permissions=["change"])
    def recusar_comprovante_acao(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Pede o motivo; a fatura volta a aberta ou vencida."""
        return tela_motivo(
            self,
            request,
            queryset,
            "recusar_comprovante_acao",
            "Recusar comprovante",
            True,
            recusar_comprovante,
            "{n} comprovante(s) recusado(s); anunciantes avisados.",
        )

    @admin.action(description="Cancelar fatura (com motivo)", permissions=["change"])
    def cancelar_acao(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Cancela faturas ainda não pagas (fica no histórico)."""
        return tela_motivo(
            self,
            request,
            queryset,
            "cancelar_acao",
            "Cancelar faturas",
            True,
            cancelar_fatura,
            "{n} fatura(s) cancelada(s).",
        )


@admin.register(ModeloEmailCobranca)
class ModeloEmailCobrancaAdmin(SimpleHistoryAdmin):
    """Textos dos e-mails de cobrança (régua e decisões), editáveis sem deploy. Os e-mails são fixos."""

    list_display = ("chave", "assunto", "ativo", "atualizado_em")
    list_editable = ("ativo",)
    readonly_fields = ("chave", "atualizado_em")
    fields = ("chave", "assunto", "corpo", "ativo", "atualizado_em")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Cada e-mail é disparado por uma regra do sistema: os registros vêm da migration."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ModeloEmailCobranca | None = None) -> bool:
        """Para não mandar um e-mail, desmarque "enviar"."""
        return False


# --- Lote 3B: Cadastros aguardando e Configuração do Pix ------------------------------------------------


class TipoPedidoFiltro(admin.SimpleListFilter):
    """Pedido novo (loja sem plano ativo) ou renovação (loja que já tem plano); usado pelo Painel de hoje."""

    title = "tipo"
    parameter_name = "tipo"
    NOVOS = (Assinatura.Situacao.PENDENTE, Assinatura.Situacao.CANCELADA)

    def lookups(self, request: HttpRequest, model_admin):
        """As duas opções do filtro."""
        return (("novo", "Cadastro novo"), ("renovacao", "Renovação"))

    def queryset(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Filtra pela situação da assinatura."""
        if self.value() == "novo":
            return queryset.filter(assinatura__situacao__in=self.NOVOS)
        if self.value() == "renovacao":
            return queryset.exclude(assinatura__situacao__in=self.NOVOS)
        return queryset


@admin.register(PedidoAguardando)
class PedidoAguardandoAdmin(admin.ModelAdmin):
    """Cadastros aguardando: pedidos pagos pelo Pix esperando a equipe conferir no banco.

    "Aprovar" (primeira coluna) aprova com um clique, com a vigência sugerida, e faz tudo de uma vez: fatura
    paga, vigência, loja aprovada (CRECI/CNPJ conferido) e plano ativo. "ajustar datas" abre a tela da
    vigência para os casos raros. Loja que ainda não confirmou o e-mail não é aprovada: a linha mostra isso
    e o botão "Reenviar link". Ações: Recusar e Marcar como não pago (com motivo).
    Grupos Administrador, Financeiro e Comercial; o comprovante só abre para quem vê as faturas (Financeiro e
    Administrador: pode ter dados de quem pagou).
    """

    list_display = (
        "botao_aprovar",
        "loja",
        "documento",
        "descricao",
        "valor",
        "identificador",
        "pedido_em",
        "situacao_do_pedido",
        "comprovante_do_pedido",
    )
    list_display_links = None
    list_filter = (TipoPedidoFiltro, "situacao")
    search_fields = (
        "codigo",
        "assinatura__anunciante__nome_publico",
        "assinatura__anunciante__usuario__email",
    )
    list_select_related = ("assinatura__anunciante__usuario", "assinatura__plano")
    # Aguardando conferência primeiro (o cliente já disse que pagou), depois os mais antigos.
    ordering = (
        Case(When(situacao=Fatura.Situacao.AGUARDANDO, then=Value(0)), default=Value(1)),
        "criado_em",
    )
    actions = ["recusar_acao", "marcar_nao_pago_acao"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Fatura]:
        """Só os pedidos que esperam a equipe (`pagamentos.services.pedidos_aguardando`)."""
        return pedidos_aguardando().select_related("assinatura__anunciante", "assinatura__plano")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """O pedido nasce na tela Escolher plano (cliente) ou na rotina de faturas."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Registro financeiro: nunca se apaga (recuse, com motivo)."""
        return False

    @admin.display(description="loja")
    def loja(self, fatura: Fatura) -> str:
        """Nome público e situação da loja (pendente = ainda não verificada)."""
        anunciante = fatura.assinatura.anunciante
        return f"{anunciante.nome_publico} ({anunciante.get_status_display().lower()})"

    @admin.display(description="documento")
    def documento(self, fatura: Fatura) -> str:
        """CRECI ou CNPJ, para conferir junto com o pagamento."""
        anunciante = fatura.assinatura.anunciante
        numero = anunciante.documento_numero
        if anunciante.documento_tipo == "cnpj":
            numero = cnpj(numero)
        return f"{anunciante.get_documento_tipo_display()} {numero}"

    @admin.display(description="pedido em", ordering="criado_em")
    def pedido_em(self, fatura: Fatura):
        """Quando o pedido (ou a fatura de renovação) foi criado."""
        return fatura.criado_em

    @admin.display(description="situação")
    def situacao_do_pedido(self, fatura: Fatura) -> str:
        """Aguardando conferência (o cliente tocou em "Já paguei") ou aguardando pagamento."""
        if fatura.situacao == Fatura.Situacao.AGUARDANDO:
            desde = timezone.localtime(fatura.comprovante_enviado_em)
            return f"Aguardando conferência (desde {desde:%d/%m %H:%M})"
        return "Aguardando pagamento"

    @admin.display(description="comprovante")
    def comprovante_do_pedido(self, fatura: Fatura) -> str:
        """Link do comprovante (a coluna só aparece para quem vê faturas: `get_list_display`)."""
        if not fatura.comprovante:
            return "—"
        url = reverse("admin:pagamentos_fatura_comprovante", args=[fatura.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">abrir</a>', url)

    @admin.display(description="identificador do Pix", ordering="codigo")
    def identificador(self, fatura: Fatura) -> str:
        """O que aparece no extrato do banco (txid do Pix)."""
        return fatura.identificador_pix

    @admin.display(description="aprovar")
    def botao_aprovar(self, fatura: Fatura) -> str:
        """Aprovar com um clique (botão do próprio formulário da lista, enviado para outro endereço com
        `formaction`) e o link "ajustar datas". Sem e-mail confirmado: o aviso e "Reenviar link"."""
        usuario = fatura.assinatura.anunciante.usuario
        if not usuario.email_confirmado_em:
            return format_html(
                "<small>Aguardando o cliente confirmar o e-mail.</small><br>"
                '<button type="submit" class="button" formaction="{}" formmethod="post">'
                "Reenviar link</button>",
                reverse("admin:pagamentos_pedidoaguardando_reenviar", args=[fatura.pk]),
            )
        return format_html(
            '<button type="submit" class="button default" formaction="{}" formmethod="post">Aprovar</button>'
            '<br><small><a href="{}">ajustar datas</a></small>',
            reverse("admin:pagamentos_pedidoaguardando_aprovar_rapido", args=[fatura.pk]),
            reverse("admin:pagamentos_pedidoaguardando_aprovar", args=[fatura.pk]),
        )

    def get_list_display(self, request: HttpRequest):
        """Sem a coluna do comprovante para quem não vê faturas (Comercial): pode ter dados de quem pagou."""
        if request.user.has_perm("pagamentos.view_fatura"):
            return self.list_display
        return tuple(coluna for coluna in self.list_display if coluna != "comprovante_do_pedido")

    def get_urls(self):
        """Aprovar com um clique, a tela "ajustar datas" e o reenvio do link de confirmação."""
        protegida = self.admin_site.admin_view
        extras = [
            path("<int:pk>/aprovar/", protegida(self.aprovar), name="pagamentos_pedidoaguardando_aprovar"),
            path(
                "<int:pk>/aprovar-agora/",
                protegida(require_POST(self.aprovar_rapido)),
                name="pagamentos_pedidoaguardando_aprovar_rapido",
            ),
            path(
                "<int:pk>/reenviar-link/",
                protegida(require_POST(self.reenviar_link)),
                name="pagamentos_pedidoaguardando_reenviar",
            ),
        ]
        return extras + super().get_urls()

    def _voltar(self, request: HttpRequest) -> HttpResponse:
        """Volta para onde o botão estava (lista, ficha da loja ou painel de hoje), só dentro do site."""
        destino = request.POST.get("next") or request.GET.get("next") or ""
        if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
            return redirect(destino)
        return redirect("admin:pagamentos_pedidoaguardando_changelist")

    def aprovar_rapido(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Aprovar com um clique: vigência sugerida (`datas_sugeridas`), sem motivo. Faz tudo de uma vez:
        fatura paga, loja aprovada (CRECI/CNPJ conferido) e plano ativo; o cliente recebe um e-mail."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        fatura = get_object_or_404(self.get_queryset(request), pk=pk)
        inicio, fim = datas_sugeridas(fatura)
        try:
            aprovar_pedido_pago(fatura, request.user, inicio, fim)
        except ValueError as erro:
            self.message_user(request, str(erro), messages.ERROR)
        else:
            self.message_user(
                request,
                f"{fatura.codigo} aprovado: {fatura.assinatura.anunciante.nome_publico} com plano ativo até "
                f"{fim:%d/%m/%Y}. Cliente avisado por e-mail.",
                messages.SUCCESS,
            )
        return self._voltar(request)

    def reenviar_link(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Manda um link novo de confirmação de e-mail ao cliente do pedido (se ainda não confirmou)."""
        from anunciantes.services import enviar_confirmacao

        if not self.has_change_permission(request):
            raise PermissionDenied
        fatura = get_object_or_404(self.get_queryset(request), pk=pk)
        usuario = fatura.assinatura.anunciante.usuario
        if usuario.email_confirmado_em:
            self.message_user(request, "Este cliente já confirmou o e-mail.", messages.INFO)
        else:
            enviar_confirmacao(usuario)
            self.message_user(request, "Link de confirmação reenviado ao cliente.", messages.SUCCESS)
        return self._voltar(request)

    def aprovar(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Confere as datas sugeridas (a equipe ajusta) e aprova: fatura paga, vigência, loja e plano."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        fatura = get_object_or_404(self.get_queryset(request), pk=pk)
        inicio, fim = datas_sugeridas(fatura)
        form = AprovarPedidoForm(request.POST or None, initial={"inicio": inicio, "fim": fim})
        if request.method == "POST" and form.is_valid():
            try:
                aprovar_pedido_pago(
                    fatura,
                    request.user,
                    form.cleaned_data["inicio"],
                    form.cleaned_data["fim"],
                    form.cleaned_data["observacao"],
                )
            except ValueError as erro:
                form.add_error(None, str(erro))
            else:
                anunciante = fatura.assinatura.anunciante
                self.message_user(
                    request,
                    f"{fatura.codigo} aprovado: {anunciante.nome_publico} com plano ativo até "
                    f"{form.cleaned_data['fim']:%d/%m/%Y}. Cliente avisado por e-mail.",
                    messages.SUCCESS,
                )
                return redirect("admin:pagamentos_pedidoaguardando_changelist")
        anunciante = fatura.assinatura.anunciante
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Aprovar {fatura.codigo}",
            "opts": self.model._meta,
            "fatura": fatura,
            "anunciante": anunciante,
            "documento": self.documento(fatura),
            "situacao": self.situacao_do_pedido(fatura),
            "ve_comprovante": request.user.has_perm("pagamentos.view_fatura"),
            "dias": fatura.assinatura.plano.dias(fatura.assinatura.periodicidade),
            "form": form,
            "url_voltar": reverse("admin:pagamentos_pedidoaguardando_changelist"),
        }
        return TemplateResponse(request, "admin/pagamentos/aprovar_pedido.html", contexto)

    @admin.action(description="Recusar pedido (cancela; motivo enviado por e-mail)", permissions=["change"])
    def recusar_acao(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Pede o motivo e cancela cada pedido."""
        return tela_motivo(
            self,
            request,
            queryset,
            "recusar_acao",
            "Recusar pedidos",
            True,
            recusar_pedido_pago,
            "{n} pedido(s) recusado(s); clientes avisados.",
        )

    @admin.action(
        description="Marcar como não pago (volta a aguardar pagamento; motivo por e-mail)",
        permissions=["change"],
    )
    def marcar_nao_pago_acao(self, request: HttpRequest, queryset: QuerySet[Fatura]):
        """Pede o motivo; o pedido volta a "aguardando pagamento"."""
        return tela_motivo(
            self,
            request,
            queryset,
            "marcar_nao_pago_acao",
            "Marcar como não pago",
            True,
            marcar_nao_pago,
            "{n} pedido(s) marcado(s) como não pago(s); clientes avisados.",
        )


@admin.register(ConfiguracaoPix)
class ConfiguracaoPixAdmin(admin.ModelAdmin):
    """Configuração do Pix (registro único): chave, recebedor e instrução, com a prévia do QR Code.

    Só Administrador e Financeiro (permissão própria); a chave não aparece na tela geral de Configurações.
    """

    form = ConfiguracaoPixForm
    fields = ("pix_chave", "pix_nome", "pix_cidade", "pix_instrucao", "previa_pix")
    readonly_fields = ("previa_pix",)

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Registro único: o menu leva direto ao formulário."""
        return redirect("admin:pagamentos_configuracaopix_change", configuracao().pk)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Só existe um registro (o das Configurações do site)."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """O registro único nunca é apagado."""
        return False

    @admin.display(description="prévia (R$ 1,00)")
    def previa_pix(self, obj: ConfiguracaoPix) -> str:
        """QR Code e copia e cola de teste com os dados salvos (salve para atualizar)."""
        dados = gerar_pix(Decimal("1.00"), "TESTE")
        if dados is None:
            return "Preencha chave, nome e cidade e salve para ver a prévia."
        return format_html(
            '<img src="{}" width="180" height="180" alt="QR Code Pix de teste, R$ 1,00"><br>'
            '<code style="word-break: break-all">{}</code><br>'
            '<span class="help">Teste com o app do banco: deve aparecer o nome do recebedor e R$ 1,00 '
            "(não precisa pagar). Mostra os dados salvos: salve para atualizar.</span>",
            dados["qr_code"],
            dados["copia_e_cola"],
        )
