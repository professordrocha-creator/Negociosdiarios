"""Testes da LGPD (Sprint 7B, parte 1): documentos com versão e aceite (cadastro, versão nova no login e no
painel), aviso de rascunho só no admin, Encarregado, cookies (só essenciais, sem banner), "Baixar meus dados"
(senha de novo, JSON completo), "Excluir minha conta" (anonimização, fotos apagadas, faturas guardadas),
pedidos do titular com prazo, guarda fiscal e demonstração."""

import io
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from axes.models import AccessAttempt
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from anuncios.models import Anuncio, DetalheImovel, Foto
from contas.models import AceiteDocumento, Usuario
from core.services import configuracao
from pagamentos.models import Fatura
from pagamentos.services import enviar_comprovante, gerar_fatura
from planos.models import Assinatura
from planos.services import assinatura_de
from privacidade import services
from privacidade.models import DocumentoLegal, PedidoTitular

pytestmark = pytest.mark.django_db

NAVEGADOR = {"HTTP_USER_AGENT": "Mozilla/5.0"}


def png() -> bytes:
    """Imagem pequena para comprovante."""
    saida = io.BytesIO()
    Image.new("RGB", (200, 200), (1, 2, 3)).save(saida, format="PNG")
    return saida.getvalue()


def nova_versao(
    tipo: str = "termos", versao: str = "2026-11", vigencia: date | None = None
) -> DocumentoLegal:
    """Publica uma versão nova (em vigor hoje, salvo outra data)."""
    return DocumentoLegal.objects.create(
        tipo=tipo,
        versao=versao,
        vigencia=vigencia or timezone.localdate(),
        resumo="Nova regra de denúncias.\nPrazo de resposta explicado.",
        texto="## 1. Uso\nTexto novo do {site}.\n\n- item um\n- item dois",
        publicado=True,
    )


# --- Documentos legais e aceite -------------------------------------------------------------------


def test_versao_em_vigor_e_texto_em_blocos_escapados(client):
    """Vale a publicada com a vigência mais recente que já começou; o texto vira blocos (HTML escapado)."""
    nova_versao(versao="futura", vigencia=timezone.localdate() + timedelta(days=5))
    doc = nova_versao(versao="2026-11")
    DocumentoLegal.objects.filter(pk=doc.pk).update(texto="## Título\nOlá <script>alert(1)</script> {site}")

    assert services.documento_vigente("termos").versao == "2026-11"
    html = client.get(reverse("core:termos")).content.decode()
    assert "Versão 2026-11" in html and '<h2 id="titulo">Título</h2>' in html
    assert "&lt;script&gt;" in html and "<script>alert" not in html
    assert configuracao().nome in html


def test_aviso_de_rascunho_so_no_admin(client, entrar_no_admin):
    """O público não vê "revisão jurídica pendente"; o admin vê ao abrir o documento."""
    assert "revisão jurídica" not in client.get(reverse("core:termos")).content.decode()
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    doc = services.documento_vigente("termos")
    html = (
        entrar_no_admin(daniel)
        .get(reverse("admin:privacidade_documentolegal_change", args=[doc.pk]))
        .content.decode()
    )
    assert "revisão jurídica pendente" in html


