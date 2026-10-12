"""Admin do app publicidade: patrocinadores, campanhas (com as peças), painel com CSV e a fatura da campanha.

Nada se apaga (campanha se cancela). Imagens enviadas viram WebP no Celery. A equipe Comercial cadastra e
vende; a cobrança usa a mesma Fatura (Pix estático, comprovante, confirmação no admin de Cobrança).
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from core.services import textos_ajuda
from publicidade import services
from publicidade.forms import BannerForm, CampanhaForm, PeriodoForm
from publicidade.models import Banner, Campanha, Patrocinador
from publicidade.tasks import processar_banner


@admin.register(Patrocinador)
class PatrocinadorAdmin(SimpleHistoryAdmin):
    """Empresas que compram publicidade (contato recebe fatura e lembretes)."""

    list_display = ("nome", "contato_nome", "email", "anunciante", "demo")
    search_fields = ("nome", "email", "cnpj")
    list_filter = ("demo",)
    autocomplete_fields = ("anunciante",)
    readonly_fields = ("demo", "criado_em")

    def has_delete_permission(self, request: HttpRequest, obj: Patrocinador | None = None) -> bool:
        """Registro comercial: não se apaga."""
        return False


class BannerInline(admin.StackedInline):
    """Peças da campanha: imagens (com tamanho e peso da Configuracao na ajuda), textos e link."""

    model = Banner
    form = BannerForm
    extra = 0
    readonly_fields = ("previa",)
    fields = (
        "formato",
        "previa",
        "envio_imagem",
        "envio_imagem_celular",
        "texto_alternativo",
        "titulo",
        "texto",
        "link",
        "ativo",
    )

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Para tirar uma peça do ar, desmarque "ativo" (métricas ficam)."""
        return False

    @admin.display(description="prévia")
    def previa(self, banner: Banner) -> str:
        """Miniatura da imagem processada (ou o aviso de processamento)."""
        if not banner.pk or banner.formato == "nativo":
            return "—"
        if banner.imagem_original or banner.imagem_celular_original:
            return "Processando a imagem enviada… recarregue em instantes."
        if banner.imagem:
            return format_html('<img src="{}" alt="" width="240">', banner.imagem.url)
        return "Sem imagem."


@admin.register(Campanha)
class CampanhaAdmin(SimpleHistoryAdmin):
    """Campanhas: período, posições, cidades, valor e situação; peças na mesma tela; painel e fatura."""

    form = CampanhaForm
    inlines = [BannerInline]
    list_display = ("nome", "patrocinador", "inicio", "fim", "valor", "situacao", "no_ar_hoje", "demo")
    list_filter = ("situacao", "demo")
    search_fields = ("nome", "patrocinador__nome")
    list_select_related = ("patrocinador",)
    autocomplete_fields = ("patrocinador",)
    filter_horizontal = ("cidades",)
    change_list_template = "admin/publicidade/campanha/change_list.html"
    actions = ["gerar_fatura"]

    def has_delete_permission(self, request: HttpRequest, obj: Campanha | None = None) -> bool:
        """Nada se apaga: cancele (as métricas e a fatura ficam)."""
        return False

    @admin.display(description="no ar hoje", boolean=True)
    def no_ar_hoje(self, campanha: Campanha) -> bool:
        """Ativa e dentro do período."""
        return campanha.no_ar()

    def save_related(self, request: HttpRequest, form, formsets, change: bool) -> None:
        """Depois de salvar as peças, manda as imagens novas para o Celery (WebP, sem EXIF)."""
        super().save_related(request, form, formsets, change)
        for banner in form.instance.banners.exclude(imagem_original="", imagem_celular_original=""):
            transaction.on_commit(lambda pk=banner.pk: processar_banner.delay(pk))

    def get_urls(self):
        """Painel de publicidade (e o CSV)."""
        extras = [
            path("painel/", self.admin_site.admin_view(self.painel), name="publicidade_campanha_painel"),
            path(
                "painel.csv",
                self.admin_site.admin_view(self.painel_csv),
                name="publicidade_campanha_painel_csv",
            ),
        ]
        return extras + super().get_urls()

    def _periodo(self, request: HttpRequest):
        """Período pedido (padrão: últimos 30 dias até hoje)."""
        hoje = timezone.localdate()
        form = PeriodoForm(request.GET or None)
        de, ate = hoje - timedelta(days=29), hoje
        if form.is_valid():
            de = form.cleaned_data["de"] or de
            ate = form.cleaned_data["ate"] or ate
        return form, min(de, ate), max(de, ate)

    def painel(self, request: HttpRequest) -> TemplateResponse:
        """Campanhas ativas, a vencer, impressões, cliques e CTR por campanha no período."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        form, de, ate = self._periodo(request)
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Painel de publicidade",
            "opts": self.model._meta,
            "form": form,
            "de": de,
            "ate": ate,
            "ajuda_itens": textos_ajuda("admin_publicidade"),
            "url_csv": reverse("admin:publicidade_campanha_painel_csv")
            + f"?de={de:%Y-%m-%d}&ate={ate:%Y-%m-%d}",
            **services.painel(de, ate),
        }
        return TemplateResponse(request, "admin/publicidade/painel.html", contexto)

    def painel_csv(self, request: HttpRequest) -> HttpResponse:
        """O mesmo painel em CSV (Excel em português: separador ;)."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        _form, de, ate = self._periodo(request)
        resposta = HttpResponse(
            "﻿" + services.painel_csv(de, ate), content_type="text/csv; charset=utf-8"
        )  # BOM: o Excel abre com acentos
        resposta["Content-Disposition"] = f'attachment; filename="publicidade-{de:%Y%m%d}-{ate:%Y%m%d}.csv"'
        return resposta

    @admin.action(description="Gerar fatura (Pix) e enviar ao patrocinador", permissions=["change"])
    def gerar_fatura(self, request: HttpRequest, queryset: QuerySet[Campanha]):
        """Uma fatura por campanha, pelo mesmo fluxo da cobrança (Pix estático, comprovante, confirmação)."""
        from pagamentos.services import gerar_fatura_campanha

        feitas = 0
        for campanha in queryset.select_related("patrocinador"):
            try:
                gerar_fatura_campanha(campanha)
                feitas += 1
            except ValueError as erro:
                self.message_user(request, str(erro), messages.WARNING)
        self.message_user(
            request,
            f"{feitas} fatura(s) gerada(s) e enviada(s) por e-mail. Acompanhe em Cobrança › Faturas.",
            messages.SUCCESS,
        )
