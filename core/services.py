"""Regras e verificações do app core."""

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection, send_mail
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.text import slugify

from core import imagens
from core.models import (
    CHAVE_CACHE_AJUDA,
    CHAVE_CACHE_CONFIGURACAO,
    Bairro,
    Cidade,
    Configuracao,
    Estado,
    Regiao,
    TextoAjuda,
)

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
    logo: str = ""  # URL do logo 96 px; vazio = monograma

    @property
    def tipo_rotulo(self) -> str:
        """Ex.: "Revenda", "Corretor"."""
        return ROTULOS_TIPO_LOJA.get(self.tipo, self.tipo)


@dataclass(frozen=True)
class AnuncioVitrine:
    """Anúncio como aparece num card (montado do banco por `anuncios.services.para_vitrine`)."""

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
    capa: str = ""  # miniatura da primeira foto (vazia: o card mostra o desenho de exemplo)

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


def destaques(limite: int = LIMITE_DESTAQUES) -> list[AnuncioVitrine]:
    """Anúncios em destaque (pagos, selo "Destaque"), mais novos primeiro. Só os visíveis ao público."""
    from anuncios.services import anuncios_visiveis, para_vitrine  # o core é a base: import local

    escolhidos = anuncios_visiveis().filter(destaque_ate__gt=timezone.now()).order_by("-publicado_em")
    return [para_vitrine(anuncio) for anuncio in escolhidos[:limite]]


def recem_anunciados(
    limite: int = LIMITE_RECEM_ANUNCIADOS, por_loja: int = MAX_POR_LOJA_RECEM
) -> list[AnuncioVitrine]:
    """Anúncios de todas as lojas, mais novos primeiro, no máximo `por_loja` de cada (ARQUITETURA §9).

    Só os visíveis ao público. Olha no máximo os 200 mais novos (a home não precisa de mais).
    """
    from anuncios.services import anuncios_visiveis, para_vitrine

    usados: Counter[int] = Counter()
    resultado = []
    for anuncio in anuncios_visiveis().order_by("-publicado_em")[:200]:
        if usados[anuncio.anunciante_id] >= por_loja:
            continue
        usados[anuncio.anunciante_id] += 1
        resultado.append(para_vitrine(anuncio))
        if len(resultado) == limite:
            break
    return resultado


@dataclass(frozen=True)
class ResumoDemo:
    """O que o criar/apagar_dados_demo fez, para o comando mostrar."""

    usuarios: int
    cidades: int
    anunciantes: int = 0
    anuncios: int = 0


def criar_dados_demo(senha: str, arquivo: Path = ARQUIVO_DEMO) -> ResumoDemo:
    """Cria (ou atualiza) os dados de demonstração do que já existe no sistema. Idempotente.

    Hoje: usuários de equipe demo (um por grupo, senha = DEMO_SENHA), as cidades do
    demo.json liberadas (marcadas com `liberada_pela_demo`, para o apagar desfazer só
    essas), as 6 lojas como anunciantes ativos com login próprio e uma assinatura
    para cada loja ativa (planos diferentes; as de `assinaturas_em_atraso` já em atraso).
    Guia de Negócios (G1): 10 perfis fictícios com as categorias do CSV.
    Os imóveis viram anúncios publicados no banco (`anuncios.demo`), com fotos de exemplo. Faturas
    (Sprint 6): histórico pago, uma aberta, uma aguardando confirmação e as das lojas em atraso vencidas.
    Recusa fora de dev (DEBUG) e do servidor de teste (DEMO_NO_SERVIDOR, que exige SITE_NOINDEX), sem senha,
    ou se um e-mail demo já for de uma conta real (nunca sobrescreve conta de verdade).
    """
    if not (settings.DEBUG or settings.DEMO_NO_SERVIDOR):
        raise PermissionError(
            "Dados de demonstração só em dev (DEBUG=True) ou no servidor de teste (DEMO_NO_SERVIDOR=True)."
        )
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
        # Import aqui: o core é a base dos apps; cada app cuida dos próprios dados demo.
        from anunciantes.services import criar_anunciantes_demo

        for regiao in dados.get("regioes", []):
            obj, _ = Regiao.objects.update_or_create(
                slug=regiao["slug"], defaults={"nome": regiao["nome"], "demo": True}
            )
            obj.cidades.set(Cidade.objects.filter(codigo_ibge__in=regiao["cidades"]))
        for codigo, nomes in dados.get("bairros", {}).items():
            cidade = Cidade.objects.get(codigo_ibge=int(codigo))
            for nome in nomes:
                Bairro.objects.update_or_create(
                    cidade=cidade, slug=slugify(nome), defaults={"nome": nome, "ativo": True, "demo": True}
                )
        lojas = criar_anunciantes_demo(dados["lojas"] + dados.get("lojas_pendentes", []), senha)
        from planos.services import criar_assinaturas_demo

        criar_assinaturas_demo(dados.get("assinaturas_em_atraso", []))
        from pagamentos.services import criar_faturas_demo

        criar_faturas_demo(dados.get("assinaturas_em_atraso", []))
        from publicidade.services import criar_publicidade_demo

        criar_publicidade_demo()
        from privacidade.services import criar_pedido_demo

        criar_pedido_demo()
        from moderacao.services import apagar_denuncias_demo, criar_denuncias_demo

        apagar_denuncias_demo()  # a denúncia protege o anúncio: sai antes de recriar os anúncios demo
        from anuncios.demo import criar_anuncios_demo

        anuncios = criar_anuncios_demo(dados["anuncios"])
        criar_denuncias_demo()
        from guia.services import criar_guia_demo

        criar_guia_demo()  # Guia de Negócios (G1): 12 categorias usadas e 10 perfis fictícios
    return ResumoDemo(
        usuarios=len(dados["equipe"]) + lojas, cidades=liberadas, anunciantes=lojas, anuncios=anuncios
    )


