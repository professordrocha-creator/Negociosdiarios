"""Testes da página pública do anúncio: conteúdo, SEO e prévia de compartilhamento, localização
conforme a escolha do anunciante, WhatsApp com contagem, "não está mais disponível" e sitemap."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from anunciantes.models import Anunciante
from anuncios import services
from anuncios.models import Anuncio
from anuncios.tests.conftest import envio
from estatisticas.models import EstatisticaDiaria

pytestmark = pytest.mark.django_db

NAVEGADOR = "Mozilla/5.0 (Linux; Android 14) Chrome/128 Mobile"


@pytest.fixture
def visitante(client):
    """Client com cara de navegador de gente (robôs não contam visita)."""
    client.defaults["HTTP_USER_AGENT"] = NAVEGADOR
    return client


def pagina(client, anuncio):
    """HTML da página pública do anúncio."""
    resposta = client.get(services.url_publica(anuncio))
    assert resposta.status_code == 200
    return resposta.content.decode()


# --- Conteúdo e URL -------------------------------------------------------------------------


def test_url_tem_codigo_e_slug(loja, publicado):
    """/anuncio/ND-IM-00001-casa-3-quartos-com-area-gourmet/."""
    anuncio = publicado(loja())

    assert services.url_publica(anuncio) == f"/anuncio/{anuncio.codigo}-casa-3-quartos-com-area-gourmet/"


def test_pagina_mostra_galeria_ficha_preco_e_loja(visitante, loja, publicado):
    """Fotos grandes, ficha, preço, descrição, loja com selo, ajuda de segurança e link de denúncia."""
    anuncio = publicado(loja())

    html = pagina(visitante, anuncio)

    assert anuncio.titulo in html and "R$ 420.000" in html and "Casa ampla, perto do centro." in html
    assert anuncio.fotos.first().imagem.url in html and "data-galeria" in html
    assert "<dt>Quartos</dt><dd>3</dd>" in html and "180 m²" in html
    assert "Loja Alfa" in html and "CNPJ verificado" in html
    assert reverse("core:denunciar") + f"?anuncio={anuncio.codigo}" in html
    assert "Dica de segurança" in html


def test_whatsapp_sem_numero_no_html_e_com_mensagem_pronta(visitante, loja, publicado):
    """O número da loja nunca aparece; o botão passa pelo redirecionamento; a mensagem cita o código."""
    anuncio = publicado(loja())

    html = pagina(visitante, anuncio)

    assert "999990001" not in html and "wa.me" not in html
    assert reverse("anuncios:whatsapp", args=[anuncio.codigo]) in html
    assert f"o anúncio {anuncio.codigo}" in html


def test_slug_antigo_redireciona_para_o_novo(visitante, loja, publicado):
    """Título mudou: o link antigo (e o código sozinho) levam à URL nova com 301."""
    anuncio = publicado(loja())
    antiga = services.url_publica(anuncio)
    services.atualizar_anuncio(anuncio, {"titulo": "Casa reformada com piscina"})

    for url in (antiga, f"/anuncio/{anuncio.codigo}/", f"/anuncio/{anuncio.codigo.lower()}-x/"):
        resposta = visitante.get(url)
        assert resposta.status_code == 301
        assert resposta["Location"] == f"/anuncio/{anuncio.codigo}-casa-reformada-com-piscina/"


def test_codigo_inexistente_da_404(visitante):
    """Código que nunca existiu: 404."""
    assert visitante.get("/anuncio/ND-IM-99999-qualquer/").status_code == 404


# --- SEO e prévia de compartilhamento -------------------------------------------------------


def test_seo_title_description_canonical_og_e_schema(visitante, loja, publicado, settings):
    """Título com preço e cidade, canonical absoluto, og:image JPEG 1200×630 e schema.org Offer."""
    anuncio = publicado(loja())
    capa = anuncio.fotos.first()

    html = pagina(visitante, anuncio)

    assert f"<title>{anuncio.titulo} · R$ 420.000 · Tangará da Serra" in html
    assert f'<link rel="canonical" href="{settings.SITE_URL}{services.url_publica(anuncio)}">' in html
    assert f'<meta property="og:image" content="{settings.SITE_URL}{capa.compartilhamento.url}">' in html
    assert html.count('property="og:image"') == 1  # uma só (o WhatsApp usa a primeira)
    assert '<meta property="og:image:type" content="image/jpeg">' in html
    assert 'content="1200"' in html and 'content="630"' in html
    dados = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert dados["@type"] == "Offer" and dados["sku"] == anuncio.codigo and dados["priceCurrency"] == "BRL"
    assert "noindex" not in html


def test_jpeg_de_compartilhamento_tem_1200x630(loja, imovel):
    """A prévia do link usa um JPEG 1200×630 sem EXIF, gerado junto com os WebP."""
    from PIL import Image

    anuncio = imovel(loja(), completo=False)
    foto = services.adicionar_fotos(anuncio, [envio(largura=2400, altura=1800, gps=True)])[0]
    services.processar_foto(foto)

    with Image.open(foto.compartilhamento) as imagem:
        assert imagem.format == "JPEG" and imagem.size == (1200, 630) and not imagem.getexif()


# --- Localização conforme a escolha do anunciante -------------------------------------------


def localizacao_no_html(html: str) -> dict | None:
    """Os dados do mapa que vão para o navegador (json_script), ou None."""
    achado = re.search(r'<script id="localizacao-anuncio" type="application/json">(.*?)</script>', html)
    return json.loads(achado.group(1)) if achado else None


def test_localizacao_exata_mostra_o_ponto(visitante, loja, publicado):
    """Exata: o marcador fica no ponto marcado."""
    anuncio = publicado(loja())
    anuncio.imovel.exibir_localizacao = "exata"
    anuncio.imovel.save()

    local = localizacao_no_html(pagina(visitante, anuncio))

    assert local == {"tipo": "exata", "lat": -14.62, "lng": -57.49}


def test_localizacao_aproximada_nunca_revela_o_ponto(visitante, loja, publicado):
    """Aproximada: círculo de 300 m com o centro deslocado (fixo) e o ponto exato fora do HTML."""
    anuncio = publicado(loja())
    anuncio.imovel.ponto = Point(-57.491234, -14.621234, srid=4326)
    anuncio.imovel.save()

    html = pagina(visitante, anuncio)
    local = localizacao_no_html(html)

    assert local["tipo"] == "aproximada" and local["raio"] == 300
    assert "-14.621234" not in html and "-57.491234" not in html
    distancia = (
        Point(local["lng"], local["lat"], srid=4326)
        .transform(3857, clone=True)
        .distance(anuncio.imovel.ponto.transform(3857, clone=True))
    )
    assert 30 < distancia < 260  # deslocado, mas o imóvel continua dentro do círculo
    assert localizacao_no_html(pagina(visitante, anuncio)) == local  # mesmo círculo a cada visita


def test_so_bairro_mostra_so_o_nome(visitante, loja, publicado, tangara):
    """Só o bairro: sem mapa e sem coordenada; aparece o nome do bairro."""
    from core.models import Bairro

    anuncio = publicado(loja())
    anuncio.bairro = Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")
    anuncio.save()
    anuncio.imovel.exibir_localizacao = "so_bairro"
    anuncio.imovel.save()

    html = pagina(visitante, anuncio)

    assert localizacao_no_html(html) is None and 'id="mapa-anuncio"' not in html
    assert "Bairro <b>Jardim Europa</b>" in html and "leaflet.js" not in html


def test_endereco_privado_nunca_aparece(visitante, loja, publicado):
    """O endereço digitado no painel é só para a equipe."""
    anuncio = publicado(loja())
    anuncio.imovel.endereco = "Rua Secreta, 123"
    anuncio.imovel.save()

    assert "Rua Secreta" not in pagina(visitante, anuncio)


def test_mapa_usa_o_leaflet_do_proprio_site(visitante, loja, publicado):
    """Leaflet servido do nosso static, sem CDN."""
    html = pagina(visitante, publicado(loja()))

    assert "/static/vendor/leaflet/leaflet.js" in html and "/static/vendor/leaflet/leaflet.css" in html
    assert "unpkg" not in html and "cdn" not in html.lower()


# --- WhatsApp -------------------------------------------------------------------------------


def test_whatsapp_redireciona_com_mensagem_e_conta_o_clique(visitante, loja, publicado):
    """302 para o wa.me da loja com a mensagem pronta; o clique entra na estatística do dia."""
    anuncio = publicado(loja())

    resposta = visitante.get(reverse("anuncios:whatsapp", args=[anuncio.codigo]))

    destino = urlparse(resposta["Location"])
    assert resposta.status_code == 302 and destino.netloc == "wa.me" and destino.path == "/5565999990001"
    texto = parse_qs(destino.query)["text"][0]
    assert anuncio.codigo in texto and anuncio.titulo in texto
    assert EstatisticaDiaria.objects.get(anuncio=anuncio).cliques_whatsapp == 1


def test_whatsapp_de_anuncio_fora_do_ar_volta_para_a_pagina(visitante, loja, publicado):
    """Pausado: não manda para o WhatsApp nem conta clique."""
    anuncio = publicado(loja())
    services.pausar(anuncio)

    resposta = visitante.get(reverse("anuncios:whatsapp", args=[anuncio.codigo]))

    assert resposta["Location"] == services.url_publica(anuncio)
    assert not EstatisticaDiaria.objects.exists()


# --- "Não está mais disponível" e prévia do dono --------------------------------------------


@pytest.mark.parametrize(
    ("acao", "status"),
    [("pausar", 404), ("expirar", 404), ("excluir", 410), ("suspender_loja", 404)],
)
def test_fora_do_ar_mostra_indisponivel_com_parecidos(visitante, loja, publicado, acao, status):
    """Pausado, expirado, excluído ou loja suspensa: página explicativa, noindex e parecidos."""
    anunciante = loja()
    anuncio = publicado(anunciante, "Casa 3 quartos com área gourmet")
    outra = loja("b@exemplo.com", "Loja Beta")
    parecido = publicado(outra, "Casa 2 quartos perto da praça")
    if acao == "pausar":
        services.pausar(anuncio)
    elif acao == "expirar":
        Anuncio.objects.filter(pk=anuncio.pk).update(situacao="expirado")
    elif acao == "excluir":
        services.excluir(anuncio)
    else:
        Anunciante.objects.filter(pk=anunciante.pk).update(status="suspenso")

    resposta = visitante.get(services.url_publica(anuncio))
    html = resposta.content.decode()

    assert resposta.status_code == status
    assert (
        "Este anúncio não está mais disponível" in html and '<meta name="robots" content="noindex">' in html
    )
    assert parecido.titulo in html


def test_rascunho_nunca_publicado_da_404_para_o_publico(visitante, loja, imovel):
    """O que nunca esteve no ar não existe para o público."""
    anuncio = imovel(loja())

    assert visitante.get(services.url_publica(anuncio)).status_code == 404


def test_dono_ve_previa_sem_contar_visita(client, loja, imovel):
    """O dono vê o próprio rascunho (aviso de pré-visualização, noindex) e não conta visualização."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    client.force_login(anunciante.usuario)
    client.defaults["HTTP_USER_AGENT"] = NAVEGADOR

    html = client.get(services.url_publica(anuncio)).content.decode()

    assert "Pré-visualização:" in html and 'content="noindex"' in html
    assert not EstatisticaDiaria.objects.exists()


