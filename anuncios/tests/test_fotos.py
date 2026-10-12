"""Testes das fotos de anúncio: validação, WebP sem EXIF (GPS), rotação, limites, ordem e exclusão."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from anuncios import services
from anuncios.forms import FotosForm
from anuncios.models import Foto
from anuncios.tests.conftest import CAMERA, envio, jpeg
from core.services import configuracao

pytestmark = pytest.mark.django_db


def test_jpeg_de_teste_tem_gps_e_camera():
    """Confere a fixture: o arquivo de entrada carrega mesmo o GPS e a câmera."""
    import io

    exif = Image.open(io.BytesIO(jpeg(gps=True))).getexif()
    assert exif[0x010F] == CAMERA and exif.get_ifd(0x8825)


def test_envio_gera_webp_1600_e_400_sem_exif_e_apaga_o_original(client, loja, imovel):
    """Upload pelo painel: Celery (eager) gera os WebP, sem GPS nem câmera; o original some do storage."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)

    resposta = client.post(
        reverse("anuncios:fotos", args=[anuncio.codigo]),
        {"fotos": [envio(largura=2400, altura=1800, gps=True)]},
    )

    assert resposta.status_code == 302
    foto = anuncio.fotos.get()
    assert not foto.original and foto.imagem.name.endswith(".webp") and foto.miniatura.name.endswith(".webp")
    with Image.open(foto.imagem) as grande, Image.open(foto.miniatura) as mini:
        assert grande.format == "WEBP" and grande.size == (1600, 1200) and mini.size == (400, 300)
        assert not grande.getexif() and not mini.getexif()


def test_rotacao_do_celular_e_aplicada(loja, imovel):
    """Foto tirada em pé (EXIF orientação 6): o WebP sai em pé, sem depender do EXIF."""
    anuncio = imovel(loja(), completo=False)
    foto = services.adicionar_fotos(anuncio, [envio(largura=1200, altura=900, orientacao=6)])[0]

    services.processar_foto(foto)

    with Image.open(foto.imagem) as imagem:
        assert imagem.size == (900, 1200)


def test_varias_fotos_de_uma_vez_e_a_primeira_e_a_capa(client, loja, imovel):
    """Upload múltiplo na ordem enviada; a de menor ordem é a capa."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)

    client.post(reverse("anuncios:fotos", args=[anuncio.codigo]), {"fotos": [envio("a.jpg"), envio("b.jpg")]})

    fotos = list(anuncio.fotos.all())
    assert [f.ordem for f in fotos] == [0, 1]
    assert anuncio.capa == fotos[0]


@pytest.mark.parametrize(
    ("arquivo", "mensagem"),
    [
        (SimpleUploadedFile("falsa.jpg", b"isto nao e imagem", content_type="image/jpeg"), "inválida"),
        (SimpleUploadedFile("icone.jpg", jpeg(150, 100), content_type="image/jpeg"), "mínimo é 200×150"),
    ],
)
def test_formulario_recusa_arquivo_falso_e_imagem_minuscula(arquivo, mensagem):
    """Tipo real conferido pelo Pillow (não a extensão); só ícone/miniatura é recusado (Configuracao)."""
    form = FotosForm(data={}, files={"fotos": arquivo}, vagas=10)

    assert not form.is_valid()
    assert mensagem in str(form.errors)


def test_formulario_respeita_tamanho_maximo_da_configuracao():
    """Limite em KB vem do admin."""
    config = configuracao()
    config.limite_foto_anuncio_kb = 10
    config.save()

    form = FotosForm(data={}, files={"fotos": envio()}, vagas=10)

    assert not form.is_valid() and "máximo é 10 KB" in str(form.errors)


def test_limite_de_fotos_por_anuncio(loja, imovel):
    """Configuracao.max_fotos_anuncio: passar do limite é recusado."""
    config = configuracao()
    config.max_fotos_anuncio = 2
    config.save()
    anuncio = imovel(loja(), completo=False)
    services.adicionar_fotos(anuncio, [envio("a.jpg")])

    with pytest.raises(ValueError, match="no máximo 2 fotos"):
        services.adicionar_fotos(anuncio, [envio("b.jpg"), envio("c.jpg")])
    assert services.vagas_de_foto(anuncio) == 1


def test_reordenar_mover_e_excluir(client, loja, imovel):
    """Arrastar (lista de ids), setas e excluir (apaga também os arquivos)."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    a, b, c = services.adicionar_fotos(anuncio, [envio("a.jpg"), envio("b.jpg"), envio("c.jpg")])
    for foto in (a, b, c):
        services.processar_foto(foto)
    client.force_login(anunciante.usuario)
    url_ordem = reverse("anuncios:ordenar_fotos", args=[anuncio.codigo])

    client.post(url_ordem, {"ordem": [c.pk, a.pk, b.pk]})
    assert list(anuncio.fotos.values_list("pk", flat=True)) == [c.pk, a.pk, b.pk]

    client.post(url_ordem, {"mover": f"{b.pk}:subir"})
    assert list(anuncio.fotos.values_list("pk", flat=True)) == [c.pk, b.pk, a.pk]

    c.refresh_from_db()
    arquivo = c.imagem.name
    client.post(reverse("anuncios:excluir_foto", args=[anuncio.codigo, c.pk]))
    assert list(anuncio.fotos.values_list("pk", flat=True)) == [b.pk, a.pk]
    assert not c.imagem.storage.exists(arquivo)
    assert anuncio.fotos.first().ordem == 0  # a nova primeira vira a capa


