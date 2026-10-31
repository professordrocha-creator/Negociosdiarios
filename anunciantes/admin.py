"""Admin de anunciantes: lista com filtros, verificação e ações Aprovar/Suspender com motivo."""

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from anunciantes.forms import AnuncianteAdminForm, MotivoStatusForm
from anunciantes.models import Anunciante, SolicitacaoCidade
from anunciantes.services import (
    aprovar,
    devolver_confianca,
    enviar_imagem_loja,
    liberar_cidade_da_solicitacao,
    recusar_solicitacao,
    retirar_confianca,
    suspender,
    tem_confianca_para_o_admin,
)
from core.models import Cidade


class AprovacaoFilter(admin.SimpleListFilter):
    """Separa os pendentes: só quem já confirmou o e-mail está pronto para aprovação."""

    title = "aprovação"
    parameter_name = "aprovacao"

    def lookups(self, request, model_admin):
        """Opções do filtro."""
        return [
            ("aguardando", "Aguardando aprovação (e-mail confirmado)"),
            ("sem_confirmacao", "Pendente: e-mail ainda não confirmado"),
        ]

    def queryset(self, request, queryset):
        """Aplica a opção escolhida."""
        pendentes = queryset.filter(status=Anunciante.Status.PENDENTE)
        if self.value() == "aguardando":
            return pendentes.filter(usuario__email_confirmado_em__isnull=False)
        if self.value() == "sem_confirmacao":
            return pendentes.filter(usuario__email_confirmado_em__isnull=True)
        return queryset


