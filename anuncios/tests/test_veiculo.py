"""Testes do anúncio de veículo: código ND-VE, formulário com catálogo encadeado (HTMX e sem JS),
validações, publicação pelas mesmas regras do imóvel e a página pública (ficha, sem mapa)."""

import json
import re

import pytest
from django.urls import reverse

from anuncios import services
from anuncios.forms import DadosVeiculoForm
from anuncios.models import Anuncio
from planos.services import LimiteDoPlano

pytestmark = pytest.mark.django_db

NOVO_VEICULO = "/painel/anuncios/novo/?categoria=veiculo"


def dados(catalogo, tangara, **mudancas):
    """POST válido do formulário de veículo (Hilux SRV)."""
    base = {
        "tipo_veiculo": "caminhonete",
        "marca": catalogo["toyota"].pk,
        "modelo": catalogo["hilux"].pk,
        "versao": catalogo["hilux_srv"].pk,
        "ano_fabricacao": "2019",
        "ano_modelo": "2020",
        "quilometragem": "98.000",
        "combustivel": "diesel",
        "cambio": "automatico",
        "cor": "prata",
        "portas": "4",
        "final_placa": "7",
        "opcionais": ["ar_condicionado", "tracao_4x4"],
        "preco": "189.900,00",
        "cidade": tangara.pk,
        "titulo": "",
        "descricao": "Revisada.",
    }
    return {**base, **mudancas}


# --- Criação pelo painel --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "categoria"),
    [
        ("corretor_autonomo", "imovel"),
        ("imobiliaria", "imovel"),
        ("revenda", "veiculo"),
        ("concessionaria", "veiculo"),
        ("garagem", "veiculo"),
    ],
)
def test_novo_vai_direto_para_o_ramo_da_loja(client, loja, tipo, categoria):
    """Corretor e imobiliária anunciam só imóvel; revenda, concessionária e garagem, só veículo."""
    client.force_login(loja(tipo=tipo).usuario)

    resposta = client.get(reverse("anuncios:novo"))

    assert resposta.status_code == 302 and resposta["Location"].endswith(f"?categoria={categoria}")


def test_categoria_de_outro_ramo_pela_url_leva_ao_certo(client, loja):
    """Revenda pedindo ?categoria=imovel (URL à mão): aviso e o formulário de veículo; nada é criado."""
    client.force_login(loja().usuario)

    resposta = client.get(reverse("anuncios:novo") + "?categoria=imovel", follow=True)

    assert resposta.redirect_chain[-1][0].endswith("?categoria=veiculo")
    assert "anuncia só veículos" in resposta.content.decode()
    resposta = client.post(
        reverse("anuncios:novo") + "?categoria=imovel", {"titulo": "Casa grande no centro"}
    )
    assert resposta.status_code == 302 and not Anuncio.objects.exists()


def test_servico_recusa_categoria_de_outro_ramo(loja, criar_anunciante, catalogo_teste):
    """A regra vale no serviço (não só na tela): corretor não cria veículo, revenda não cria imóvel."""
    corretor = criar_anunciante("c@exemplo.com", "Corretor Zé", corretor=True)
    with pytest.raises(services.CategoriaNaoPermitida, match="só imóveis"):
        services.criar_anuncio_veiculo(
            corretor, {"preco": 1}, {"versao": catalogo_teste["cg_fan"], "ano_modelo": 2023}
        )
    with pytest.raises(services.CategoriaNaoPermitida, match="só veículos"):
        services.criar_anuncio_imovel(loja(), {"titulo": "Casa", "preco": 1}, {"tipo": "casa"})
    assert not Anuncio.objects.exists()


def test_cria_veiculo_com_codigo_titulo_automatico_e_vai_para_fotos(client, loja, catalogo_teste, tangara):
    """ND-VE-…, título montado do catálogo, km "98.000" e preço brasileiro; próxima etapa: fotos."""
    client.force_login(loja().usuario)

    resposta = client.post(NOVO_VEICULO, dados(catalogo_teste, tangara))

    anuncio = Anuncio.objects.get()
    assert anuncio.codigo.startswith("ND-VE-") and anuncio.e_veiculo
    assert anuncio.titulo == "Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"
    assert resposta["Location"] == reverse("anuncios:fotos", args=[anuncio.codigo])
    veiculo = anuncio.veiculo
    assert (veiculo.quilometragem, veiculo.final_placa, veiculo.opcionais) == (
        98000,
        "7",
        ["ar_condicionado", "tracao_4x4"],
    )
    assert str(anuncio.preco) == "189900.00"


