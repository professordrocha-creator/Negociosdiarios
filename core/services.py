"""Regras e verificações do app core."""

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.gis.geos import Point
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.db import DatabaseError, connection, transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.text import slugify

from core.models import Cidade, Estado

logger = logging.getLogger(__name__)

DIR_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO_ESTADOS = DIR_DADOS / "estados.csv"
ARQUIVO_MUNICIPIOS = DIR_DADOS / "municipios.csv"


def banco_disponivel() -> bool:
    """Testa a conexão com o banco executando um `SELECT 1`.

    Retorna False (sem lançar exceção) se o banco não responder, e registra
    no log só o tipo do erro, sem a mensagem, que pode conter host e usuário.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as erro:
        logger.error("Banco indisponível na verificação de saúde: %s", type(erro).__name__)
        return False
    return True


@dataclass(frozen=True)
class ResultadoCarga:
    """Resumo de uma execução de `carregar_municipios`."""

    estados_novos: int
    estados_total: int
    cidades_novas: int
    cidades_total: int


def _ler_csv(caminho: Path, colunas: set[str]) -> list[dict[str, str]]:
    """Lê um CSV UTF-8 e confere se as colunas obrigatórias existem."""
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = colunas - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"{caminho.name}: faltam as colunas {sorted(faltando)}.")
        return list(leitor)


@transaction.atomic
def carregar_municipios(
    arquivo_estados: Path = ARQUIVO_ESTADOS,
    arquivo_municipios: Path = ARQUIVO_MUNICIPIOS,
    uf_liberada: str = "MT",
) -> ResultadoCarga:
    """Carrega (ou atualiza) estados e cidades a partir dos CSVs de `core/dados/`.

    Idempotente: pode rodar quantas vezes quiser. Registros existentes têm só
    os dados do IBGE atualizados (nome, slug, UF, ponto); `liberado` e
    `liberada` **nunca** são alterados, para não desfazer o que o admin liberou.
    Na primeira carga, só o estado `uf_liberada` nasce liberado e nenhuma
    cidade. Tudo roda numa transação: se uma linha estiver errada, nada é gravado.
    """
    uf_liberada = uf_liberada.upper()

    linhas_estados = _ler_csv(arquivo_estados, {"uf", "nome"})
    ufs_no_arquivo = {linha["uf"].strip().upper() for linha in linhas_estados}
    if uf_liberada not in ufs_no_arquivo:
        raise ValueError(f"UF '{uf_liberada}' não existe em {arquivo_estados.name}.")

    ufs_existentes = set(Estado.objects.values_list("uf", flat=True))
    estados = [
        Estado(
            uf=linha["uf"].strip().upper(),
            nome=linha["nome"].strip(),
            liberado=linha["uf"].strip().upper() == uf_liberada,  # só vale para estado novo
        )
        for linha in linhas_estados
    ]
    Estado.objects.bulk_create(estados, update_conflicts=True, unique_fields=["uf"], update_fields=["nome"])

    linhas_cidades = _ler_csv(arquivo_municipios, {"codigo_ibge", "nome", "uf", "latitude", "longitude"})
    codigos_existentes = set(Cidade.objects.values_list("codigo_ibge", flat=True))
    cidades = []
    for numero, linha in enumerate(linhas_cidades, start=2):  # linha 1 é o cabeçalho
        try:
            uf = linha["uf"].strip().upper()
            if uf not in ufs_no_arquivo:
                raise ValueError(f"UF '{uf}' desconhecida")
            nome = linha["nome"].strip()
            cidades.append(
                Cidade(
                    codigo_ibge=int(linha["codigo_ibge"]),
                    nome=nome,
                    slug=slugify(nome),
                    uf_id=uf,
                    ponto=Point(float(linha["longitude"]), float(linha["latitude"]), srid=4326),
                )
            )
        except (ValueError, TypeError) as erro:
            raise ValueError(f"{arquivo_municipios.name}, linha {numero}: {erro}") from erro

    Cidade.objects.bulk_create(
        cidades,
        update_conflicts=True,
        unique_fields=["codigo_ibge"],
        update_fields=["nome", "slug", "uf", "ponto"],
        batch_size=1000,
    )

    return ResultadoCarga(
        estados_novos=len(ufs_no_arquivo - ufs_existentes),
        estados_total=Estado.objects.count(),
        cidades_novas=len({c.codigo_ibge for c in cidades} - codigos_existentes),
        cidades_total=Cidade.objects.count(),
    )


def liberar_cidades(cidades: QuerySet[Cidade]) -> int:
    """Marca as cidades como liberadas e devolve quantas mudaram de situação.

    Cidades já liberadas são ignoradas na contagem. A cidade só aparece no site
    se o estado dela também estiver liberado (docs/ARQUITETURA.md §9).
    """
    # Quando existir o cache da lista de cidades liberadas (Redis), limpar aqui.
    return cidades.filter(liberada=False).update(liberada=True)


@dataclass(frozen=True)
class EstadoAtendido:
    """Um estado liberado e as suas cidades liberadas, para exibir no site."""

    estado: Estado
    cidades: list[Cidade]


def cidades_atendidas() -> list[EstadoAtendido]:
    """Lista as cidades que aparecem no site, agrupadas por estado.

    Regra (docs/ARQUITETURA.md §9): só cidades `liberada=True` de estados
    `liberado=True`. Estados sem nenhuma cidade liberada ficam de fora.
    Ordem: estados por nome, cidades por nome. Uma consulta só.
    """
    # Quando existir o cache (Redis), guardar este resultado e limpar ao liberar/bloquear.
    cidades = (
        Cidade.objects.filter(liberada=True, uf__liberado=True)
        .select_related("uf")
        .order_by("uf__nome", "nome")
    )
    grupos: dict[str, EstadoAtendido] = {}
    for cidade in cidades:
        if cidade.uf_id not in grupos:
            grupos[cidade.uf_id] = EstadoAtendido(estado=cidade.uf, cidades=[])
        grupos[cidade.uf_id].cidades.append(cidade)
    return list(grupos.values())


def mostrar_link_admin(usuario: AbstractBaseUser | AnonymousUser | None, debug: bool) -> bool:
    """Diz se o rodapé mostra o atalho para o admin.

    O endereço do admin é secreto (ADMIN_URL): publicá-lo para todos entregaria o
    alvo a robôs. Por isso o link só sai no HTML em dev (DEBUG ligado, no PC do
    desenvolvedor) ou para quem já é da equipe e está logado. Visitantes em
    produção nunca recebem o endereço.
    """
    return debug or bool(getattr(usuario, "is_staff", False))


# --- E-mail pela fila do Celery ---------------------------------------------------------


def email_para_fila(mensagem: EmailMessage) -> dict:
    """Transforma um e-mail do Django em dados simples (JSON) para viajar pela fila do Celery.

    Anexos ainda não são aceitos: nenhum e-mail do sistema usa e eles pesariam na
    fila (quando precisar, guardar o arquivo no storage e mandar só o caminho).
    """
    if mensagem.attachments:
        raise ValueError("E-mail com anexo ainda não é suportado pela fila (core.services.email_para_fila).")
    return {
        "subject": str(mensagem.subject),
        "body": str(mensagem.body),
        "from_email": mensagem.from_email,
        "to": list(mensagem.to),
        "cc": list(mensagem.cc),
        "bcc": list(mensagem.bcc),
        "reply_to": list(mensagem.reply_to),
        "headers": dict(mensagem.extra_headers),
        "alternatives": [[str(conteudo), tipo] for conteudo, tipo in getattr(mensagem, "alternatives", [])],
        "content_subtype": mensagem.content_subtype,
    }


def enviar_email_agora(dados: dict) -> int:
    """Envia de verdade (SMTP em produção, Mailpit em dev) um e-mail vindo da fila.

    Usa `EMAIL_BACKEND_REAL`; só o worker do Celery chama isto. Devolve quantos
    e-mails saíram (0 ou 1). Erros de SMTP sobem para a tarefa tentar de novo.
    """
    mensagem = EmailMultiAlternatives(
        subject=dados["subject"],
        body=dados["body"],
        from_email=dados["from_email"],
        to=dados["to"],
        cc=dados["cc"],
        bcc=dados["bcc"],
        reply_to=dados["reply_to"],
        headers=dados["headers"],
        alternatives=[tuple(alternativa) for alternativa in dados["alternatives"]],
        connection=get_connection(settings.EMAIL_BACKEND_REAL),
    )
    mensagem.content_subtype = dados["content_subtype"]
    return mensagem.send()


# --- Dados de demonstração (regra do CLAUDE.md) -------------------------------------------

ARQUIVO_DEMO = DIR_DADOS / "demo.json"

# Quantidades da home. Viram campos de Configuracao (editáveis no admin) na Sprint 1.
LIMITE_DESTAQUES = 4
LIMITE_RECEM_ANUNCIADOS = 8
MAX_POR_LOJA_RECEM = 2  # rodízio justo: nenhuma loja grande ocupa a home (ARQUITETURA §9)
LIMITE_LOJAS_HOME = 6

ROTULOS_TIPO_LOJA = {
    "corretor_autonomo": "Corretor",
    "imobiliaria": "Imobiliária",
    "revenda": "Revenda",
    "concessionaria": "Concessionária",
    "garagem": "Garagem",
}


@dataclass(frozen=True)
class LojaVitrine:
    """Loja como aparece na home (mini-vitrine). Hoje vem do demo.json; na Sprint 2, do banco."""

    slug: str
    nome: str
    tipo: str
    sigla: str
    cor: int
    cidade: str
    total_anuncios: int
    url: str | None = None  # None = página ainda não existe ("em breve")

    @property
    def tipo_rotulo(self) -> str:
        """Ex.: "Revenda", "Corretor"."""
        return ROTULOS_TIPO_LOJA.get(self.tipo, self.tipo)


@dataclass(frozen=True)
class AnuncioVitrine:
    """Anúncio como aparece num card. Hoje vem do demo.json; na Sprint 3, do banco."""

    titulo: str
    categoria: str  # "imovel" ou "veiculo"
    finalidade: str  # "venda" ou "aluguel"
    tipo: str
    preco: Decimal
    cidade: str
    bairro: str
    resumo: str
    loja_nome: str
    loja_slug: str
    destaque: bool
    fotos: int
    estilo_foto: str
    publicado_em: datetime
    url: str | None = None  # None = página do anúncio ainda não existe ("em breve")

    @property
    def local(self) -> str:
        """Ex.: "Tangará da Serra · Jardim Europa" (veículos: só a cidade)."""
        return f"{self.cidade} · {self.bairro}" if self.bairro else self.cidade

    @property
    def aluguel(self) -> bool:
        """Preço mensal (mostra "/mês" e o selo "Aluguel")."""
        return self.finalidade == "aluguel"

    @property
    def icone(self) -> str:
        """Ícone da foto de exemplo."""
        return "carro" if self.categoria == "veiculo" else "casa"


def ler_demo(arquivo: Path = ARQUIVO_DEMO) -> dict:
    """Lê core/dados/demo.json (fonte única dos dados fictícios)."""
    with open(arquivo, encoding="utf-8") as fp:
        return json.load(fp)


def _resumo(categoria: str, detalhes: dict) -> str:
    """Linha de ficha do card. Ex.: "3 qts · 2 banh · 2 vagas · 180 m²" ou "2019 · 98.000 km · automático"."""
    if categoria == "veiculo":
        km = f"{detalhes['km']:,}".replace(",", ".")
        return f"{detalhes['ano']} · {km} km · {detalhes['cambio']}"
    partes = []
    for chave, sufixo in (("quartos", "qts"), ("banheiros", "banh"), ("vagas", "vagas")):
        if detalhes.get(chave):
            partes.append(f"{detalhes[chave]} {sufixo}")
    area = detalhes.get("area_m2")
    if area:
        partes.append(f"{area / 10000:g} ha".replace(".", ",") if area >= 10000 else f"{area} m²")
    return " · ".join(partes)


def _vitrine_demo() -> tuple[list[AnuncioVitrine], list[LojaVitrine]]:
    """Anúncios e lojas do demo.json que podem aparecer: só com MOSTRAR_DEMO e só em cidades liberadas.

    Respeitar as cidades liberadas deixa a demonstração fiel ao site de verdade: cidade
    desligada no admin some da home, com ou sem dados fictícios.
    """
    if not settings.MOSTRAR_DEMO:
        return [], []
    dados = ler_demo()
    codigos = {a["cidade_ibge"] for a in dados["anuncios"]} | {loja["cidade_ibge"] for loja in dados["lojas"]}
    cidades = {
        c.codigo_ibge: c.nome
        for c in Cidade.objects.filter(codigo_ibge__in=codigos, liberada=True, uf__liberado=True)
    }
    lojas = {loja["slug"]: loja for loja in dados["lojas"]}
    agora = timezone.now()
    anuncios = [
        AnuncioVitrine(
            titulo=a["titulo"],
            categoria=a["categoria"],
            finalidade=a["finalidade"],
            tipo=a["tipo"],
            preco=Decimal(a["preco"]),
            cidade=cidades[a["cidade_ibge"]],
            bairro=a["bairro"],
            resumo=_resumo(a["categoria"], a["detalhes"]),
            loja_nome=lojas[a["loja"]]["nome"],
            loja_slug=a["loja"],
            destaque=a["destaque"],
            fotos=a["fotos"],
            estilo_foto=a["estilo_foto"],
            publicado_em=agora - timedelta(hours=a["publicado_ha_horas"]),
        )
        for a in dados["anuncios"]
        if a["cidade_ibge"] in cidades
    ]
    contagem = Counter(a.loja_slug for a in anuncios)
    vitrine_lojas = [
        LojaVitrine(
            slug=loja["slug"],
            nome=loja["nome"],
            tipo=loja["tipo"],
            sigla=loja["sigla"],
            cor=loja["cor"],
            cidade=cidades[loja["cidade_ibge"]],
            total_anuncios=contagem[loja["slug"]],
        )
        for loja in dados["lojas"]
        if loja["cidade_ibge"] in cidades
    ]
    return anuncios, vitrine_lojas


def destaques(limite: int = LIMITE_DESTAQUES) -> list[AnuncioVitrine]:
    """Anúncios em destaque (pagos, selo "Patrocinado"), mais novos primeiro."""
    anuncios, _ = _vitrine_demo()
    escolhidos = sorted((a for a in anuncios if a.destaque), key=lambda a: a.publicado_em, reverse=True)
    return escolhidos[:limite]


def recem_anunciados(
    limite: int = LIMITE_RECEM_ANUNCIADOS, por_loja: int = MAX_POR_LOJA_RECEM
) -> list[AnuncioVitrine]:
    """Anúncios de todas as lojas, mais novos primeiro, no máximo `por_loja` de cada (ARQUITETURA §9)."""
    anuncios, _ = _vitrine_demo()
    usados: Counter[str] = Counter()
    resultado = []
    for anuncio in sorted(anuncios, key=lambda a: a.publicado_em, reverse=True):
        if usados[anuncio.loja_slug] >= por_loja:
            continue
        usados[anuncio.loja_slug] += 1
        resultado.append(anuncio)
        if len(resultado) == limite:
            break
    return resultado


def lojas_verificadas(limite: int = LIMITE_LOJAS_HOME) -> list[LojaVitrine]:
    """Lojas verificadas com anúncios no ar, as com mais anúncios primeiro."""
    _, lojas = _vitrine_demo()
    com_anuncio = [loja for loja in lojas if loja.total_anuncios]
    return sorted(com_anuncio, key=lambda loja: (-loja.total_anuncios, loja.nome))[:limite]


@dataclass(frozen=True)
class ResumoDemo:
    """O que o criar/apagar_dados_demo fez, para o comando mostrar."""

    usuarios: int
    cidades: int


def criar_dados_demo(senha: str, arquivo: Path = ARQUIVO_DEMO) -> ResumoDemo:
    """Cria (ou atualiza) os dados de demonstração do que já existe no sistema. Idempotente.

    Hoje: usuários de equipe demo (um por grupo, senha = DEMO_SENHA) e as cidades do
    demo.json liberadas (marcadas com `liberada_pela_demo`, para o apagar desfazer só
    essas). Lojas e anúncios entram no banco nas Sprints 1 a 3; até lá a home os lê do
    mesmo demo.json. Recusa sem DEBUG, sem senha, ou se um e-mail demo já for de
    uma conta real (nunca sobrescreve conta de verdade).
    """
    if not settings.DEBUG:
        raise PermissionError("Dados de demonstração só com DEBUG=True (nunca em produção).")
    if not senha:
        raise ValueError("Defina DEMO_SENHA no .env (senha dos usuários de demonstração).")
    dados = ler_demo(arquivo)
    Usuario = get_user_model()
    emails = [pessoa["email"] for pessoa in dados["equipe"]]
    reais = list(Usuario.objects.filter(email__in=emails, demo=False).values_list("email", flat=True))
    if reais:
        raise ValueError(f"E-mail de demonstração já usado por conta real: {', '.join(reais)}.")

    with transaction.atomic():
        for pessoa in dados["equipe"]:
            usuario, _ = Usuario.objects.get_or_create(
                email=pessoa["email"], defaults={"nome": pessoa["nome"], "demo": True}
            )
            usuario.nome = pessoa["nome"]
            usuario.demo = True
            usuario.is_staff = True
            usuario.is_active = True
            usuario.set_password(senha)
            usuario.save()
            usuario.groups.set([Group.objects.get(name=pessoa["grupo"])])
        liberadas = Cidade.objects.filter(codigo_ibge__in=dados["cidades"], liberada=False).update(
            liberada=True, liberada_pela_demo=True
        )
    return ResumoDemo(usuarios=len(dados["equipe"]), cidades=liberadas)


def apagar_dados_demo() -> ResumoDemo:
    """Remove de uma vez tudo o que é demonstração (exceção à regra "nada é apagado de verdade").

    Apaga os registros com `demo=True` e desliga só as cidades que a demonstração
    ligou (as liberadas à mão continuam). Roda em qualquer ambiente: é o que limpa a
    base antes do lançamento (Sprint 9).
    """
    Usuario = get_user_model()
    with transaction.atomic():
        usuarios = Usuario.objects.filter(demo=True).count()
        Usuario.objects.filter(demo=True).delete()
        cidades = Cidade.objects.filter(liberada_pela_demo=True).update(
            liberada=False, liberada_pela_demo=False
        )
    return ResumoDemo(usuarios=usuarios, cidades=cidades)