@admin.register(Anunciante)
class AnuncianteAdmin(SimpleHistoryAdmin):
    """Anunciantes (lojas). A situação só muda pelas ações, que exigem motivo e ficam no histórico."""

    list_display = (
        "nome_publico",
        "tipo",
        "documento_tipo",
        "documento_numero",
        "cidade",
        "status",
        "email_confirmado",
        "demo",
    )
    list_filter = (AprovacaoFilter, "status", "tipo", "demo")
    search_fields = ("nome_publico", "slug", "documento_numero", "usuario__email")
    list_select_related = ("cidade", "usuario")
    prepopulated_fields = {"slug": ("nome_publico",)}
    autocomplete_fields = ("usuario",)
    form = AnuncianteAdminForm
    readonly_fields = (
        "status",
        "motivo_status",
        "demo",
        "criado_em",
        "atualizado_em",
        "previa_imagens",
        "plano_e_assinatura",
        "situacao_da_confianca",
    )
    fieldsets = (
        ("Loja", {"fields": ("usuario", "tipo", "nome_publico", "slug", "cidade")}),
        ("Verificação", {"fields": ("documento_tipo", "documento_numero", "status", "motivo_status")}),
        ("Plano", {"fields": ("plano_e_assinatura",)}),
        ("Publicação por confiança", {"fields": ("situacao_da_confianca",)}),
        (
            "Página da loja",
            {
                "fields": (
                    "previa_imagens",
                    "logo_envio",
                    "capa_envio",
                    "sobre",
                    "endereco_publico",
                    "mostrar_no_mapa",
                    "horario",
                    "instagram",
                    "site",
                )
            },
        ),
        ("Contato público", {"fields": ("whatsapp", "email_publico")}),
        ("Avançado", {"classes": ("collapse",), "fields": ("sigla", "cor")}),
        ("Registro", {"fields": ("demo", "criado_em", "atualizado_em")}),
    )
    actions = [
        "suspender_selecionados",
        "retirar_confianca_selecionados",
        "devolver_confianca_selecionados",
        "aprovar_selecionados",  # exceção: o caminho normal é "Cadastros aguardando" (Parte 4)
    ]

    change_form_template = "admin/anunciantes/anunciante/change_form.html"

    def change_view(self, request: HttpRequest, object_id: str, form_url: str = "", extra_context=None):
        """Topo da ficha (Parte 4): o pedido de plano aguardando, com Aprovar (um clique) e Recusar."""
        from pagamentos.services import pedido_em_aberto

        anunciante = self.get_object(request, object_id)
        pedido = pedido_em_aberto(anunciante) if anunciante else None
        if pedido is not None and request.user.has_perm("pagamentos.change_pedidoaguardando"):
            extra_context = {
                **(extra_context or {}),
                "pedido": pedido,
                "url_aprovar": reverse("admin:pagamentos_pedidoaguardando_aprovar_rapido", args=[pedido.pk]),
                "url_ajustar": reverse("admin:pagamentos_pedidoaguardando_aprovar", args=[pedido.pk]),
                "url_reenviar": reverse("admin:pagamentos_pedidoaguardando_reenviar", args=[pedido.pk]),
                "url_recusar": reverse("admin:pagamentos_pedidoaguardando_changelist")
                + f"?q={pedido.codigo}",
                "url_ficha": request.get_full_path(),
            }
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request: HttpRequest, obj: Anunciante, form, change: bool) -> None:
        """Salva a ficha e, se a equipe mandou logo ou capa, processa como o painel (Celery: WebP, sem
        EXIF)."""
        super().save_model(request, obj, form, change)
        for tipo in ("logo", "capa"):
            envio = form.cleaned_data.get(f"{tipo}_envio")
            if envio:
                enviar_imagem_loja(obj, tipo, envio)
                self.message_user(request, f"{tipo.capitalize()} enviado: em instantes aparece processado.")

    @admin.display(description="plano e assinatura")
    def plano_e_assinatura(self, anunciante: Anunciante) -> str:
        """Plano atual e situação da assinatura (só leitura), com o link para a assinatura (onde se edita)."""
        from planos.services import assinatura_de

        assinatura = assinatura_de(anunciante) if anunciante.pk else None
        if assinatura is None:
            return "Sem assinatura."
        return format_html(
            '{} · {} · vence em {} · <b>{}</b> · <a href="{}">abrir a assinatura</a>',
            assinatura.plano.nome,
            assinatura.get_periodicidade_display(),
            assinatura.vencimento.strftime("%d/%m/%Y"),
            assinatura.get_situacao_display(),
            reverse("admin:planos_assinatura_change", args=[assinatura.pk]),
        )

    @admin.display(description="situação")
    def situacao_da_confianca(self, anunciante: Anunciante) -> str:
        """Se os anúncios novos publicam direto ou passam pela fila, e por quê."""
        if not anunciante.pk:
            return "—"
        return tem_confianca_para_o_admin(anunciante)

    @admin.action(description="Retirar confiança (anúncios novos vão para a fila)", permissions=["change"])
    def retirar_confianca_selecionados(self, request: HttpRequest, queryset: QuerySet[Anunciante]):
        """Tela do motivo; depois a loja passa a ser moderada à mão."""
        from core.admin_acoes import tela_motivo

        return tela_motivo(
            self,
            request,
            queryset,
            "retirar_confianca_selecionados",
            "Retirar a confiança",
            True,
            lambda anunciante, por, motivo: retirar_confianca(anunciante, motivo, por),
            "{n} loja(s) sem confiança: os anúncios novos vão para a fila.",
        )

    @admin.action(
        description="Devolver confiança (anúncios novos voltam a publicar direto)", permissions=["change"]
    )
    def devolver_confianca_selecionados(self, request: HttpRequest, queryset: QuerySet[Anunciante]):
        """Tela do motivo (opcional); depois os anúncios novos seguem as regras normais."""
        from core.admin_acoes import tela_motivo

        return tela_motivo(
            self,
            request,
            queryset,
            "devolver_confianca_selecionados",
            "Devolver a confiança",
            False,
            devolver_confianca,
            "{n} loja(s) com a confiança devolvida.",
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Campos de URL: endereço sem esquema vira https:// (padrão do Django 6)."""
        if isinstance(db_field, models.URLField):
            kwargs["assume_scheme"] = "https"
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """No campo cidade, só cidades liberadas de estados liberados."""
        if db_field.name == "cidade":
            kwargs["queryset"] = Cidade.objects.filter(liberada=True, uf__liberado=True).select_related("uf")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="logo e capa")
    def previa_imagens(self, anunciante: Anunciante) -> str:
        """Logo (96 px) e capa (800 px) já processados, ou o aviso de processamento."""
        if anunciante.imagens_processando:
            return "Imagens sendo processadas pelo Celery."
        if not (anunciante.logo_mini or anunciante.capa_media):
            return "Sem logo e sem capa (a página usa o monograma e a cor da loja)."
        return format_html(
            '<img src="{}" width="64" height="64" alt="logo"> <img src="{}" height="64" alt="capa">',
            anunciante.logo_mini.url if anunciante.logo_mini else "",
            anunciante.capa_media.url if anunciante.capa_media else "",
        )

    @admin.display(description="e-mail confirmado", boolean=True, ordering="usuario__email_confirmado_em")
    def email_confirmado(self, anunciante: Anunciante) -> bool:
        """O anunciante já clicou no link de confirmação?"""
        return anunciante.usuario.email_confirmado_em is not None

    def has_delete_permission(self, request: HttpRequest, obj: Anunciante | None = None) -> bool:
        """Anunciante nunca é apagado pelo admin (exclusão lógica: suspender)."""
        return False

    @admin.action(
        description="Exceção: aprovar só a loja, sem plano (o normal é Cadastros aguardando)",
        permissions=["change"],
    )
    def aprovar_selecionados(self, request: HttpRequest, queryset: QuerySet[Anunciante]):
        """Exceção (loja sem pedido de plano): pede o motivo (opcional) e aprova só a loja. O caminho normal é
        "Cadastros aguardando", que aprova loja, pagamento e plano de uma vez."""
        return self._mudar_com_motivo(request, queryset, "aprovar_selecionados", aprovar, obrigatorio=False)

    @admin.action(description="Suspender selecionados (motivo obrigatório)", permissions=["change"])
    def suspender_selecionados(self, request: HttpRequest, queryset: QuerySet[Anunciante]):
        """Pede o motivo (obrigatório) e suspende."""
        return self._mudar_com_motivo(
            request, queryset, "suspender_selecionados", suspender, obrigatorio=True
        )

    def _mudar_com_motivo(self, request, queryset, acao: str, servico, obrigatorio: bool):
        """Primeiro mostra a tela do motivo; ao confirmar, aplica o serviço em cada anunciante."""
        form = MotivoStatusForm(request.POST if "aplicar" in request.POST else None, obrigatorio=obrigatorio)
        if "aplicar" in request.POST and form.is_valid():
            feitos = 0
            for anunciante in queryset:
                try:
                    servico(anunciante, request.user, form.cleaned_data["motivo"])
                    feitos += 1
                except ValueError as erro:  # ex.: aprovar quem não confirmou o e-mail
                    self.message_user(request, str(erro), messages.WARNING)
            verbo = "aprovado(s)" if servico is aprovar else "suspenso(s)"
            self.message_user(
                request, f"{feitos} anunciante(s) {verbo}; e-mail de aviso enviado.", messages.SUCCESS
            )
            return None
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Aprovar anunciantes" if servico is aprovar else "Suspender anunciantes",
            "form": form,
            "itens": [f"{a.nome_publico} ({a.get_status_display()})" for a in queryset],
            "ids": [a.pk for a in queryset],
            "url_voltar": reverse("admin:anunciantes_anunciante_changelist"),
            "acao": acao,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/anunciantes/motivo_status.html", contexto)


