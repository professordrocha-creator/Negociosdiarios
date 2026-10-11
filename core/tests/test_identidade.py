"""Testes da identidade do site (Configuracao), valores, textos de ajuda e favicon."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.models import Configuracao, TextoAjuda, ValorEmpresa
from core.services import configuracao, dados_do_site, textos_ajuda

pytestmark = pytest.mark.django_db

SVG_OK = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<circle cx="5" cy="5" r="4" fill="#f2b705"/></svg>'
)


@pytest.fixture
def midia(settings, tmp_path):
    """Uploads numa pasta temporária (nada vai para media/ do projeto)."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def admin_logado(client, entrar_no_admin):
    """Superusuário logado e verificado no admin."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    return client


def png(lado: int = 64, exif: bool = False, formato: str = "PNG") -> bytes:
    """Imagem de teste (com EXIF de GPS, se pedido)."""
    imagem = Image.new(
        "RGBA" if formato == "PNG" else "RGB", (lado, lado), (14, 74, 87, 255)[: 4 if formato == "PNG" else 3]
    )
    saida = io.BytesIO()
    if exif:
        dados = Image.Exif()
        dados[0x8825] = {2: (15.0, 30.0, 0.0)}  # GPSInfo: latitude
        dados[0x010F] = "Camera Teste"  # fabricante
        imagem.save(saida, format=formato, exif=dados)
    else:
        imagem.save(saida, format=formato)
    return saida.getvalue()


def postar_config(client, **mudancas):
    """Envia o formulário da identidade no admin com os valores atuais + `mudancas`."""
    config = configuracao()
    dados = {
        campo: getattr(config, campo)
        for campo in [
            "nome",
            "linha_regiao",
            "slogan",
            "empresa",
            "cidade_sede",
            "whatsapp",
            "email_contato",
            "email_privacidade",
            "endereco",
            "cnpj",
            "instagram",
            "sobre_quem_somos",
            "sobre_missao",
            "sobre_visao",
            "limite_simbolo_kb",
            "limite_compartilhamento_kb",
            "limite_logo_kb",
            "logo_min_px",
            "limite_capa_kb",
            "capa_min_largura_px",
            "capa_min_altura_px",
            "max_fotos_anuncio",
            "limite_foto_anuncio_kb",
            "foto_min_largura_px",
            "foto_min_altura_px",
            "titulo_min_caracteres",
            "titulo_max_caracteres",
            "descricao_max_caracteres",
            "carencia_dias",
            "expiracao_dias",
            "aviso_expiracao_dias",
            "moderacao",
        ]
    }
    dados.update(mudancas)
    return client.post(reverse("admin:core_configuracao_change", args=[Configuracao.ID_UNICO]), dados)


# --- Registro único e cache ----------------------------------------------------------------


def test_configuracao_nasce_do_settings_e_e_unica(settings):
    """Primeira leitura cria o registro 1 com os SITE_* do settings; nunca há um segundo."""
    config = configuracao()

    assert config.pk == 1 and config.nome == settings.SITE_NOME and config.slogan == settings.SITE_SLOGAN
    Configuracao(nome="Outro", email_contato="a@b.com", email_privacidade="a@b.com").save()
    assert Configuracao.objects.count() == 1
    with pytest.raises(PermissionError):
        configuracao().delete()


def test_trocar_o_slogan_aparece_no_site_na_hora(client):
    """Salvar limpa o cache: o novo slogan aparece já na próxima página."""
    assert "Slogan de teste" not in client.get(reverse("core:sobre")).content.decode()

    config = configuracao()
    config.slogan = "Slogan de teste"
    config.save()

    assert "Slogan de teste" in client.get(reverse("core:sobre")).content.decode()


def test_site_usa_o_cache(django_assert_num_queries):
    """Depois da primeira leitura, os dados do site vêm do cache (nenhuma consulta)."""
    dados_do_site()

    with django_assert_num_queries(0):
        assert dados_do_site()["nome"]


# --- Admin da identidade ----------------------------------------------------------------


def test_menu_identidade_abre_o_formulario_unico(admin_logado):
    """A lista redireciona para o único registro; não há "adicionar" nem "apagar"."""
    resposta = admin_logado.get(reverse("admin:core_configuracao_changelist"))

    assert resposta["Location"] == reverse("admin:core_configuracao_change", args=[1])
    assert admin_logado.get(reverse("admin:core_configuracao_add")).status_code == 403


def test_admin_troca_slogan_e_contatos(client, admin_logado, midia):
    """Pelo admin: slogan muda no site; WhatsApp e CNPJ são normalizados; Instagram sem @."""
    resposta = postar_config(
        admin_logado,
        slogan="Novo slogan pelo admin",
        whatsapp="(65) 99999-0000",
        cnpj="90.000.001/0001-29",
        instagram="@negociosdiarios",
    )

    assert resposta.status_code == 302
    config = configuracao()
    assert (config.whatsapp, config.cnpj, config.instagram) == (
        "+5565999990000",
        "90000001000129",
        "negociosdiarios",
    )
    assert "Novo slogan pelo admin" in client.get(reverse("core:inicio")).content.decode()


def test_cnpj_invalido_no_admin_e_recusado(admin_logado):
    """CNPJ com dígito errado não é salvo."""
    resposta = postar_config(admin_logado, cnpj="90.000.001/0001-28")

    assert resposta.status_code == 200 and "cnpj" in resposta.context["adminform"].form.errors


# --- Símbolos, favicon e imagem de compartilhamento --------------------------------------


def test_simbolo_svg_gera_favicons_e_aparece_no_site(client, admin_logado, midia):
    """SVG seguro: vira favicon SVG, gera os PNG 32/180/512 e o .ico; /favicon.ico aponta para ele."""
    postar_config(admin_logado, simbolo_claro=SimpleUploadedFile("logo.svg", SVG_OK, "image/svg+xml"))

    config = configuracao()
    assert (
        config.simbolo_claro.name.endswith(".svg") and "logo" not in config.simbolo_claro.name
    )  # nome aleatório
    for campo, lado in [("favicon_32", 32), ("favicon_180", 180), ("favicon_512", 512)]:
        with Image.open(getattr(config, campo).path) as imagem:
            assert imagem.size == (lado, lado)
    html = client.get(reverse("core:inicio")).content.decode()
    assert f'href="{config.simbolo_claro.url}" type="image/svg+xml"' in html
    assert f'href="{config.favicon_180.url}"' in html
    assert client.get("/favicon.ico")["Location"] == config.favicon_ico.url


def test_simbolo_escuro_aparece_no_topo_e_rodape(client, admin_logado, midia):
    """O símbolo para fundo escuro substitui o padrão no topo e no rodapé."""
    postar_config(admin_logado, simbolo_escuro=SimpleUploadedFile("escuro.png", png(), "image/png"))

    url = configuracao().simbolo_escuro.url
    assert client.get(reverse("core:inicio")).content.decode().count(f'src="{url}"') == 2


@pytest.mark.parametrize(
    "svg",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><rect/></a></svg>',
        b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><p>oi</p></foreignObject></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://site.example/x.png"/></svg>',
        b"isto nao e svg",
    ],
)
def test_svg_perigoso_ou_invalido_e_recusado(admin_logado, midia, svg):
    """SVG com script, evento, javascript:, DOCTYPE, foreignObject, link externo ou lixo: recusado."""
    resposta = postar_config(admin_logado, simbolo_claro=SimpleUploadedFile("x.svg", svg, "image/svg+xml"))

    assert "simbolo_claro" in resposta.context["adminform"].form.errors
    assert not configuracao().simbolo_claro


def test_arquivo_falso_e_recusado_pelo_tipo_real(admin_logado, midia):
    """Extensão .png com conteúdo que não é imagem: recusado (o Pillow confere o tipo real)."""
    resposta = postar_config(
        admin_logado, simbolo_claro=SimpleUploadedFile("x.png", b"<?php echo 1;", "image/png")
    )

    assert "simbolo_claro" in resposta.context["adminform"].form.errors


def test_simbolo_jpg_e_recusado(admin_logado, midia):
    """Símbolo precisa de transparência: SVG ou PNG, não JPG."""
    jpg = SimpleUploadedFile("x.png", png(formato="JPEG"), "image/jpeg")

    resposta = postar_config(admin_logado, simbolo_claro=jpg)

    assert "simbolo_claro" in resposta.context["adminform"].form.errors


def test_limite_de_tamanho_vem_da_configuracao(admin_logado, midia):
    """Arquivo maior que o limite (editável) é recusado com mensagem que diz o máximo."""
    config = configuracao()
    config.limite_simbolo_kb = 1
    config.save()

    resposta = postar_config(admin_logado, simbolo_claro=SimpleUploadedFile("x.png", png(400), "image/png"))

    erros = resposta.context["adminform"].form.errors["simbolo_claro"]
    assert "o máximo é 1 KB" in erros[0]


def test_imagem_de_compartilhamento_sem_exif(client, admin_logado, midia):
    """JPG com GPS: salvo regravado, sem EXIF; aparece no og:image."""
    postar_config(
        admin_logado,
        imagem_compartilhamento=SimpleUploadedFile("og.jpg", png(exif=True, formato="JPEG"), "image/jpeg"),
    )

    config = configuracao()
    with Image.open(config.imagem_compartilhamento.path) as imagem:
        assert not imagem.getexif()
    html = client.get(reverse("core:inicio")).content.decode()
    assert f'<meta property="og:image" content="{config.imagem_compartilhamento.url}">' in html


def test_sem_simbolo_usa_os_arquivos_padrao(client):
    """Sem nada enviado, o site usa os símbolos e favicons de static/img/."""
    html = client.get(reverse("core:inicio")).content.decode()

    assert 'href="/static/img/simbolo.svg" type="image/svg+xml"' in html
    assert 'src="/static/img/simbolo-ipe.svg"' in html
    assert client.get("/favicon.ico")["Location"] == "/static/img/favicon.ico"


# --- Página Sobre e valores ------------------------------------------------------------


def test_sobre_le_textos_e_valores_do_admin(client):
    """Quem somos, missão e visão da Configuracao; valores ativos na ordem do admin."""
    config = configuracao()
    config.sobre_quem_somos = "Primeiro parágrafo.\n\nSegundo parágrafo."
    config.sobre_missao = "Missão de teste."
    config.save()
    ValorEmpresa.objects.update(ativo=False)
    ValorEmpresa.objects.create(ordem=2, titulo="Segundo valor", texto="b")
    ValorEmpresa.objects.create(ordem=1, titulo="Primeiro valor", texto="a")

    html = client.get(reverse("core:sobre")).content.decode()

    assert "<p>Primeiro parágrafo.</p><p>Segundo parágrafo.</p>" in html
    assert "Missão de teste." in html
    assert html.index("Primeiro valor") < html.index("Segundo valor")
    assert "Confiança" not in html  # valor inicial desativado


def test_valores_iniciais_vieram_da_migration():
    """Os 5 valores que estavam no template agora estão no banco, editáveis."""
    assert list(ValorEmpresa.objects.values_list("titulo", flat=True)) == [
        "Confiança",
        "Proximidade",
        "Transparência",
        "Respeito aos seus dados",
        "Simplicidade",
    ]


# --- Textos de ajuda ------------------------------------------------------------------


def test_textos_de_ajuda_iniciais_vieram_da_migration():
    """As telas que tinham ajuda no código continuam com ela, agora no banco."""
    assert set(TextoAjuda.objects.values_list("chave", flat=True)) >= {
        "planos",
        "anuncie",
        "contato",
        "entrar",
        "painel",
        "cadastro",
        "em_breve",
    }
    assert textos_ajuda("planos")[0].startswith("Os planos diferem")


def test_editar_texto_de_ajuda_aparece_na_tela(client):
    """Mudou no admin, mudou na caixa "Sobre esta tela" (cache limpo ao salvar)."""
    client.get(reverse("core:planos"))  # enche o cache
    texto = TextoAjuda.objects.get(chave="planos")
    texto.texto = "Primeira dica nova.\nSegunda dica nova."
    texto.save()

    html = client.get(reverse("core:planos")).content.decode()

    assert "<li>Primeira dica nova.</li><li>Segunda dica nova.</li>" in html


def test_texto_de_ajuda_em_branco_esconde_a_caixa(client):
    """Texto vazio: a caixa some da tela."""
    TextoAjuda.objects.filter(chave="contato").update(texto="")
    from django.core.cache import cache

    cache.clear()

    assert "Sobre esta tela" not in client.get(reverse("core:contato")).content.decode()


def test_texto_de_ajuda_nao_aceita_html(client):
    """Texto puro: HTML aparece escapado (sem |safe)."""
    texto = TextoAjuda.objects.get(chave="planos")
    texto.texto = "<script>alert(1)</script>"
    texto.save()

    html = client.get(reverse("core:planos")).content.decode()

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
