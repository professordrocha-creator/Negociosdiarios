"""Menu enxuto do admin por grupo (lote 3C): cada grupo vê só os menus que usa no dia a dia.

Só muda o que aparece no menu (página inicial e barra lateral). Permissões e endereços continuam iguais: quem
tem permissão abre a tela pelo endereço ou por um link. O Administrador (grupo ou superusuário) vê o dia a dia
no menu e o resto ("técnico": bloqueios de login, catálogo FIPE, grupos, cidades, textos...) no bloco
recolhido "Mais opções". Membro da equipe sem nenhum dos grupos abaixo vê o menu completo de sempre.
"""

from __future__ import annotations

# Menus de cada grupo ("app.modelo"). Conferido com as permissões das migrations de cada app (test_grupos).
MENU_POR_GRUPO: dict[str, set[str]] = {
    # Modera anúncios e denúncias, aprova/suspende lojas e atende os pedidos dos titulares do guia.
    "Moderador": {
        "anuncios.anuncioemmoderacao",
        "anuncios.anuncio",
        "moderacao.denuncia",
        "anunciantes.anunciante",
        "guia.pedidodoperfil",
    },
    # Cobrança: faturas, pedidos pelo Pix, a chave Pix e as assinaturas/planos (pagamento manual, preços).
    "Financeiro": {
        "pagamentos.fatura",
        "pagamentos.pedidoaguardando",
        "pagamentos.configuracaopix",
        "planos.assinatura",
        "planos.pedidotrocaplano",
        "planos.plano",
    },
    "Comercial": {
        "anunciantes.anunciante",
        "pagamentos.pedidoaguardando",
        "publicidade.campanha",
        "publicidade.patrocinador",
    },
    "Guia": {"guia.perfilguia", "guia.contatoconvite"},
}

# Dia a dia do Administrador: tudo o que os grupos usam + privacidade, configurações, equipe e cidades novas.
DIA_A_DIA_ADMINISTRADOR: set[str] = set().union(*MENU_POR_GRUPO.values()) | {
    "privacidade.pedidotitular",
    "core.configuracao",
    "contas.usuario",
    "anunciantes.solicitacaocidade",
    "core.cidade",
}

# Item mostrado no bloco de outro app, logo depois do item com que se usa junto (só no menu do dia a dia).
JUNTO_DE = {"core.cidade": "anunciantes.solicitacaocidade"}

# Ordem dos blocos no menu (o trabalho do dia primeiro); os outros vêm depois, em ordem alfabética.
ORDEM_DOS_APPS = [
    "pagamentos",
    "anuncios",
    "moderacao",
    "anunciantes",
    "planos",
    "publicidade",
    "guia",
    "privacidade",
    "core",
    "contas",
]

# Nomes em português simples (só no menu; os modelos não mudam).
NOMES_DOS_APPS = {
    "anunciantes": "Lojas (anunciantes)",
    "moderacao": "Denúncias",
    "core": "Site e configurações",
    "contas": "Equipe e usuários",
    "auth": "Grupos e permissões",
    "axes": "Bloqueios de login",
    "catalogo": "Catálogo de veículos (FIPE)",
    "otp_email": "Códigos de acesso por e-mail",
    "otp_static": "Códigos de emergência",
}
NOMES_DOS_MODELOS = {
    "guia.contatoconvite": "Convites e interessados",
    "axes.accessattempt": "Tentativas bloqueadas",
    "axes.accessfailurelog": "Falhas de login",
    "axes.accesslog": "Registros de login",
    "otp_email.emaildevice": "Aparelhos com código por e-mail",
    "otp_static.staticdevice": "Códigos de emergência",
}


def e_administrador(usuario) -> bool:
    """Superusuário ou grupo Administrador: vê o bloco "Mais opções"."""
    return usuario.is_superuser or usuario.groups.filter(name="Administrador").exists()


def _chave(app: dict, modelo: dict) -> str:
    """ "app.modelo" de um item do menu do admin."""
    return f"{app['app_label']}.{modelo['object_name'].lower()}"


def _renomear(app: dict, modelos: list[dict]) -> dict:
    """Cópia do bloco do menu com os nomes simples e só os `modelos` dados."""
    modelos = [{**m, "name": NOMES_DOS_MODELOS.get(_chave(app, m), m["name"])} for m in modelos]
    return {**app, "name": NOMES_DOS_APPS.get(app["app_label"], app["name"]), "models": modelos}


def _ordenar(apps: list[dict]) -> list[dict]:
    """Blocos do dia a dia primeiro (ORDEM_DOS_APPS), depois os outros em ordem alfabética."""
    posicao = {rotulo: i for i, rotulo in enumerate(ORDEM_DOS_APPS)}
    return sorted(apps, key=lambda app: (posicao.get(app["app_label"], len(posicao)), app["name"]))


def separar_menu(usuario, app_list: list[dict]) -> tuple[list[dict], list[dict]]:
    """Divide o menu do admin (já filtrado pelas permissões do Django) em (dia a dia, "Mais opções").

    Administrador: dia a dia + o resto em "Mais opções". Outros grupos: só os menus do(s) grupo(s), sem
    "Mais opções". Sem grupo conhecido: o menu inteiro, como antes.
    """
    administrador = e_administrador(usuario)
    if administrador:
        visiveis = DIA_A_DIA_ADMINISTRADOR
    else:
        grupos = set(usuario.groups.values_list("name", flat=True)) & set(MENU_POR_GRUPO)
        if not grupos:
            return _ordenar([_renomear(app, app["models"]) for app in app_list]), []
        visiveis = set().union(*(MENU_POR_GRUPO[nome] for nome in grupos))
    principal, mais = [], []
    for app in app_list:
        dia = [m for m in app["models"] if _chave(app, m) in visiveis]
        resto = [m for m in app["models"] if _chave(app, m) not in visiveis]
        if dia:
            principal.append(_renomear(app, dia))
        if resto and administrador:
            mais.append(_renomear(app, resto))
    return _ordenar(_juntar(principal)), _ordenar(mais)


def _juntar(blocos: list[dict]) -> list[dict]:
    """Move cada item de `JUNTO_DE` para logo depois do item vizinho (se os dois estão no menu); bloco que
    fica vazio sai do menu."""
    for chave, vizinho in JUNTO_DE.items():
        origem = next((b for b in blocos for m in b["models"] if _chave(b, m) == chave), None)
        destino = next((b for b in blocos for m in b["models"] if _chave(b, m) == vizinho), None)
        if origem is None or destino is None or origem is destino:
            continue
        item = next(m for m in origem["models"] if _chave(origem, m) == chave)
        origem["models"] = [m for m in origem["models"] if m is not item]
        posicao = next(i for i, m in enumerate(destino["models"]) if _chave(destino, m) == vizinho)
        destino["models"] = [*destino["models"][: posicao + 1], item, *destino["models"][posicao + 1 :]]
    return [b for b in blocos if b["models"]]
