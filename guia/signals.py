"""Sinais do app guia: travas das categorias do perfil valendo em qualquer caminho (admin, serviço, shell).

O formulário já valida antes (mensagem amigável); aqui é a última barreira do modelo, porque a escolha de
categorias (muitos-para-muitos) só é gravada depois do `save` do perfil e não passa pelo `clean`.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from guia.models import CategoriaServico, PerfilGuia


@receiver(m2m_changed, sender=PerfilGuia.categorias.through)
def travar_categorias(sender, instance, action, reverse, pk_set, **kwargs) -> None:
    """Antes de acrescentar categorias: no máximo `max_categorias` e nada de regulamentada com frase.

    Levanta ValidationError (a gravação não acontece). Só o lado do perfil (`perfil.categorias.add`).
    """
    if action != "pre_add" or reverse or not pk_set:
        return
    from guia.services import configuracao_guia

    atuais = set(instance.categorias.values_list("pk", flat=True))
    maximo = configuracao_guia().max_categorias
    if len(atuais | set(pk_set)) > maximo:
        raise ValidationError(f"Escolha no máximo {maximo} categorias.")
    if instance.frase and CategoriaServico.objects.filter(pk__in=pk_set, regulamentada=True).exists():
        raise ValidationError("Categoria regulamentada não aceita frase promocional. Apague a frase.")
