"""Parte 4, etapa 2 (telas e textos): botão do topo por perfil, ficha da loja no admin mais simples, "Sobre
esta tela" recolhida e discreta no painel do cliente, Faturas sem a linha repetida e "Ações recentes"
agrupadas."""

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Group
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.services import acoes_recentes

pytestmark = pytest.mark.django_db


def membro(grupo: str) -> Usuario:
    """Usuário da equipe num grupo."""
    usuario = Usuario.objects.create_user(
        email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
    )
    usuario.groups.add(Group.objects.get(name=grupo))
    return usuario


def test_botao_do_topo_por_perfil(client, loja, entrar_no_admin):
    """Visitante vê "Entrar"; cliente, "Meu painel"; equipe logada, "Painel administrativo"."""
    pagina = client.get("/").content.decode()
    assert f'href="{reverse("contas:entrar")}">' in pagina and "Entrar</a>" in pagina
    assert "Painel administrativo" not in pagina and "Meu painel" not in pagina

    client.force_login(loja().usuario)
    assert "Meu painel" in client.get("/").content.decode()

    equipe = entrar_no_admin(membro("Moderador"))
    assert "Painel administrativo" in equipe.get("/").content.decode()


def test_ficha_da_loja_link_endereco_e_avancado(entrar_no_admin, loja):
    """ "Link da loja no site" (o slug) separado do "Endereço da loja" (físico); sigla e cor em "Avançado"
    recolhido; "Publicação por confiança" só com a situação."""
    cliente = entrar_no_admin(membro("Administrador"))
    pagina = cliente.get(reverse("admin:anunciantes_anunciante_change", args=[loja().pk])).content.decode()

    assert "Link da loja no site" in pagina and "Endereço da loja" in pagina
    avancado = pagina[pagina.index(">Avançado<") - 400 :]
    assert "collapse" in avancado[:400] and 'name="sigla"' in avancado and 'name="cor"' in avancado
    assert "Use as ações" not in pagina  # descrição longa da confiança saiu


def test_sobre_esta_tela_recolhida_e_discreta_no_painel(client, loja):
    """No painel do cliente a ajuda continua existindo (regra das telas), fechada e no estilo compacto."""
    client.force_login(loja().usuario)
    for url in (reverse("pagamentos:faturas"), reverse("planos:meu_plano")):
        pagina = client.get(url).content.decode()
        assert '<details class="nd-ajuda nd-ajuda-compacta">' in pagina, url  # sem "open"


def test_faturas_sem_historico_tem_uma_mensagem_so(client, criar_anunciante):
    """Sem nenhuma fatura: some o "Nenhuma fatura em aberto" e fica só a mensagem do histórico."""
    from planos.models import Periodicidade, Plano
    from planos.services import criar_assinatura

    anunciante = criar_anunciante("nova@exemplo.com", "Loja Nova")
    criar_assinatura(anunciante, Plano.objects.get(slug="basico"), Periodicidade.MENSAL)
    client.force_login(anunciante.usuario)
    anunciante.assinatura.faturas.all().delete()

    pagina = client.get(reverse("pagamentos:faturas")).content.decode()

    assert "Nenhuma fatura em aberto" not in pagina and "Você ainda não tem faturas" in pagina


def test_acoes_recentes_agrupa_repetidas_e_mostra_5(entrar_no_admin, loja):
    """A mesma ação no mesmo item vira uma linha com o total; no máximo 5 linhas."""
    from anunciantes.models import Anunciante
    from planos.models import Plano

    usuario = membro("Administrador")
    lojas = [loja(f"l{i}@exemplo.com", f"Loja {i}") for i in range(3)]
    itens = [Anunciante.objects.filter(pk=item.pk) for item in lojas]
    itens += [Plano.objects.filter(pk=plano.pk) for plano in Plano.objects.all()[:3]]

    for _ in range(4):
        LogEntry.objects.log_actions(usuario.pk, itens[0], CHANGE, "salvou")
    for item in itens[1:]:
        LogEntry.objects.log_actions(usuario.pk, item, CHANGE, "salvou")

    acoes = acoes_recentes(usuario)

    assert len(acoes) == 5 and all(acao.vezes == 1 for acao in acoes)
    LogEntry.objects.log_actions(usuario.pk, itens[-1], CHANGE, "de novo")
    assert acoes_recentes(usuario)[0].vezes == 2
    pagina = entrar_no_admin(usuario).get(reverse("admin:index")).content.decode()
    assert "Ações recentes" in pagina and "(2×)" in pagina
