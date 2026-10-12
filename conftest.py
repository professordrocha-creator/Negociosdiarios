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
    settings.DEMO_FOTO_ESCALA = 0.5  # fotos demo em 800×600: os testes da demonstração rodam mais rápido
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


# --- Catálogo de veículos (Sprint 4): um pedaço pequeno da FIPE ------------------------------


@pytest.fixture
def catalogo_teste(db):
    """Toyota Hilux (caminhonete, 2 versões), Toyota Corolla (carro) e Honda CG (moto)."""
    from catalogo.models import Marca, Modelo, Versao

    toyota = Marca.objects.create(nome="Toyota", slug="toyota")
    honda = Marca.objects.create(nome="Honda", slug="honda")
    hilux = Modelo.objects.create(marca=toyota, tipo="caminhonete", nome="Hilux", slug="hilux")
    corolla = Modelo.objects.create(marca=toyota, tipo="carro", nome="Corolla", slug="corolla")
    cg = Modelo.objects.create(marca=honda, tipo="moto", nome="CG", slug="cg")
    return {
        "toyota": toyota,
        "honda": honda,
        "hilux": hilux,
        "corolla": corolla,
        "cg": cg,
        "hilux_srv": Versao.objects.create(
            modelo=hilux, nome="CD SRV 4x4 2.8 TDI Diesel Aut.", codigo_fipe="7406"
        ),
        "hilux_sr": Versao.objects.create(modelo=hilux, nome="CD SR 4x4 2.8 TDI Diesel", codigo_fipe="7405"),
        "corolla_xei": Versao.objects.create(
            modelo=corolla, nome="XEi 2.0 Flex 16V Aut.", codigo_fipe="6000"
        ),
        "cg_fan": Versao.objects.create(modelo=cg, nome="160 FAN Flex", codigo_fipe="8000"),
    }


@pytest.fixture
def veiculo(catalogo_teste, tangara):
    """Fábrica: anúncio de veículo em rascunho; `completo=True` já tem descrição e foto."""
    from decimal import Decimal

    from anuncios import services
    from anuncios.tests.conftest import foto_pronta

    def _criar(anunciante, versao: str = "hilux_srv", completo: bool = True, titulo: str = "", **ficha):
        dados = {
            "titulo": titulo,
            "descricao": "Revisada, pneus novos." if completo else "",
            "preco": Decimal("189900"),
            "cidade": tangara,
        }
        ficha = {
            "versao": catalogo_teste[versao],
            "ano_fabricacao": 2019,
            "ano_modelo": 2020,
            "quilometragem": 98000,
            "combustivel": "diesel",
            "cambio": "automatico",
            "cor": "prata",
            "portas": 4,
            "final_placa": "",
            "opcionais": ["ar_condicionado", "tracao_4x4"],
            **ficha,
        }
        anuncio = services.criar_anuncio_veiculo(anunciante, dados, ficha)
        if completo:
            foto_pronta(anuncio)
        return anuncio

    return _criar


# --- Anúncios (Sprint 3): loja com plano, imóvel e anúncio publicado ------------------------


@pytest.fixture
def loja(criar_anunciante, tangara):
    """Fábrica: anunciante ativo com assinatura ativa (padrão: Básico, 10 anúncios)."""
    from planos.models import Periodicidade, Plano
    from planos.services import criar_assinatura

    def _criar(
        email: str = "loja@exemplo.com", nome: str = "Loja Alfa", slug_plano: str = "basico", limite=None
    ):
        anunciante = criar_anunciante(email, nome)
        plano = Plano.objects.get(slug=slug_plano)
        if limite is not None:
            plano.limite_anuncios = limite
            plano.save()
        criar_assinatura(anunciante, plano, Periodicidade.MENSAL)
        return anunciante

    return _criar


@pytest.fixture
def imovel(tangara):
    """Fábrica: anúncio de imóvel em rascunho; `completo=True` já tem descrição, ponto e foto."""
    from decimal import Decimal

    from anuncios import services
    from anuncios.tests.conftest import foto_pronta

    def _criar(anunciante, titulo: str = "Casa 3 quartos com área gourmet", completo: bool = True, **ficha):
        dados = {
            "titulo": titulo,
            "descricao": "Casa ampla, perto do centro." if completo else "",
            "preco": Decimal("420000"),
        }
        ficha = {"tipo": "casa", "modalidade": "venda", "quartos": 3, "area_total": Decimal("180"), **ficha}
        anuncio = services.criar_anuncio_imovel(anunciante, dados, ficha)
        if completo:
            anuncio.imovel.ponto = Point(-57.49, -14.62, srid=4326)
            anuncio.imovel.save()
            foto_pronta(anuncio)
        return anuncio

    return _criar


@pytest.fixture
def publicado(imovel):
    """Fábrica: anúncio já publicado (moderação desligada só para montar o cenário)."""
    from anuncios import services
    from core.services import configuracao

    def _criar(anunciante, titulo: str = "Casa 3 quartos com área gourmet"):
        config = configuracao()
        regra, config.moderacao = config.moderacao, "nenhum"
        config.save()
        anuncio = imovel(anunciante, titulo)
        services.enviar_para_publicacao(anuncio)
        config.moderacao = regra
        config.save()
        anuncio.refresh_from_db()
        return anuncio

    return _criar
