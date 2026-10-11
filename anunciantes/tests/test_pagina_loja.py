"""Testes da Sprint 2, parte A: Painel › Página da loja, imagens (WebP, sem EXIF), vitrine pública,
/lojas/, SEO (title, description, Open Graph, schema.org), WhatsApp sem número no HTML e sitemap."""

import io
import json
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from anunciantes.models import Anunciante
from anunciantes.services import processar_imagem_loja
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.services import configuracao

pytestmark = pytest.mark.django_db


def imagem(largura: int, altura: int, formato: str = "PNG", exif: bool = False) -> bytes:
    """Imagem de teste; com `exif`, leva GPS e fabricante da câmera."""
    saida = io.BytesIO()
    img = Image.new("RGB", (largura, altura), (200, 120, 40))
    if exif:
        dados = Image.Exif()
        dados[0x8825] = {2: (15.0, 30.0, 0.0)}
        dados[0x010F] = "Camera Teste"
        img.save(saida, format=formato, exif=dados)
    else:
        img.save(saida, format=formato)
    return saida.getvalue()


def envio(nome: str, conteudo: bytes, tipo: str = "image/png") -> SimpleUploadedFile:
    """Arquivo enviado pelo formulário."""
    return SimpleUploadedFile(nome, conteudo, tipo)


@pytest.fixture
def loja(criar_anunciante):
    """Revenda ativa em Tangará."""
    return criar_anunciante("loja@exemplo.com", "Loja Alfa")


def dados_da_pagina(anunciante: Anunciante, **mudancas) -> dict:
    """Formulário da Página da loja com os valores atuais + `mudancas`."""
    dados = {
        "nome_publico": anunciante.nome_publico,
        "slug": anunciante.slug,
        "cor": anunciante.cor,
        "sobre": anunciante.sobre,
        "whatsapp": anunciante.whatsapp,
        "endereco_publico": anunciante.endereco_publico,
        "horario": anunciante.horario,
        "instagram": anunciante.instagram,
        "site": anunciante.site,
    }
    if anunciante.mostrar_no_mapa:
        dados["mostrar_no_mapa"] = "on"
    dados.update(mudancas)
    return dados


def salvar_pagina(client, anunciante: Anunciante, **mudancas):
    """Envia o formulário do painel como o dono da loja."""
    client.force_login(anunciante.usuario)
    return client.post(reverse("anunciantes:painel_loja"), dados_da_pagina(anunciante, **mudancas))


# --- Painel › Página da loja ------------------------------------------------------------


def test_painel_loja_so_para_anunciante_ativo(client, loja, db):
    """Anônimo vai ao login; equipe recebe 403; o dono vê a tela com a prévia."""
    assert client.get(reverse("anunciantes:painel_loja"))["Location"].startswith(reverse("contas:entrar"))

    equipe = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="D")
    client.force_login(equipe)
    assert client.get(reverse("anunciantes:painel_loja")).status_code == 403

    client.force_login(loja.usuario)
    html = client.get(reverse("anunciantes:painel_loja")).content.decode()
    assert 'id="prev-nome"' in html and "js/painel-loja.js" in html
    assert "Sobre esta tela" in html


def test_salvar_dados_publicos(client, loja):
    """Sobre, horário, endereço, Instagram (sem @) e site são salvos; WhatsApp em E.164."""
    resposta = salvar_pagina(
        client,
        loja,
        sobre="Carros revisados com garantia.",
        horario="Seg a sáb 8h–18h",
        endereco_publico="Av. Brasil, 100",
        mostrar_no_mapa="on",
        instagram="@lojaalfa",
        site="https://lojaalfa.example",
        whatsapp="(65) 98888-7777",
    )

    assert resposta["Location"] == reverse("anunciantes:painel_loja")
    loja.refresh_from_db()
    assert (loja.sobre, loja.horario, loja.instagram) == (
        "Carros revisados com garantia.",
        "Seg a sáb 8h–18h",
        "lojaalfa",
    )
    assert loja.mostrar_no_mapa and loja.whatsapp == "+5565988887777"
    assert loja.history.first().history_change_reason == "Página da loja editada pelo anunciante."


