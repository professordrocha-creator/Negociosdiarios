"""Testes da preparação para produção (docs/DEPLOY.md): SITE_NOINDEX nos dois estados, IP real só vindo do
proxy confiável (não dá para forjar pelo cabeçalho) e a trava dos dados de demonstração no servidor."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory

from config.settings import validar_demo_no_servidor, validar_mostrar_demo
from core.middleware import IPRealMiddleware, ip_real

pytestmark = pytest.mark.django_db

REDES_DOCKER = ["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]


# --- SITE_NOINDEX --------------------------------------------------------------------------------------


def test_noindex_ligado_marca_tudo_robots_fecha_e_sitemap_some(client, settings):
    """Servidor de teste: todas as respostas com "noindex, nofollow, noarchive" (até as que tinham outro
    valor), robots.txt "Disallow: /" sem sitemap e /sitemap.xml 404."""
    settings.SITE_NOINDEX = True

    inicio = client.get("/")
    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")
    nao_existe = client.get("/pagina-que-nao-existe/")

    for resposta in (inicio, robots, sitemap, nao_existe):
        assert resposta["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert robots.content.decode() == "User-agent: *\nDisallow: /\n"
    assert sitemap.status_code == 404


def test_noindex_desligado_volta_ao_normal(client, settings):
    """Lançamento: sem o cabeçalho na home, robots.txt com as regras e o sitemap, /sitemap.xml no ar."""
    settings.SITE_NOINDEX = False

    inicio = client.get("/")
    robots = client.get("/robots.txt").content.decode()

    assert "X-Robots-Tag" not in inicio
    assert "Disallow: /painel/" in robots and "Sitemap: http" in robots and "Disallow: /\n" not in robots
    assert client.get("/sitemap.xml").status_code == 200


# --- IP real -----------------------------------------------------------------------------------------------


def _pedido(remoto: str, **cabecalhos):
    """Requisição com o REMOTE_ADDR e os cabeçalhos dados."""
    return RequestFactory().get("/", REMOTE_ADDR=remoto, **cabecalhos)


def test_ip_real_so_vale_vindo_do_proxy_confiavel(settings):
    """X-Real-IP do nd_nginx (rede Docker) vale; o mesmo cabeçalho vindo direto do visitante é ignorado,
    assim como o X-Forwarded-For (que o visitante escreve o que quiser)."""
    settings.PROXIES_CONFIAVEIS = REDES_DOCKER

    assert ip_real(_pedido("172.20.0.5", HTTP_X_REAL_IP="200.150.10.77")) == "200.150.10.77"
    assert ip_real(_pedido("200.150.10.77", HTTP_X_REAL_IP="1.2.3.4")) == "200.150.10.77"  # forjado
    assert ip_real(_pedido("172.20.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4")) == "172.20.0.5"
    assert ip_real(_pedido("172.20.0.5", HTTP_X_REAL_IP="lixo")) == "172.20.0.5"


def test_ip_real_desligado_em_dev(settings):
    """Sem proxies confiáveis (dev), o cabeçalho nunca vale."""
    settings.PROXIES_CONFIAVEIS = []
    assert ip_real(_pedido("172.20.0.5", HTTP_X_REAL_IP="200.150.10.77")) == "172.20.0.5"


def test_middleware_troca_o_remote_addr_antes_dos_outros(settings):
    """O REMOTE_ADDR que o axes e os limites leem já é o do visitante."""
    settings.PROXIES_CONFIAVEIS = REDES_DOCKER
    visto = {}

    def proxima(request):
        visto["ip"] = request.META["REMOTE_ADDR"]

    IPRealMiddleware(proxima)(_pedido("10.0.0.2", HTTP_X_REAL_IP="2804:14c::1"))
    assert visto["ip"] == "2804:14c::1"


# --- Demonstração no servidor -------------------------------------------------------------------------------


def test_demo_no_servidor_exige_noindex_e_libera_mostrar_demo():
    """DEMO_NO_SERVIDOR só com SITE_NOINDEX; com ele, MOSTRAR_DEMO vale mesmo com DEBUG=False."""
    with pytest.raises(ImproperlyConfigured, match="SITE_NOINDEX"):
        validar_demo_no_servidor(True, noindex=False)
    assert validar_demo_no_servidor(True, noindex=True) is True
    with pytest.raises(ImproperlyConfigured, match="DEMO_NO_SERVIDOR"):
        validar_mostrar_demo(True, debug=False)
    assert validar_mostrar_demo(True, debug=False, demo_no_servidor=True) is True
