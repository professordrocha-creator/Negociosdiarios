"""Fixtures compartilhadas por todos os testes."""

import pytest
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.utils import timezone

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from config.celery import app as celery_app
from contas.models import Usuario
from contas.services import SESSAO_ACESSO_VERIFICADO
from core.models import Cidade, Estado


@pytest.fixture(autouse=True)
def ambiente_de_teste_previsivel(settings, tmp_path):
    """Padrões dos testes, independentes do .env de quem roda (dev, CI):

    - código por e-mail do admin desligado (os testes de acesso ligam com o fixture `producao`);
    - e-mail em memória (`mail.outbox`), cache em memória e mídia local; Celery roda as tarefas na hora,
      sem precisar de worker (`task_always_eager`).
    """
    settings.ADMIN_CODIGO_EMAIL = False
    settings.MOSTRAR_DEMO = False  # os testes da demonstração ligam quando precisam
    # Cache em memória e vazio a cada teste: os limites por IP não vazam entre testes.
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.MEDIA_ROOT = tmp_path / "media"  # uploads e imagens geradas nunca caem na media/ do projeto
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


@pytest.fixture
def tangara(db):
    """Tangará da Serra liberada (MT liberado)."""
    mt = Estado.objects.create(uf="MT", nome="Mato Grosso", liberado=True)
    return Cidade.objects.create(
        codigo_ibge=5107958,
        nome="Tangará da Serra",
        slug="tangara-da-serra",
        uf=mt,
        liberada=True,
        ponto=Point(-57, -14),
    )


@pytest.fixture
def criar_anunciante(tangara):
    """Fábrica: usuário (e-mail já confirmado, salvo `sem_confirmacao`) + anunciante (revenda ou corretor)."""
    cnpjs = iter(["90000001000129", "90000002000173", "90000003000118", "90000004000162"])

    def _criar(
        email: str,
        nome: str,
        status: str = Anunciante.Status.ATIVO,
        corretor: bool = False,
        sem_confirmacao: bool = False,
        **campos,
    ):
        usuario = Usuario.objects.create_user(
            email=email,
            password=SENHA,
            nome=nome,
            email_confirmado_em=None if sem_confirmacao else timezone.now(),
        )
        documento = ("creci", "CRECI/MT 12345-F") if corretor else ("cnpj", next(cnpjs))
        return Anunciante.objects.create(
            usuario=usuario,
            tipo=Anunciante.Tipo.CORRETOR_AUTONOMO if corretor else Anunciante.Tipo.REVENDA,
            nome_publico=nome,
            slug=nome.lower().replace(" ", "-"),
            documento_tipo=documento[0],
            documento_numero=documento[1],
            whatsapp="+5565999990001",
            cidade=campos.pop("cidade", tangara),
            status=status,
            **campos,
        )

    return _criar