@admin.register(SolicitacaoCidade)
class SolicitacaoCidadeAdmin(admin.ModelAdmin):
    """Pedidos de cidade ainda não atendida: "Liberar cidade" ou "Recusar" (com motivo e e-mail)."""

    list_display = ("cidade", "anunciante", "status", "criado_em", "decidido_por", "demo")
    list_filter = ("status", "demo", "cidade__uf")
    search_fields = ("cidade__nome", "anunciante__nome_publico", "anunciante__usuario__email")
    list_select_related = ("cidade", "anunciante", "decidido_por")
    readonly_fields = (
        "anunciante",
        "cidade",
        "status",
        "motivo",
        "decidido_por",
        "decidido_em",
        "criado_em",
        "demo",
    )
    actions = ["liberar_cidades_selecionadas", "recusar_selecionadas"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Solicitações nascem do cadastro, nunca à mão."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: SolicitacaoCidade | None = None) -> bool:
        """Nunca apagadas: ficam como registro da decisão."""
        return False

    @admin.action(description="Liberar a cidade das solicitações selecionadas", permissions=["change"])
    def liberar_cidades_selecionadas(self, request: HttpRequest, queryset: QuerySet[SolicitacaoCidade]):
        """Libera cada cidade pedida; todas as solicitações pendentes dela ficam atendidas."""
        atendidas = 0
        for solicitacao in queryset.filter(status=SolicitacaoCidade.Status.PENDENTE).select_related("cidade"):
            solicitacao.refresh_from_db()
            if solicitacao.status == SolicitacaoCidade.Status.PENDENTE:  # outra da mesma cidade já liberou
                atendidas += liberar_cidade_da_solicitacao(solicitacao, request.user)
        self.message_user(
            request,
            f"{atendidas} solicitação(ões) atendida(s). Agora aprove as lojas em Anunciantes.",
            messages.SUCCESS,
        )

    @admin.action(description="Recusar selecionadas (motivo enviado por e-mail)", permissions=["change"])
    def recusar_selecionadas(self, request: HttpRequest, queryset: QuerySet[SolicitacaoCidade]):
        """Pede o motivo e recusa, avisando cada anunciante por e-mail."""
        pendentes = queryset.filter(status=SolicitacaoCidade.Status.PENDENTE)
        form = MotivoStatusForm(request.POST if "aplicar" in request.POST else None, obrigatorio=True)
        if "aplicar" in request.POST and form.is_valid():
            for solicitacao in pendentes:
                recusar_solicitacao(solicitacao, request.user, form.cleaned_data["motivo"])
            self.message_user(
                request, f"{pendentes.count()} solicitação(ões) recusada(s); anunciantes avisados."
            )
            return None
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Recusar solicitações de cidade",
            "form": form,
            "itens": [str(s) for s in pendentes],
            "ids": [s.pk for s in pendentes],
            "url_voltar": reverse("admin:anunciantes_solicitacaocidade_changelist"),
            "acao": "recusar_selecionadas",
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/anunciantes/motivo_status.html", contexto)
