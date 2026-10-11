"""Testes das páginas institucionais (etapa 4d): legais, planos, mídia kit, contato e "em breve"."""

import re
from decimal import Decimal

import pytest
from django.template import Context, Template
from django.urls import reverse

from core.services import PAGINAS_EM_BREVE, planos

pytestmark = pytest.mark.django_db

PAGINAS = ["privacidade", "termos", "cookies", "planos", "anuncie", "contato", *PAGINAS_EM_BREVE]


def html_de(client, rota: str) -> str:
    """HTML de uma rota do app core."""
    return client.get(reverse(f"core:{rota}")).content.decode()


# --- Todas abrem, com SEO básico ---------------------------------------------------------


@pytest.mark.parametrize("rota", PAGINAS)
def test_pagina_responde_200_com_titulo_e_descricao_proprios(client, settings, rota):
    """Cada página abre e tem <title> e meta description próprios (não o slogan genérico)."""
    resposta = client.get(reverse(f"core:{rota}"))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    titulo = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    descricao = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert settings.SITE_NOME in titulo and titulo.strip() != f"{settings.SITE_SLOGAN} · {settings.SITE_NOME}"
    assert descricao and descricao != settings.SITE_SLOGAN


@pytest.mark.parametrize("rota", ["privacidade", "termos", "cookies", *PAGINAS_EM_BREVE])
def test_paginas_provisorias_nao_sao_indexadas(client, rota):
    """Rascunhos legais e páginas "em breve" pedem noindex aos buscadores."""
    assert '<meta name="robots" content="noindex">' in html_de(client, rota)


@pytest.mark.parametrize("rota", ["planos", "anuncie", "contato"])
def test_caixa_sobre_esta_tela(client, rota):
    """Planos, mídia kit e contato mostram a caixa "Sobre esta tela" (docs/TELAS.md)."""
    assert "Sobre esta tela" in html_de(client, rota)


# --- Nenhum link do rodapé ou do menu dá 404 ---------------------------------------------


@pytest.mark.parametrize("trecho", ["<footer", '<header class="nd-topo"'])
def test_links_do_rodape_e_do_menu_abrem(client, trecho):
    """Todo link interno do rodapé e do cabeçalho responde 200 (página pronta ou "em breve")."""
    html = html_de(client, "inicio")
    bloco = html.split(trecho, 1)[1].split("</footer>" if trecho == "<footer" else "</header>", 1)[0]
    links = {href.split("#")[0] for href in re.findall(r'href="([^"]+)"', bloco) if href.startswith("/")}

    assert len(links) >= (9 if trecho == "<footer" else 4)
    for link in links:
        assert client.get(link).status_code == 200, link


def test_rodape_nao_tem_link_sem_destino(client):
    """Acabaram os links "mortos" do rodapé: todos têm href."""
    rodape = html_de(client, "inicio").split("<footer", 1)[1]

    assert "aria-disabled" not in rodape


# --- Documentos legais ---------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["privacidade", "termos", "cookies"])
def test_documentos_legais_tem_aviso_de_rascunho_e_dados_do_site(client, settings, rota):
    """Aviso de rascunho visível; empresa e cidade vêm do settings (nada fixo no texto)."""
    settings.SITE_EMPRESA = "Empresa Teste Ltda"
    settings.SITE_CIDADE_SEDE = "Cidade Teste, XX"
    settings.SITE_EMAIL_PRIVACIDADE = "dados@teste.example"

    html = html_de(client, rota)

    assert "Rascunho — será revisado por advogado antes do lançamento" in html
    assert "Empresa Teste Ltda" in html and "Cidade Teste, XX" in html
    assert "dados@teste.example" in html
    assert "D&#x27;Rocha" not in html and "Tangará da Serra" not in html.split("<footer", 1)[0]


def test_privacidade_cobre_os_pontos_da_lgpd(client):
    """Dados, finalidades, bases legais, retenção, operadores, direitos e cookies."""
    html = html_de(client, "privacidade")

    for trecho in [
        "Base legal",
        "Por quanto tempo",
        "Execução de contrato",
        "Obrigação legal",
        "Legítimo interesse",
        "Cloudflare R2",
        "Mercado Pago",
        "art. 18",
        "15 dias",
        "ANPD",
        reverse("core:cookies"),
    ]:
        assert trecho in html, trecho


def test_cnpj_aparece_formatado_ou_a_informar(client):
    """Sem CNPJ na identidade do site: "(CNPJ a informar)"; com CNPJ (admin): formatado."""
    from core.services import configuracao

    assert "(CNPJ a informar)" in html_de(client, "termos")

    config = configuracao()
    config.cnpj = "90000001000129"
    config.save()  # o save limpa o cache: a mudança aparece na hora
    assert "CNPJ 90.000.001/0001-29" in html_de(client, "termos")


def test_cookies_lista_os_cookies_reais(client):
    """A política lista os cookies que o site usa hoje."""
    html = html_de(client, "cookies")

    for nome in ["csrftoken", "sessionid", "messages", "nd_admin_navegador"]:
        assert f"<code>{nome}</code>" in html


# --- Planos ----------------------------------------------------------------------------