def apagar_dados_demo() -> ResumoDemo:
    """Remove de uma vez tudo o que é demonstração (exceção à regra "nada é apagado de verdade").

    Apaga os registros com `demo=True` e desliga só as cidades que a demonstração
    ligou (as liberadas à mão continuam). Roda em qualquer ambiente: é o que limpa a
    base antes do lançamento (Sprint 9).
    """
    from anunciantes.services import apagar_anunciantes_demo  # ver criar_dados_demo
    from anuncios.services import apagar_anuncios_demo
    from guia.services import apagar_guia_demo
    from moderacao.services import apagar_denuncias_demo
    from planos.services import apagar_assinaturas_demo
    from privacidade.services import apagar_pedidos_demo
    from publicidade.services import apagar_publicidade_demo

    Usuario = get_user_model()
    with transaction.atomic():
        apagar_denuncias_demo()  # antes dos anúncios (Denuncia.anuncio é PROTECT)
        apagar_guia_demo()  # perfis do guia com aceites, convites e pedidos (antes dos usuários demo)
        apagar_anuncios_demo()  # anúncios, fotos e histórico (Anuncio.anunciante é PROTECT)
        apagar_assinaturas_demo()  # antes dos anunciantes (e leva o histórico junto)
        apagar_publicidade_demo()  # campanhas, peças e patrocinadores demo
        apagar_pedidos_demo()  # pedidos de titulares fictícios (antes dos usuários demo)
        anunciantes = apagar_anunciantes_demo()  # antes dos usuários (Anunciante.usuario é PROTECT)
        Bairro.objects.filter(demo=True).delete()
        Regiao.objects.filter(demo=True).delete()
        # Superusuário nunca sai, mesmo se marcado como demo por engano (o dono do sistema).
        demo = Usuario.objects.filter(demo=True, is_superuser=False)
        usuarios = demo.count()
        demo.delete()
        cidades = Cidade.objects.filter(liberada_pela_demo=True).update(
            liberada=False, liberada_pela_demo=False
        )
    return ResumoDemo(usuarios=usuarios, cidades=cidades, anunciantes=anunciantes)


# --- Páginas institucionais (mídia kit, "em breve"; planos vêm do app planos) ------------------------------


@dataclass(frozen=True)
class FormatoPublicidade:
    """Espaço de publicidade do mídia kit (/anuncie/). Na Sprint 7 vem do app publicidade."""

    slug: str
    nome: str
    onde: str
    tamanho: str
    arquivo: str
    preco_de: Decimal
    preco_ate: Decimal | None
    periodo: str