def test_versao_em_vigor_nao_pode_ter_o_texto_mudado(entrar_no_admin):
    """Publicada e em vigor: texto travado no admin (é o que foi aceito)."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    doc = services.documento_vigente("privacidade")
    html = (
        entrar_no_admin(daniel)
        .get(reverse("admin:privacidade_documentolegal_change", args=[doc.pk]))
        .content.decode()
    )
    assert 'name="texto"' not in html and "Para mudar, adicione uma versão nova" in html


def test_cadastro_grava_aceite_das_versoes_em_vigor(criar_anunciante):
    """A fábrica (como o cadastro) registra usuário, documento, versão, data e hora; nada pendente."""
    anunciante = criar_anunciante("a@exemplo.com", "Loja A")
    aceites = set(
        AceiteDocumento.objects.filter(usuario=anunciante.usuario).values_list("documento", "versao")
    )

    assert aceites == {(d.tipo, d.versao) for d in services.documentos_vigentes()}
    assert services.pendencias_de_aceite(anunciante.usuario) == []


def test_versao_nova_pede_aceite_no_login_e_no_painel(client, loja):
    """Versão nova publicada: o login leva ao aceite (com o resumo); o painel também; aceitou, segue."""
    anunciante = loja()
    nova_versao()

    resposta = client.post(
        reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": SENHA}, **NAVEGADOR
    )
    assert resposta.status_code == 302 and resposta["Location"].startswith(reverse("privacidade:aceitar"))
    assert client.get(reverse("anunciantes:painel"))["Location"].startswith(reverse("privacidade:aceitar"))
    html = client.get(resposta["Location"]).content.decode()
    assert "Nova regra de denúncias." in html and "versão 2026-11" in html
    assert 'type="checkbox"' in html and "checked" not in html  # nada pré-marcado

    sem_marcar = client.post(reverse("privacidade:aceitar"), {"aceitar": "1"})
    assert sem_marcar.status_code == 200 and "é preciso aceitar" in sem_marcar.content.decode()
    client.post(
        reverse("privacidade:aceitar"),
        {"aceitar": "1", "aceito": "on", "next": reverse("anunciantes:painel")},
    )
    assert AceiteDocumento.objects.filter(usuario=anunciante.usuario, versao="2026-11").exists()
    assert client.get(reverse("anunciantes:painel")).status_code == 200


def test_recusar_versao_nova_sai_e_meus_dados_continua_acessivel(client, loja):
    """Sem aceitar, "Meus dados" ainda funciona (direitos do titular); recusar desloga."""
    anunciante = loja()
    nova_versao()
    client.force_login(anunciante.usuario)
    assert client.get(reverse("privacidade:meus_dados")).status_code == 200

    client.post(reverse("privacidade:aceitar"), {"recusar": "1"})
    assert "_auth_user_id" not in client.session


def test_aceite_nao_redireciona_para_outro_site(client, loja):
    """O `next` do aceite só vale para endereço deste site."""
    client.force_login(loja().usuario)
    nova_versao()
    resposta = client.post(
        reverse("privacidade:aceitar"), {"aceitar": "1", "aceito": "on", "next": "https://golpe.exemplo.com/"}
    )
    assert resposta["Location"] == reverse("anunciantes:painel")


# --- Encarregado e cookies -------------------------------------------------------------------------


def test_politica_tem_encarregado_da_configuracao(client):
    """Seção do Encarregado com nome e e-mail da Identidade do site e o prazo de resposta."""
    config = configuracao()
    config.encarregado_nome, config.email_privacidade = "Maria Encarregada", "dpo@exemplo.com"
    config.save()
    html = client.get(reverse("core:privacidade")).content.decode()
    assert 'id="encarregado"' in html and "Maria Encarregada" in html and "dpo@exemplo.com" in html
    assert "15 dias" in html


def test_cookies_so_essenciais_sem_banner_e_secao_na_politica(client):
    """Cookies só essenciais: sem banner; /cookies/ leva à seção da Política; o rodapé aponta para ela."""
    assert not services.precisa_aviso_de_cookies()
    destino = client.get(reverse("core:cookies"))["Location"]
    assert destino.endswith(reverse("core:privacidade") + "#cookies")
    html = client.get(reverse("core:privacidade")).content.decode()
    assert all(f"<code>{c.nome}</code>" in html for c in services.COOKIES)
    inicio = client.get(reverse("core:inicio")).content.decode()
    assert f'href="{reverse("core:privacidade")}#cookies"' in inicio
    assert "Aceitar cookies" not in inicio and "cookie-banner" not in inicio


def test_cookies_gravados_pelo_site_estao_todos_na_lista(client, loja):
    """Login, painel e um aviso: todo cookie que o site grava está documentado (e no docs/LGPD.md)."""
    anunciante = loja()
    gravados = set()
    respostas = [
        client.get(reverse("contas:entrar"), **NAVEGADOR),
        client.post(
            reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": SENHA}, **NAVEGADOR
        ),
        client.get(reverse("anunciantes:painel"), **NAVEGADOR),
        client.post(reverse("privacidade:baixar"), {"senha": "errada"}, **NAVEGADOR),
    ]
    for resposta in respostas:
        gravados |= set(resposta.cookies)
    documentados = {c.nome for c in services.COOKIES}
    assert gravados and gravados <= documentados, gravados - documentados
    lgpd = (Path(__file__).resolve().parents[2] / "docs" / "LGPD.md").read_text(encoding="utf-8")
    assert all(f"`{nome}`" in lgpd for nome in documentados)
    assert anunciante


# --- Baixar meus dados -----------------------------------------------------------------------------


def test_baixar_exige_senha_e_entrega_json_completo(client, loja, publicado):
    """Senha errada: 400 sem arquivo. Certa: JSON com conta, loja, anúncios, faturas e aceites; pedido
    registrado."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    gerar_fatura(assinatura_de(anunciante), avisar=False)
    client.force_login(anunciante.usuario)

    errado = client.post(reverse("privacidade:baixar"), {"senha": "errada"})
    assert errado.status_code == 400 and "Senha incorreta" in errado.content.decode()

    resposta = client.post(reverse("privacidade:baixar"), {"senha": SENHA})
    assert (
        resposta["Content-Type"].startswith("application/json")
        and "attachment" in resposta["Content-Disposition"]
    )
    assert resposta["Cache-Control"] == "private, no-store"
    dados = json.loads(resposta.content)
    assert (
        dados["conta"]["email"] == "loja@exemplo.com"
        and dados["loja"]["nome_publico"] == anunciante.nome_publico
    )
    assert (
        dados["anuncios"][0]["codigo"] == anuncio.codigo
        and "endereco_privado" in dados["anuncios"][0]["imovel"]
    )
    assert dados["faturas"] and dados["aceites"] and dados["assinatura"]["plano"] == "Básico"
    assert PedidoTitular.objects.get(usuario=anunciante.usuario).tipo == "exportacao"


