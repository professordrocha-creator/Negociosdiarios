"""Admin do app moderacao: fila de denúncias (aceitar pausando ou removendo, ou descartar), com histórico.

A origem (resumo do dia) nunca aparece; o e-mail de quem denunciou só para a equipe com permissão.
"""

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from core.admin_acoes import tela_motivo
from moderacao import services
from moderacao.forms import DecisaoForm
from moderacao.models import Denuncia


@admin.register(Denuncia)
class DenunciaAdmin(SimpleHistoryAdmin):
    """Fila: pendentes primeiro, as mais antigas no topo. A decisão vale para as pendentes do anúncio."""

    list_display = ("criado_em", "anuncio_link", "motivo", "situacao", "situacao_do_anuncio", "acao", "demo")
    list_filter = ("situacao", "motivo", "demo")
    search_fields = ("anuncio__codigo", "anuncio__titulo")
    list_select_related = ("anuncio",)
    date_hierarchy = "criado_em"
    readonly_fields = (
        "anuncio_link",
        "motivo",
        "texto",
        "email",
        "situacao",
        "acao",
        "motivo_decisao",
        "decidido_por",
        "decidido_em",
        "criado_em",
        "demo",
    )
    fields = readonly_fields
    actions = ["aceitar_acao", "descartar_acao"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Denúncias chegam pelo site."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Denuncia | None = None) -> bool:
        """Registro da moderação: não se apaga."""
        return False

    @admin.display(description="anúncio", ordering="anuncio__codigo")
    def anuncio_link(self, denuncia: Denuncia) -> str:
        """Código com link para a página pública (abre em outra aba)."""
        from anuncios.services import url_publica

        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{} · {}</a>',
            url_publica(denuncia.anuncio),
            denuncia.anuncio.codigo,
            denuncia.anuncio.titulo,
        )

    @admin.display(description="anúncio está")
    def situacao_do_anuncio(self, denuncia: Denuncia) -> str:
        """Situação atual do anúncio (com "em revisão" se a pausa foi automática)."""
        anuncio = denuncia.anuncio
        if (
            anuncio.pausado_por == anuncio.PausadoPor.DENUNCIA
            and anuncio.situacao == anuncio.Situacao.PAUSADO
        ):
            return "Em revisão (fora do ar)"
        return anuncio.get_situacao_display()

    @admin.action(
        description="Aceitar: pausar ou remover o anúncio (avisa o anunciante)", permissions=["change"]
    )
    def aceitar_acao(self, request: HttpRequest, queryset: QuerySet[Denuncia]):
        """Tela com a ação (pausar/remover) e o motivo; depois decide cada anúncio uma vez."""
        pendentes = queryset.filter(situacao=Denuncia.Situacao.PENDENTE).select_related("anuncio")
        form = DecisaoForm(request.POST if "aplicar" in request.POST else None)
        if "aplicar" in request.POST and form.is_valid():
            feitos, vistos = 0, set()
            for denuncia in pendentes:
                if denuncia.anuncio_id in vistos:
                    continue
                vistos.add(denuncia.anuncio_id)
                try:
                    services.aceitar(
                        denuncia, request.user, form.cleaned_data["acao"], form.cleaned_data["motivo"]
                    )
                    feitos += 1
                except ValueError as erro:
                    self.message_user(request, str(erro), messages.WARNING)
            self.message_user(
                request, f"{feitos} anúncio(s) decidido(s); anunciantes avisados.", messages.SUCCESS
            )
            return None
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Aceitar denúncias",
            "form": form,
            "itens": [str(d) for d in pendentes],
            "ids": [d.pk for d in pendentes],
            "url_voltar": reverse("admin:moderacao_denuncia_changelist"),
            "acao": "aceitar_acao",
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/moderacao/decisao.html", contexto)

    @admin.action(
        description="Descartar (se estava em revisão, o anúncio volta ao ar)", permissions=["change"]
    )
    def descartar_acao(self, request: HttpRequest, queryset: QuerySet[Denuncia]):
        """Motivo opcional (fica só no registro interno)."""

        def descartar_uma(denuncia, por, motivo):
            if denuncia.situacao == Denuncia.Situacao.PENDENTE:
                denuncia.refresh_from_db()
                if denuncia.situacao == Denuncia.Situacao.PENDENTE:  # outra do mesmo anúncio já decidiu
                    services.descartar(denuncia, por, motivo)

        return tela_motivo(
            self,
            request,
            queryset.filter(situacao=Denuncia.Situacao.PENDENTE),
            "descartar_acao",
            "Descartar denúncias",
            False,
            descartar_uma,
            "{n} denúncia(s) descartada(s).",
        )
