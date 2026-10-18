"""Admin do app privacidade: documentos legais (versão, vigência, aviso de rascunho só aqui) e pedidos dos
titulares (prazo de 15 dias, configurável)."""

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from core.admin_acoes import tela_motivo
from privacidade.models import DocumentoLegal, PedidoTitular
from privacidade.services import responder_pedido

AVISO_RASCUNHO = (
    "Rascunho: revisão jurídica pendente. O público não vê este aviso (o advogado revisa na Sprint 9)."
)


@admin.register(DocumentoLegal)
class DocumentoLegalAdmin(SimpleHistoryAdmin):
    """Termos e Política por versão. Em vigor = texto travado (o que foi aceito): crie outra versão."""

    list_display = ("__str__", "vigencia", "publicado", "revisao_juridica_pendente", "em_vigor_hoje")
    list_filter = ("tipo", "publicado", "revisao_juridica_pendente")
    fields = ("tipo", "versao", "vigencia", "resumo", "texto", "publicado", "revisao_juridica_pendente")

    @admin.display(description="em vigor", boolean=True)
    def em_vigor_hoje(self, documento: DocumentoLegal) -> bool:
        """Publicado e com a vigência já começada."""
        return documento.em_vigor()

    def get_readonly_fields(self, request: HttpRequest, obj: DocumentoLegal | None = None) -> tuple[str, ...]:
        """Em vigor: só o aviso de revisão jurídica muda (o texto aceito não pode mudar)."""
        if obj is not None and obj.em_vigor():
            return ("tipo", "versao", "vigencia", "resumo", "texto", "publicado")
        return ()

    def changeform_view(self, request: HttpRequest, object_id=None, form_url="", extra_context=None):
        """Mostra o aviso de rascunho (só para a equipe) e lembra como publicar uma mudança."""
        obj = self.get_object(request, object_id) if object_id else None
        if request.method == "GET" and (obj is None or obj.revisao_juridica_pendente):
            messages.warning(request, AVISO_RASCUNHO)
        if request.method == "GET" and obj is not None and obj.em_vigor():
            messages.info(
                request, "Versão em vigor: o texto não muda mais. Para mudar, adicione uma versão nova."
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_delete_permission(self, request: HttpRequest, obj: DocumentoLegal | None = None) -> bool:
        """Prova do que foi aceito: nunca se apaga."""
        return False


@admin.register(PedidoTitular)
class PedidoTitularAdmin(SimpleHistoryAdmin):
    """Pedidos de titulares (LGPD, art. 18): data, tipo, situação e prazo (15 dias, na Identidade do site)."""

    list_display = ("recebido_em", "tipo", "titular", "origem", "situacao", "prazo", "atrasado_hoje", "demo")
    list_filter = ("situacao", "tipo", "origem", "demo")
    search_fields = ("contato", "usuario__email", "descricao")
    date_hierarchy = "recebido_em"
    readonly_fields = ("usuario", "atendido_em", "demo")
    fields = (
        "usuario",
        "contato",
        "tipo",
        "origem",
        "descricao",
        "recebido_em",
        "prazo",
        "situacao",
        "atendido_em",
        "resposta",
        "demo",
    )
    actions = ["marcar_atendido"]

    @admin.display(description="titular")
    def titular(self, pedido: PedidoTitular) -> str:
        """A conta (pedido pelo painel) ou o contato informado (pedido por e-mail)."""
        return str(pedido.usuario) if pedido.usuario_id else pedido.contato or "—"

    @admin.display(description="prazo vencido", boolean=True)
    def atrasado_hoje(self, pedido: PedidoTitular) -> bool:
        """Em aberto e com o prazo vencido."""
        return pedido.atrasado(timezone.localdate())

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Lembra os pedidos dos titulares do Guia de Negócios, que ficam na fila do guia."""
        if request.method == "GET":
            from guia.admin import _avisar_outra_fila

            _avisar_outra_fila(request, "guia")
        return super().changelist_view(request, extra_context)

    def has_delete_permission(self, request: HttpRequest, obj: PedidoTitular | None = None) -> bool:
        """Registro de atendimento (prova para a ANPD): não se apaga."""
        return False

    @admin.action(description="Marcar como atendido (com o que foi feito)", permissions=["change"])
    def marcar_atendido(self, request: HttpRequest, queryset: QuerySet[PedidoTitular]):
        """Pede a resposta e marca os pedidos em aberto como atendidos."""
        return tela_motivo(
            self,
            request,
            queryset.filter(
                situacao__in=[PedidoTitular.Situacao.ABERTO, PedidoTitular.Situacao.EM_ANDAMENTO]
            ),
            "marcar_atendido",
            "Marcar pedidos como atendidos",
            True,
            responder_pedido,
            "{n} pedido(s) marcado(s) como atendido(s).",
        )
