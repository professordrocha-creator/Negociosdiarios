"""Regras do app anunciantes: acesso ao painel, aprovação/suspensão e dados de demonstração."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db import transaction

from anunciantes.models import Anunciante
from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from core.models import Cidade
from core.services import AnuncioVitrine, PlanoVitrine, anuncios_demo_da_loja, planos

if TYPE_CHECKING:
    from contas.models import Usuario

# Mensagens mostradas no login e no painel para quem não pode entrar (dizem o que fazer).
MENSAGENS_SEM_ACESSO = {
    "equipe": "Esta é uma conta da equipe do site. Use o painel administrativo.",
    "sem_loja": "Esta conta não tem loja cadastrada. Para anunciar, veja os planos e fale com a gente.",
    Anunciante.Status.PENDENTE: "Seu cadastro está em análise. Avisaremos por e-mail quando for aprovado.",
    Anunciante.Status.SUSPENSO: "Sua loja está suspensa. Fale com a gente para entender o motivo.",
}


def motivo_sem_painel(usuario: AbstractBaseUser | AnonymousUser) -> str | None:
    """Diz por que o usuário NÃO pode usar o painel do anunciante, ou None se pode.

    Regras: equipe (staff) nunca usa o painel do cliente (tem o admin); é preciso ter
    loja (Anunciante) e ela estar `ativo`. Devolve a chave de MENSAGENS_SEM_ACESSO.
    """
    if not usuario.is_authenticated:
        return "anonimo"
    if usuario.is_staff:
        return "equipe"
    anunciante = Anunciante.objects.filter(usuario=usuario).first()
    if anunciante is None:
        return "sem_loja"
    if anunciante.status != Anunciante.Status.ATIVO:
        return anunciante.status
    return None


def _mudar_status(anunciante: Anunciante, status: str, por: Usuario | None, motivo: str) -> Anunciante:
    """Troca o status, guarda o motivo e registra no histórico quem mudou e por quê."""
    anunciante.status = status
    anunciante.motivo_status = motivo
    anunciante._history_user = por  # simple_history: autor da mudança
    anunciante._change_reason = motivo[:100]  # aparece na lista de histórico do admin
    anunciante.save(update_fields=["status", "motivo_status", "atualizado_em"])
    return anunciante


def aprovar(anunciante: Anunciante, por: Usuario | None, motivo: str = "") -> Anunciante:
    """Aprova o anunciante (CRECI/CNPJ conferido): ele passa a entrar no painel e aparecer no site."""
    return _mudar_status(anunciante, Anunciante.Status.ATIVO, por, motivo.strip() or "Documento conferido.")


def suspender(anunciante: Anunciante, por: Usuario | None, motivo: str) -> Anunciante:
    """Suspende o anunciante. O motivo é obrigatório (fica no cadastro e no histórico)."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da suspensão.")
    return _mudar_status(anunciante, Anunciante.Status.SUSPENSO, por, motivo.strip())


def anuncios_da_loja(anunciante: Anunciante) -> list[AnuncioVitrine]:
    """Anúncios do anunciante para o painel.

    Por enquanto só lojas de demonstração têm anúncios (do demo.json, pelo slug da
    loja). A checagem `demo` impede que uma loja real com o mesmo endereço veja
    anúncios fictícios. Na Sprint 3 passa a ler do banco, sempre filtrando pelo dono.
    """
    return anuncios_demo_da_loja(anunciante.slug) if anunciante.demo else []


def plano_de_exemplo() -> PlanoVitrine:
    """Plano mostrado no resumo do painel até existir assinatura (Sprint 2): o Profissional."""
    lista = planos()
    return next((p for p in lista if p.slug == "profissional"), lista[0])


# --- Dados de demonstração (chamados pelo core.services.criar/apagar_dados_demo) ---------


def criar_anunciantes_demo(lojas: list[dict], senha: str) -> int:
    """Cria (ou atualiza) as lojas do demo.json, cada uma com login próprio. Idempotente.

    Cada loja vira um Usuario (e-mail da loja, senha = DEMO_SENHA, nunca equipe) e um
    Anunciante `ativo`, ambos com `demo=True`. Recusa se e-mail, endereço da loja ou
    documento já pertencerem a dados reais (nunca sobrescreve conta de verdade).
    Chame dentro de uma transação; as cidades das lojas já devem estar liberadas.
    """
    Usuario = get_user_model()
    emails = [loja["email"] for loja in lojas]
    conflitos = list(Usuario.objects.filter(email__in=emails, demo=False).values_list("email", flat=True))
    conflitos += list(
        Anunciante.objects.filter(slug__in=[loja["slug"] for loja in lojas], demo=False).values_list(
            "slug", flat=True
        )
    )
    if conflitos:
        raise ValueError(f"Dados de demonstração colidem com dados reais: {', '.join(conflitos)}.")

    cidades = {
        c.codigo_ibge: c
        for c in Cidade.objects.filter(codigo_ibge__in={loja["cidade_ibge"] for loja in lojas})
    }
    for loja in lojas:
        usuario, _ = Usuario.objects.get_or_create(
            email=loja["email"], defaults={"nome": loja["responsavel"]}
        )
        usuario.nome = loja["responsavel"]
        usuario.demo = True
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.is_active = True
        usuario.set_password(senha)
        usuario.save()

        cidade = cidades[loja["cidade_ibge"]]
        if loja["tipo"] == Anunciante.Tipo.CORRETOR_AUTONOMO:
            documento = (Anunciante.DocumentoTipo.CRECI, normalizar_creci(loja["creci"], cidade.uf_id))
        else:
            documento = (Anunciante.DocumentoTipo.CNPJ, normalizar_cnpj(loja["cnpj"]))
        Anunciante.objects.update_or_create(
            slug=loja["slug"],
            defaults={
                "usuario": usuario,
                "tipo": loja["tipo"],
                "nome_publico": loja["nome"],
                "sigla": loja["sigla"],
                "cor": loja["cor"],
                "documento_tipo": documento[0],
                "documento_numero": documento[1],
                "whatsapp": normalizar_whatsapp(loja["whatsapp"]),
                "email_publico": loja["email"],
                "cidade": cidade,
                "status": Anunciante.Status.ATIVO,
                "motivo_status": "Loja de demonstração.",
                "demo": True,
            },
        )
    return len(lojas)


def apagar_anunciantes_demo() -> int:
    """Apaga os anunciantes de demonstração e o histórico deles. Devolve quantos eram.

    Os usuários (logins) demo são apagados depois, pelo core, com os demais `demo=True`.
    """
    with transaction.atomic():
        quantos = Anunciante.objects.filter(demo=True).count()
        Anunciante.objects.filter(demo=True).delete()
        Anunciante.history.filter(demo=True).delete()
    return quantos