def test_creci_e_cnpj_nao_sao_editaveis(client, loja):
    """Mesmo forçando no POST, o documento verificado não muda."""
    salvar_pagina(client, loja, documento_numero="11222333000181", documento_tipo="creci", status="suspenso")

    loja.refresh_from_db()
    assert loja.documento_numero == "90000001000129" and loja.status == "ativo"


def test_sobre_tem_limite_de_500(client, loja):
    """Texto maior que 500 caracteres é recusado."""
    resposta = salvar_pagina(client, loja, sobre="x" * 501)

    assert "sobre" in resposta.context["form"].errors


def test_cliente_a_nao_edita_a_loja_de_b(client, criar_anunciante):
    """O painel sempre edita a loja de quem está logado; B não muda com o POST de A."""
    a = criar_anunciante("a@exemplo.com", "Loja A")
    b = criar_anunciante("b@exemplo.com", "Loja B")

    salvar_pagina(client, a, sobre="Texto de A")
    resposta = salvar_pagina(client, a, slug=b.slug)  # tentar "virar" a loja B pelo endereço

    b.refresh_from_db()
    assert b.sobre == "" and b.slug == "loja-b"
    assert "slug" in resposta.context["form"].errors


# --- Imagens -----------------------------------------------------------------------------


def test_logo_vira_webp_400_e_96_e_o_original_some(client, loja):
    """Logo retangular: recortado em quadrado, WebP 400 e 96 px; o envio original é apagado."""
    salvar_pagina(client, loja, logo_envio=envio("logo.png", imagem(600, 450)))

    loja.refresh_from_db()
    assert not loja.logo_original and not loja.imagens_processando
    for campo, lado in [("logo", 400), ("logo_mini", 96)]:
        arquivo = getattr(loja, campo)
        assert arquivo.name.endswith(".webp") and "logo.png" not in arquivo.name
        with Image.open(arquivo.path) as img:
            assert (img.format, img.size) == ("WEBP", (lado, lado))


def test_capa_recortada_em_4_por_1(client, loja):
    """Capa 2000×1000: recorte 4:1 pelo centro, WebP 1600×400 e 800×200."""
    salvar_pagina(client, loja, capa_envio=envio("capa.jpg", imagem(2000, 1000, "JPEG"), "image/jpeg"))

    loja.refresh_from_db()
    with Image.open(loja.capa.path) as img:
        assert img.size == (1600, 400)
    with Image.open(loja.capa_media.path) as img:
        assert img.size == (800, 200)


def test_exif_e_removido(client, loja):
    """Foto de celular com GPS: o WebP final não tem EXIF nenhum."""
    salvar_pagina(
        client, loja, logo_envio=envio("foto.jpg", imagem(500, 500, "JPEG", exif=True), "image/jpeg")
    )

    loja.refresh_from_db()
    with Image.open(loja.logo.path) as img:
        assert not img.getexif() and "exif" not in img.info


def test_trocar_o_logo_apaga_as_versoes_antigas(client, loja):
    """Ao enviar outro logo, os WebP antigos saem do storage."""
    salvar_pagina(client, loja, logo_envio=envio("a.png", imagem(500, 500)))
    loja.refresh_from_db()
    antigo = loja.logo.path

    salvar_pagina(client, loja, logo_envio=envio("b.png", imagem(500, 500)))

    import os

    assert not os.path.exists(antigo)


@pytest.mark.parametrize(
    ("arquivo", "trecho"),
    [
        (envio("x.png", b"<?php echo 1; ?>"), "inválida"),
        (envio("x.gif", imagem(500, 500, "GIF"), "image/gif"), "não aceito"),
        (envio("x.png", imagem(300, 300)), "o mínimo é 400×400"),
    ],
)
def test_logo_invalido_e_recusado(client, loja, arquivo, trecho):
    """Arquivo falso, formato errado ou pequeno demais: erro no campo, nada salvo."""
    resposta = salvar_pagina(client, loja, logo_envio=arquivo)

    erros = resposta.context["form"].errors["logo_envio"]
    assert trecho in erros[0]
    loja.refresh_from_db()
    assert not loja.logo and not loja.logo_original


