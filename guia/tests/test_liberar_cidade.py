"""Testes do atalho "Liberar cidade" (Guia): botão ao lado da pendência na ficha, "Liberar cidade e vincular"
na fila de convites, permissão (só Administrador/superusuário), confirmação, estado fechado liberado junto,
histórico (quem e quando) e "Cidades" no menu do dia a dia do Administrador."""

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.urls import reverse

from core.models import Cidade, Estado
from guia import services
from guia.models import ContatoConvite, PerfilGuia

pytestmark = pytest.mark.django_db


@pytest.fixture
def mato_grosso_do_sul(db):
    """Estado fechado, com duas cidades do IBGE (uma delas homônima de outra UF não é preciso aqui)."""
    return Estado.objects.create(uf="MS", nome="Mato Grosso do Sul", liberado=False)


@pytest.fixture
def cuiaba(tangara):
    """Cuiabá/MT ainda não liberada (MT liberado)."""
    return Cidade.objects.create(
        codigo_ibge=5103403, nome="Cuiabá", slug="cuiaba", uf=tangara.uf, liberada=False, ponto=tangara.ponto
    )


def na_cidade(perfil_pronto, cidade) -> PerfilGuia:
    """Perfil completo (sem aceite) numa cidade ainda fechada."""
    perfil = perfil_pronto()
    PerfilGuia.objects.filter(pk=perfil.pk).update(cidade=cidade, bairro=None)
    perfil.refresh_from_db()
    return perfil


def historico(objeto) -> list[LogEntry]:
    """Registros do "Histórico" do admin para o objeto."""
    return list(
        LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(objeto), object_id=str(objeto.pk)
        )
    )


# --- Ficha do Guia --------------------------------------------------------------------------------------


def test_botao_liberar_cidade_so_para_o_administrador(entrar_no_admin, membro, perfil_pronto, cuiaba):
    """A pendência da cidade ganha "Liberar Cuiabá" para o Administrador; o grupo Guia não vê nem consegue."""
    perfil = na_cidade(perfil_pronto, cuiaba)
    ficha = reverse("admin:guia_perfilguia_change", args=[perfil.pk])
    atalho = reverse("admin:guia_perfil_liberar_cidade", args=[perfil.pk])

    administrador = entrar_no_admin(membro("Administrador"))
    assert f'href="{atalho}">Liberar Cuiabá</a>' in administrador.get(ficha).content.decode()

    do_guia = entrar_no_admin(membro("Guia"))
    assert "Liberar Cuiabá" not in do_guia.get(ficha).content.decode()
    assert do_guia.get(atalho).status_code == 403
    assert do_guia.post(atalho).status_code == 403
    cuiaba.refresh_from_db()
    assert not cuiaba.liberada


def test_confirmacao_e_liberacao_com_historico(entrar_no_admin, membro, perfil_pronto, cuiaba):
    """GET mostra a confirmação (nada muda); POST libera, tira a marca da demo e registra quem liberou."""
    Cidade.objects.filter(pk=cuiaba.pk).update(liberada_pela_demo=True)
    perfil = na_cidade(perfil_pronto, cuiaba)
    usuario = membro("Administrador")
    cliente = entrar_no_admin(usuario)
    atalho = reverse("admin:guia_perfil_liberar_cidade", args=[perfil.pk])

    pagina = cliente.get(atalho).content.decode()
    assert "Liberar Cuiabá abre o site para anúncios, lojas e buscas dessa cidade. Confirmar?" in pagina
    cuiaba.refresh_from_db()
    assert not cuiaba.liberada

    resposta = cliente.post(atalho)

    assert resposta.status_code == 302
    cuiaba.refresh_from_db()
    assert cuiaba.liberada and not cuiaba.liberada_pela_demo
    [registro] = historico(cuiaba)
    assert registro.user == usuario and "ficha do Guia" in registro.change_message
    assert services.PENDENCIA_CIDADE not in services.pendencias(perfil, exigir_aceite=False)


def test_estado_fechado_e_liberado_junto_avisando(entrar_no_admin, membro, perfil_pronto, mato_grosso_do_sul):
    """Cidade de estado fechado: a confirmação avisa e o estado é liberado junto (com histórico)."""
    campo_grande = Cidade.objects.create(
        codigo_ibge=5002704,
        nome="Campo Grande",
        slug="campo-grande",
        uf=mato_grosso_do_sul,
        liberada=False,
        ponto=Point(-54.6, -20.4),
    )
    perfil = na_cidade(perfil_pronto, campo_grande)
    cliente = entrar_no_admin(membro("Administrador"))
    atalho = reverse("admin:guia_perfil_liberar_cidade", args=[perfil.pk])

    assert "será liberado junto" in cliente.get(atalho).content.decode()
    cliente.post(atalho)

    mato_grosso_do_sul.refresh_from_db()
    campo_grande.refresh_from_db()
    assert mato_grosso_do_sul.liberado and campo_grande.liberada
    assert "Estado liberado junto com Campo Grande" in historico(mato_grosso_do_sul)[0].change_message


