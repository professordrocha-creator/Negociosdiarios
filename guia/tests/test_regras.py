"""Testes das regras do guia (docs/GUIA.md §5 e §10): publicação só com aceite, máximo de categorias,
regulamentada sem frase, CPF nunca em claro, duplicidade que alerta sem bloquear e carga das categorias."""

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.urls import reverse

from guia import services
from guia.models import CategoriaServico, GrupoCategoria, PerfilGuia
from guia.tests.conftest import dados_do_formulario

pytestmark = pytest.mark.django_db

CPF = "529.982.247-25"
CPF_DIGITOS = "52998224725"


def mensagens(resposta) -> str:
    """Todas as mensagens do admin (messages framework) numa string."""
    return " ".join(str(m) for m in get_messages(resposta.wsgi_request))


# --- Publicação --------------------------------------------------------------------------------------


def test_publicar_sem_aceite_falha(perfil_pronto):
    """Cadastro completo, mas sem aceite: o serviço recusa e explica; o perfil não vai ao ar."""
    perfil = perfil_pronto()

    with pytest.raises(services.PublicacaoRecusada) as erro:
        services.publicar(perfil)

    assert any("aceite" in falta for falta in erro.value.pendencias)
    perfil.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.RASCUNHO and perfil.publicado_em is None


def test_admin_botao_publicar_desabilitado_e_post_nao_publica(perfil_pronto, admin_guia):
    """Na ficha do admin o botão vem desabilitado com a explicação; forçar o POST também não publica."""
    perfil = perfil_pronto()
    url = reverse("admin:guia_perfilguia_change", args=[perfil.pk])

    pagina = admin_guia.get(url).content.decode()
    resposta = admin_guia.post(reverse("admin:guia_perfil_publicar", args=[perfil.pk]))

    assert 'disabled aria-describedby="explica-publicar"' in pagina
    assert "a equipe não pula essa etapa" in pagina
    assert "aceite do responsável" in mensagens(resposta)
    perfil.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.RASCUNHO


def test_requisitos_de_publicacao(perfil_pronto, tangara):
    """Sem categoria, cidade desligada, sem contato e sem local: cada falta aparece (mesmo com aceite)."""
    perfil = perfil_pronto(whatsapp="")
    perfil.categorias.clear()
    perfil.endereco = ""
    perfil.save()
    tangara.liberada = False
    tangara.save()

    faltas = " ".join(services.pendencias(perfil, exigir_aceite=False))

    assert "categoria" in faltas
    assert "cidade" in faltas
    assert "WhatsApp ou telefone" in faltas
    assert "endereço" in faltas


def test_a_domicilio_exige_area_e_nao_expoe_o_ponto(perfil_pronto, tangara):
    """A domicílio: precisa da área; o ponto público é o centro da cidade (nunca o ponto marcado)."""
    perfil = perfil_pronto()
    perfil.atendimento = PerfilGuia.Atendimento.DOMICILIO
    perfil.save()

    assert any("área de atendimento" in f for f in services.pendencias(perfil, exigir_aceite=False))
    assert perfil.ponto_publico.equals(tangara.ponto)


def test_publicado_com_aceite_e_pausar_e_voltar(perfil_pronto):
    """Com o aceite vigente publica; pausar tira do ar e "publicar" devolve (o aceite continua valendo)."""
    perfil = perfil_pronto()
    _, token = services.gerar_convite(perfil)
    services.aceitar_convite(token, "Maria Responsável", "10.1.2.3", "Mozilla/5.0 Chrome/120")
    perfil.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.PUBLICADO

    services.pausar(perfil)
    assert perfil.status == PerfilGuia.Status.PAUSADO
    services.publicar(perfil)
    assert perfil.status == PerfilGuia.Status.PUBLICADO


# --- Categorias ----------------------------------------------------------------------------------------


def test_maximo_de_3_categorias_no_modelo(perfil_pronto, categorias):
    """A quarta categoria é recusada mesmo fora do formulário (sinal do muitos-para-muitos)."""
    perfil = perfil_pronto(slugs=("eletricista", "pintor", "encanador"))

    with pytest.raises(ValidationError, match="no máximo 3"), transaction.atomic():
        perfil.categorias.add(categorias["pedreiro"])

    assert perfil.categorias.count() == 3


