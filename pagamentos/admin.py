"""Admin do app pagamentos: faturas (painel de cobrança, confirmar/recusar/cancelar) e textos dos e-mails."""

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from core.admin_acoes import tela_motivo
from pagamentos.forms import ConfirmarPagamentoForm
from pagamentos.models import Fatura, ModeloEmailCobranca
from pagamentos.services import cancelar_fatura, confirmar_pagamento, recusar_comprovante, resumo_cobranca
from pagamentos.views import resposta_do_comprovante


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
        """Tela intermediária com forma de pagamento e observação; depois baixa cada fatura em aberto."""
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