# --- Fila de convites -----------------------------------------------------------------------------------


def test_liberar_cidade_e_vincular_os_contatos_que_pediram(entrar_no_admin, membro, cuiaba):
    """Acha a cidade pelo texto (com ou sem UF e acento), mostra quantos serão ligados, libera e vincula."""
    um = services.registrar_interessado("A", None, None, "+5565999990801", "A", cidade_informada="Cuiabá/MT")
    services.registrar_interessado("B", None, None, "+5565999990802", "B", cidade_informada="cuiaba")
    services.registrar_interessado("C", None, None, "+5565999990803", "C", cidade_informada="Sinop")
    usuario = membro("Administrador")
    cliente = entrar_no_admin(usuario)
    lista = reverse("admin:guia_contatoconvite_changelist")
    atalho = reverse("admin:guia_contato_liberar_cidade", args=[um.pk])

    assert f'href="{atalho}">Liberar cidade e vincular</a>' in cliente.get(lista).content.decode()
    confirmacao = cliente.get(atalho).content.decode()
    assert "Liberar Cuiabá abre o site" in confirmacao and "2 contato(s)" in confirmacao

    cliente.post(atalho, {"cidade": cuiaba.pk})

    cuiaba.refresh_from_db()
    assert cuiaba.liberada and historico(cuiaba)[0].user == usuario
    ligados = ContatoConvite.objects.filter(cidade=cuiaba)
    assert set(ligados.values_list("nome", flat=True)) == {"A", "B"}
    assert ligados.get(nome="A").cidade_informada == "Cuiabá/MT"  # o texto da pessoa fica guardado
    assert ContatoConvite.objects.get(nome="C").cidade is None
    filtrada = cliente.get(lista + "?outra_cidade=sim").content.decode()
    assert "<b>Cidade informada:</b> Cuiabá/MT" not in filtrada  # vinculado sai de "Pedidos de outra cidade"
    assert "<b>Cidade informada:</b> Sinop" in filtrada


def test_mais_de_uma_cidade_com_o_nome_pede_para_escolher(
    entrar_no_admin, membro, tangara, mato_grosso_do_sul
):
    """Nome que existe em dois estados: mostra as opções e só vincula a escolhida."""
    mt = Cidade.objects.create(
        codigo_ibge=5106232, nome="Nova Olímpia", slug="nova-olimpia", uf=tangara.uf, ponto=tangara.ponto
    )
    ms = Cidade.objects.create(
        codigo_ibge=5099999,
        nome="Nova Olímpia",
        slug="nova-olimpia-ms",
        uf=mato_grosso_do_sul,
        ponto=tangara.ponto,
    )
    contato = services.registrar_interessado(
        "D", None, None, "+5565999990804", "D", cidade_informada="Nova Olimpia"
    )
    cliente = entrar_no_admin(membro("Administrador"))
    atalho = reverse("admin:guia_contato_liberar_cidade", args=[contato.pk])

    pagina = cliente.get(atalho).content.decode()
    assert f'value="{mt.pk}"' in pagina and f'value="{ms.pk}"' in pagina and "será liberado junto" in pagina
    cliente.post(atalho, {"cidade": mt.pk})

    contato.refresh_from_db()
    ms.refresh_from_db()
    assert contato.cidade == mt and not ms.liberada


def test_vincular_so_para_o_administrador(entrar_no_admin, membro, cuiaba):
    """O grupo Guia não vê o atalho na lista e recebe 403 no endereço."""
    contato = services.registrar_interessado(
        "E", None, None, "+5565999990805", "E", cidade_informada="Cuiabá"
    )
    cliente = entrar_no_admin(membro("Guia"))
    atalho = reverse("admin:guia_contato_liberar_cidade", args=[contato.pk])

    assert (
        "Liberar cidade e vincular"
        not in cliente.get(reverse("admin:guia_contatoconvite_changelist")).content.decode()
    )
    assert cliente.post(atalho, {"cidade": cuiaba.pk}).status_code == 403
    cuiaba.refresh_from_db()
    assert not cuiaba.liberada


# --- Menu -----------------------------------------------------------------------------------------------


def test_cidades_no_menu_do_dia_a_dia_perto_das_solicitacoes(entrar_no_admin, membro):
    """Administrador: "Cidades" logo depois de "Solicitações de cidade", fora do "Mais opções"."""
    pagina = entrar_no_admin(membro("Administrador")).get(reverse("admin:index")).content.decode()
    dia_a_dia = pagina[: pagina.index("Mais opções")]
    solicitacoes = dia_a_dia.index(reverse("admin:anunciantes_solicitacaocidade_changelist"))
    cidades = dia_a_dia.index(reverse("admin:core_cidade_changelist"))
    assert solicitacoes < cidades