def test_planos_mostra_os_3_planos_com_precos_mensal_e_anual(client):
    """Básico 10, Profissional 25, Premium 50, com preço mensal e anual formatados."""
    html = html_de(client, "planos")

    for trecho in [
        "Básico",
        "Profissional",
        "Premium",
        "10 anúncios",
        "25 anúncios",
        "50 anúncios",
        "R$ 49,90",
        "R$ 499",
        "R$ 99,90",
        "R$ 999",
        "R$ 149,90",
        "R$ 1.499",
    ]:
        assert trecho in html, trecho


def test_planos_tem_alternancia_mensal_anual_sem_javascript(client):
    """Dois rádios (mensal marcado) e os blocos de preço que o CSS alterna."""
    html = html_de(client, "planos")

    assert 'id="periodo-mensal" autocomplete="off" checked' in html
    assert 'id="periodo-anual"' in html
    assert (
        html.count('class="nd-plano-preco so-mensal"') == html.count('class="nd-plano-preco so-anual"') == 3
    )


def test_botao_quero_anunciar_leva_ao_contato(client):
    """Cada plano tem "Quero anunciar" apontando para /contato/."""
    html = html_de(client, "planos")
    botoes = re.findall(r'href="([^"]+)">Quero anunciar</a>', html)

    assert len(botoes) == 3
    assert all(b.startswith(reverse("core:contato")) for b in botoes)


def test_planos_vem_do_settings(client, settings):
    """Valores não são fixos no template: mudar o settings muda a página."""
    settings.PLANOS = [
        {"slug": "teste", "nome": "Plano Teste", "limite_anuncios": 7, "mensal": "12.34", "anual": "123.40"}
    ]

    html = html_de(client, "planos")

    assert "Plano Teste" in html and "R$ 12,34" in html and "Básico" not in html


def test_economia_do_plano_anual():
    """O anual equivale a 10 mensalidades: 2 meses grátis."""
    basico = planos()[0]

    assert basico.economia_anual == Decimal("99.80")
    assert basico.meses_pagos_no_anual == 10
    assert basico.meses_gratis == 2


# --- Mídia kit -------------------------------------------------------------------------


def test_anuncie_mostra_formatos_tamanhos_precos_e_previas(client):
    """Os 3 formatos do PUBLICIDADE.md, com tamanho, preço, prévia e rótulo "Publicidade"."""
    html = html_de(client, "anuncie")

    for trecho in [
        "Banner topo",
        "Card patrocinador",
        "Anúncio nativo",
        "970×90",
        "320×100",
        "R$ 299 a R$ 599",
        "R$ 149 a R$ 299",
        "R$ 49,90",
        "nd-previa-banner-desktop",
        "nd-previa-banner-celular",
        "nd-previa-card",
        "nd-previa-nativo",
    ]:
        assert trecho in html, trecho
    assert html.count(">Publicidade<") >= 5


# --- Contato ---------------------------------------------------------------------------


def test_contato_sem_whatsapp_mostra_em_breve(client, settings):
    """Sem SITE_WHATSAPP: nada de número inventado."""
    settings.SITE_WHATSAPP = ""

    html = html_de(client, "contato")

    assert "wa.me" not in html
    assert "Em breve" in html


def test_contato_com_dados_do_site(client, settings):
    """WhatsApp formatado com link, e-mails e endereço vêm do settings."""
    settings.SITE_WHATSAPP = "+5565999990000"
    settings.SITE_ENDERECO = "Rua Teste, 100"
    settings.SITE_EMAIL_CONTATO = "fale@teste.example"

    html = html_de(client, "contato")

    assert 'href="https://wa.me/5565999990000"' in html and "(65) 99999-0000" in html
    assert "Rua Teste, 100" in html and "fale@teste.example" in html


# --- Em breve ------------------------------------------------------------------------------


@pytest.mark.parametrize("rota", list(PAGINAS_EM_BREVE))
def test_em_breve_e_amigavel(client, rota):
    """Página "em breve" com título, explicação e caminho de volta (nunca 404)."""
    html = html_de(client, rota)

    assert PAGINAS_EM_BREVE[rota]["titulo"] in html
    assert ">Em breve<" in html
    assert f'href="{reverse("core:inicio")}"' in html


def test_menu_marca_a_pagina_atual(client):
    """No menu, a página atual ganha a classe "ativo" e aria-current."""
    html = html_de(client, "veiculos")

    assert re.search(r'class="px-1 py-2 ativo" href="/veiculos/" aria-current="page"', html)


# --- Filtros ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filtro", "valor", "esperado"),
    [
        ("telefone", "+5565999990000", "(65) 99999-0000"),
        ("telefone", "+556533221100", "(65) 3322-1100"),
        ("telefone", "", ""),
        ("link_whatsapp", "+5565999990000", "https://wa.me/5565999990000"),
        ("link_whatsapp", "", ""),
        ("cnpj", "90000001000129", "90.000.001/0001-29"),
        ("cnpj", "123", "123"),
    ],
)
def test_filtros_de_contato(filtro, valor, esperado):
    """Telefone, link do WhatsApp e CNPJ formatados nos templates."""
    assert Template(f"{{% load nd %}}{{{{ v|{filtro} }}}}").render(Context({"v": valor})) == esperado