def test_limite_de_tamanho_vem_da_configuracao(client, loja):
    """Limite do logo em KB é o da Configuracao (editável no admin)."""
    config = configuracao()
    config.limite_logo_kb = 1
    config.save()

    resposta = salvar_pagina(client, loja, logo_envio=envio("x.png", imagem(500, 500)))

    assert "o máximo é 1 KB" in resposta.context["form"].errors["logo_envio"][0]


def test_capa_pequena_demais(client, loja):
    """Capa abaixo do mínimo (1200×300) é recusada."""
    resposta = salvar_pagina(client, loja, capa_envio=envio("c.png", imagem(800, 200)))

    assert "o mínimo é 1200×300" in resposta.context["form"].errors["capa_envio"][0]


def test_processamento_com_arquivo_corrompido_descarta_o_envio(loja):
    """Se o arquivo não abrir no Celery, o envio é descartado e a página não quebra."""
    from django.core.files.base import ContentFile

    loja.logo_original.save("x.png", ContentFile(b"lixo"), save=True)

    assert processar_imagem_loja(loja, "logo") is False
    loja.refresh_from_db()
    assert not loja.logo_original and not loja.logo


# --- Vitrine pública ----------------------------------------------------------------------


def test_vitrine_da_loja_ativa(client, loja):
    """Nome, selo de verificado, sobre e horário aparecem; endereço só se a loja permitir."""
    loja.sobre, loja.horario, loja.endereco_publico = (
        "Revisados com garantia.",
        "Seg a sex 8h–18h",
        "Rua X, 10",
    )
    loja.save()

    html = client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()

    assert "Loja Alfa" in html and "CNPJ verificado" in html
    assert "Revisados com garantia." in html and "Seg a sex 8h–18h" in html
    assert "Rua X, 10" not in html  # mostrar_no_mapa desligado

    loja.mostrar_no_mapa = True
    loja.save()
    assert "Rua X, 10" in client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()


@pytest.mark.parametrize("status", [Anunciante.Status.PENDENTE, Anunciante.Status.SUSPENSO])
def test_loja_pendente_ou_suspensa_da_404(client, criar_anunciante, status):
    """Só lojas ativas têm página; o resto é 404 (página e WhatsApp)."""
    loja = criar_anunciante("x@exemplo.com", "Loja X", status=status)

    assert client.get(reverse("anunciantes:loja", args=[loja.slug])).status_code == 404
    assert client.get(reverse("anunciantes:loja_whatsapp", args=[loja.slug])).status_code == 404


def test_loja_em_cidade_desligada_da_404(client, loja, tangara):
    """Cidade tirada do site: a loja some junto."""
    tangara.liberada = False
    tangara.save()

    assert client.get(reverse("anunciantes:loja", args=[loja.slug])).status_code == 404


def test_loja_demo_so_aparece_com_mostrar_demo(client, loja, settings):
    """Loja de demonstração não aparece sem MOSTRAR_DEMO (nunca misturada a lojas reais sem aviso)."""
    Anunciante.objects.filter(pk=loja.pk).update(demo=True)
    url = reverse("anunciantes:loja", args=[loja.slug])
    assert client.get(url).status_code == 404

    settings.MOSTRAR_DEMO = True
    html = client.get(url).content.decode()
    assert "Dados de demonstração:" in html


def test_whatsapp_nao_aparece_em_texto_e_redireciona(client, loja):
    """O número não fica no HTML; o botão passa por /whatsapp/ e cai no wa.me."""
    html = client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()
    assert "5565999990001" not in html and "99999-0001" not in html and "wa.me" not in html

    resposta = client.get(reverse("anunciantes:loja_whatsapp", args=[loja.slug]))

    assert resposta.status_code == 302 and resposta["Location"].startswith(
        "https://wa.me/5565999990001?text="
    )


# --- SEO ---------------------------------------------------------------------------------


