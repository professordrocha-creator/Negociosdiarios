"""Testes do Manual do Administrador em /painel/ajuda/ (só equipe) e do conversor de Markdown seguro."""

import pytest
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.markdown_seguro import ancora, markdown_para_html

URL = "/painel/ajuda/"


def test_endereco_da_ajuda():
    """A rota tem o endereço combinado."""
    assert reverse("core:ajuda_equipe") == URL


@pytest.mark.django_db
def test_equipe_ve_o_manual(entrar_no_admin):
    """Equipe com o navegador verificado: 200, manual com sumário e âncoras, fora dos buscadores."""
    equipe = Usuario.objects.create_user(email="eq@exemplo.com", password=SENHA, nome="Eq", is_staff=True)
    cliente = entrar_no_admin(equipe)

    resposta = cliente.get(URL)
    pagina = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Manual do Administrador" in pagina and "Sumário" in pagina
    assert 'id="1-primeiro-acesso"' in pagina and 'href="#10-guia-de-negocios"' in pagina
    assert resposta["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.django_db
def test_visitante_e_cliente_nao_veem(client, criar_anunciante):
    """Visitante e cliente comum: 404 (a página não existe para eles)."""
    assert client.get(URL).status_code == 404
    loja = criar_anunciante("loja@exemplo.com", "Loja X")
    client.force_login(loja.usuario)
    assert client.get(URL).status_code == 404


@pytest.mark.django_db
def test_equipe_sem_codigo_passa_pela_verificacao(client, settings):
    """Com o código por e-mail ligado, navegador não verificado vai à tela do código (sem atalho)."""
    settings.ADMIN_CODIGO_EMAIL = True
    equipe = Usuario.objects.create_user(email="eq@exemplo.com", password=SENHA, nome="Eq", is_staff=True)
    client.force_login(equipe)

    resposta = client.get(URL)

    assert resposta.status_code == 302 and resposta["Location"].startswith(reverse("admin:verificar"))


@pytest.mark.django_db
def test_link_ajuda_no_topo_do_admin(entrar_no_admin):
    """O topo do painel administrativo tem o link "Ajuda"."""
    equipe = Usuario.objects.create_superuser(email="d@exemplo.com", password=SENHA, nome="D")
    pagina = entrar_no_admin(equipe).get(reverse("admin:index")).content.decode()
    assert f'<a href="{URL}">Ajuda</a>' in pagina


def test_markdown_escapa_html_e_links_perigosos():
    """HTML do arquivo vira texto; link javascript: não vira link; o resto da marcação funciona."""
    html = markdown_para_html(
        "# Título <b>x</b>\n\n<script>alert(1)</script>\n\n[ruim](javascript:alert(1)) [bom](#secao)\n\n"
        "1. **Onde clicar:** menu `Núcleo`\n   - subitem\n2. segundo\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n> nota"
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html and 'id="titulo-b-x-b"' in html
    assert 'href="javascript' not in html and '<a href="#secao">bom</a>' in html
    assert (
        "<ol><li><strong>Onde clicar:</strong> menu <code>Núcleo</code><ul><li>subitem</li></ul></li>" in html
    )
    assert '<th scope="col">a</th>' in html and "<td>2</td>" in html
    assert '<blockquote class="nd-ajuda-nota">nota</blockquote>' in html


def test_ancora_igual_ao_sumario():
    """Âncora sem acento, minúscula e com hífens (os links do sumário usam o mesmo formato)."""
    assert ancora("9. LGPD: pedidos, exclusão e termos") == "9-lgpd-pedidos-exclusao-e-termos"
