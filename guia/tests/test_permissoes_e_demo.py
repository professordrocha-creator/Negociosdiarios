"""Testes das permissões do guia (grupo Guia cadastra e publica; Moderador vê os pedidos; Financeiro e
Comercial não veem nada do guia), do aviso de rascunho do termo e dos dados de demonstração."""

import pytest
from django.contrib.gis.geos import Point
from django.contrib.messages import get_messages
from django.urls import reverse

from core.models import Cidade
from guia import services
from guia.models import AceitePublicacao, ConviteAceite, PedidoDoPerfil, PerfilGuia

pytestmark = pytest.mark.django_db


def test_grupo_guia_cadastra_e_nao_mexe_no_termo_nem_na_configuracao(admin_guia, perfil_pronto, termo):
    """Guia: abre o cadastro e a ficha; o termo só para ler; configuração e categorias, só o Administrador."""
    perfil = perfil_pronto()

    assert admin_guia.get(reverse("admin:guia_perfilguia_add")).status_code == 200
    assert admin_guia.get(reverse("admin:guia_perfilguia_change", args=[perfil.pk])).status_code == 200
    termo_pagina = admin_guia.get(reverse("admin:guia_termoguia_change", args=[termo.pk])).content.decode()
    assert 'name="texto"' not in termo_pagina  # só leitura
    assert admin_guia.get(reverse("admin:guia_termoguia_add")).status_code == 403
    assert admin_guia.get(reverse("admin:guia_configuracaoguia_change", args=[1])).status_code == 403
    assert admin_guia.get(reverse("admin:guia_categoriaservico_add")).status_code == 403


@pytest.mark.parametrize("grupo", ["Financeiro", "Comercial"])
def test_financeiro_e_comercial_nao_veem_o_guia(grupo, membro, entrar_no_admin, perfil_pronto):
    """Nem no menu do admin, nem pelas URLs."""
    perfil = perfil_pronto()
    cliente = entrar_no_admin(membro(grupo))

    indice = cliente.get(reverse("admin:index")).content.decode()

    assert "Guia de Negócios" not in indice
    assert cliente.get(reverse("admin:guia_perfilguia_changelist")).status_code == 403
    assert cliente.get(reverse("admin:guia_perfilguia_change", args=[perfil.pk])).status_code == 403
    assert cliente.post(reverse("admin:guia_perfil_convite", args=[perfil.pk])).status_code == 403


def test_moderador_ve_pedidos_mas_nao_cadastra(membro, entrar_no_admin, perfil_pronto):
    """Moderador resolve os pedidos dos titulares; não cadastra nem publica perfis."""
    perfil = perfil_pronto()
    PedidoDoPerfil.objects.create(perfil=perfil, tipo=PedidoDoPerfil.Tipo.REMOVER, descricao="Tirar do guia.")
    cliente = entrar_no_admin(membro("Moderador"))

    assert cliente.get(reverse("admin:guia_pedidodoperfil_changelist")).status_code == 200
    assert cliente.get(reverse("admin:guia_perfilguia_add")).status_code == 403
    assert cliente.post(reverse("admin:guia_perfil_publicar", args=[perfil.pk])).status_code == 403


def test_aviso_de_rascunho_juridico_no_termo(membro, entrar_no_admin, termo):
    """Enquanto rascunho_juridico = true, a lista e a ficha do termo avisam a equipe."""
    cliente = entrar_no_admin(membro("Administrador"))

    lista = cliente.get(reverse("admin:guia_termoguia_changelist"))
    ficha = cliente.get(reverse("admin:guia_termoguia_change", args=[termo.pk]))

    for resposta in (lista, ficha):
        assert any("revisão jurídica pendente" in str(m) for m in get_messages(resposta.wsgi_request))
    termo.rascunho_juridico = False
    termo.save()
    lista = cliente.get(reverse("admin:guia_termoguia_changelist"))
    assert not any("revisão jurídica" in str(m) for m in get_messages(lista.wsgi_request))


def test_termo_em_vigor_fica_travado(membro, entrar_no_admin, termo):
    """Versão em vigor: texto só leitura (mudar = criar versão nova)."""
    cliente = entrar_no_admin(membro("Administrador"))
    pagina = cliente.get(reverse("admin:guia_termoguia_change", args=[termo.pk])).content.decode()
    assert 'name="texto"' not in pagina and 'name="rascunho_juridico"' in pagina


@pytest.fixture
def cidades_demo(tangara):
    """As outras duas cidades usadas pelos perfis demo, liberadas."""
    outras = [
        (5101704, "Barra do Bugres", "barra-do-bugres"),
        (5102637, "Campo Novo do Parecis", "campo-novo-do-parecis"),
    ]
    for codigo, nome, slug in outras:
        Cidade.objects.create(
            codigo_ibge=codigo, nome=nome, slug=slug, uf=tangara.uf, liberada=True, ponto=Point(-57.2, -14.3)
        )


def test_demo_cria_cerca_de_60_perfis_e_apaga_tudo(cidades_demo, termo):
    """64 perfis demo em 3 cidades (variados, com aceite nos publicados); o apagar leva aceites, convites e
    pedidos."""
    assert services.criar_guia_demo() == 64
    assert services.criar_guia_demo() == 64  # idempotente (recria)

    perfis = PerfilGuia.objects.all()
    assert perfis.count() == 64 and not perfis.filter(demo=False).exists()
    assert perfis.values("cidade").distinct().count() == 3
    assert perfis.filter(status="pausado").count() == 1
    assert perfis.filter(tipo="profissional_regulamentado").exclude(registro_profissional="").exists()
    assert perfis.filter(tipo="empresa").exclude(cnpj_verificado_em=None).exists()
    assert (
        not perfis.exclude(status="removido").exclude(responsavel_contato__endswith="@demo.invalid").exists()
    )
    assert len({c for p in perfis for c in p.categorias.values_list("slug", flat=True)}) == 12
    status = set(perfis.values_list("status", flat=True))
    assert {"publicado", "pausado", "aguardando_aceite", "rascunho"} <= status
    for perfil in perfis.filter(status=PerfilGuia.Status.PUBLICADO):
        assert perfil.aceites.filter(revogado_em__isnull=True).exists()
    # G3: 6 pedidos (um removeu o perfil), 15 contatos de convite e o termo novo (demo) aceito por metade.
    from guia.models import ContatoConvite, TermoGuia

    assert PedidoDoPerfil.objects.count() == 6 and perfis.filter(status="removido").count() == 1
    assert ContatoConvite.objects.filter(demo=True).count() == 18  # 15 da lista + 3 do "Quero ser listado"
    assert ContatoConvite.objects.filter(origem="formulario").count() == 3
    assert ContatoConvite.objects.filter(situacao="nao_contatar").count() == 2
    assert services.termo_vigente().demo and services.pendentes_do_termo()
    assert perfis.filter(tipo="autonomo").exclude(cpf_hash="").exists()
    assert perfis.filter(atendimento=PerfilGuia.Atendimento.DOMICILIO).exists()
    assert perfis.filter(horarios={}).exists()

    services.apagar_guia_demo()

    assert not PerfilGuia.objects.exists() and not AceitePublicacao.objects.exists()
    assert not ConviteAceite.objects.exists() and not PedidoDoPerfil.objects.exists()
    assert not PerfilGuia.history.exists()
    assert not ContatoConvite.objects.exists() and not TermoGuia.objects.filter(demo=True).exists()
    assert services.termo_vigente() == termo