def test_limite_de_tentativas_de_senha(client, loja):
    """Senha errada várias vezes na hora: bloqueia (429)."""
    client.force_login(loja().usuario)
    for _ in range(10):
        client.post(reverse("privacidade:baixar"), {"senha": "errada"})
    assert client.post(reverse("privacidade:baixar"), {"senha": SENHA}).status_code == 429


# --- Excluir minha conta ----------------------------------------------------------------------------


@pytest.fixture
def loja_completa(loja, publicado):
    """Loja com anúncio (foto, endereço, ponto), fatura em aberto com comprovante e tentativa de login."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    DetalheImovel.objects.filter(anuncio=anuncio).update(endereco="Rua das Flores, 10")
    imovel = DetalheImovel.objects.get(anuncio=anuncio)
    imovel.save()  # histórico com o endereço
    fatura = gerar_fatura(assinatura_de(anunciante), avisar=False)
    enviar_comprovante(fatura, SimpleUploadedFile("c.png", png(), "image/png"))
    AccessAttempt.objects.create(username="loja@exemplo.com", ip_address="10.0.0.1", failures_since_start=2)
    mail.outbox.clear()
    return anunciante, anuncio, Fatura.objects.get(pk=fatura.pk)


def test_excluir_avisa_fatura_em_aberto_e_exige_senha_e_palavra(client, loja_completa):
    """A tela avisa a fatura em aberto (não impede); sem senha certa ou sem EXCLUIR, nada acontece."""
    anunciante, _anuncio, fatura = loja_completa
    client.force_login(anunciante.usuario)
    html = client.get(reverse("privacidade:excluir")).content.decode()
    assert "fatura" in html and fatura.codigo in html

    assert (
        client.post(reverse("privacidade:excluir"), {"senha": SENHA, "confirmacao": "sim"}).status_code == 400
    )
    assert (
        client.post(reverse("privacidade:excluir"), {"senha": "x", "confirmacao": "EXCLUIR"}).status_code
        == 400
    )
    assert Usuario.objects.get(pk=anunciante.usuario_id).is_active


def test_excluir_anonimiza_remove_e_guarda_o_exigido(
    client, loja_completa, django_capture_on_commit_callbacks
):
    """Conta e loja anonimizadas, anúncios removidos e fotos apagadas, endereço apagado (também no
    histórico), assinatura cancelada, tentativas de login apagadas; faturas e comprovante guardados; e-mail
    ao endereço antigo."""
    anunciante, anuncio, fatura = loja_completa
    usuario = anunciante.usuario
    arquivos = [Path(f.imagem.path) for f in Foto.objects.filter(anuncio=anuncio)]
    client.force_login(usuario)

    with django_capture_on_commit_callbacks(execute=True):  # o e-mail sai depois de gravar
        resposta = client.post(reverse("privacidade:excluir"), {"senha": SENHA, "confirmacao": "excluir"})

    assert resposta.status_code == 302 and "_auth_user_id" not in client.session
    usuario.refresh_from_db()
    assert usuario.email == f"removido-{usuario.pk}@anonimo.invalid" and usuario.nome == "Conta removida"
    assert not usuario.is_active and not usuario.has_usable_password()
    loja = Anunciante.objects.get(pk=anunciante.pk)
    assert loja.status == "encerrado" and loja.whatsapp == "" and loja.slug == f"loja-removida-{loja.pk}"
    assert (
        not Anunciante.history.filter(id=loja.pk, whatsapp=anunciante.whatsapp).exclude(whatsapp="").exists()
    )
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.REMOVIDO and not anuncio.fotos.exists()
    assert arquivos and not any(caminho.exists() for caminho in arquivos)
    assert DetalheImovel.objects.get(anuncio=anuncio).endereco == ""
    assert not DetalheImovel.history.filter(anuncio_id=anuncio.pk).exclude(endereco="").exists()
    assert assinatura_de(loja).situacao == Assinatura.Situacao.CANCELADA
    assert not AccessAttempt.objects.filter(username="loja@exemplo.com").exists()
    fatura.refresh_from_db()
    assert fatura.situacao == "aguardando_confirmacao" and Path(fatura.comprovante.path).exists()
    assert fatura.cliente_nome == f"Loja removida {loja.pk}"
    (email,) = mail.outbox
    assert email.to == ["loja@exemplo.com"] and "5 anos" in email.body
    assert PedidoTitular.objects.get(tipo="exclusao").situacao == "atendido"
    assert client.get(reverse("anunciantes:loja", args=[anunciante.slug])).status_code == 404
    client.post(reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": SENHA}, **NAVEGADOR)
    assert "_auth_user_id" not in client.session  # o e-mail antigo não entra mais


# --- Pedidos do titular e guarda fiscal ----------------------------------------------------------------


def test_pedido_por_email_tem_prazo_de_15_dias_e_aparece_atrasado(entrar_no_admin):
    """Prazo = recebido + 15 dias (configurável); vencido em aberto aparece no admin; Moderador não vê."""
    pedido = PedidoTitular.objects.create(
        contato="pessoa@exemplo.com", tipo="acesso", recebido_em=timezone.now() - timedelta(days=20)
    )
    assert pedido.prazo == timezone.localdate() - timedelta(days=5) and pedido.atrasado()

    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    html = entrar_no_admin(daniel).get(reverse("admin:privacidade_pedidotitular_changelist")).content.decode()
    assert "pessoa@exemplo.com" in html and "icon-yes.svg" in html
    moderador = Usuario.objects.create_user(
        email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True
    )
    moderador.groups.add(Group.objects.get(name="Moderador"))
    assert (
        entrar_no_admin(moderador).get(reverse("admin:privacidade_pedidotitular_changelist")).status_code
        == 403
    )


def test_responder_pedido_exige_o_que_foi_feito():
    """Atender pede a resposta (fica no registro)."""
    pedido = PedidoTitular.objects.create(contato="p@exemplo.com", tipo="correcao")
    with pytest.raises(ValueError):
        services.responder_pedido(pedido, None, " ")
    assert services.responder_pedido(pedido, None, "Nome corrigido.").situacao == "atendido"


def test_guarda_fiscal_apaga_comprovante_antigo(loja):
    """Fatura paga há mais que a guarda (5 anos): comprovante e anotações apagados; recente fica."""
    from pagamentos.services import confirmar_pagamento

    anunciante = loja()
    fatura = gerar_fatura(assinatura_de(anunciante), avisar=False)
    fatura = enviar_comprovante(fatura, SimpleUploadedFile("c.png", png(), "image/png"), "recado com nome")
    confirmar_pagamento(fatura, None)
    caminho = Path(Fatura.objects.get(pk=fatura.pk).comprovante.path)

    assert services.limpar_dados_vencidos() == 0 and caminho.exists()
    assert services.limpar_dados_vencidos(fatura.vencimento + timedelta(days=366 * 5)) == 1
    fatura.refresh_from_db()
    assert not caminho.exists() and not fatura.comprovante and fatura.observacao == ""


def test_pedido_demo():
    """Um pedido fictício em aberto, marcado como demo; apagar limpa."""
    pedido = services.criar_pedido_demo()
    assert pedido.demo and pedido.em_aberto and PedidoTitular.objects.count() == 1
    services.apagar_pedidos_demo()
    assert not PedidoTitular.objects.exists()
