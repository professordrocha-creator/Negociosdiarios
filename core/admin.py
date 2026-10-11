"""Admin de estados e cidades (tela "Cidades atendidas", docs/TELAS.md §4)."""

from django.contrib import admin, messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest

from core.models import Cidade, Estado
from core.services import liberar_cidades


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