def test_maximo_de_3_categorias_no_formulario(admin_guia, categorias, tangara):
    """No cadastro do admin, 4 categorias dão erro e nada é gravado."""
    escolhidas = [categorias[s].pk for s in ("eletricista", "pintor", "encanador", "pedreiro")]

    resposta = admin_guia.post(
        reverse("admin:guia_perfilguia_add"),
        dados_do_formulario(categorias=escolhidas, cidade=tangara.pk),
    )

    assert resposta.status_code == 200
    assert "Escolha no máximo 3 categorias." in resposta.content.decode()
    assert not PerfilGuia.objects.exists()


def test_categoria_regulamentada_nao_aceita_frase(admin_guia, categorias, tangara, perfil_pronto):
    """Formulário recusa a frase; o modelo recusa juntar categoria regulamentada a perfil com frase."""
    resposta = admin_guia.post(
        reverse("admin:guia_perfilguia_add"),
        dados_do_formulario(
            categorias=[categorias["dentista"].pk], cidade=tangara.pk, frase="O melhor sorriso da cidade"
        ),
    )
    assert "não tem frase promocional" in resposta.content.decode()
    assert not PerfilGuia.objects.exists()

    perfil = perfil_pronto(frase="Atendimento rápido", slugs=())
    with pytest.raises(ValidationError, match="regulamentada"), transaction.atomic():
        perfil.categorias.add(categorias["dentista"])


def test_regulamentado_exige_registro_e_previa_restrita(perfil_pronto):
    """Regulamentado: sem registro não publica; a prévia não mostra frase, logo nem horário."""
    perfil = perfil_pronto(slugs=("dentista",), horarios={"seg": [["08:00", "12:00"]]})

    assert any("registro" in f for f in services.pendencias(perfil, exigir_aceite=False))
    perfil.registro_profissional = "CRO-MT 1234"
    perfil.save()
    previa = services.previa(perfil)
    assert previa.registro == "CRO-MT 1234"
    assert previa.frase == "" and previa.horarios == [] and previa.logo == ""


def test_frase_sem_links_nem_html(perfil_pronto):
    """Frase é texto puro: link, domínio ou marcação são recusados."""
    for frase in ("Veja www.exemplo.com", "Acesse https://x.io", "<b>Promoção</b>", "loja.com.br"):
        perfil = PerfilGuia(nome_publico="X", responsavel_nome="Y", frase=frase)
        with pytest.raises(ValidationError) as erro:
            perfil.clean()
        assert "frase" in erro.value.message_dict


def test_carregar_categorias_e_idempotente(db):
    """Duas cargas: mesmos 82 registros (upsert por slug), regulamentadas com o rótulo do conselho."""
    call_command("carregar_categorias_guia")
    call_command("carregar_categorias_guia")

    assert CategoriaServico.objects.count() == 82
    assert GrupoCategoria.objects.count() == 9
    medico = CategoriaServico.objects.get(slug="medico")
    assert medico.regulamentada and medico.rotulo_registro == "CRM"
    assert not CategoriaServico.objects.get(slug="pedreiro").regulamentada


def test_categoria_com_perfis_nao_se_apaga(perfil_pronto, categorias, membro, entrar_no_admin):
    """Nem o Administrador apaga categoria em uso (só desativa)."""
    perfil_pronto()
    cliente = entrar_no_admin(membro("Administrador"))

    resposta = cliente.get(reverse("admin:guia_categoriaservico_delete", args=[categorias["eletricista"].pk]))

    assert resposta.status_code == 403


# --- CPF e duplicidade --------------------------------------------------------------------------------


