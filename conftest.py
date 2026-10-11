"""Fixtures compartilhadas por todos os testes."""

import pytest

from config.celery import app as celery_app
from contas.services import SESSAO_ACESSO_VERIFICADO


@pytest.fixture(autouse=True)
def ambiente_de_teste_previsivel(settings):
    """Padrões dos testes, independentes do .env de quem roda (dev, CI):

    - código por e-mail do admin desligado (os testes de acesso ligam com o fixture `producao`);
    - e-mail em memória (`mail.outbox`) e mídia local; Celery roda as tarefas na hora,
      sem precisar de worker (`task_always_eager`).
    """
    settings.ADMIN_CODIGO_EMAIL = False
    settings.MOSTRAR_DEMO = False  # os testes da demonstração ligam quando precisam
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture
def entrar_no_admin(client):
    """Devolve uma função que loga o usuário no client **já com o navegador verificado**.

    Assim os testes de telas do admin funcionam com ou sem o código por e-mail
    ligado. Para testar o login em si, ver contas/tests/test_acesso_admin.py.
    """

    def _entrar(usuario):
        client.force_login(usuario)
        sessao = client.session
        sessao[SESSAO_ACESSO_VERIFICADO] = usuario.pk
        sessao.save()
        return client

    return _entrar
