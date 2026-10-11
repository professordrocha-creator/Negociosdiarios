"""Testes dos dados de demonstração: demo.json, home demo e criar/apagar_dados_demo."""

import csv
import re
from decimal import Decimal

import environ
import pytest
from django.contrib.auth.models import Group
from django.contrib.gis.geos import Point
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.template import Context, Template
from django.urls import reverse

from anunciantes.services import lojas_verificadas
from config.settings import validar_mostrar_demo
from contas.models import Usuario
from core.models import Cidade, Estado
from core.services import (
    ARQUIVO_MUNICIPIOS,
    _resumo,
    apagar_dados_demo,
    criar_dados_demo,
    destaques,
    ler_demo,
    recem_anunciados,
)

DADOS = ler_demo()
SENHA_DEMO = "Senha-Demo-Forte-123"
USUARIOS_DEMO = 3 + 8  # equipe (3) + um login por loja (6 ativas + 2 pendentes)
SENHA_REAL = "Outra-Senha-Forte-1"
TANGARA, BARRA_DO_BUGRES = 5107958, 5101704


def cnpj_valido(cnpj: str) -> bool:
    """Confere os dígitos verificadores do CNPJ (o validador do sistema chega na Sprint 1)."""
    if not re.fullmatch(r"\d{14}", cnpj) or len(set(cnpj)) == 1:
        return False

    def digito(base: str, pesos: list[int]) -> str:
        resto = sum(int(n) * p for n, p in zip(base, pesos, strict=True)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digito(cnpj[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return cnpj[12:] == d1 + d2


# --- demo.json: a fonte única precisa estar sempre coerente ------------------------------


def test_demo_tem_1_corretor_e_5_revendas():
    """Combinado do roadmap: 1 corretor com CRECI e 5 revendas de veículos com CNPJ válido."""
    tipos = [loja["tipo"] for loja in DADOS["lojas"]]
    assert tipos.count("corretor_autonomo") == 1
    assert tipos.count("revenda") == 5
    for loja in DADOS["lojas"]:
        if loja["tipo"] == "corretor_autonomo":
            assert re.fullmatch(r"CRECI/MT \d{5}-F", loja["creci"])
        else:
            assert cnpj_valido(loja["cnpj"]), loja["cnpj"]


def test_demo_tem_cerca_de_12_anuncios_ligados_a_lojas_existentes():
    """Todo anúncio aponta para uma loja do arquivo, com preço Decimal positivo e foto de exemplo."""
    slugs = {loja["slug"] for loja in DADOS["lojas"]}
    assert len(DADOS["anuncios"]) == 12
    for anuncio in DADOS["anuncios"]:
        assert anuncio["loja"] in slugs
        assert anuncio["categoria"] in {"imovel", "veiculo"}
        assert anuncio["finalidade"] in {"venda", "aluguel"}
        assert Decimal(anuncio["preco"]) > 0
        assert anuncio["estilo_foto"] in {f"f{n}" for n in range(1, 7)}


def test_demo_usa_cidades_reais_de_mt_e_contatos_ficticios():
    """Cidades existem no CSV do IBGE (MT); telefones em E.164; e-mails no domínio reservado .invalid."""
    with open(ARQUIVO_MUNICIPIOS, encoding="utf-8") as fp:
        uf_por_codigo = {int(linha["codigo_ibge"]): linha["uf"] for linha in csv.DictReader(fp)}
    usadas = {a["cidade_ibge"] for a in DADOS["anuncios"]} | {loja["cidade_ibge"] for loja in DADOS["lojas"]}
    assert usadas <= set(DADOS["cidades"])
    assert all(uf_por_codigo[codigo] == "MT" for codigo in DADOS["cidades"])
    for loja in DADOS["lojas"]:
        assert re.fullmatch(r"\+5565\d{9}", loja["whatsapp"])
        assert loja["email"].endswith(".invalid")
        assert 1 <= loja["cor"] <= 6
    assert all(pessoa["email"].endswith("@demo.invalid") for pessoa in DADOS["equipe"])


# --- MOSTRAR_DEMO nunca em produção ------------------------------------------------------


def test_mostrar_demo_e_proibido_sem_debug():
    """MOSTRAR_DEMO=True com DEBUG=False derruba a subida do Django."""
    with pytest.raises(ImproperlyConfigured):
        validar_mostrar_demo(True, debug=False)
    assert validar_mostrar_demo(True, debug=True) is True
    assert validar_mostrar_demo(False, debug=False) is False


# --- Vitrine da home (destaques, recém-anunciados, lojas) --------------------------------


@pytest.fixture
def cidades_demo(db):
    """MT liberado e as cidades do demo.json liberadas (como depois do criar_dados_demo)."""
    mt = Estado.objects.create(uf="MT", nome="Mato Grosso", liberado=True)
    nomes = {5107958: "Tangará da Serra", 5101704: "Barra do Bugres", 5102637: "Campo Novo do Parecis"}
    nomes[5106232] = "Nova Olímpia"
    for codigo, nome in nomes.items():
        Cidade.objects.create(
            codigo_ibge=codigo, nome=nome, slug=str(codigo), uf=mt, liberada=True, ponto=Point(-57, -14)
        )
    # Sinop fica desligada: a loja demo de lá gera uma solicitação de cidade.
    Cidade.objects.create(codigo_ibge=5107909, nome="Sinop", slug="sinop", uf=mt, ponto=Point(-55, -11))
    return mt


@pytest.fixture
def demo_ligada(settings, cidades_demo):
    """Home com dados de demonstração."""
    settings.MOSTRAR_DEMO = True


@pytest.fixture
def lojas_demo(demo_ligada, settings):
    """Demo completa no banco (as lojas da vitrine vêm do banco desde a Sprint 2)."""
    settings.DEBUG = True
    criar_dados_demo(SENHA_DEMO)


def test_sem_mostrar_demo_nao_ha_vitrine(cidades_demo):
    """Com MOSTRAR_DEMO desligado as três listas ficam vazias (a home mostra "em breve")."""
    assert destaques() == recem_anunciados() == lojas_verificadas() == []


def test_destaques_sao_so_os_marcados_mais_novos_primeiro(demo_ligada):
    """4 destaques no demo.json, do mais novo ao mais antigo."""
    titulos = [a.titulo for a in destaques()]

    assert titulos == [
        "Ford Ranger XLT 3.2 4x4 Diesel",
        "Toyota Hilux SRV 2.8 4x4 Diesel",
        "Casa 3 quartos com área gourmet",
        "Chácara 2 ha com represa e pomar",
    ]


def test_recem_anunciados_no_maximo_2_por_loja(demo_ligada):
    """A Garagem Rota 358 tem 3 anúncios, mas só os 2 mais novos entram (rodízio justo)."""
    lista = recem_anunciados()

    assert len(lista) == 8
    assert [a.publicado_em for a in lista] == sorted((a.publicado_em for a in lista), reverse=True)
    rota = [a.titulo for a in lista if a.loja_slug == "garagem-rota-358"]
    assert rota == ["Volkswagen Gol 1.0 MPI", "Chevrolet Onix LT 1.0 Turbo"]
    assert all(sum(1 for b in lista if b.loja_slug == a.loja_slug) <= 2 for a in lista)


def test_lojas_verificadas_com_mais_anuncios_primeiro(lojas_demo):
    """6 lojas ativas do banco (as pendentes não), por quantidade de anúncios e depois pelo nome."""
    lojas = [(loja.nome, loja.total_anuncios) for loja in lojas_verificadas()]

    assert lojas == [
        ("Paulo Mendes Corretor", 4),
        ("Garagem Rota 358", 3),
        ("Chapada Motos", 2),
        ("Bugres Auto Center", 1),
        ("Parecis Veículos", 1),
        ("Serra Caminhonetes", 1),
    ]


def test_cidade_desligada_some_da_vitrine(lojas_demo):
    """Como no site real: cidade não liberada não mostra anúncios nem lojas, mesmo na demonstração."""
    Cidade.objects.filter(codigo_ibge=BARRA_DO_BUGRES).update(liberada=False)

    titulos = {a.titulo for a in recem_anunciados(limite=50, por_loja=50)}

    assert "Fiat Toro Volcano 2.0 Diesel 4x4" not in titulos
    assert "Terreno 12×30 em rua asfaltada" not in titulos
    assert "Bugres Auto Center" not in {loja.nome for loja in lojas_verificadas()}


@pytest.mark.parametrize(
    ("categoria", "detalhes", "esperado"),
    [
        (
            "imovel",
            {"quartos": 3, "banheiros": 2, "vagas": 2, "area_m2": 180},
            "3 qts · 2 banh · 2 vagas · 180 m²",
        ),
        (
            "imovel",
            {"quartos": 2, "banheiros": 1, "vagas": 4, "area_m2": 20000},
            "2 qts · 1 banh · 4 vagas · 2 ha",
        ),
        ("imovel", {"area_m2": 360}, "360 m²"),
        ("veiculo", {"ano": 2019, "km": 98000, "cambio": "automático"}, "2019 · 98.000 km · automático"),
    ],
)
def test_resumo_do_card(categoria, detalhes, esperado):
    """A linha de ficha do card segue o padrão do protótipo."""
    assert _resumo(categoria, detalhes) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("189900.00", "R$ 189.900"),
        ("1600", "R$ 1.600"),
        ("1234.5", "R$ 1.234,50"),
        ("0.99", "R$ 0,99"),
        (None, ""),
    ],
)
def test_filtro_moeda(valor, esperado):
    """Preço no padrão brasileiro, sem centavos quando inteiro."""
    html = Template("{% load nd %}{{ v|moeda }}").render(Context({"v": Decimal(valor) if valor else None}))
    assert html == esperado


# --- Home com e sem demonstração ---------------------------------------------------------


def test_home_com_demo_mostra_faixa_cards_e_lojas(client, lojas_demo):
    """Faixa de aviso, cards com preço formatado, aluguel com /mês e vitrine de lojas."""
    resposta = client.get(reverse("core:inicio"))
    html = resposta.content.decode()

    assert "Dados de demonstração:" in html
    assert "R$ 189.900" in html and "Toyota Hilux SRV 2.8 4x4 Diesel" in html
    assert "R$ 1.600" in html and "/mês" in html
    assert "Lojas verificadas" in html and "Paulo Mendes Corretor" in html
    assert {"_card_anuncio.html", "_loja_mini.html"} <= {t.name for t in resposta.templates}


def test_links_da_demo_ficam_em_breve(client, demo_ligada):
    """Página de anúncio e de loja ainda não existem: links sem destino e com título "Em breve"."""
    html = client.get(reverse("core:inicio")).content.decode()
    cards = html.split('class="nd-card', 1)[1].split("Lojas verificadas", 1)[0]

    assert 'title="Em breve"' in cards
    assert 'class="titulo stretched-link" href=' not in cards
    assert 'class="nd-loja-mini" href=' not in html


def test_home_sem_demo_continua_em_breve(client, cidades_demo):
    """Sem MOSTRAR_DEMO: nenhuma faixa, nenhum card, avisos "Em breve"."""
    html = client.get(reverse("core:inicio")).content.decode()

    assert "Dados de demonstração:" not in html
    assert "nd-card" not in html
    assert html.count("Em breve") >= 2


# --- criar_dados_demo e apagar_dados_demo ------------------------------------------------


@pytest.fixture
def dev(settings, cidades_demo):
    """Ambiente de dev (DEBUG=True) com as cidades ainda desligadas e Tangará liberada à mão."""
    settings.DEBUG = True
    settings.DEMO_SENHA = SENHA_DEMO
    Cidade.objects.update(liberada=False)
    Cidade.objects.filter(codigo_ibge=TANGARA).update(liberada=True)  # como o Daniel fez no admin


def test_criar_dados_demo_so_com_debug(settings, cidades_demo):
    """Em produção (DEBUG=False) o comando se recusa e não cria nada."""
    settings.DEBUG = False
    settings.DEMO_SENHA = SENHA_DEMO

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("criar_dados_demo")
    assert not Usuario.objects.filter(demo=True).exists()


def test_criar_dados_demo_exige_demo_senha(dev, settings):
    """Sem DEMO_SENHA não há usuário demo (nada de senha conhecida no código)."""
    settings.DEMO_SENHA = ""

    with pytest.raises(CommandError, match="DEMO_SENHA"):
        call_command("criar_dados_demo")


def test_criar_dados_demo_cria_equipe_nos_grupos(dev):
    """3 usuários de equipe demo, um por grupo, com a senha do .env e marcados como demo."""
    call_command("criar_dados_demo")

    for pessoa in DADOS["equipe"]:
        usuario = Usuario.objects.get(email=pessoa["email"])
        assert usuario.demo and usuario.is_staff and not usuario.is_superuser
        assert usuario.check_password(SENHA_DEMO)
        assert list(usuario.groups.values_list("name", flat=True)) == [pessoa["grupo"]]


def test_criar_dados_demo_e_idempotente(dev):
    """Rodar de novo atualiza, não duplica."""
    call_command("criar_dados_demo")
    call_command("criar_dados_demo")

    assert Usuario.objects.filter(demo=True).count() == USUARIOS_DEMO
    assert Group.objects.get(name="Moderador").user_set.count() == 1


def test_criar_dados_demo_nao_toma_conta_real(dev):
    """Se um e-mail demo for de uma conta real, o comando para sem mexer nela."""
    real = Usuario.objects.create_user(email="moderador@demo.invalid", password=SENHA_REAL, nome="Real")

    with pytest.raises(CommandError, match="conta real"):
        call_command("criar_dados_demo")
    real.refresh_from_db()
    assert not real.demo and not real.is_staff and real.check_password(SENHA_REAL)


def test_usuario_demo_entra_no_admin(client, dev):
    """Os usuários demo servem para testar os grupos no admin (senha = DEMO_SENHA)."""
    call_command("criar_dados_demo")

    resposta = client.post(
        reverse("admin:login"),
        {"username": "financeiro@demo.invalid", "password": SENHA_DEMO, "next": reverse("admin:index")},
    )

    assert resposta["Location"] == reverse("admin:index")
    assert client.get(reverse("admin:index")).status_code == 200


def test_apagar_dados_demo_remove_so_o_que_e_demo(dev):
    """Usuários demo somem; conta real fica; só as cidades ligadas pela demo são desligadas."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA_REAL, nome="Daniel")
    resumo = criar_dados_demo(SENHA_DEMO)
    assert resumo.cidades == 3  # Tangará já estava liberada (à mão) e não é marcada

    apagado = apagar_dados_demo()

    assert apagado.usuarios == USUARIOS_DEMO and apagado.cidades == 3 and apagado.anunciantes == 8
    assert list(Usuario.objects.all()) == [daniel]
    assert list(Cidade.objects.filter(liberada=True).values_list("codigo_ibge", flat=True)) == [TANGARA]
    assert not Cidade.objects.filter(liberada_pela_demo=True).exists()


def test_comando_apagar_pede_confirmacao(dev, monkeypatch, capsys):
    """Sem --sim, só apaga se a pessoa digitar "sim"."""
    criar_dados_demo(SENHA_DEMO)
    monkeypatch.setattr("builtins.input", lambda _: "não")

    call_command("apagar_dados_demo")

    assert "Nada foi apagado." in capsys.readouterr().out
    assert Usuario.objects.filter(demo=True).count() == USUARIOS_DEMO

    call_command("apagar_dados_demo", "--sim")
    assert not Usuario.objects.filter(demo=True).exists()


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("True", True), ("true", True), ("1", True), ("yes", True), ("False", False), ("0", False), ("", False)],
)
def test_mostrar_demo_aceita_true_true_e_1(monkeypatch, valor, esperado):
    """O settings lê MOSTRAR_DEMO como booleano: True, true, 1 (e yes) ligam; o resto desliga."""
    monkeypatch.setenv("MOSTRAR_DEMO", valor)

    assert environ.Env().bool("MOSTRAR_DEMO", default=False) is esperado


# --- Anunciantes de demonstração (Sprint 1) ---------------------------------------------


def test_criar_dados_demo_cria_6_lojas_ativas_e_2_pendentes(dev):
    """As 6 lojas do demo.json ficam ativas e a de "lojas_pendentes" fica pendente (para testar a
    aprovação no admin). Todas marcadas como demo, com e-mail confirmado e documento válido."""
    from anunciantes.models import Anunciante

    criar_dados_demo(SENHA_DEMO)

    lojas = Anunciante.objects.filter(demo=True)
    assert lojas.count() == 8
    assert lojas.filter(status="ativo").count() == 6
    pendentes = set(lojas.filter(status="pendente").values_list("slug", flat=True))
    assert pendentes == {"cerrado-novo-imoveis", "sinop-auto-prime"}
    assert all(loja.usuario.email_confirmado_em for loja in lojas)
    corretor = lojas.get(slug="paulo-mendes-corretor")
    assert (corretor.documento_tipo, corretor.documento_numero) == ("creci", "CRECI/MT 08765-F")
    revenda = lojas.get(slug="garagem-rota-358")
    assert (revenda.documento_tipo, revenda.documento_numero, revenda.whatsapp) == (
        "cnpj",
        "90000001000129",
        "+5565999990002",
    )
    for loja in lojas:
        loja.full_clean()  # tudo o que o demo cria passa nas mesmas regras do cadastro real
        assert loja.usuario.demo and not loja.usuario.is_staff


def test_cliente_demo_entra_e_ve_os_proprios_anuncios(client, dev):
    """Login com DEMO_SENHA em /entrar/; o painel lista só os anúncios da própria loja."""
    criar_dados_demo(SENHA_DEMO)

    resposta = client.post(
        reverse("contas:entrar"), {"username": "contato@rota358.demo.invalid", "password": SENHA_DEMO}
    )
    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert resposta["Location"] == reverse("anunciantes:painel")
    assert "Garagem Rota 358" in html
    assert "Toyota Hilux SRV 2.8 4x4 Diesel" in html and "Volkswagen Gol 1.0 MPI" in html
    assert "Ford Ranger" not in html  # é da Serra Caminhonetes
    assert "Casa 3 quartos" not in html  # é do corretor


def test_criar_dados_demo_nao_toma_loja_real(dev):
    """Se o endereço de uma loja demo já for de uma loja real, o comando para."""
    from anunciantes.models import Anunciante

    real = Usuario.objects.create_user(email="real@exemplo.com", password=SENHA_REAL, nome="Real")
    Anunciante.objects.create(
        usuario=real,
        tipo="revenda",
        nome_publico="Rota Real",
        slug="garagem-rota-358",
        documento_tipo="cnpj",
        documento_numero="11222333000181",
        whatsapp="+5565988887777",
        cidade=Cidade.objects.get(codigo_ibge=TANGARA),
    )

    with pytest.raises(ValueError, match="colidem com dados reais"):
        criar_dados_demo(SENHA_DEMO)
    assert not Usuario.objects.filter(demo=True).exists()  # transação: nada pela metade


def test_apagar_dados_demo_remove_anunciantes_e_historico(dev):
    """Anunciantes demo, logins e histórico somem; nada sobra para a produção."""
    from anunciantes.models import Anunciante

    criar_dados_demo(SENHA_DEMO)
    criar_dados_demo(SENHA_DEMO)  # gera histórico de atualização

    apagar_dados_demo()

    assert not Anunciante.objects.exists()
    assert not Anunciante.history.exists()
    assert not Usuario.objects.filter(demo=True).exists()


# --- Regiões, bairros e solicitação de cidade (Sprint 1, parte 3) -----------------------


def test_criar_dados_demo_cria_regiao_bairros_e_solicitacao(dev):
    """Região de Tangará com as 4 cidades, bairros de Tangará e o pedido de Sinop pendente."""
    from anunciantes.models import SolicitacaoCidade
    from core.models import Bairro, Regiao

    criar_dados_demo(SENHA_DEMO)
    criar_dados_demo(SENHA_DEMO)  # idempotente: não duplica nada

    regiao = Regiao.objects.get(slug="regiao-de-tangara")
    assert regiao.demo and regiao.cidades.count() == 4
    assert set(Bairro.objects.filter(cidade__codigo_ibge=TANGARA).values_list("nome", flat=True)) == {
        "Centro",
        "Jardim Europa",
        "Vila Alta",
        "Jardim Tarumã",
        "Estrada da Serra",
    }
    solicitacao = SolicitacaoCidade.objects.get()
    assert solicitacao.cidade.nome == "Sinop" and solicitacao.status == "pendente" and solicitacao.demo
    assert not solicitacao.cidade.liberada


def test_liberar_cidade_demo_e_desfeito_pelo_apagar(dev):
    """Sinop liberada pela solicitação demo é desligada de novo pelo apagar_dados_demo."""
    from anunciantes.models import SolicitacaoCidade
    from anunciantes.services import liberar_cidade_da_solicitacao
    from core.models import Bairro, Regiao

    criar_dados_demo(SENHA_DEMO)
    liberar_cidade_da_solicitacao(SolicitacaoCidade.objects.get(), None)
    assert Cidade.objects.get(nome="Sinop").liberada

    apagar_dados_demo()

    assert not Cidade.objects.get(nome="Sinop").liberada
    assert not Regiao.objects.exists() and not Bairro.objects.exists()
    assert not SolicitacaoCidade.objects.exists()