def _texto_de_todas_as_tabelas_do_guia() -> str:
    """Todo o conteúdo das tabelas do guia (inclusive histórico) como texto, para procurar o CPF."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'guia_%'")
        tabelas = [linha[0] for linha in cursor.fetchall()]
        partes = []
        for tabela in tabelas:
            cursor.execute(f'SELECT row_to_json(t)::text FROM "{tabela}" t')  # noqa: S608 (nome vem do catálogo)
            partes.extend(linha[0] for linha in cursor.fetchall())
    return "\n".join(partes)


def test_cpf_nunca_em_claro_no_banco_nem_no_html(admin_guia, categorias, tangara):
    """Autônomo com CPF pelo admin: no banco só o HMAC e o final; na ficha do admin, só ***-25."""
    resposta = admin_guia.post(
        reverse("admin:guia_perfilguia_add"),
        dados_do_formulario(
            tipo="autonomo", cnpj="", cpf=CPF, categorias=[categorias["eletricista"].pk], cidade=tangara.pk
        ),
    )
    assert resposta.status_code == 302, resposta.content.decode()[:2000]
    perfil = PerfilGuia.objects.get()

    assert perfil.cpf_final == "25" and len(perfil.cpf_hash) == 64
    assert CPF_DIGITOS not in _texto_de_todas_as_tabelas_do_guia()
    assert CPF_DIGITOS not in perfil.cpf_hash
    pagina = admin_guia.get(reverse("admin:guia_perfilguia_change", args=[perfil.pk])).content.decode()
    assert CPF_DIGITOS not in pagina and "529.982.247" not in pagina
    assert "***.***.***-25" in pagina


def test_resumo_do_cpf_depende_da_chave(settings):
    """Mesmo CPF e mesma chave: mesmo resumo (acha duplicidade); outra chave: outro resumo."""
    primeiro, final = services.resumo_cpf(CPF)
    assert services.resumo_cpf("52998224725")[0] == primeiro and final == "25"
    settings.GUIA_CPF_CHAVE = "outra-chave"
    assert services.resumo_cpf(CPF)[0] != primeiro


def test_cpf_invalido_recusado():
    """Dígitos verificadores conferidos."""
    with pytest.raises(ValidationError):
        services.normalizar_cpf("529.982.247-26")


def test_duplicidade_alerta_sem_bloquear(admin_guia, perfil_pronto, categorias, tangara):
    """Mesmo WhatsApp e mesmo CNPJ de outro perfil: salva (não bloqueia) e avisa a equipe."""
    perfil_pronto(nome="Vidraçaria Antiga", whatsapp="+5565999990202", cnpj="90000002000173")

    resposta = admin_guia.post(
        reverse("admin:guia_perfilguia_add"),
        dados_do_formulario(categorias=[categorias["eletricista"].pk], cidade=tangara.pk),
    )

    assert resposta.status_code == 302, resposta.context["adminform"].form.errors
    assert PerfilGuia.objects.count() == 2
    texto = mensagens(resposta)
    assert "Possível cadastro repetido" in texto and "Mesmo WhatsApp" in texto and "Mesmo CNPJ" in texto
    novo = PerfilGuia.objects.get(nome_publico="Vidraçaria Nova")
    assert len(services.duplicidades(novo)) == 2


def test_duplicidade_pelo_cpf(perfil_pronto):
    """Dois autônomos com o mesmo CPF: o alerta vem do resumo (sem guardar o CPF)."""
    primeiro = perfil_pronto(nome="A", whatsapp="+5565999990301", tipo="autonomo", cnpj="")
    segundo = perfil_pronto(nome="B", whatsapp="+5565999990302", tipo="autonomo", cnpj="")
    for perfil in (primeiro, segundo):
        services.definir_cpf(perfil, CPF)
        perfil.save()

    assert any("Mesmo CPF" in aviso for aviso in services.duplicidades(segundo))


# --- Campos auxiliares -----------------------------------------------------------------------------


def test_horarios_e_ip_e_navegador():
    """Horário em texto livre vira intervalos; IP fica com o último bloco zerado; navegador só em resumo."""
    assert services.interpretar_horario("8-12, 14:00-18:00") == [["08:00", "12:00"], ["14:00", "18:00"]]
    with pytest.raises(ValidationError):
        services.interpretar_horario("18-8")
    assert services.truncar_ip("200.150.10.77") == "200.150.10.0"
    assert services.truncar_ip("2804:14c:1:2:3:4:5:6") == "2804:14c:1::"
    assert services.truncar_ip("lixo") == ""
    agente = "Mozilla/5.0 (Linux; Android 14; SM-A515F) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
    assert services.resumir_agente(agente) == "Chrome · Android"


def test_grupo_guia_existe():
    """A migration cria o grupo Guia."""
    assert Group.objects.filter(name="Guia").exists()