@pytest.mark.parametrize(
    ("mudanca", "erro"),
    [
        ({"versao": "hilux_sr_de_outro_modelo"}, "escolha válida"),
        ({"ano_modelo": "2022"}, "o mesmo da fabricação ou o seguinte"),
        ({"final_placa": "AB1"}, "Só o último dígito"),
        ({"quilometragem": "98.5"}, "número inteiro"),
        ({"titulo": "Hilux"}, "pelo menos 10 caracteres"),
    ],
)
def test_validacoes(client, loja, catalogo_teste, tangara, mudanca, erro):
    """Versão fora do modelo, ano do modelo incoerente, placa inteira, km quebrado, título curto."""
    client.force_login(loja().usuario)
    if mudanca.get("versao") == "hilux_sr_de_outro_modelo":
        mudanca = {"versao": catalogo_teste["cg_fan"].pk}

    html = client.post(NOVO_VEICULO, dados(catalogo_teste, tangara, **mudanca)).content.decode()

    assert erro in html and not Anuncio.objects.exists()


def test_catalogo_htmx_devolve_opcoes_do_que_foi_escolhido(client, loja, catalogo_teste):
    """O bloco do catálogo vem com as marcas do tipo, os modelos da marca e as versões do modelo."""
    client.force_login(loja().usuario)
    url = reverse("anuncios:catalogo")

    so_tipo = client.get(url, {"tipo_veiculo": "moto"}).content.decode()
    completo = client.get(
        url,
        {
            "tipo_veiculo": "caminhonete",
            "marca": catalogo_teste["toyota"].pk,
            "modelo": catalogo_teste["hilux"].pk,
        },
    ).content.decode()

    assert ">Honda<" in so_tipo and ">Toyota<" not in so_tipo
    assert ">Hilux<" in completo and ">Corolla<" not in completo
    assert ">CD SRV 4x4 2.8 TDI Diesel Aut.<" in completo
    assert 'id="bloco-catalogo"' in completo and "hx-get" in completo
    assert "Este campo é obrigatório" not in completo  # a resposta do HTMX não mostra erros


def test_sem_javascript_o_botao_atualiza_as_listas_sem_salvar(client, loja, catalogo_teste, tangara):
    """ "Atualizar listas" reenvia, carrega as opções e não cria anúncio."""
    client.force_login(loja().usuario)

    html = client.post(
        NOVO_VEICULO,
        {"tipo_veiculo": "caminhonete", "marca": catalogo_teste["toyota"].pk, "_atualizar_catalogo": "1"},
    ).content.decode()

    assert ">Hilux<" in html and not Anuncio.objects.exists()


def test_catalogo_exige_login(client):
    """Endpoint do painel: visitante vai para o login."""
    assert client.get(reverse("anuncios:catalogo")).status_code == 302


def test_formulario_inicial_ao_editar(loja, veiculo, catalogo_teste):
    """Editar carrega tipo, marca, modelo e versão a partir da versão gravada."""
    anuncio = veiculo(loja())

    inicial = DadosVeiculoForm.inicial(anuncio)

    assert (inicial["tipo_veiculo"], inicial["marca"], inicial["modelo"], inicial["versao"]) == (
        "caminhonete",
        catalogo_teste["toyota"].pk,
        catalogo_teste["hilux"].pk,
        catalogo_teste["hilux_srv"].pk,
    )


def test_editar_veiculo_salva_e_pula_a_localizacao(client, loja, veiculo, catalogo_teste, tangara):
    """Editar grava a ficha; a etapa de localização (mapa) não existe para veículo."""
    anunciante = loja()
    anuncio = veiculo(anunciante)
    client.force_login(anunciante.usuario)

    resposta = client.post(
        reverse("anuncios:editar", args=[anuncio.codigo]),
        dados(catalogo_teste, tangara, quilometragem="100.000"),
    )

    assert resposta["Location"] == reverse("anuncios:fotos", args=[anuncio.codigo])
    anuncio.refresh_from_db()
    assert anuncio.veiculo.quilometragem == 100000
    localizacao = client.get(reverse("anuncios:localizacao", args=[anuncio.codigo]))
    assert localizacao["Location"] == reverse("anuncios:editar", args=[anuncio.codigo])
    html = client.get(reverse("anuncios:revisao", args=[anuncio.codigo])).content.decode()
    assert "Localização" not in html.split('aria-label="Etapas do anúncio"', 1)[1].split("</nav>", 1)[0]


