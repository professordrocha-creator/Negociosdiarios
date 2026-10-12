"""Admin do core: estados, cidades ("Cidades atendidas"), regiões, bairros e identidade do site."""

from django.contrib import admin, messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.html import format_html

from core.forms import ConfiguracaoForm
from core.models import Bairro, Cidade, Configuracao, Estado, Regiao, TextoAjuda, ValorEmpresa
from core.services import configuracao, dados_do_site, liberar_cidades, processar_identidade


class BairroInline(admin.TabularInline):
    """Bairros dentro da página da cidade."""

    model = Bairro
    fields = ("nome", "slug", "ativo")
    prepopulated_fields = {"slug": ("nome",)}
    extra = 0
    can_delete = False


@admin.register(Estado)
class EstadoAdmin(admin.ModelAdmin):
    """Estados: liga/desliga o estado no site. Os dados do IBGE não são editáveis."""

    list_display = ("nome", "uf", "liberado", "cidades_liberadas")
    list_filter = ("liberado",)
    search_fields = ("nome", "uf")
    readonly_fields = ("uf", "nome")
    fields = ("uf", "nome", "liberado")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Estado]:
        """Conta as cidades liberadas numa consulta só (sem N+1)."""
        return (
            super()
            .get_queryset(request)
            .annotate(_cidades_liberadas=Count("cidades", filter=Q(cidades__liberada=True)))
        )

    @admin.display(description="cidades liberadas", ordering="_cidades_liberadas")
    def cidades_liberadas(self, estado: Estado) -> int:
        """Quantas cidades do estado estão liberadas."""
        return estado._cidades_liberadas

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Estados vêm só da carga do IBGE (`carregar_municipios`)."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Estado | None = None) -> bool:
        """Estado nunca é apagado; para tirar do site, desmarque 'liberado'."""
        return False


@admin.register(Cidade)
class CidadeAdmin(admin.ModelAdmin):
    """Cidades: busca, filtro por UF e situação, e liberação em massa."""

    list_display = ("nome", "uf", "codigo_ibge", "liberada")
    list_filter = ("liberada", "uf")
    search_fields = ("nome", "codigo_ibge")
    list_select_related = ("uf",)
    list_per_page = 50
    readonly_fields = ("codigo_ibge", "nome", "slug", "uf", "ponto")
    fields = ("nome", "uf", "codigo_ibge", "slug", "ponto", "liberada")
    actions = ["liberar_selecionadas"]
    inlines = [BairroInline]

    @admin.action(description="Liberar cidades selecionadas", permissions=["change"])
    def liberar_selecionadas(self, request: HttpRequest, queryset: QuerySet[Cidade]) -> None:
        """Libera as cidades marcadas e avisa quantas mudaram e se algum estado está bloqueado."""
        alteradas = liberar_cidades(queryset)
        self.message_user(request, f"{alteradas} cidade(s) liberada(s).", messages.SUCCESS)

        ufs_bloqueadas = sorted(
            queryset.filter(uf__liberado=False).values_list("uf_id", flat=True).distinct()
        )
        if ufs_bloqueadas:
            self.message_user(
                request,
                f"Atenção: o estado {', '.join(ufs_bloqueadas)} não está liberado; "
                "estas cidades só aparecem no site depois de liberar o estado.",
                messages.WARNING,
            )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Cidades vêm só da carga do IBGE (`carregar_municipios`)."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Cidade | None = None) -> bool:
        """Cidade nunca é apagada; para tirar do site, desmarque 'liberada'."""
        return False


# --- Regiões e bairros ---------------------------------------------------------------------