def test_reordenar_com_lista_errada_e_recusado(loja, imovel):
    """A lista precisa ter exatamente as fotos do anúncio."""
    anuncio = imovel(loja(), completo=False)
    services.adicionar_fotos(anuncio, [envio("a.jpg")])

    with pytest.raises(ValueError, match="mudou"):
        services.reordenar_fotos(anuncio, [999])


def test_fotos_de_outra_loja_dao_404(client, loja, imovel):
    """Sem IDOR: código de outra loja nas URLs de foto dá 404 e nada muda."""
    alfa = loja()
    anuncio = imovel(alfa)
    foto = anuncio.fotos.get()
    beta = loja("b@exemplo.com", "Loja Beta")
    client.force_login(beta.usuario)

    assert client.get(reverse("anuncios:fotos", args=[anuncio.codigo])).status_code == 404
    assert client.post(reverse("anuncios:excluir_foto", args=[anuncio.codigo, foto.pk])).status_code == 404
    assert Foto.objects.filter(pk=foto.pk).exists()


# --- Fotos fáceis: foto pequena com aviso, HEIC do iPhone e redução no navegador ------------------


def heic(largura: int = 1200, altura: int = 900, gps: bool = False) -> bytes:
    """HEIC de teste (como o iPhone grava), opcionalmente com GPS no EXIF."""
    import io

    import pillow_heif  # noqa: F401  (registrado em core.imagens; aqui só para deixar claro o formato)

    saida = io.BytesIO()
    imagem = Image.new("RGB", (largura, altura), (90, 60, 30))
    exif = Image.Exif()
    exif[0x010F] = CAMERA
    if gps:
        exif[0x8825] = {2: (15.0, 30.0, 0.0)}
    imagem.save(saida, format="HEIF", exif=exif.tobytes())
    return saida.getvalue()


def test_foto_pequena_e_aceita_com_aviso(client, loja, imovel):
    """400×300 passa (antes era recusada) e o painel avisa que pode ficar borrada; a grande, não."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    url = reverse("anuncios:fotos", args=[anuncio.codigo])

    resposta = client.post(
        url, {"fotos": [envio("pequena.jpg", largura=400, altura=300), envio("grande.jpg")]}
    )

    assert resposta.status_code == 302
    pequena, grande = anuncio.fotos.order_by("ordem")
    assert (pequena.largura, pequena.altura, grande.largura) == (400, 300, 1200)
    with Image.open(pequena.imagem) as imagem:
        assert imagem.size == (400, 300)  # nunca amplia
    html = client.get(url).content.decode()
    assert html.count('class="nd-foto-pequena"') == 1 and "1 foto pequena" in html


def test_aviso_de_foto_pequena_vem_da_configuracao(loja, imovel):
    """O tamanho do aviso é do admin (nada fixo no código)."""
    config = configuracao()
    config.foto_aviso_largura_px, config.foto_aviso_altura_px = 1300, 1000
    config.save()
    anuncio = imovel(loja(), completo=False)
    foto = services.adicionar_fotos(anuncio, [envio(largura=1200, altura=900)])[0]
    services.processar_foto(foto)

    assert services.marcar_fotos_pequenas([foto])[0].pequena


def test_heic_do_iphone_e_aceito_e_vira_webp_sem_exif(client, loja, imovel):
    """HEIC passa na validação e o processamento converte em WebP, sem GPS nem câmera; o HEIC some."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    arquivo = SimpleUploadedFile("IMG_0001.HEIC", heic(gps=True), content_type="image/heic")

    resposta = client.post(reverse("anuncios:fotos", args=[anuncio.codigo]), {"fotos": [arquivo]})

    assert resposta.status_code == 302
    foto = anuncio.fotos.get()
    assert not foto.original and (foto.largura, foto.altura) == (1200, 900)
    with Image.open(foto.imagem) as imagem:
        assert imagem.format == "WEBP" and imagem.size == (1200, 900) and not imagem.getexif()


def test_logo_e_capa_da_loja_continuam_sem_heic_e_com_o_minimo():
    """Só as fotos de anúncio mudaram: a validação padrão (logo/capa) recusa HEIC e mantém o mínimo."""
    from django.core.exceptions import ValidationError

    from core import imagens

    with pytest.raises(ValidationError, match="não aceito"):
        imagens.validar_foto(
            SimpleUploadedFile("logo.heic", heic(), content_type="image/heic"), 4096, 400, 400
        )
    with pytest.raises(ValidationError, match="mínimo é 400×400"):
        imagens.validar_foto(
            SimpleUploadedFile("logo.jpg", jpeg(300, 300), content_type="image/jpeg"), 4096, 400, 400
        )


def test_padroes_novos_e_campo_preparado_para_reduzir_no_navegador():
    """15 MB de rede de segurança, mínimo 200×150, aviso abaixo de 800×600; o campo leva o lado máximo."""
    config = configuracao()
    assert (config.limite_foto_anuncio_kb, config.foto_min_largura_px, config.foto_min_altura_px) == (
        15360,
        200,
        150,
    )
    assert (config.foto_aviso_largura_px, config.foto_aviso_altura_px) == (800, 600)

    html = str(FotosForm(vagas=10)["fotos"])
    assert "data-reduzir-fotos" in html and f'data-lado-maximo="{services.LADO_MAXIMO_NO_NAVEGADOR}"' in html
    assert "image/heic" in html
    assert "HEIC" in FotosForm(vagas=10).fields["fotos"].help_text
