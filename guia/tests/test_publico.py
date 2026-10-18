"""Testes das páginas públicas do guia (etapa G2; docs/GUIA.md §5 a §7): entrada no menu e na home só com o
guia no ar, 404 com o guia desligado (e pré-visualização da equipe), perfil não publicado dá 404, contato sem
expor o número, contagem de cliques (robô não conta), "aberto agora" no fuso do estado, página fina com
noindex e fora do sitemap, ficha restrita do regulamentado, lista sem JavaScript, busca e rodízio."""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from contas.models import Usuario
from core.models import Bairro
from guia import services
from guia.models import EstatisticaGuiaDia, PerfilGuia

pytestmark = pytest.mark.django_db

PESSOA = {"HTTP_USER_AGENT": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile Safari/537.36"}
ROBO = {"HTTP_USER_AGENT": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
UTC = datetime.UTC


def url_categoria(slug: str = "eletricista") -> str:
    """Lista de uma categoria em Tangará."""
    return reverse("guia:categoria", args=["mt", "tangara-da-serra", slug])


def html(client, url: str, **extra) -> str:
    """Conteúdo da página (asserta 200)."""
    resposta = client.get(url, **{**PESSOA, **extra})
    assert resposta.status_code == 200, resposta.status_code
    return resposta.content.decode()


# --- Entrada no site ------------------------------------------------------------------------------------


def test_menu_cartao_e_rodape_so_com_o_guia_no_ar(client, tangara):
    """Desligado: nada do guia na home. Ligado: menu (primeiro item, com "Novo"), cartão e rodapé."""
    desligado = html(client, reverse("core:inicio"))
    assert 'href="/guia/"' not in desligado and "Guia de Negócios" not in desligado

    config = services.configuracao_guia()
    config.ativo = True
    config.nome_guia = "Guia da Região"
    config.save()
    ligado = html(client, reverse("core:inicio"))

    menu = ligado.split('aria-label="Principal"')[1].split("</nav>")[0]
    assert menu.index("Guia da Região") < menu.index("Imóveis")
    assert "Novo" in menu
    assert "Encontre eletricista, pedreiro, clínica, restaurante e mais na sua cidade" in ligado
    assert ligado.count('href="/guia/"') >= 4  # menu, menu do celular, cartão e rodapé


def test_guia_desligado_da_404_e_a_equipe_ve_a_previa(client, perfil_publicado):
    """Público: 404 em todas as páginas. Equipe logada: vê, com a faixa e noindex."""
    perfil = perfil_publicado()
    urls = [
        reverse("guia:inicio"),
        reverse("guia:cidade", args=["mt", "tangara-da-serra"]),
        url_categoria(),
        reverse("guia:empresa", args=[perfil.slug]),
        reverse("guia:whatsapp", args=[perfil.pk]),
    ]
    for url in urls:
        assert client.get(url, **PESSOA).status_code == 404, url

    equipe = Usuario.objects.create_user(email="eq@exemplo.com", password="x" * 12, nome="Eq", is_staff=True)
    client.force_login(equipe)
    pagina = html(client, reverse("guia:empresa", args=[perfil.slug]))
    assert "Guia desligado:" in pagina and "visível só para a equipe" in pagina
    assert '<meta name="robots" content="noindex, follow">' in pagina


@pytest.mark.parametrize("situacao", ["pausado", "rascunho", "aguardando_aceite", "removido"])
def test_perfil_nao_publicado_da_404(client, guia_ligado, perfil_publicado, situacao):
    """Fora do ar em qualquer situação: ficha e contatos dão 404; some da lista."""
    perfil = perfil_publicado(telefone="+556533330000")
    PerfilGuia.objects.filter(pk=perfil.pk).update(status=situacao)

    for url in ("guia:empresa", "guia:whatsapp", "guia:telefone"):
        arg = perfil.slug if url == "guia:empresa" else perfil.pk
        assert client.get(reverse(url, args=[arg]), **PESSOA).status_code == 404
    assert perfil.nome_publico not in html(client, url_categoria())


# --- Contato sem expor dados -------------------------------------------------------------------------


def test_numeros_fora_do_html(client, guia_ligado, perfil_publicado):
    """Nem o WhatsApp nem o telefone aparecem em texto na ficha, na lista ou no schema.org."""
    perfil = perfil_publicado(whatsapp="+5565999990101", telefone="+556533334444")

    for pagina in (html(client, reverse("guia:empresa", args=[perfil.slug])), html(client, url_categoria())):
        for trecho in ("99999-0101", "65999990101", "999990101", "3333-4444", "6533334444"):
            assert trecho not in pagina
    assert reverse("guia:whatsapp", args=[perfil.pk]) in pagina


def test_whatsapp_conta_o_clique_e_redireciona(client, guia_ligado, perfil_publicado):
    """302 para o wa.me; o mesmo visitante conta uma vez por dia; robô não conta."""
    perfil = perfil_publicado()
    url = reverse("guia:whatsapp", args=[perfil.pk])

    resposta = client.get(url, **PESSOA)
    client.get(url, **PESSOA)
    client.get(url, **ROBO, REMOTE_ADDR="10.9.9.9")

    assert resposta.status_code == 302 and resposta["Location"].startswith(
        "https://wa.me/5565999990101?text="
    )
    assert resposta["X-Robots-Tag"] == "noindex, nofollow"
    assert EstatisticaGuiaDia.objects.get(perfil=perfil).cliques_whatsapp == 1


def test_ver_telefone_com_htmx_e_sem_js(client, guia_ligado, perfil_publicado):
    """HTMX: só o número (troca o botão). Sem JS: página com o número. Conta o clique uma vez."""
    perfil = perfil_publicado(telefone="+556533334444")
    url = reverse("guia:telefone", args=[perfil.pk])

    fragmento = client.get(url, HTTP_HX_REQUEST="true", **PESSOA).content.decode()
    pagina = html(client, url)

    assert "(65) 3333-4444" in fragmento and "<html" not in fragmento
    assert "(65) 3333-4444" in pagina and "<html" in pagina and "noindex" in pagina
    assert EstatisticaGuiaDia.objects.get(perfil=perfil).cliques_telefone == 1


def test_limite_de_contatos_por_hora(client, guia_ligado, perfil_publicado):
    """Passou do limite da configuração: 429 sem o número."""
    guia_ligado.contatos_por_hora = 2
    guia_ligado.save()
    perfil = perfil_publicado(telefone="+556533334444")
    url = reverse("guia:telefone", args=[perfil.pk])

    codigos = [client.get(url, **PESSOA).status_code for _ in range(3)]
    ultimo = client.get(url, **PESSOA).content.decode()

    assert codigos == [200, 200, 429] and "3333-4444" not in ultimo


def test_visualizacao_conta_e_robo_e_equipe_nao(client, guia_ligado, perfil_publicado):
    """Ficha vista por gente conta 1 por dia; robô e equipe logada não contam."""
    perfil = perfil_publicado()
    url = reverse("guia:empresa", args=[perfil.slug])

    client.get(url, **PESSOA)
    client.get(url, **PESSOA)
    client.get(url, **ROBO, REMOTE_ADDR="10.8.8.8")

    assert EstatisticaGuiaDia.objects.get(perfil=perfil).visualizacoes == 1


# --- Aberto agora, rodízio e busca --------------------------------------------------------------------


def test_aberto_agora_no_fuso_do_estado(perfil_publicado):
    """Segunda 08:00–12:00 em Cuiabá (UTC−4): 13:00 UTC = 09:00 (aberto); 16:30 UTC = 12:30 (fechado)."""
    perfil = perfil_publicado(horarios={"seg": [["08:00", "12:00"]]})
    segunda = datetime.date(2026, 10, 12)
    assert segunda.weekday() == 0 and perfil.fuso == "America/Cuiaba"

    assert services.aberto_agora(perfil, datetime.datetime(2026, 10, 12, 13, 0, tzinfo=UTC)) is True
    assert services.aberto_agora(perfil, datetime.datetime(2026, 10, 12, 16, 30, tzinfo=UTC)) is False
    # 03:30 UTC de terça = 23:30 de segunda em Cuiabá: fechado (e não "terça").
    assert services.aberto_agora(perfil, datetime.datetime(2026, 10, 13, 3, 30, tzinfo=UTC)) is False
    perfil.horarios = {}
    assert services.aberto_agora(perfil) is None
    assert services.fuso_da_uf("AM") == "America/Manaus" and services.fuso_da_uf("SP") == "America/Sao_Paulo"


def test_lista_sem_js_filtra_aberto_e_bairro(client, guia_ligado, perfil_publicado, tangara):
    """Formulário GET: "Aberto agora" (24h x sem horário) e bairro funcionam sem JavaScript."""
    centro = Bairro.objects.create(cidade=tangara, nome="Centro", slug="centro")
    todo_dia = {d: [["00:00", "24:00"]] for d in services.CHAVES_DIAS}
    perfil_publicado(nome="Sempre Aberto", whatsapp="+5565999990111", horarios=todo_dia, bairro=centro)
    perfil_publicado(nome="Sem Horario", whatsapp="+5565999990112")

    todos = html(client, url_categoria())
    abertos = html(client, url_categoria() + "?aberto=1")
    no_bairro = html(client, url_categoria() + "?bairro=centro")

    assert "Sempre Aberto" in todos and "Sem Horario" in todos
    assert "Sempre Aberto" in abertos and "Sem Horario" not in abertos
    assert "Sempre Aberto" in no_bairro and "Sem Horario" not in no_bairro
    assert '<form id="guia-filtros"' in todos and 'method="get"' in todos
    assert '<meta name="robots" content="noindex, follow">' in abertos  # filtrada não indexa


def test_rodizio_estavel_no_dia_e_nao_por_cadastro(perfil_publicado):
    """Mesma semente (mesmo dia): mesma ordem; outro dia: outra ordem."""
    perfis = [perfil_publicado(nome=f"P{i}", whatsapp=f"+55659999901{i:02d}") for i in range(8)]

    hoje = [p.pk for p in services.rodizio(perfis, "2026-10-18-x")]
    de_novo = [p.pk for p in services.rodizio(list(reversed(perfis)), "2026-10-18-x")]
    amanha = [p.pk for p in services.rodizio(perfis, "2026-10-19-x")]

    assert hoje == de_novo and hoje != amanha


def test_busca_sem_acento_e_com_erro_de_digitacao(client, guia_ligado, perfil_publicado):
    """ "eletrecista" (erro) e "ELETRICISTA" acham pela categoria; o nome também é buscado."""
    perfil_publicado(nome="Faísca Instalações")

    for termo in ("eletrecista", "ELETRICISTA", "faisca"):
        assert "Faísca Instalações" in html(client, reverse("guia:inicio") + f"?q={termo}"), termo
    assert "noindex" in html(client, reverse("guia:inicio") + "?q=faisca")


# --- SEO -----------------------------------------------------------------------------------------------


def test_categoria_fina_vira_noindex_e_sai_do_sitemap(client, guia_ligado, perfil_publicado):
    """Menos que o mínimo (3): noindex, follow e fora do sitemap. Com 3: indexável e no sitemap."""
    perfil_publicado(nome="A", whatsapp="+5565999990121")
    pagina = html(client, url_categoria())
    sitemap = client.get("/sitemap.xml").content.decode()
    assert '<meta name="robots" content="noindex, follow">' in pagina
    assert url_categoria() not in sitemap

    perfil_publicado(nome="B", whatsapp="+5565999990122")
    perfil_publicado(nome="C", whatsapp="+5565999990123")
    pagina = html(client, url_categoria())
    sitemap = client.get("/sitemap.xml").content.decode()
    assert 'name="robots"' not in pagina
    assert url_categoria() in sitemap and reverse("guia:cidade", args=["mt", "tangara-da-serra"]) in sitemap
    assert '<link rel="canonical" href="http' in pagina and "Eletricista em Tangará da Serra - MT" in pagina


def test_sitemap_sem_guia_quando_desligado(client, perfil_publicado):
    """Guia desligado: nada do guia no sitemap."""
    perfil = perfil_publicado()
    assert reverse("guia:empresa", args=[perfil.slug]) not in client.get("/sitemap.xml").content.decode()


def test_ficha_tem_local_business_sem_telefone(client, guia_ligado, perfil_publicado):
    """schema.org LocalBusiness com endereço e horário; sem telefone (o número não vai ao HTML)."""
    perfil = perfil_publicado(horarios={"seg": [["08:00", "18:00"]]}, frase="Box e espelhos sob medida")
    pagina = html(client, reverse("guia:empresa", args=[perfil.slug]))
    schema = pagina.split('<script type="application/ld+json">')[1].split("</script>")[0]

    assert '"@type": "LocalBusiness"' in schema and '"PostalAddress"' in schema
    assert '"openingHoursSpecification"' in schema and "telephone" not in schema
    assert "Box e espelhos sob medida" in pagina and "Horário" in pagina


def _logo() -> SimpleUploadedFile:
    """Logo de verdade (Pillow)."""
    saida = io.BytesIO()
    Image.new("RGB", (400, 400), (10, 120, 140)).save(saida, format="PNG")
    return SimpleUploadedFile("logo.png", saida.getvalue(), content_type="image/png")


def test_regulamentado_sem_frase_logo_e_horario(client, guia_ligado, perfil_publicado):
    """Dentista: nome, especialidade, registro, contato e local; sem logo, horário nem frase."""
    perfil = perfil_publicado(
        slugs=("dentista",), registro_profissional="CRO-MT 1234", horarios={"seg": [["08:00", "18:00"]]}
    )
    services.definir_logo(perfil, _logo())

    pagina = html(client, reverse("guia:empresa", args=[perfil.slug]))

    assert "CRO-MT 1234" in pagina and "Dentista" in pagina and "Rua das Flores, 100" in pagina
    assert perfil.logo.url not in pagina
    assert "Horário" not in pagina and "Aberto agora" not in pagina and "Fechado agora" not in pagina
    assert "openingHours" not in pagina


def test_pagina_da_cidade_mostra_grupos_com_contagem(client, guia_ligado, perfil_publicado):
    """Grupos e categorias da cidade com a contagem; categoria sem empresa não aparece."""
    perfil_publicado(nome="A", whatsapp="+5565999990131")
    perfil_publicado(nome="B", whatsapp="+5565999990132", slugs=("eletricista", "pintor"))

    pagina = html(client, reverse("guia:cidade", args=["mt", "tangara-da-serra"]))

    assert "Construção e Reforma" in pagina
    assert 'eletricista/">Eletricista</a> <span class="text-suave tabular">(2)' in pagina
    assert 'pintor/">Pintor</a> <span class="text-suave tabular">(1)' in pagina
    assert "Encanador" not in pagina