def test_demo_desligada_nao_aparece(visitante, criar_anunciante, publicado, loja, settings):
    """Anúncio de loja demo com MOSTRAR_DEMO desligado: 404 (demonstração não vaza)."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    Anuncio.objects.filter(pk=anuncio.pk).update(demo=True)
    Anunciante.objects.filter(pk=anunciante.pk).update(demo=True)
    settings.MOSTRAR_DEMO = False

    assert visitante.get(services.url_publica(anuncio)).status_code == 404


# --- Mais desta loja, sitemap, robots -------------------------------------------------------


def test_mais_desta_loja(visitante, loja, publicado):
    """Outros anúncios da mesma loja, sem repetir o atual."""
    anunciante = loja()
    anuncio = publicado(anunciante, "Casa 3 quartos com área gourmet")
    publicado(anunciante, "Apartamento 2 quartos no Centro")

    html = pagina(visitante, anuncio)

    secao = html.split("Mais desta loja", 1)[1]
    assert "Apartamento 2 quartos no Centro" in secao and "Casa 3 quartos com área gourmet" not in secao


def test_sitemap_lista_so_publicados(client, loja, publicado, imovel):
    """Publicados entram; rascunho e pausado não."""
    anunciante = loja()
    no_ar = publicado(anunciante, "Casa 3 quartos com área gourmet")
    pausado = publicado(anunciante, "Apartamento 2 quartos no Centro")
    services.pausar(pausado)
    rascunho = imovel(anunciante, "Terreno de esquina no Centro")

    xml = client.get("/sitemap.xml").content.decode()

    assert services.url_publica(no_ar) in xml
    assert pausado.codigo not in xml and rascunho.codigo not in xml


def test_robots_bloqueia_os_redirecionamentos_do_whatsapp(client):
    """Robôs não seguem os links de WhatsApp (nem contam cliques)."""
    texto = client.get("/robots.txt").content.decode()

    assert "Disallow: /anuncio/*/whatsapp/" in texto and "Disallow: /loja/*/whatsapp/" in texto


def test_painel_mostra_visualizacoes_e_cliques(client, loja, publicado):
    """Por anúncio (total) e da loja (30 dias)."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    from django.utils import timezone

    EstatisticaDiaria.objects.create(
        anuncio=anuncio, dia=timezone.localdate(), visualizacoes=37, cliques_whatsapp=5
    )
    client.force_login(anunciante.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Visualizações · 30 dias" in html and ">37<" in html and ">5<" in html
    assert services.url_publica(anuncio) in html