def formatos_publicidade() -> list[FormatoPublicidade]:
    """Formatos à venda, na ordem do docs/PUBLICIDADE.md (hoje do settings PUBLICIDADE_FORMATOS)."""
    return [
        FormatoPublicidade(
            slug=f["slug"],
            nome=f["nome"],
            onde=f["onde"],
            tamanho=f["tamanho"],
            arquivo=f["arquivo"],
            preco_de=Decimal(f["preco_de"]),
            preco_ate=Decimal(f["preco_ate"]) if f["preco_ate"] else None,
            periodo=f["periodo"],
        )
        for f in settings.PUBLICIDADE_FORMATOS
    ]


# Páginas que existem no menu e no rodapé mas ainda não foram construídas: mostram
# "Em breve" (nunca 404). A chave é o nome da rota em core/urls.py.
# (A última, "Denunciar anúncio", virou o formulário de verdade na Sprint 7B parte 2: app moderacao.)
PAGINAS_EM_BREVE: dict[str, dict] = {}


def textos_ajuda(tela: str) -> list[str]:
    """Itens da caixa "Sobre esta tela" da tela pedida, editáveis no admin (modelo TextoAjuda).

    Todos os textos ficam num só registro de cache (limpo ao salvar no admin). Lista
    vazia = a caixa não aparece.
    """
    textos = cache.get(CHAVE_CACHE_AJUDA)
    if textos is None:
        textos = {t.chave: t.itens for t in TextoAjuda.objects.all()}
        cache.set(CHAVE_CACHE_AJUDA, textos, timeout=60 * 60)
    return textos.get(tela, [])


# --- Identidade do site (Configuracao) ----------------------------------------------------

TEXTOS_SOBRE_INICIAIS = {
    "sobre_quem_somos": (
        "Nascemos em Tangará da Serra para resolver um problema simples: os bons negócios da região "
        "ficavam espalhados em grupos, sites nacionais e placas na rua. Aqui, imobiliárias, corretores "
        "e revendas da região mostram seu estoque com fotos, mapa e preço, e você fala direto com quem vende."
    ),
    "sobre_missao": (
        "Aproximar quem quer comprar ou alugar de quem vende com seriedade, com anúncios de "
        "profissionais verificados e contato direto."
    ),
    "sobre_visao": (
        "Ser a referência em imóveis e veículos no interior de Mato Grosso, lembrada pela confiança "
        "de quem compra e pelos resultados de quem anuncia."
    ),
}


def configuracao() -> Configuracao:
    """O registro único da identidade do site. Na primeira vez, nasce com os `SITE_*` do settings.

    Dois acessos simultâneos ao site novo podem tentar criar o registro ao mesmo tempo: quem
    perde a corrida lê o que o outro gravou (em vez de quebrar com chave duplicada).
    """
    config = Configuracao.objects.filter(pk=Configuracao.ID_UNICO).first()
    if config is None:
        config = Configuracao(
            nome=settings.SITE_NOME,
            linha_regiao=settings.SITE_LINHA_REGIAO,
            slogan=settings.SITE_SLOGAN,
            empresa=settings.SITE_EMPRESA,
            cidade_sede=settings.SITE_CIDADE_SEDE,
            whatsapp=settings.SITE_WHATSAPP,
            email_contato=settings.SITE_EMAIL_CONTATO,
            email_privacidade=settings.SITE_EMAIL_PRIVACIDADE,
            endereco=settings.SITE_ENDERECO,
            cnpj=settings.SITE_CNPJ,
            **TEXTOS_SOBRE_INICIAIS,
        )
        try:
            with transaction.atomic():
                config.save(force_insert=True)
        except IntegrityError:
            config = Configuracao.objects.get(pk=Configuracao.ID_UNICO)
    return config


def _url_ou_padrao(arquivo, padrao_estatico: str) -> str:
    """URL do arquivo enviado no admin ou, sem ele, do arquivo padrão em static/."""
    from django.templatetags.static import static

    return arquivo.url if arquivo else static(padrao_estatico)


def _favicon_svg(config: Configuracao) -> str:
    """Favicon SVG: o símbolo enviado (se for SVG), o padrão (favicon.svg, sem símbolo) ou nenhum (PNG)."""
    from django.templatetags.static import static

    if not config.simbolo_claro:
        return static("img/favicon.svg")
    return config.simbolo_claro.url if config.simbolo_claro.name.endswith(".svg") else ""


