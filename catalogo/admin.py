"""Admin do catálogo de veículos: consulta e "ativo" (esconder do formulário). Nada é criado nem apagado
à mão: tudo vem do `carregar_catalogo` (Tabela FIPE)."""

from django.contrib import admin
from django.http import HttpRequest

from catalogo.models import Marca, Modelo, Versao


class SoCargaAdmin(admin.ModelAdmin):
    """Sem criar nem apagar pelo admin (anúncios dependem das versões; a carga é que cria)."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Criados pelo comando de carga."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Nunca apagados (anúncios antigos apontam para eles)."""
        return False


@admin.register(Marca)
class MarcaAdmin(SoCargaAdmin):
    """Marcas: "ativo" editável na lista."""

    list_display = ("nome", "ativo")
    list_editable = ("ativo",)
    search_fields = ("nome",)
    readonly_fields = ("nome", "slug")


@admin.register(Modelo)
class ModeloAdmin(SoCargaAdmin):
    """Modelos por marca e tipo."""

    list_display = ("nome", "marca", "tipo", "ativo")
    list_editable = ("ativo",)
    list_filter = ("tipo", "ativo")
    search_fields = ("nome", "marca__nome")
    list_select_related = ("marca",)
    readonly_fields = ("marca", "tipo", "nome", "slug")


@admin.register(Versao)
class VersaoAdmin(SoCargaAdmin):
    """Versões (com o código FIPE)."""

    list_display = ("nome", "modelo", "codigo_fipe", "ativo")
    list_editable = ("ativo",)
    list_filter = ("modelo__tipo", "ativo")
    search_fields = ("nome", "modelo__nome", "modelo__marca__nome", "codigo_fipe")
    list_select_related = ("modelo", "modelo__marca")
    readonly_fields = ("modelo", "nome", "codigo_fipe")