def test_outra_loja_nao_edita_o_veiculo(client, loja, veiculo):
    """Sem IDOR também no veículo."""
    anuncio = veiculo(loja())
    client.force_login(loja("b@exemplo.com", "Loja Beta").usuario)

    assert client.get(reverse("anuncios:editar", args=[anuncio.codigo])).status_code == 404


# --- Regras (as mesmas do imóvel) -----------------------------------------------------------


def test_veiculo_segue_moderacao_e_limite(loja, veiculo):
    """Primeiro vai para análise; o segundo no plano de 1 vaga é barrado."""
    anunciante = loja(limite=1)
    primeiro = veiculo(anunciante)

    assert services.enviar_para_publicacao(primeiro) == Anuncio.Situacao.EM_MODERACAO
    with pytest.raises(LimiteDoPlano):
        services.enviar_para_publicacao(veiculo(anunciante, "cg_fan"))


def test_veiculo_nao_precisa_de_ponto_no_mapa(loja, veiculo):
    """Pendências do veículo: descrição e foto, sem mapa."""
    assert services.pendencias(veiculo(loja())) == []
    assert any(
        "foto" in p for p in services.pendencias(veiculo(loja("b@exemplo.com", "Loja B"), completo=False))
    )


# --- Página pública -------------------------------------------------------------------------


def publicar(anuncio):
    """Envia e, se for para a moderação (primeiro anúncio da loja), aprova."""
    if services.enviar_para_publicacao(anuncio) == Anuncio.Situacao.EM_MODERACAO:
        services.aprovar(anuncio, None)
    anuncio.refresh_from_db()
    return anuncio


def test_pagina_do_veiculo_tem_ficha_opcionais_e_nada_de_mapa(client, loja, veiculo):
    """Ficha (marca, modelo, versão, ano, km, câmbio), opcionais, schema.org Car e sem mapa."""
    anuncio = publicar(veiculo(loja()))

    html = client.get(services.url_publica(anuncio), HTTP_USER_AGENT="Mozilla/5.0").content.decode()

    for trecho in ("<dt>Marca</dt><dd>Toyota</dd>", "2019/2020", "98.000 km", "Automático", "Tração 4x4"):
        assert trecho in html
    assert 'id="mapa-anuncio"' not in html and "leaflet" not in html.lower()
    dados_ld = json.loads(
        re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    )
    assert dados_ld["itemOffered"]["@type"] == "Car" and dados_ld["seller"]["@type"] == "AutoDealer"
    assert dados_ld["itemOffered"]["brand"]["name"] == "Toyota"


def test_endereco_da_loja_so_se_ela_permitir(client, loja, veiculo):
    """ "Onde ver": o endereço público da loja aparece só com "mostrar no mapa" marcado."""
    anunciante = loja()
    anunciante.endereco_publico = "Av. Brasil, 1000"
    anunciante.save()
    anuncio = publicar(veiculo(anunciante))
    url = services.url_publica(anuncio)

    assert "Av. Brasil, 1000" not in client.get(url).content.decode()
    anunciante.mostrar_no_mapa = True
    anunciante.save()
    assert "Av. Brasil, 1000" in client.get(url).content.decode()


def test_card_e_parecidos_de_veiculo(loja, veiculo):
    """Card com resumo de veículo; parecidos do mesmo tipo (caminhonete) na cidade."""
    alfa = loja()
    hilux = publicar(veiculo(alfa))
    outra = publicar(veiculo(loja("b@exemplo.com", "Loja Beta"), "hilux_sr"))
    publicar(veiculo(loja("c@exemplo.com", "Loja Gama"), "cg_fan"))

    card = services.para_vitrine(hilux)

    assert card.resumo == "2019/2020 · 98.000 km · Automático" and card.tipo == "Caminhonete"
    assert services.parecidos(hilux, limite=1) == [outra]
