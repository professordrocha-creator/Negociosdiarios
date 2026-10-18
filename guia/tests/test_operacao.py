"""Testes da etapa G3 do guia (LGPD e operação; docs/GUIA.md §5, §8 e §9): pedido do titular pela ficha,
remoção e limpeza depois do prazo de prova, termo novo com prazo e pausa, lista de convites e "não contatar",
importação de CSV, ações em lote com confirmação, CSV exportado sem fórmulas, estabelecimentos regulados com
horário e permissões."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from guia import services
from guia.models import AceitePublicacao, ContatoConvite, PedidoDoPerfil, PerfilGuia, TermoGuia

pytestmark = pytest.mark.django_db

PESSOA = {"HTTP_USER_AGENT": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile Safari/537.36"}


def url_pedido(perfil) -> str:
    """Formulário "Esta é minha empresa"."""
    return reverse("guia:pedido", args=[perfil.slug])


def pedir(client, perfil, **extra):
    """Envia o pedido público."""
    dados = {
        "tipo": "remover",
        "descricao": "Fechei a loja.",
        "contato": "dono@exemplo.com",
        "site_empresa": "",
        **extra,
    }
    return client.post(url_pedido(perfil), dados, **PESSOA)


def _logo() -> SimpleUploadedFile:
    """Logo de verdade (Pillow)."""
    saida = io.BytesIO()
    Image.new("RGB", (400, 400), (10, 120, 140)).save(saida, format="PNG")
    return SimpleUploadedFile("logo.png", saida.getvalue(), content_type="image/png")


# --- Pedido do titular -----------------------------------------------------------------------------------


def test_pedido_publico_entra_na_fila_com_prazo_de_15_dias(client, guia_ligado, perfil_publicado):
    """A ficha leva ao formulário; o pedido nasce aberto, com prazo de 15 dias, e a equipe é avisada."""
    perfil = perfil_publicado()
    ficha = client.get(reverse("guia:empresa", args=[perfil.slug]), **PESSOA).content.decode()
    assert url_pedido(perfil) in ficha and "escreva para" not in ficha

    pagina = client.get(url_pedido(perfil), **PESSOA).content.decode()
    resposta = pedir(client, perfil)

    assert "15 dias" in pagina and "Sobre esta tela" in pagina
    assert resposta.status_code == 200 and "Pedido recebido" in resposta.content.decode()
    pedido = PedidoDoPerfil.objects.get()
    assert pedido.status == "aberto" and pedido.origem == "ficha" and pedido.contato == "dono@exemplo.com"
    assert pedido.prazo_ate == timezone.localdate() + timedelta(days=15)
    assert mail.outbox and "dono@exemplo.com" not in mail.outbox[0].body  # o aviso não leva o contato


def test_pedido_honeypot_csrf_e_limite_por_hora(client, guia_ligado, perfil_publicado):
    """Robô: sucesso sem gravar. Sem CSRF: 403. Passou do limite: 429."""
    perfil = perfil_publicado()
    assert pedir(client, perfil, site_empresa="spam").status_code == 200
    assert not PedidoDoPerfil.objects.exists()

    assert Client(enforce_csrf_checks=True).post(url_pedido(perfil), {"tipo": "outro"}).status_code == 403

    guia_ligado.pedidos_por_hora = 2
    guia_ligado.save()
    codigos = [pedir(client, perfil).status_code for _ in range(3)]
    assert codigos[-1] == 429 and PedidoDoPerfil.objects.count() == 1  # o 1º contou no limite (o robô)


def test_pedido_de_perfil_fora_do_ar_da_404(client, guia_ligado, perfil_publicado):
    """Perfil pausado: o formulário dá 404 (o canal é o e-mail do Encarregado)."""
    perfil = perfil_publicado()
    services.pausar(perfil)
    assert client.get(url_pedido(perfil), **PESSOA).status_code == 404


# --- Remoção e limpeza ------------------------------------------------------------------------------------


def test_remocao_apaga_logo_e_contatos_e_mantem_o_aceite(client, guia_ligado, perfil_publicado):
    """Despublica, apaga logo (arquivo), WhatsApp, telefone e contato do responsável (também no histórico);
    o aceite e o pedido ficam. Pedido por e-mail recebe a confirmação."""
    perfil = perfil_publicado(telefone="+556533334444")
    services.definir_logo(perfil, _logo())
    arquivo = Path(perfil.logo.path)
    pedido = services.registrar_pedido(perfil, "remover", "Sair do guia", "dono@exemplo.com")
    mail.outbox.clear()

    services.remover_perfil(perfil, None, "Pedido por e-mail.", pedido=pedido)

    perfil.refresh_from_db()
    pedido.refresh_from_db()
    assert perfil.status == "removido" and perfil.removido_em
    assert not perfil.logo and not arquivo.exists()
    assert perfil.whatsapp == perfil.telefone == perfil.responsavel_contato == ""
    historico = perfil.history.all()
    assert (
        not historico.exclude(whatsapp="").exists() and not historico.exclude(responsavel_contato="").exists()
    )
    assert AceitePublicacao.objects.filter(perfil=perfil).count() == 1
    assert pedido.status == "atendido" and pedido.decidido_em
    assert mail.outbox and mail.outbox[0].to == ["dono@exemplo.com"]
    assert client.get(reverse("guia:empresa", args=[perfil.slug]), **PESSOA).status_code == 404


def test_limpeza_diaria_apaga_tudo_so_depois_do_prazo_de_prova(perfil_publicado):
    """Removido há menos de 5 anos: fica (prova). Depois do prazo: perfil, aceite, pedido e histórico saem."""
    perfil = perfil_publicado()
    pedido = services.registrar_pedido(perfil, "remover", "", "x")
    services.remover_perfil(perfil, None, "teste", pedido=pedido)

    assert services.limpar_guia_vencido() == 0
    assert PerfilGuia.objects.filter(pk=perfil.pk).exists()

    seis_anos = timezone.now() - timedelta(days=6 * 365)
    PerfilGuia.objects.filter(pk=perfil.pk).update(removido_em=seis_anos)
    PedidoDoPerfil.objects.update(decidido_em=seis_anos)

    assert services.limpar_guia_vencido() == 1
    assert not PerfilGuia.objects.exists() and not AceitePublicacao.objects.exists()
    assert not PedidoDoPerfil.objects.exists() and not PerfilGuia.history.filter(id=perfil.pk).exists()


def test_revogar_registra_a_data(perfil_publicado):
    """Revogação despublica e guarda a data (G1, conferido aqui com a remoção)."""
    perfil = perfil_publicado()
    aceite = services.aceite_vigente(perfil)
    services.revogar_aceite(aceite, None, "pedido")
    aceite.refresh_from_db()
    assert aceite.revogado_em is not None


# --- Termo novo --------------------------------------------------------------------------------------------


def _termo_novo(vigente_desde) -> TermoGuia:
    """Cria a versão nova do termo."""
    return TermoGuia.objects.create(
        versao="2026-11", texto="Novo texto {nome_guia}.", vigente_desde=vigente_desde
    )


def test_termo_novo_gera_convites_e_a_rotina_pausa_depois_do_prazo(perfil_publicado):
    """Convite com validade até o fim do prazo (30 dias) e e-mail a quem tem e-mail; quem aceitou continua;
    no dia 31 a rotina pausa quem não aceitou (nada é apagado)."""
    aceita = perfil_publicado(nome="Aceita", whatsapp="+5565999990401")
    nao_aceita = perfil_publicado(nome="Nao Aceita", whatsapp="+5565999990402")
    hoje = timezone.localdate()
    novo = _termo_novo(hoje)
    mail.outbox.clear()

    assert services.convidar_para_termo_novo() == 2
    assert services.convidar_para_termo_novo() == 0  # não repete
    assert len(mail.outbox) == 2 and "Atualizamos o termo" in mail.outbox[0].subject
    convite = nao_aceita.convites.order_by("-criado_em").first()
    assert timezone.localtime(convite.expira_em).date() == hoje + timedelta(days=30)
    _, token = services.gerar_convite(aceita)
    services.aceitar_convite(token, "Maria Responsável", avisar=False)
    assert [p.perfil for p in services.pendentes_do_termo()] == [nao_aceita]

    assert services.pausar_sem_aceite_do_termo(hoje + timedelta(days=30)) == 0
    assert services.pausar_sem_aceite_do_termo(hoje + timedelta(days=31)) == 1
    nao_aceita.refresh_from_db()
    aceita.refresh_from_db()
    assert nao_aceita.status == "pausado" and aceita.status == "publicado"
    assert services.aceite_vigente(aceita).termo == novo


def test_salvar_termo_novo_no_admin_cria_os_convites(perfil_publicado, membro, entrar_no_admin):
    """Administrador grava a versão em vigor: os publicados ganham o link; o painel mostra quem falta."""
    perfil = perfil_publicado()
    cliente = entrar_no_admin(membro("Administrador"))
    dados = {
        "versao": "2026-12",
        "vigente_desde": timezone.localdate().strftime("%d/%m/%Y"),
        "texto": "Texto",
        "rascunho_juridico": "on",
    }

    resposta = cliente.post(reverse("admin:guia_termoguia_add"), dados)
    painel = cliente.get(reverse("admin:guia_termo_pendentes")).content.decode()

    assert resposta.status_code == 302
    assert perfil.convites.filter(usado_em__isnull=True).count() == 1
    assert perfil.nome_publico in painel and "vale até" in painel


# --- Lista de convites -----------------------------------------------------------------------------------


def test_nao_contatar_bloqueia_convites(perfil_pronto, tangara, admin_guia):
    """Número na lista "não contatar": nem convite da lista, nem link de aceite de perfil."""
    perfil = perfil_pronto(whatsapp="+5565999990501")
    contato = ContatoConvite.objects.create(
        nome="Fulano",
        whatsapp="+5565999990501",
        cidade=tangara,
        situacao=ContatoConvite.Situacao.NAO_CONTATAR,
    )

    with pytest.raises(services.PublicacaoRecusada, match="não ser contatado"):
        services.gerar_convite(perfil)
    with pytest.raises(ValueError):
        services.convidar_contato(contato)
    pagina = admin_guia.get(reverse("admin:guia_contato_convidar", args=[contato.pk])).content.decode()
    assert "não envie convite" in pagina.lower() and "wa.me" not in pagina


def test_convidar_marca_e_quem_aceita_vira_perfil_da_lista_antiga(admin_guia, tangara, categorias, termo):
    """Convidar: marca a data e abre o wa.me. Criar perfil: rascunho origem lista antiga; com o aceite, o
    contato fica "aceitou"."""
    contato = ContatoConvite.objects.create(
        nome="Zé Pintor", whatsapp="+5565999990601", cidade=tangara, categoria=categorias["pintor"]
    )

    resposta = admin_guia.post(reverse("admin:guia_contato_convidar", args=[contato.pk]))
    contato.refresh_from_db()
    assert "https://wa.me/5565999990601?text=" in resposta.content.decode()
    assert contato.situacao == "convidado" and contato.convidado_em

    resposta = admin_guia.post(reverse("admin:guia_contato_criar_perfil", args=[contato.pk]))
    contato.refresh_from_db()
    perfil = contato.perfil
    assert resposta.status_code == 302 and perfil.origem == "lista_antiga" and perfil.status == "rascunho"
    perfil.atendimento = PerfilGuia.Atendimento.DOMICILIO
    perfil.area_atendimento = "Tangará e região"
    perfil.save()
    _, token = services.gerar_convite(perfil)
    services.aceitar_convite(token, "Zé Pintor da Silva", avisar=False)
    contato.refresh_from_db()
    assert contato.situacao == "aceitou"


def test_importar_csv_mostra_erros_por_linha_e_importa_so_as_validas(admin_guia, tangara, categorias):
    """Prévia com o número da linha do erro; repetido e bloqueado ficam de fora; só as válidas entram."""
    ContatoConvite.objects.create(
        nome="Bloqueado", whatsapp="+5565999990703", cidade=tangara, situacao=ContatoConvite.Situacao.RECUSOU
    )
    csv = (
        "nome;whatsapp;cidade;categoria\n"
        "Ana;(65) 99999-0701;Tangará da Serra;eletricista\n"
        "Bia;123;Tangará da Serra;\n"
        "Caio;65999990703;Tangará da Serra/MT;\n"
        "Dani;65999990701;tangara-da-serra;\n"
        "Edu;65999990705;Cidade Inexistente;padeiro voador\n"
    )
    arquivo = SimpleUploadedFile("lista.csv", csv.encode("utf-8"), content_type="text/csv")

    previa = admin_guia.post(
        reverse("admin:guia_contato_importar"), {"arquivo": arquivo, "origem": "lista_antiga"}
    )
    pagina = previa.content.decode()

    assert "Linha 3: WhatsApp inválido (123)" in pagina
    assert "Linha 6:" in pagina and "cidade não atendida" in pagina and "categoria desconhecida" in pagina
    assert "Linha 4: não contatar" in pagina and "Linha 5: número repetido" in pagina
    assert not ContatoConvite.objects.filter(nome="Ana").exists()  # prévia não grava

    resposta = admin_guia.post(
        reverse("admin:guia_contato_importar"), {"texto": csv, "origem": "lista_antiga", "importar": "1"}
    )
    assert resposta.status_code == 302
    ana = ContatoConvite.objects.get(nome="Ana")
    assert ana.whatsapp == "+5565999990701" and ana.categoria.slug == "eletricista"
    assert ContatoConvite.objects.count() == 2


# --- Fila, lotes, CSV --------------------------------------------------------------------------------------


def test_acao_em_lote_pede_confirmacao(admin_guia, perfil_publicado):
    """Pausar os selecionados: primeiro a tela de confirmação (nada muda); depois pausa."""
    perfil = perfil_publicado()
    url = reverse("admin:guia_perfilguia_changelist")
    dados = {"action": "pausar_selecionados", ACTION_CHECKBOX_NAME: [perfil.pk]}

    confirmacao = admin_guia.post(url, dados)
    perfil.refresh_from_db()
    assert confirmacao.status_code == 200 and perfil.status == "publicado"

    admin_guia.post(url, {**dados, "aplicar": "1", "motivo": "Teste"})
    perfil.refresh_from_db()
    assert perfil.status == "pausado"


def test_pausar_por_cidade_mostra_a_lista_antes(admin_guia, perfil_publicado, tangara, categorias):
    """Pausar em lote por cidade/categoria: lista quem será pausado e só pausa ao confirmar."""
    perfil = perfil_publicado()
    url = reverse("admin:guia_pausar_lote")
    dados = {"cidade": tangara.pk, "categoria": categorias["eletricista"].pk, "motivo": "Chuva"}

    previa = admin_guia.post(url, dados)
    perfil.refresh_from_db()
    assert perfil.nome_publico in previa.content.decode() and perfil.status == "publicado"
    assert "Escolha a cidade" in admin_guia.post(url, {"motivo": "x"}).content.decode()

    admin_guia.post(url, {**dados, "confirmar": "1"})
    perfil.refresh_from_db()
    assert perfil.status == "pausado"


def test_csv_exportado_neutraliza_formulas(admin_guia, perfil_publicado):
    """Célula que começa com = + - @ ganha um apóstrofo (não vira fórmula na planilha)."""
    perfil = perfil_publicado(nome='=HYPERLINK("http://x")')
    resposta = admin_guia.post(
        reverse("admin:guia_perfilguia_changelist"),
        {"action": "exportar_csv", ACTION_CHECKBOX_NAME: [perfil.pk]},
    )
    texto = resposta.content.decode("utf-8-sig")

    assert resposta["Content-Type"].startswith("text/csv")
    assert "'=HYPERLINK" in texto and "\n=HYPERLINK" not in texto
    for perigoso in ("+1", "-1", "@SUM", "=1"):
        assert services.celula_csv(perigoso) == "'" + perigoso
    assert services.celula_csv("Normal") == "Normal"


def test_estatisticas_e_filas_abrem(admin_guia, perfil_publicado, client):
    """Painel de estatísticas (7 e 30 dias, CSV) e as visões da fila abrem para o grupo Guia."""
    perfil_publicado()
    for url in (
        reverse("admin:guia_estatisticas") + "?dias=7",
        reverse("admin:guia_perfilguia_changelist") + "?fila=link_vencido",
        reverse("admin:guia_perfilguia_changelist") + "?fila=duplicidade",
        reverse("admin:guia_termo_pendentes"),
        reverse("admin:guia_contato_importar"),
    ):
        assert admin_guia.get(url).status_code == 200, url
    csv = admin_guia.get(reverse("admin:guia_estatisticas") + "?csv=1")
    assert csv["Content-Disposition"].startswith("attachment")


# --- Estabelecimentos regulados (ajuste da G2) ------------------------------------------------------


def test_estabelecimento_regulado_mostra_horario_e_individual_nao(client, guia_ligado, perfil_publicado):
    """Farmácia: horário e "aberto agora", sem frase nem logo. Dentista: sem horário."""
    todo_dia = {d: [["00:00", "24:00"]] for d in services.CHAVES_DIAS}
    farmacia = perfil_publicado(
        nome="Farmácia Central", slugs=("farmacia",), registro_profissional="CRF-MT 1", horarios=todo_dia
    )
    dentista = perfil_publicado(
        nome="Dra. Ana", whatsapp="+5565999990801", slugs=("dentista",), registro_profissional="CRO-MT 2",
        horarios=todo_dia,
    )  # fmt: skip
    services.definir_logo(farmacia, _logo())

    pagina_farmacia = client.get(reverse("guia:empresa", args=[farmacia.slug]), **PESSOA).content.decode()
    pagina_dentista = client.get(reverse("guia:empresa", args=[dentista.slug]), **PESSOA).content.decode()

    assert (
        "Horário" in pagina_farmacia
        and "Aberto agora" in pagina_farmacia
        and "openingHours" in pagina_farmacia
    )
    assert farmacia.logo.url not in pagina_farmacia
    assert "Horário" not in pagina_dentista and "Aberto agora" not in pagina_dentista
    assert farmacia.mostra_horario and not dentista.mostra_horario


# --- Permissões --------------------------------------------------------------------------------------


def test_permissoes_moderador_guia_financeiro(perfil_publicado, membro, entrar_no_admin, tangara):
    """Moderador: pedidos (ver, registrar, atender); não mexe na lista de convites. Guia: lista de convites.
    Financeiro: nada do guia."""
    perfil = perfil_publicado()
    pedido = services.registrar_pedido(perfil, "remover", "", "x")
    contato = ContatoConvite.objects.create(nome="C", whatsapp="+5565999990901", cidade=tangara)

    moderador = entrar_no_admin(membro("Moderador"))
    assert moderador.get(reverse("admin:guia_pedidodoperfil_changelist")).status_code == 200
    assert moderador.get(reverse("admin:guia_pedidodoperfil_add")).status_code == 200
    assert moderador.get(reverse("admin:guia_contatoconvite_changelist")).status_code == 403
    assert moderador.get(reverse("admin:guia_contato_convidar", args=[contato.pk])).status_code == 403
    moderador.post(
        reverse("admin:guia_pedidodoperfil_changelist"),
        {"action": "atender_removendo", ACTION_CHECKBOX_NAME: [pedido.pk], "aplicar": "1", "motivo": "ok"},
    )
    perfil.refresh_from_db()
    assert perfil.status == "removido"
    moderador.logout()

    guia = entrar_no_admin(membro("Guia"))
    assert guia.get(reverse("admin:guia_contatoconvite_changelist")).status_code == 200
    assert guia.get(reverse("admin:guia_pedidodoperfil_changelist")).status_code == 403
    guia.logout()

    financeiro = entrar_no_admin(membro("Financeiro"))
    for nome in ("guia_pedidodoperfil_changelist", "guia_contatoconvite_changelist", "guia_estatisticas"):
        assert financeiro.get(reverse(f"admin:{nome}")).status_code == 403, nome


def test_rotina_do_guia_roda_as_tres_partes(perfil_publicado):
    """A tarefa diária devolve o resumo das três rotinas."""
    from guia.tasks import rotina_do_guia

    perfil_publicado()
    assert set(rotina_do_guia()) == {"convites_termo", "pausados_termo", "removidos_de_vez"}