def test_seo_title_description_open_graph(client, loja, settings):
    """Title e description próprios, canonical, og:title/url/image (com logo) e og:type."""
    loja.sobre = "Os melhores seminovos de Tangará."
    loja.save()
    client.force_login(loja.usuario)
    client.post(
        reverse("anunciantes:painel_loja"), dados_da_pagina(loja, logo_envio=envio("l.png", imagem(500, 500)))
    )
    client.logout()
    loja.refresh_from_db()
    url = settings.SITE_URL + reverse("anunciantes:loja", args=[loja.slug])

    html = client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()

    assert re.search(r"<title>Loja Alfa · Revenda de veículos em Tangará da Serra", html)
    assert '<meta name="description" content="Os melhores seminovos de Tangará.">' in html
    assert f'<link rel="canonical" href="{url}">' in html
    assert f'<meta property="og:url" content="{url}">' in html
    assert f'<meta property="og:image" content="{settings.SITE_URL}{loja.logo.url}">' in html
    assert '<meta property="og:title" content="Loja Alfa · 0 anúncios' in html


@pytest.mark.parametrize(("corretor", "tipo"), [(False, "AutoDealer"), (True, "RealEstateAgent")])
def test_schema_org_por_tipo_de_loja(client, criar_anunciante, corretor, tipo):
    """Revenda = AutoDealer; corretor/imobiliária = RealEstateAgent."""
    loja = criar_anunciante("x@exemplo.com", "Loja X", corretor=corretor)

    html = client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()
    bloco = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)

    dados = json.loads(bloco)
    assert dados["@type"] == tipo and dados["name"] == "Loja X" and dados["@context"] == "https://schema.org"


def test_schema_org_escapa_texto_do_anunciante(client, loja):
    """Um "sobre" com </script> não fecha o bloco ld+json (escape do json_script)."""
    loja.sobre = "Oi </script><script>alert(1)</script>"
    loja.save()

    html = client.get(reverse("anunciantes:loja", args=[loja.slug])).content.decode()

    assert "<script>alert(1)</script>" not in html
    assert "\\u003C/script\\u003E" in html


def test_sitemap_tem_lojas_ativas_e_robots_aponta_para_ele(client, criar_anunciante):
    """Loja ativa entra no sitemap; suspensa não. robots.txt indica o sitemap."""
    ativa = criar_anunciante("a@exemplo.com", "Loja Ativa")
    suspensa = criar_anunciante("s@exemplo.com", "Loja Suspensa", status=Anunciante.Status.SUSPENSO)

    xml = client.get("/sitemap.xml").content.decode()

    assert f"/loja/{ativa.slug}/" in xml and f"/loja/{suspensa.slug}/" not in xml
    assert "/lojas/" in xml and "/privacidade/" not in xml
    robots = client.get("/robots.txt").content.decode()
    assert "Sitemap: http://testserver/sitemap.xml" in robots and "Disallow: /painel/" in robots


# --- /lojas/ e home ----------------------------------------------------------------------


def test_lista_de_lojas_com_filtros(client, criar_anunciante):
    """Lista só ativas; filtros por tipo e cidade; filtro inválido é ignorado."""
    criar_anunciante("r@exemplo.com", "Revenda Um")
    criar_anunciante("c@exemplo.com", "Corretor Dois", corretor=True)
    criar_anunciante("p@exemplo.com", "Pendente Tres", status=Anunciante.Status.PENDENTE)

    html = client.get(reverse("anunciantes:lojas")).content.decode()
    assert "Revenda Um" in html and "Corretor Dois" in html and "Pendente Tres" not in html

    html = client.get(reverse("anunciantes:lojas"), {"tipo": "corretor_autonomo"}).content.decode()
    assert "Corretor Dois" in html and "Revenda Um" not in html

    html = client.get(reverse("anunciantes:lojas"), {"tipo": "xyz", "cidade": "abc"}).content.decode()
    assert "Revenda Um" in html and "Corretor Dois" in html


def test_home_mostra_lojas_do_banco_com_logo(client, loja):
    """A vitrine de lojas da home lê do banco (com link para a página e logo, se houver)."""
    client.force_login(loja.usuario)
    client.post(
        reverse("anunciantes:painel_loja"), dados_da_pagina(loja, logo_envio=envio("l.png", imagem(500, 500)))
    )
    client.logout()
    loja.refresh_from_db()

    html = client.get(reverse("core:inicio")).content.decode()

    assert "Lojas verificadas" in html and f'href="{reverse("anunciantes:loja", args=[loja.slug])}"' in html
    assert f'src="{loja.logo_mini.url}"' in html