def dados_do_site() -> dict:
    """Dicionário `site` dos templates (context processor), em cache até o admin salvar.

    Sem logo, símbolo ou favicon enviados, usa os arquivos padrão de static/img/ (logo final, ver
    docs/marca/logo/LEIA-ME.md): logo horizontal, símbolo quadrado, símbolo para fundo escuro e favicon.
    """
    dados = cache.get(CHAVE_CACHE_CONFIGURACAO)
    if dados is not None:
        return dados
    config = configuracao()
    dados = {
        "nome": config.nome,
        "slogan": config.slogan,
        "frase_rodape": config.frase_rodape,
        "linha_regiao": config.linha_regiao,
        "empresa": config.empresa,
        "cidade_sede": config.cidade_sede,
        "whatsapp": config.whatsapp,
        "email_contato": config.email_contato,
        "email_privacidade": config.email_privacidade,
        "endereco": config.endereco,
        "cnpj": config.cnpj,
        "instagram": config.instagram,
        "logo_completo": _url_ou_padrao(config.logo_completo, "img/logo-horizontal-fundo-escuro.svg"),
        "simbolo_claro": _url_ou_padrao(config.simbolo_claro, "img/simbolo-quadrado.svg"),
        "simbolo_escuro": _url_ou_padrao(config.simbolo_escuro, "img/simbolo-fundo-escuro.svg"),
        "imagem_compartilhamento": config.imagem_compartilhamento.url
        if config.imagem_compartilhamento
        else "",
        "favicon_svg": _favicon_svg(config),
        "favicon_32": _url_ou_padrao(config.favicon_32, "img/favicon-32.png"),
        "favicon_180": _url_ou_padrao(config.favicon_180, "img/apple-touch-icon.png"),
        "favicon_512": _url_ou_padrao(config.favicon_512, "img/icone-512.png"),
        "favicon_ico": _url_ou_padrao(config.favicon_ico, "img/favicon.ico"),
    }
    cache.set(CHAVE_CACHE_CONFIGURACAO, dados, timeout=60 * 60)
    return dados


def processar_identidade(config: Configuracao, campos_mudados: set[str]) -> Configuracao:
    """Depois do admin salvar: limpa imagens novas (sem EXIF, nome aleatório) e refaz os favicons.

    Os arquivos já foram validados pelo formulário (`core.imagens`). PNG/JPG enviados são
    regravados a partir dos pixels; SVG fica como está (passou na checagem de segurança).
    Trocou o símbolo para fundo claro (ou não há favicon ainda) → gera os 4 favicons.
    """
    for campo in ("logo_completo", "simbolo_claro", "simbolo_escuro", "imagem_compartilhamento"):
        arquivo = getattr(config, campo)
        if campo in campos_mudados and arquivo and not arquivo.name.endswith(".svg"):
            limpo = imagens.reprocessar_raster(arquivo)
            arquivo.save(limpo.name, limpo, save=False)
    if config.simbolo_claro and ("simbolo_claro" in campos_mudados or not config.favicon_32):
        for campo, conteudo in imagens.favicons(config.simbolo_claro).items():
            getattr(config, campo).save(conteudo.name, conteudo, save=False)
    elif not config.simbolo_claro:  # voltou ao símbolo padrão: volta ao favicon padrão
        for campo in ("favicon_ico", "favicon_32", "favicon_180", "favicon_512"):
            setattr(config, campo, "")
    config.save()
    return config


# --- Limite por IP e e-mails com modelo ---------------------------------------------------


def limite_por_ip_excedido(request: HttpRequest, acao: str, limite: int, janela_segundos: int = 3600) -> bool:
    """Conta mais uma tentativa da `acao` vinda deste IP e diz se passou do `limite` na janela.

    Proteção contra robô (cadastro, "esqueci minha senha"...). Contador no cache (Redis),
    que vale para todos os processos. O IP entra na chave só como resumo (HMAC): o IP em
    si não é guardado (LGPD). O IP vem do REMOTE_ADDR (o X-Forwarded-For pode ser
    forjado; atrás do Nginx, etapa de produção, ajustar junto com o axes).
    """
    ip = request.META.get("REMOTE_ADDR", "")
    chave = f"limite:{acao}:{salted_hmac('core.limite_por_ip', ip).hexdigest()[:24]}"
    cache.add(chave, 0, timeout=janela_segundos)
    try:
        tentativas = cache.incr(chave)
    except ValueError:  # a chave venceu entre o add e o incr
        cache.set(chave, 1, timeout=janela_segundos)
        tentativas = 1
    return tentativas > limite


