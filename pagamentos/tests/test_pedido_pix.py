"""Testes do lote 3B: o cliente escolhe o plano e paga pelo Pix (tela Pagar, "Já paguei"); a equipe aprova
numa tela só ("Cadastros aguardando": fatura paga, vigência, loja aprovada e plano ativo), recusa ou marca
como não pago; vigência (sem anúncio novo após o vencimento) e Configuração do Pix (Administrador e
Financeiro)."""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.services import configuracao, pendencias_da_equipe
from pagamentos import services
from pagamentos.models import Fatura
from planos.models import Assinatura, Periodicidade, Plano
from planos.services import SemAssinaturaAtiva, assinatura_de

pytestmark = pytest.mark.django_db

Situacao = Fatura.Situacao


@pytest.fixture
def pendente(criar_anunciante):
    """Loja recém-cadastrada (e-mail confirmado, ainda pendente de aprovação), sem plano."""
    return criar_anunciante("nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)


@pytest.fixture
def cliente(client, pendente):
    """O dono da loja pendente logado no site."""
    client.force_login(pendente.usuario)
    return client


def basico() -> Plano:
    """Plano Básico (da migration inicial)."""
    return Plano.objects.get(slug="basico")


def mudar_config(**valores):
    """Altera as Configurações do site (como no admin)."""
    config = configuracao()
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    config.save()


# --- Fluxo do cliente ------------------------------------------------------------------------------------


def test_pendente_escolhe_plano_confere_dados_e_ve_o_pix(cliente, pendente):
    """Escolher plano cria o pedido (fatura aguardando pagamento, plano "aguardando pagamento") e leva à tela
    Pagar com o valor, o QR Code e o Pix copia e cola; o WhatsApp conferido é gravado em E.164."""
    assert cliente.get(reverse("pagamentos:assinar")).status_code == 200

    resposta = cliente.post(
        reverse("pagamentos:assinar"),
        {
            "plano": basico().pk,
            "periodicidade": "mensal",
            "nome_publico": "Loja Nova",
            "whatsapp": "(65) 98888-0002",
        },
    )

    fatura = Fatura.objects.get(assinatura__anunciante=pendente)
    assert resposta.status_code == 302 and resposta.url == reverse("pagamentos:pagar", args=[fatura.codigo])
    assert fatura.situacao == Situacao.ABERTA and fatura.valor == basico().preco_mensal
    assert assinatura_de(pendente).situacao == Assinatura.Situacao.PENDENTE
    pendente.refresh_from_db()
    assert pendente.whatsapp == "+5565988880002" and pendente.status == Anunciante.Status.PENDENTE

    pagina = cliente.get(resposta.url).content.decode()
    assert "data:image/svg+xml" in pagina and "br.gov.bcb.pix" in pagina
    assert "Fiz o Pix, avisar a equipe" in pagina
    assert "a loja é aprovada e o plano fica ativo" in pagina


def test_sem_email_confirmado_nao_escolhe_plano(client, criar_anunciante):
    """Antes de confirmar o e-mail, nada de pedido (403 com a mensagem do que fazer)."""
    loja = criar_anunciante(
        "sem@exemplo.com", "Sem Email", status=Anunciante.Status.PENDENTE, sem_confirmacao=True
    )
    client.force_login(loja.usuario)
    assert client.get(reverse("pagamentos:assinar")).status_code == 403


def test_tela_do_pendente_leva_a_escolher_o_plano(cliente):
    """O painel do pendente (403) mostra o botão "Escolher plano e pagar"."""
    pagina = cliente.get(reverse("anunciantes:painel")).content.decode()
    assert reverse("pagamentos:assinar") in pagina and "Escolher plano e pagar" in pagina


def test_ja_paguei_sem_comprovante_avisa_a_equipe(cliente, pendente):
    """ "Já paguei" sem comprovante: aguardando conferência, e-mail à equipe e contador em Pendências."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)

    resposta = cliente.post(reverse("pagamentos:pagar_ja_paguei", args=[fatura.codigo]), {"recado": ""})

    fatura.refresh_from_db()
    assert resposta.status_code == 302 and fatura.situacao == Situacao.AGUARDANDO and not fatura.comprovante
    (email,) = mail.outbox
    assert fatura.codigo in email.body and "/pagamentos/pedidoaguardando/" in email.body
    dono = Usuario.objects.create_superuser(email="dono@exemplo.com", password=SENHA, nome="Dono")
    contador = next(p for p in pendencias_da_equipe(dono) if "Cadastros aguardando" in p.rotulo)
    assert contador.total == 1
    assert "aguardando conferência" in cliente.get(resposta.url).content.decode().lower()


def test_pedido_novo_substitui_o_anterior(pendente):
    """O pedido ainda não pago é cancelado (com motivo) quando o cliente escolhe outro plano."""
    primeiro = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    segundo = services.fazer_pedido(pendente, Plano.objects.get(slug="profissional"), Periodicidade.ANUAL)

    primeiro.refresh_from_db()
    assert primeiro.situacao == Situacao.CANCELADA and segundo.situacao == Situacao.ABERTA
    assert segundo.valor == Plano.objects.get(slug="profissional").preco_anual


def test_limite_de_pedidos_por_hora(cliente, pendente):
    """Passou de `pedidos_por_hora`: recusa (429 na tela) e não cria fatura."""
    mudar_config(pedidos_por_hora=2)
    services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    services.fazer_pedido(pendente, basico(), Periodicidade.ANUAL)

    dados = {
        "plano": basico().pk,
        "periodicidade": "mensal",
        "nome_publico": "Loja Nova",
        "whatsapp": "65999990001",
    }
    resposta = cliente.post(reverse("pagamentos:assinar"), dados)

    assert resposta.status_code == 429 and Fatura.objects.count() == 2


def test_pagar_so_a_propria_fatura(client, pendente, criar_anunciante):
    """Fatura de outra loja: 404 (sem IDOR)."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    outra = criar_anunciante("outra@exemplo.com", "Outra", status=Anunciante.Status.PENDENTE)
    client.force_login(outra.usuario)

    assert client.get(reverse("pagamentos:pagar", args=[fatura.codigo])).status_code == 404
    assert client.post(reverse("pagamentos:pagar_ja_paguei", args=[fatura.codigo])).status_code == 404


def test_quem_ja_tem_plano_vai_para_meu_plano(client, loja):
    """Loja com plano ativo não faz pedido novo: troca em Meu plano e renova pagando a fatura."""
    client.force_login(loja().usuario)
    resposta = client.get(reverse("pagamentos:assinar"))
    assert resposta.status_code == 302 and resposta.url == reverse("planos:meu_plano")


def test_pedido_fica_fora_da_regua_e_da_rotina(pendente):
    """Pedido não pago não recebe lembrete de cobrança nem gera fatura de renovação."""
    services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    amanha = timezone.localdate() + timedelta(days=3)
    mail.outbox.clear()

    assert services.enviar_avisos(amanha) == 0 and services.gerar_faturas(amanha) == 0
    assert not mail.outbox


# --- Aprovação numa tela só -----------------------------------------------------------------------------


def test_aprovar_faz_tudo_de_uma_vez(pendente):
    """Fatura paga, vigência de início a fim, loja aprovada e plano ativo; quem aprovou fica no histórico."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    dono = Usuario.objects.create_superuser(email="dono@exemplo.com", password=SENHA, nome="Dono")
    inicio, fim = services.datas_sugeridas(fatura)
    assert (inicio, fim) == (timezone.localdate(), timezone.localdate() + timedelta(days=30))

    services.aprovar_pedido_pago(fatura, dono, inicio, fim)

    fatura.refresh_from_db()
    pendente.refresh_from_db()
    assinatura = assinatura_de(pendente)
    assert fatura.situacao == Situacao.PAGA and fatura.confirmado_por == dono
    assert (assinatura.situacao, assinatura.inicio, assinatura.vencimento) == (
        Assinatura.Situacao.ATIVA,
        inicio,
        fim,
    )
    assert pendente.status == Anunciante.Status.ATIVO
    for registro in (fatura, assinatura, pendente):
        assert registro.history.order_by("-history_id").first().history_user == dono
    (email,) = mail.outbox  # lote 3C: um e-mail só (loja aprovada + pagamento confirmado)
    assert "aprovada e o plano está ativo" in email.subject
    assert fatura.codigo in email.body and f"{fim:%d/%m/%Y}" in email.body


def test_vigencia_anual_usa_os_dias_do_plano(pendente):
    """Anual: fim = início + "dias de vigência (anual)" do Plano (admin)."""
    plano = basico()
    plano.dias_vigencia_anual = 360
    plano.save()
    fatura = services.fazer_pedido(pendente, plano, Periodicidade.ANUAL)
    assert services.datas_sugeridas(fatura)[1] == timezone.localdate() + timedelta(days=360)


def test_aprovar_sem_cidade_liberada_nao_muda_nada(pendente, tangara):
    """Cidade ainda não atendida: aprovar falha e nada muda (fatura, plano e loja continuam como estavam)."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    tangara.liberada = False
    tangara.save()

    with pytest.raises(ValueError, match="não é atendida"):
        services.aprovar_pedido_pago(fatura, None, *services.datas_sugeridas(fatura))

    fatura.refresh_from_db()
    pendente.refresh_from_db()
    assert fatura.situacao == Situacao.ABERTA and pendente.status == Anunciante.Status.PENDENTE
    assert assinatura_de(pendente).situacao == Assinatura.Situacao.PENDENTE


def test_recusar_cancela_e_avisa_com_motivo(pendente):
    """Recusar: fatura cancelada, plano cancelado e o motivo por e-mail; a loja pode pedir de novo."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)

    services.recusar_pedido_pago(fatura, None, "Documento ilegível.")

    fatura.refresh_from_db()
    assert fatura.situacao == Situacao.CANCELADA
    assert assinatura_de(pendente).situacao == Assinatura.Situacao.CANCELADA
    assert "Documento ilegível." in mail.outbox[-1].body
    assert services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL).situacao == Situacao.ABERTA


def test_marcar_como_nao_pago_volta_a_aguardar_pagamento(pendente):
    """O Pix não apareceu: volta a "aguardando pagamento" com o motivo para o cliente."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    services.enviar_comprovante(fatura, None)

    services.marcar_nao_pago(fatura, None, "Pix não encontrado no extrato.")

    fatura.refresh_from_db()
    assert fatura.situacao == Situacao.ABERTA and fatura.motivo_recusa == "Pix não encontrado no extrato."


def test_nada_de_dado_de_pagamento_no_log(pendente, caplog):
    """Pedido, "Já paguei" e aprovação não registram chave Pix, valor nem identificador no log."""
    mudar_config(pix_chave="contato@exemplo.com", pix_nome="Negocios Diarios", pix_cidade="Tangara")
    with caplog.at_level(logging.DEBUG):
        fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
        services.dados_pix(fatura)
        services.enviar_comprovante(fatura, None)
        services.aprovar_pedido_pago(fatura, None, *services.datas_sugeridas(fatura))
    for dado in ("contato@exemplo.com", fatura.identificador_pix, str(fatura.valor)):
        assert dado not in caplog.text


# --- Tela "Cadastros aguardando" (admin) ------------------------------------------------------------------


@pytest.fixture
def equipe_admin(entrar_no_admin):
    """Membro da equipe num grupo, logado no admin."""
    from django.contrib.auth.models import Group

    def _entrar(grupo: str):
        usuario = Usuario.objects.create_user(
            email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return entrar_no_admin(usuario), usuario

    return _entrar


def test_comercial_ve_a_lista_e_aprova_com_datas_ajustadas(equipe_admin, pendente):
    """Comercial: lista com loja, plano, valor e documento; "Aprovar" com as datas ajustadas pela equipe."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    client, comercial = equipe_admin("Comercial")

    lista = client.get(reverse("admin:pagamentos_pedidoaguardando_changelist")).content.decode()
    assert fatura.codigo in lista and "Loja Nova" in lista and "Aprovar" in lista and "CNPJ" in lista

    url = reverse("admin:pagamentos_pedidoaguardando_aprovar", args=[fatura.pk])
    assert client.get(url).status_code == 200
    inicio, fim = timezone.localdate() + timedelta(days=1), timezone.localdate() + timedelta(days=46)
    resposta = client.post(url, {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "observacao": ""})

    assert resposta.status_code == 302
    assinatura = assinatura_de(pendente)
    assert (assinatura.inicio, assinatura.vencimento, assinatura.situacao) == (inicio, fim, "ativa")
    assert Fatura.objects.get(pk=fatura.pk).confirmado_por == comercial


def test_moderador_nao_ve_cadastros_aguardando(equipe_admin, pendente):
    """Só Administrador, Financeiro e Comercial."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    client, _ = equipe_admin("Moderador")
    assert client.get(reverse("admin:pagamentos_pedidoaguardando_changelist")).status_code == 403
    assert (
        client.get(reverse("admin:pagamentos_pedidoaguardando_aprovar", args=[fatura.pk])).status_code == 403
    )


def test_acoes_recusar_e_marcar_nao_pago_pedem_motivo(equipe_admin, pendente):
    """As ações da lista usam a tela de motivo (obrigatório)."""
    from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME

    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    services.enviar_comprovante(fatura, None)
    client, _ = equipe_admin("Financeiro")
    lista = reverse("admin:pagamentos_pedidoaguardando_changelist")

    client.post(
        lista,
        {"action": "marcar_nao_pago_acao", ACTION_CHECKBOX_NAME: [fatura.pk], "aplicar": "1", "motivo": ""},
    )
    assert Fatura.objects.get(pk=fatura.pk).situacao == Situacao.AGUARDANDO  # sem motivo, nada muda
    client.post(
        lista,
        {
            "action": "marcar_nao_pago_acao",
            ACTION_CHECKBOX_NAME: [fatura.pk],
            "aplicar": "1",
            "motivo": "Não caiu.",
        },
    )
    assert Fatura.objects.get(pk=fatura.pk).situacao == Situacao.ABERTA
    client.post(
        lista,
        {"action": "recusar_acao", ACTION_CHECKBOX_NAME: [fatura.pk], "aplicar": "1", "motivo": "Desistiu."},
    )
    assert Fatura.objects.get(pk=fatura.pk).situacao == Situacao.CANCELADA


# --- Vigência e confiança -------------------------------------------------------------------------------


def test_vencido_nao_publica_anuncio_novo_mas_os_do_ar_seguem(loja, imovel, publicado):
    """No dia do vencimento ainda publica; depois, anúncio novo é recusado e os publicados continuam."""
    from anuncios import services as anuncios
    from anuncios.models import Anuncio

    anunciante = loja()
    no_ar = publicado(anunciante)
    assinatura = assinatura_de(anunciante)
    assinatura.vencimento = timezone.localdate()
    assinatura.save()
    assert anuncios.enviar_para_publicacao(imovel(anunciante, "Casa no dia do vencimento")) == "publicado"

    assinatura.vencimento = timezone.localdate() - timedelta(days=1)
    assinatura.save()
    with pytest.raises(SemAssinaturaAtiva, match="venceu"):
        anuncios.enviar_para_publicacao(imovel(anunciante, "Casa depois do vencimento"))
    no_ar.refresh_from_db()
    assert no_ar.situacao == Anuncio.Situacao.PUBLICADO


def test_confianca_so_dentro_da_vigencia(loja):
    """Parte A: loja aprovada e dentro da vigência publica direto; vencida, perde (até pagar)."""
    from anuncios.services import tem_confianca

    anunciante = loja()
    assert tem_confianca(anunciante)
    Assinatura.objects.filter(anunciante=anunciante).update(
        vencimento=timezone.localdate() - timedelta(days=1)
    )
    assert not tem_confianca(anunciante)


def test_loja_aprovada_pelo_pedido_publica_direto(pendente, imovel):
    """Aprovada em Cadastros aguardando (verificação + plano em dia): o primeiro anúncio vai direto ao ar."""
    from anuncios import services as anuncios

    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    services.aprovar_pedido_pago(fatura, None, *services.datas_sugeridas(fatura))
    pendente.refresh_from_db()
    assert anuncios.enviar_para_publicacao(imovel(pendente)) == "publicado"


# --- Configuração do Pix --------------------------------------------------------------------------------


def test_financeiro_configura_o_pix_e_ve_a_previa(equipe_admin):
    """Chave normalizada (CNPJ só dígitos), nome e cidade; a prévia mostra o QR de teste salvo."""
    client, _ = equipe_admin("Financeiro")
    url = reverse("admin:pagamentos_configuracaopix_change", args=[configuracao().pk])

    resposta = client.post(
        url,
        {
            "pix_chave": "12.345.678/0001-95",
            "pix_nome": "Negocios Diarios",
            "pix_cidade": "Tangara",
            "pix_instrucao": "Pague.",
        },
    )

    assert resposta.status_code == 302
    config = configuracao()
    assert (config.pix_chave, config.pix_nome) == ("12345678000195", "Negocios Diarios")
    assert services.credenciais_pix()[0] == "12345678000195"
    pagina = client.get(url).content.decode()
    assert "data:image/svg+xml" in pagina and "R$ 1,00" in pagina


def test_chave_pix_invalida_e_recusada(equipe_admin):
    """CPF com dígito errado não é salvo (mensagem diz o que corrigir)."""
    client, _ = equipe_admin("Financeiro")
    url = reverse("admin:pagamentos_configuracaopix_change", args=[configuracao().pk])
    resposta = client.post(
        url, {"pix_chave": "123.456.789-00", "pix_nome": "X", "pix_cidade": "Y", "pix_instrucao": ""}
    )
    assert resposta.status_code == 200 and "Chave Pix inválida" in resposta.content.decode()
    assert configuracao().pix_chave == ""


def test_chave_pix_so_para_quem_edita(equipe_admin):
    """Comercial e Moderador não abrem a Configuração do Pix; a tela geral não tem a chave."""
    url = reverse("admin:pagamentos_configuracaopix_change", args=[configuracao().pk])
    for grupo in ("Comercial", "Moderador"):
        client, _ = equipe_admin(grupo)
        assert client.get(url).status_code == 403
    client, _ = equipe_admin("Administrador")
    geral = client.get(reverse("admin:core_configuracao_change", args=[configuracao().pk])).content.decode()
    assert 'name="pix_chave"' not in geral


def test_pix_do_admin_vale_sobre_o_env(pendente, settings):
    """Com a chave preenchida no admin, o .env é ignorado; o QR leva o valor do pedido."""
    mudar_config(pix_chave="contato@exemplo.com", pix_nome="Negocios Diarios", pix_cidade="Tangara")
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)

    codigo = services.dados_pix(fatura)["copia_e_cola"]

    assert "contato@exemplo.com" in codigo and settings.PIX_CHAVE not in codigo
    assert f"54{len(str(fatura.valor)):02d}{fatura.valor}" in codigo
    assert Decimal(str(fatura.valor)) == basico().preco_mensal


# --- Lote 3C: uma regra só de renovação ------------------------------------------------------------------


def test_confirmar_pagamento_soma_os_dias_de_vigencia(loja):
    """ "Confirmar pagamento" (ação antiga) usa os dias de vigência do plano, como "Cadastros aguardando"."""
    anunciante = loja()
    plano = basico()
    plano.dias_vigencia = 45
    plano.save()
    assinatura = assinatura_de(anunciante)
    vencimento = timezone.localdate() + timedelta(days=4)
    Assinatura.objects.filter(pk=assinatura.pk).update(vencimento=vencimento)
    fatura = services.gerar_fatura(assinatura_de(anunciante), avisar=False)
    assert fatura.periodo_fim == vencimento + timedelta(days=45)

    services.confirmar_pagamento(fatura, None)

    assert assinatura_de(anunciante).vencimento == vencimento + timedelta(days=45)


def test_pagamento_manual_anual_soma_365_dias(loja):
    """ "Registrar pagamento manual" no plano anual: vencimento original + 365 dias (não o dia do ano)."""
    anunciante = loja()
    vencimento = timezone.localdate() + timedelta(days=2)
    Assinatura.objects.filter(anunciante=anunciante).update(vencimento=vencimento, periodicidade="anual")

    services.registrar_pagamento_manual(assinatura_de(anunciante), None, "Pix conferido no extrato")

    assert assinatura_de(anunciante).vencimento == vencimento + timedelta(days=365)


# --- Parte 4: fluxo único (cadastro com plano → Pix → uma aprovação) --------------------------------------


def test_cadastro_com_plano_leva_direto_ao_pix_depois_de_entrar(client, tangara):
    """O plano escolhido viaja no cadastro e vira o pedido; confirmado o e-mail, ao entrar o cliente cai na
    tela do Pix desse pedido (sem escolher o plano de novo)."""
    import re
    from urllib.parse import urlsplit

    plano = Plano.objects.get(slug="profissional")
    pagina = client.get(
        reverse("anunciantes:cadastro") + "?plano=profissional&periodo=anual"
    ).content.decode()
    assert "Você escolheu o plano <b>Profissional</b>, anual" in pagina
    client.post(
        reverse("anunciantes:cadastro"),
        {
            "nome": "Ana Dona",
            "email": "ana@loja.example",
            "senha": SENHA,  # constante de teste compartilhada (anunciantes/tests/conftest.py)
            "tipo": "revenda",
            "nome_publico": "Loja da Ana",
            "documento": "90.000.001/0001-29",
            "whatsapp": "(65) 99999-4321",
            "cidade": tangara.pk,
            "plano": plano.pk,
            "periodicidade": "anual",
            "aceite": "on",
            "site_empresa": "",
        },
    )
    loja = Anunciante.objects.get(nome_publico="Loja da Ana")
    pedido = services.pedido_em_aberto(loja)
    assert pedido.valor == plano.preco_anual and assinatura_de(loja).periodicidade == "anual"

    confirme = next(m for m in mail.outbox if m.subject.startswith("Confirme seu e-mail"))
    client.get(urlsplit(re.search(r"http\S+/cadastro/confirmar/\S+", confirme.body)[0]).path)
    aviso = next(m for m in mail.outbox if m.subject.startswith("Novo cadastro aguardando"))
    assert "Profissional (anual)" in aviso.body and pedido.identificador_pix in aviso.body
    assert reverse("admin:pagamentos_pedidoaguardando_aprovar", args=[pedido.pk]) in aviso.body

    # Login de verdade pela tela /entrar/ (sem force_login): é o que o navegador faz.
    resposta = client.post(
        reverse("contas:entrar"),
        {"username": "ana@loja.example", "password": SENHA},
        follow=True,
    )
    assert resposta.redirect_chain[-1][0] == reverse("pagamentos:pagar", args=[pedido.codigo])
    assert "Fiz o Pix, avisar a equipe" in resposta.content.decode()


def test_login_sem_email_confirmado_ou_com_senha_errada_explica(client, criar_anunciante):
    """Loja com o e-mail ainda não confirmado não entra (pede para confirmar); senha errada diz que o e-mail
    ou a senha estão incorretos. As duas mensagens aparecem em destaque de erro."""
    loja = criar_anunciante("pendente@exemplo.com", "Loja P", status=Anunciante.Status.PENDENTE)
    Usuario.objects.filter(pk=loja.usuario_id).update(email_confirmado_em=None)
    entrar = reverse("contas:entrar")

    sem_confirmar = client.post(entrar, {"username": "pendente@exemplo.com", "password": SENHA})
    assert (
        sem_confirmar.status_code == 200 and "Falta confirmar o seu e-mail" in sem_confirmar.content.decode()
    )
    assert "_auth_user_id" not in client.session

    errada = client.post(
        entrar, {"username": "pendente@exemplo.com", "password": SENHA + "-errada"}
    ).content.decode()
    assert "E-mail ou senha incorretos" in errada and 'class="alert alert-danger"' in errada


def test_aprovar_com_um_clique_na_lista(equipe_admin, pendente):
    """ "Aprovar" é a primeira coluna e aprova sem tela extra (datas sugeridas): loja, pagamento e plano."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    client, comercial = equipe_admin("Comercial")
    lista_url = reverse("admin:pagamentos_pedidoaguardando_changelist")
    rapido = reverse("admin:pagamentos_pedidoaguardando_aprovar_rapido", args=[fatura.pk])

    lista = client.get(lista_url).content.decode()
    assert f'formaction="{rapido}"' in lista and fatura.identificador_pix in lista

    resposta = client.post(rapido)

    assert resposta.status_code == 302 and resposta.url == lista_url
    pendente.refresh_from_db()
    assinatura = assinatura_de(pendente)
    assert pendente.status == Anunciante.Status.ATIVO and assinatura.situacao == "ativa"
    assert assinatura.inicio == timezone.localdate()
    assert Fatura.objects.get(pk=fatura.pk).confirmado_por == comercial


def test_sem_email_confirmado_nao_aprova_e_oferece_reenviar(equipe_admin, criar_anunciante):
    """Decisão do dono: a aprovação continua exigindo o e-mail confirmado; a linha oferece "Reenviar link"."""
    loja = criar_anunciante("semconfirmar@exemplo.com", "Loja X", status=Anunciante.Status.PENDENTE)
    Usuario.objects.filter(pk=loja.usuario_id).update(email_confirmado_em=None)
    fatura = services.fazer_pedido(loja, basico(), Periodicidade.MENSAL)
    client, _ = equipe_admin("Comercial")

    lista = client.get(reverse("admin:pagamentos_pedidoaguardando_changelist")).content.decode()
    assert "Aguardando o cliente confirmar o e-mail" in lista and "Reenviar link" in lista

    mail.outbox.clear()
    client.post(reverse("admin:pagamentos_pedidoaguardando_reenviar", args=[fatura.pk]))
    assert [m.subject for m in mail.outbox][0].startswith("Confirme seu e-mail")

    client.post(reverse("admin:pagamentos_pedidoaguardando_aprovar_rapido", args=[fatura.pk]))
    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.PENDENTE and assinatura_de(loja).situacao == "pendente"


def test_ficha_da_loja_mostra_o_pedido_com_aprovar(equipe_admin, pendente):
    """Na ficha da loja: plano, valor, identificador do Pix e o botão que aprova tudo e volta para a ficha."""
    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    client, _ = equipe_admin("Comercial")
    ficha = reverse("admin:anunciantes_anunciante_change", args=[pendente.pk])

    pagina = client.get(ficha).content.decode()
    assert "Pedido aguardando aprovação" in pagina and fatura.identificador_pix in pagina
    rapido = reverse("admin:pagamentos_pedidoaguardando_aprovar_rapido", args=[fatura.pk])
    assert f'formaction="{rapido}"' in pagina

    resposta = client.post(rapido, {"next": ficha})
    assert resposta.url == ficha and assinatura_de(pendente).situacao == "ativa"


def test_confirmar_pagamento_das_faturas_nao_aprova_cadastro_novo(equipe_admin, pendente):
    """A ação da lista de Faturas deixa de fora o pedido de cadastro novo e aponta para Cadastros
    aguardando."""
    from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME

    fatura = services.fazer_pedido(pendente, basico(), Periodicidade.MENSAL)
    client, _ = equipe_admin("Financeiro")

    resposta = client.post(
        reverse("admin:pagamentos_fatura_changelist"),
        {"action": "confirmar_pagamento_acao", ACTION_CHECKBOX_NAME: [fatura.pk]},
        follow=True,
    )

    assert "Cadastros aguardando" in resposta.content.decode()
    assert Fatura.objects.get(pk=fatura.pk).situacao == Fatura.Situacao.ABERTA
    pendente.refresh_from_db()
    assert pendente.status == Anunciante.Status.PENDENTE
