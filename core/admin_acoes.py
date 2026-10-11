"""Ações do admin com tela intermediária de motivo (aprovar/recusar/registrar com justificativa).

Usada pelos admins de planos e anúncios; o template é o mesmo das ações de anunciantes.
"""

from django.contrib import messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse
from django.urls import reverse

from anunciantes.forms import MotivoStatusForm


def tela_motivo(
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
