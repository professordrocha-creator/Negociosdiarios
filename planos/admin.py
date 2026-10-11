"""Admin do app planos: planos (preços e limites), assinaturas e pedidos de troca."""

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from simple_history.admin import SimpleHistoryAdmin

from anunciantes.forms import MotivoStatusForm
from planos.models import Assinatura, PedidoTrocaPlano, Plano
from planos.services import aprovar_pedido, recusar_pedido, registrar_pagamento


def _tela_motivo(
    modeladmin, request, queryset, acao: str, titulo: str, obrigatorio: bool, servico, sucesso: str
):
    """Tela intermediária com motivo (mesmo template das ações de anunciantes)."""
    form = MotivoStatusForm(request.POST if "aplicar" in request.POST else None, obrigatorio=obrigatorio)
    if "aplicar" in request.POST and form.is_valid():
        feitos = 0
        for obj in queryset:
            try:
                servico(obj, request.user, form.cleaned_data["motivo"])
                feitos += 1
            except ValueError as erro:
                modeladmin.message_user(request, str(erro), messages.WARNING)
        modeladmin.message_user(request, sucesso.format(n=feitos), messages.SUCCESS)
        return None
    opts = modeladmin.model._meta
    contexto = {
        **modeladmin.admin_site.each_context(request),
        "title": titulo,
        "form": form,
        "itens": [str(obj) for obj in queryset],
        "ids": [obj.pk for obj in queryset],
        "url_voltar": reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"),
        "acao": acao,
        "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        "opts": opts,
    }
    return TemplateResponse(request, "admin/anunciantes/motivo_status.html", contexto)


@admin.register(Plano)
class PlanoAdmin(SimpleHistoryAdmin):
    """Planos: preço, limite, ordem e "à venda" editáveis direto na lista (histórico de cada mudança)."""

    list_display = ("nome", "limite_anuncios", "preco_mensal", "preco_anual", "ordem", "ativo")
    list_editable = ("limite_anuncios", "preco_mensal", "preco_anual", "ordem", "ativo")
    prepopulated_fields = {"slug": ("nome",)}

    def has_delete_permission(self, request: HttpRequest, obj: Plano | None = None) -> bool:
        """Plano não é apagado (assinaturas dependem dele): desmarque "à venda"."""
        return False


@admin.register(Assinatura)
class AssinaturaAdmin(SimpleHistoryAdmin):
    """Assinaturas: filtro por situação; pagamento manual (com motivo) regulariza o atraso."""

    list_display = ("anunciante", "plano", "periodicidade", "vencimento", "situacao", "demo")
    list_filter = ("situacao", "periodicidade", "plano", "demo")
    search_fields = ("anunciante__nome_publico", "anunciante__usuario__email")
    list_select_related = ("anunciante", "plano")
    autocomplete_fields = ("anunciante",)
    readonly_fields = ("situacao", "demo", "criado_em", "atualizado_em")
    actions = ["registrar_pagamento_manual"]

    def has_delete_permission(self, request: HttpRequest, obj: Assinatura | None = None) -> bool:
        """Assinatura não é apagada (histórico financeiro)."""
        return False

    @admin.action(description="Registrar pagamento manual (renova e reativa)", permissions=["change"])
    def registrar_pagamento_manual(self, request: HttpRequest, queryset: QuerySet[Assinatura]):
        """Baixa manual com motivo/comprovante: renova o vencimento; em atraso volta a ativa."""
        return _tela_motivo(
            self,
            request,
            queryset,
            "registrar_pagamento_manual",
            "Registrar pagamento manual",
            True,
            registrar_pagamento,
            "{n} pagamento(s) registrado(s).",
        )


@admin.register(PedidoTrocaPlano)
class PedidoTrocaPlanoAdmin(admin.ModelAdmin):
    """Pedidos de plano do painel: aprovar (aplica o plano) ou recusar (com motivo). E-mail nos dois."""

    list_display = ("anunciante", "plano_atual", "plano_novo", "periodicidade", "status", "criado_em", "demo")
    list_filter = ("status", "periodicidade", "demo")
    search_fields = ("anunciante__nome_publico", "anunciante__usuario__email")
    list_select_related = ("anunciante", "plano_atual", "plano_novo")
    readonly_fields = (
        "anunciante",
        "plano_atual",
        "plano_novo",
        "periodicidade",
        "status",
        "motivo",
        "decidido_por",
        "decidido_em",
        "criado_em",
        "demo",
    )
    actions = ["aprovar_selecionados", "recusar_selecionados"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Pedidos nascem do painel do anunciante."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: PedidoTrocaPlano | None = None) -> bool:
        """Ficam como registro da decisão."""
        return False

    @admin.action(
        description="Aprovar selecionados (aplica o plano e avisa por e-mail)", permissions=["change"]
    )
    def aprovar_selecionados(self, request: HttpRequest, queryset: QuerySet[PedidoTrocaPlano]):
        """Aprova cada pedido pendente; avisa no caso de downgrade acima do novo limite."""
        feitos = 0
        for pedido in queryset:
            try:
                aprovar_pedido(pedido, request.user)
                feitos += 1
            except ValueError as erro:
                self.message_user(request, str(erro), messages.WARNING)
        self.message_user(request, f"{feitos} pedido(s) aprovado(s); anunciantes avisados.", messages.SUCCESS)

    @admin.action(description="Recusar selecionados (motivo enviado por e-mail)", permissions=["change"])
    def recusar_selecionados(self, request: HttpRequest, queryset: QuerySet[PedidoTrocaPlano]):
        """Pede o motivo e recusa."""
        return _tela_motivo(
            self,
            request,
            queryset.filter(status=PedidoTrocaPlano.Status.PENDENTE),
            "recusar_selecionados",
            "Recusar pedidos de plano",
            True,
            recusar_pedido,
            "{n} pedido(s) recusado(s); anunciantes avisados.",
        )