@admin.register(Regiao)
class RegiaoAdmin(admin.ModelAdmin):
    """Regiões: agrupam cidades de estados liberados (ex.: "Região de Tangará")."""

    list_display = ("nome", "total_cidades", "demo")
    list_filter = ("demo",)
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}
    filter_horizontal = ("cidades",)
    readonly_fields = ("demo",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Regiao]:
        """Conta as cidades numa consulta só."""
        return super().get_queryset(request).annotate(_total=Count("cidades"))

    @admin.display(description="cidades", ordering="_total")
    def total_cidades(self, regiao: Regiao) -> int:
        """Quantas cidades a região agrupa."""
        return regiao._total

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Só cidades de estados liberados."""
        if db_field.name == "cidades":
            kwargs["queryset"] = Cidade.objects.filter(uf__liberado=True).select_related("uf")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def has_delete_permission(self, request: HttpRequest, obj: Regiao | None = None) -> bool:
        """Região não é apagada pelo admin (tire as cidades ou mude o nome)."""
        return False


@admin.register(Bairro)
class BairroAdmin(admin.ModelAdmin):
    """Bairros por cidade. Inativo some das listas sem ser apagado."""

    list_display = ("nome", "cidade", "ativo", "demo")
    list_filter = ("ativo", "demo", "cidade__uf")
    list_editable = ("ativo",)
    search_fields = ("nome", "cidade__nome")
    list_select_related = ("cidade",)
    autocomplete_fields = ("cidade",)
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("demo",)

    def has_delete_permission(self, request: HttpRequest, obj: Bairro | None = None) -> bool:
        """Bairro nunca é apagado (desmarque "ativo")."""
        return False


# --- Identidade do site, valores e textos de ajuda -----------------------------------------


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    """Identidade do site (registro único): a lista abre direto o formulário."""

    form = ConfiguracaoForm
    readonly_fields = ("previa_simbolos", "favicons_gerados", "atualizado_em")

    class Media:
        css = {"all": ("css/admin-nd.css",)}

    fieldsets = (
        ("Nome e textos", {"fields": ("nome", "linha_regiao", "slogan", "empresa", "cidade_sede")}),
        (
            "Logo, símbolos e imagem de compartilhamento",
            {
                "fields": (
                    "logo_completo",
                    "simbolo_claro",
                    "simbolo_escuro",
                    "previa_simbolos",
                    "imagem_compartilhamento",
                    "favicons_gerados",
                )
            },
        ),
        (
            "Contatos",
            {"fields": ("whatsapp", "email_contato", "email_privacidade", "endereco", "cnpj", "instagram")},
        ),
        ("Página Sobre", {"fields": ("sobre_quem_somos", "sobre_missao", "sobre_visao")}),
        (
            "Limites de mídia",
            {
                "fields": (
                    "limite_simbolo_kb",
                    "limite_compartilhamento_kb",
                    "limite_logo_kb",
                    "logo_min_px",
                    "limite_capa_kb",
                    "capa_min_largura_px",
                    "capa_min_altura_px",
                )
            },
        ),
        (
            "Anúncios: fotos e textos",
            {
                "fields": (
                    "max_fotos_anuncio",
                    "limite_foto_anuncio_kb",
                    "foto_min_largura_px",
                    "foto_min_altura_px",
                    "titulo_min_caracteres",
                    "titulo_max_caracteres",
                    "descricao_max_caracteres",
                )
            },
        ),
        (
            "Regras do negócio",
            {
                "description": "Prazos e moderação valem para todas as lojas a partir do próximo uso.",
                "fields": (
                    "carencia_dias",
                    "fatura_antecedencia_dias",
                    "limite_comprovante_kb",
                    "expiracao_dias",
                    "aviso_expiracao_dias",
                    "moderacao",
                    "atualizado_em",
                ),
            },
        ),
    )

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Registro único: "Identidade do site" no menu leva direto ao formulário."""
        config = configuracao()
        return redirect("admin:core_configuracao_change", config.pk)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Só existe um registro (criado sozinho)."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Configuracao | None = None) -> bool:
        """O registro único nunca é apagado."""
        return False

    def save_model(self, request: HttpRequest, obj: Configuracao, form, change: bool) -> None:
        """Salva e, se mudou alguma imagem, limpa (sem EXIF) e refaz os favicons."""
        super().save_model(request, obj, form, change)
        processar_identidade(obj, set(form.changed_data))

    @admin.display(description="prévia do logo e dos símbolos")
    def previa_simbolos(self, config: Configuracao) -> str:
        """Logo completo e símbolo escuro sobre o azul do topo; símbolo claro sobre fundo branco."""
        dados = dados_do_site()
        return format_html(
            '<span class="nd-previa-logo"><img src="{}" height="40" alt="logo completo"></span> '
            '<span class="nd-previa-simbolo">'
            '<img src="{}" width="48" height="48" alt="claro"></span> '
            '<span class="nd-previa-simbolo nd-previa-simbolo-escuro">'
            '<img src="{}" width="48" height="48" alt="escuro"></span>',
            dados["logo_completo"],
            dados["simbolo_claro"],
            dados["simbolo_escuro"],
        )

    @admin.display(description="favicons gerados")
    def favicons_gerados(self, config: Configuracao) -> str:
        """Os favicons atuais (gerados do símbolo claro ou os padrão)."""
        dados = dados_do_site()
        return format_html(
            '<img src="{}" width="32" height="32" alt="32"> <img src="{}" width="60" height="60" alt="180">'
            ' <span class="help">Gerados sozinhos a partir do símbolo para fundo claro.</span>',
            dados["favicon_32"],
            dados["favicon_180"],
        )


@admin.register(ValorEmpresa)
class ValorEmpresaAdmin(admin.ModelAdmin):
    """Valores da página Sobre: a ordem e o "ativo" se editam direto na lista."""

    list_display = ("titulo", "ordem", "icone", "ativo")
    list_editable = ("ordem", "ativo")
    list_display_links = ("titulo",)

    def has_delete_permission(self, request: HttpRequest, obj: ValorEmpresa | None = None) -> bool:
        """Valor não é apagado: desmarque "ativo" para tirar da página."""
        return False


@admin.register(TextoAjuda)
class TextoAjudaAdmin(admin.ModelAdmin):
    """Textos da caixa "Sobre esta tela", um por tela (a chave é a variável "tela" da view)."""

    list_display = ("chave", "descricao", "atualizado_em")
    search_fields = ("chave", "descricao", "texto")
    readonly_fields = ("atualizado_em",)

    def get_readonly_fields(self, request: HttpRequest, obj: TextoAjuda | None = None):
        """A chave liga o texto à tela: depois de criada, não muda."""
        return (*self.readonly_fields, "chave") if obj else self.readonly_fields

    def has_delete_permission(self, request: HttpRequest, obj: TextoAjuda | None = None) -> bool:
        """Nunca apague: para tirar a caixa de uma tela, deixe o texto em branco."""
        return False