def enviar_email_modelo(modelo: str, assunto: str, para: list[str], contexto: dict | None = None) -> int:
    """Monta o texto a partir de templates/emails/<modelo>.txt e envia (pela fila do Celery).

    O template recebe `site_nome` e `site_url` (para links absolutos) além do `contexto`.
    Destinatários vazios não enviam nada. Devolve quantos e-mails entraram na fila.
    """
    destinatarios = [email for email in para if email]
    if not destinatarios:
        return 0
    corpo = render_to_string(
        f"emails/{modelo}.txt",
        {"site_nome": configuracao().nome, "site_url": settings.SITE_URL, **(contexto or {})},
    )
    return send_mail(f"{assunto} · {configuracao().nome}", corpo, None, destinatarios)


# --- Manual da equipe (/painel/ajuda/) ----------------------------------------------------------------

ARQUIVO_MANUAL = Path(settings.BASE_DIR) / "docs" / "MANUAL_ADMIN.md"


def manual_da_equipe(arquivo: Path = ARQUIVO_MANUAL):
    """O docs/MANUAL_ADMIN.md em HTML seguro (tudo escapado; ver core.markdown_seguro). Lido a cada pedido:
    o manual muda junto com o código e é pequeno. Sem o arquivo, uma mensagem no lugar."""
    from core.markdown_seguro import markdown_para_html

    try:
        texto = arquivo.read_text(encoding="utf-8")
    except OSError:
        texto = "# Manual indisponível\n\nO arquivo docs/MANUAL_ADMIN.md não foi encontrado no servidor."
    return markdown_para_html(texto)


# --- Painel de pendências (página inicial do admin) ---------------------------------------------------


@dataclass(frozen=True)
class Pendencia:
    """Um contador da caixa "Pendências" do admin: rótulo, quantos e o link para a lista já filtrada."""

    rotulo: str
    total: int
    url: str


def pendencias_da_equipe(usuario) -> list[Pendencia]:
    """Contadores do que espera a equipe, só do que o usuário tem permissão de ver (grupos do Django).

    Denúncias pendentes, pedidos de privacidade do site e do guia em aberto, comprovantes aguardando
    confirmação e lojas pendentes de aprovação. Cada link abre a lista do admin já filtrada.
    """
    from django.urls import reverse

    from anunciantes.models import Anunciante
    from guia.models import PedidoDoPerfil
    from moderacao.models import Denuncia
    from pagamentos.models import Fatura
    from privacidade.models import PedidoTitular

    abertos_titular = (PedidoTitular.Situacao.ABERTO, PedidoTitular.Situacao.EM_ANDAMENTO)
    abertos_guia = (PedidoDoPerfil.Status.ABERTO, PedidoDoPerfil.Status.EM_ANDAMENTO)
    itens = [  # (permissão, rótulo, consulta, rota do admin, filtro da lista)
        ("moderacao.view_denuncia", "Denúncias pendentes",
         Denuncia.objects.filter(situacao=Denuncia.Situacao.PENDENTE),
         "admin:moderacao_denuncia_changelist", "situacao__exact=pendente"),
        ("privacidade.view_pedidotitular", "Pedidos de privacidade do site",
         PedidoTitular.objects.filter(situacao__in=abertos_titular),
         "admin:privacidade_pedidotitular_changelist", "situacao__in=" + ",".join(abertos_titular)),
        ("guia.view_pedidodoperfil", "Pedidos do Guia de Negócios",
         PedidoDoPerfil.objects.filter(status__in=abertos_guia),
         "admin:guia_pedidodoperfil_changelist", "status__in=" + ",".join(abertos_guia)),
        ("pagamentos.view_fatura", "Comprovantes aguardando confirmação",
         Fatura.objects.filter(situacao=Fatura.Situacao.AGUARDANDO),
         "admin:pagamentos_fatura_changelist", f"situacao__exact={Fatura.Situacao.AGUARDANDO}"),
        ("anunciantes.view_anunciante", "Lojas pendentes de aprovação",
         Anunciante.objects.filter(status=Anunciante.Status.PENDENTE),
         "admin:anunciantes_anunciante_changelist", "status__exact=pendente"),
    ]  # fmt: skip
    return [
        Pendencia(rotulo, consulta.count(), f"{reverse(rota)}?{filtro}")
        for permissao, rotulo, consulta, rota, filtro in itens
        if usuario.has_perm(permissao)
    ]
