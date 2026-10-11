"""
Gerador do protótipo estático do Negócios Diários.

Por que existe: cabeçalho, rodapé e ícones se repetem nas 5 telas. Em vez de
copiar e colar (e gastar tokens editando 5 arquivos), as partes comuns ficam
aqui e o script grava os .html prontos. Na versão Django, cada função abaixo
vira um template parcial ({% include %}): topo() -> _topo.html, card() -> _card.html.

Uso:  python prototipo/_gerar.py
"""
from pathlib import Path

PASTA = Path(__file__).parent
BS_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
FONTES = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800"
          "&family=Figtree:wght@400;500;600;700&display=swap")

# --- Ícones (sprite SVG; na versão real pode virar Bootstrap Icons) ----------
ICONES = {
    "casa": '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "carro": '<path d="M5 16h14M3 16v-3l2-5h14l2 5v3"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>',
    "pin": '<path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    "zap": '<path d="M4 20l1.3-3.9A8 8 0 1 1 8 19.3z"/><path d="M9 9.5c.5 2 2.5 4 4.5 4.5l1.2-1.2 2 1-.5 1.7c-3.8.3-8-3.9-7.7-7.7L10.2 7l1 2z"/>',
    "verificado": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "busca": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "cama": '<path d="M3 18v-8M3 14h18v4M21 18v-6a2 2 0 0 0-2-2h-8v4"/><circle cx="7" cy="11" r="1.5"/>',
    "banho": '<path d="M4 12h16v3a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"/><path d="M6 12V6a2 2 0 0 1 4 0"/>',
    "vaga": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M10 16V8h3a2.5 2.5 0 0 1 0 5h-3"/>',
    "area": '<path d="M4 4h16v16H4z"/><path d="M4 9h3M4 14h3M9 4v3M14 4v3"/>',
    "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "olho": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "coracao": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    "share": '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 11l7.6-3.8M8.2 13l7.6 3.8"/>',
    "filtro": '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>',
    "lista": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "plano": '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>',
    "fatura": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    "grafico": '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "loja": '<path d="M4 9l1.5-5h13L20 9"/><path d="M4 9a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0A2.7 2.7 0 0 0 20 9"/><path d="M5 11v9h14v-9"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "relogio": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "alerta": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
    "sair": '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
}
SPRITE = '<svg width="0" height="0" style="position:absolute" aria-hidden="true">' + "".join(
    f'<symbol id="i-{n}" viewBox="0 0 24 24">{p}</symbol>' for n, p in ICONES.items()) + "</svg>"


def ico(nome: str, classe: str = "ico") -> str:
    """Retorna um ícone do sprite."""
    return f'<svg class="{classe}" aria-hidden="true"><use href="#i-{nome}"/></svg>'


def ajuda(itens: list[str], aberta: bool = False) -> str:
    """Caixa "Sobre esta tela" — toda tela do sistema tem uma (vira _ajuda.html no Django).
    Os textos ficam no banco (modelo TextoAjuda), editáveis pelo admin sem deploy."""
    lis = "".join(f"<li>{i}</li>" for i in itens)
    return f'<details class="nd-ajuda"{" open" if aberta else ""}><summary>{ico("alerta")} Sobre esta tela</summary><ul>{lis}</ul></details>'


# No Django: {{ site.simbolo.url|default:"img/simbolo-ipe.svg" }} — trocado no painel do admin.
LOGO_MARCA = '<img src="img/simbolo-ipe.svg" width="38" height="38" alt="">'


def pagina(titulo: str, menu_ativo: str, corpo: str, sem_rodape: bool = False) -> str:
    """Monta um documento HTML completo (cabeçalho + corpo + rodapé)."""
    def m(rotulo, href, chave):
        return f'<a class="px-1 py-2{" ativo" if chave == menu_ativo else ""}" href="{href}">{rotulo}</a>'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{titulo} · Negócios Diários</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTES}">
<link rel="stylesheet" href="css/bootstrap.min.css">
<link rel="stylesheet" href="css/nd.css">
</head>
<body>
{SPRITE}
<div class="nd-faixa-prototipo">Protótipo navegável · anúncios, lojas e preços são exemplos fictícios · <a href="index.html">voltar ao índice</a></div>
<header class="nd-topo">
  <div class="container d-flex align-items-center gap-3 py-2 flex-wrap">
    <a class="nd-logo me-auto" href="home.html">{LOGO_MARCA}<span>Negócios Diários<small>Imóveis e veículos de Mato Grosso</small></span></a>
    <nav class="nd-menu d-none d-md-flex gap-3" aria-label="Principal">
      {m("Imóveis", "busca.html", "imoveis")}{m("Veículos", "busca.html#veiculos", "veiculos")}{m("Lojas", "loja.html", "lojas")}
    </nav>
    <a class="btn btn-sm btn-ipe" href="painel.html">{ico("mais")} Anunciar</a>
    <a class="small d-none d-sm-inline" href="painel.html">Entrar</a>
  </div>
</header>
{corpo}
{"" if sem_rodape else RODAPE}
<script src="{BS_JS}"></script>
</body>
</html>
"""


RODAPE = f"""<footer class="nd-rodape mt-5">
  <div class="container py-5">
    <div class="row g-4">
      <div class="col-12 col-md-4">
        <div class="nd-logo mb-2 text-white">{LOGO_MARCA}<span>Negócios Diários</span></div>
        <p class="mb-0">Os melhores negócios da sua região, todos os dias. Só anunciantes verificados: corretores com CRECI e revendas com CNPJ.</p>
      </div>
      <div class="col-6 col-md-2"><h3>Buscar</h3><ul class="list-unstyled d-grid gap-1 mb-0"><li><a href="busca.html">Imóveis à venda</a></li><li><a href="busca.html">Imóveis para alugar</a></li><li><a href="busca.html">Carros e motos</a></li><li><a href="loja.html">Lojas</a></li></ul></div>
      <div class="col-6 col-md-3"><h3>Para anunciantes</h3><ul class="list-unstyled d-grid gap-1 mb-0"><li><a href="painel.html">Planos e preços</a></li><li><a href="painel.html">Painel do anunciante</a></li><li><a href="#">Anuncie sua marca</a></li></ul></div>
      <div class="col-12 col-md-3"><h3>Institucional</h3><ul class="list-unstyled d-grid gap-1 mb-0"><li><a href="sobre.html">Sobre nós</a></li><li><a href="#">Política de Privacidade</a></li><li><a href="#">Termos de Uso</a></li><li><a href="#">Preferências de cookies</a></li><li><a href="#">Denunciar anúncio</a></li></ul></div>
    </div>
    <hr class="border-secondary my-4">
    <p class="small mb-0">© 2026 Negócios Diários · D'Rocha Soluções · Tangará da Serra, MT · privacidade@negociosdiarios.com.br</p>
  </div>
</footer>"""


# --- Dados de exemplo --------------------------------------------------------
IMOVEIS = [
    # foto, preço, título, cidade/bairro, ficha, loja, selos
    ("f1", "R$ 420.000", "Casa 3 quartos com área gourmet", "Tangará da Serra · Jardim Europa", "3 qts · 2 banh · 2 vagas · 180 m²", "Serra Imóveis", ["destaque"]),
    ("f2", "R$ 1.600/mês", "Apartamento 2 quartos mobiliado", "Tangará da Serra · Centro", "2 qts · 1 banh · 1 vaga · 64 m²", "Cerrado Imobiliária", ["aluguel"]),
    ("f3", "R$ 380.000", "Chácara 2 ha com represa e pomar", "Tangará da Serra · Estrada da Serra", "2 qts · poço artesiano · 2 ha", "Serra Imóveis", []),
    ("f4", "R$ 95.000", "Terreno 12×30 em rua asfaltada", "Barra do Bugres · Jardim Primavera", "360 m² · escriturado", "Paulo Mendes Corretor", []),
]
VEICULOS = [
    ("f5", "R$ 189.900", "Toyota Hilux SRV 2.8 4x4 Diesel", "Tangará da Serra", "2019 · 98.000 km · automático", "Garagem Rota 358", ["destaque"]),
    ("f6", "R$ 98.900", "Fiat Strada Freedom 1.3 CD", "Campo Novo do Parecis", "2022 · 41.000 km · manual", "Parecis Veículos", []),
    ("f4", "R$ 72.500", "Chevrolet Onix LT 1.0 Turbo", "Tangará da Serra", "2021 · 52.000 km · manual", "Garagem Rota 358", []),
    ("f2", "R$ 16.900", "Honda CG 160 Fan", "Nova Olímpia", "2023 · 9.000 km · flex", "Parecis Veículos", []),
]
SELOS = {"destaque": '<span class="selo selo-destaque">Destaque</span>',
         "aluguel": '<span class="selo selo-aluguel">Aluguel</span>'}


def card(d, tipo: str) -> str:
    """Card de anúncio — vira o parcial _card_anuncio.html no Django."""
    foto, preco, titulo, local, ficha, loja, selos = d
    return f"""<div class="col"><article class="nd-card position-relative">
  <div class="nd-foto {foto}">{ico("carro" if (tipo == "veiculo" or d in VEICULOS) else "casa", "ico marca-foto")}
    <div class="selos">{"".join(SELOS[s] for s in selos)}</div><span class="qtd">1/10</span></div>
  <div class="corpo">
    <div class="preco tabular">{preco}</div>
    <a class="titulo stretched-link" href="anuncio.html">{titulo}</a>
    <div class="meta">{ico("pin")} {local}</div>
    <div class="meta">{ficha}</div>
    <div class="loja">{ico("verificado")} {loja}</div>
  </div></article></div>"""


def grade(lista, tipo, cols="row-cols-1 row-cols-sm-2 row-cols-lg-4"):
    return f'<div class="row {cols} g-3">' + "".join(card(d, tipo) for d in lista) + "</div>"


LOJAS = [("SI", "Serra Imóveis", "Imobiliária · 38 anúncios", "#0e4a57"),
         ("R3", "Garagem Rota 358", "Revenda · 24 anúncios", "#9b4d34"),
         ("CI", "Cerrado Imobiliária", "Imobiliária · 19 anúncios", "#4d7a4e"),
         ("PV", "Parecis Veículos", "Revenda · 31 anúncios", "#5b6779"),
         ("PM", "Paulo Mendes", "Corretor · 9 anúncios", "#8a6a3a"),
         ("CM", "Chapada Motors", "Concessionária · 45 anúncios", "#2f5f69")]


def loja_mini(l):
    sig, nome, info, cor = l
    return f'<a class="nd-loja-mini" href="loja.html"><span class="nd-monograma" style="background:{cor}">{sig}</span><b>{nome}</b><span>{info}</span></a>'


CIDADES = "".join(f"<option>{c}</option>" for c in ["Todas as cidades", "Tangará da Serra", "Cuiabá", "Barra do Bugres", "Campo Novo do Parecis", "Nova Olímpia", "Sinop", "Rondonópolis"])

# --- HOME --------------------------------------------------------------------
HOME = f"""<section class="nd-hero">
  <div class="container">
    <h1 class="h2 mb-1">Encontre seu próximo imóvel ou veículo em MT</h1>
    <p class="mb-3 opacity-75">Anúncios de corretores e revendas verificados. Fale direto pelo WhatsApp, sem cadastro.</p>
    <div class="nd-busca p-3 p-md-4">
      <ul class="nav nd-abas mb-3" role="tablist">
        <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#b-imovel" type="button">{ico("casa")} Imóveis</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#b-veiculo" type="button">{ico("carro")} Veículos</button></li>
      </ul>
      <div class="tab-content">
        <form class="tab-pane fade show active" id="b-imovel" action="busca.html"><div class="row g-2 align-items-end">
          <div class="col-6 col-md-2"><label class="form-label" for="h-mod">Quero</label><select id="h-mod" class="form-select"><option>Comprar</option><option>Alugar</option></select></div>
          <div class="col-6 col-md-3"><label class="form-label" for="h-tipo">Tipo</label><select id="h-tipo" class="form-select"><option>Todos</option><option>Casa</option><option>Apartamento</option><option>Kitnet</option><option>Terreno</option><option>Chácara</option><option>Sítio</option><option>Fazenda</option><option>Sala comercial</option></select></div>
          <div class="col-12 col-md-3"><label class="form-label" for="h-cid">Cidade</label><select id="h-cid" class="form-select">{CIDADES}</select></div>
          <div class="col-12 col-md-2"><label class="form-label" for="h-max">Até (R$)</label><input id="h-max" class="form-control" inputmode="numeric" placeholder="500.000"></div>
          <div class="col-12 col-md-2 d-grid"><button class="btn btn-nd">{ico("busca")} Buscar</button></div>
        </div></form>
        <form class="tab-pane fade" id="b-veiculo" action="busca.html"><div class="row g-2 align-items-end">
          <div class="col-6 col-md-2"><label class="form-label" for="h-vt">Tipo</label><select id="h-vt" class="form-select"><option>Carros</option><option>Caminhonetes</option><option>Motos</option><option>Caminhões</option></select></div>
          <div class="col-6 col-md-3"><label class="form-label" for="h-marca">Marca</label><select id="h-marca" class="form-select"><option>Todas</option><option>Chevrolet</option><option>Fiat</option><option>Honda</option><option>Toyota</option><option>Volkswagen</option></select></div>
          <div class="col-12 col-md-3"><label class="form-label" for="h-vcid">Cidade</label><select id="h-vcid" class="form-select">{CIDADES}</select></div>
          <div class="col-12 col-md-2"><label class="form-label" for="h-ano">Ano a partir de</label><input id="h-ano" class="form-control" inputmode="numeric" placeholder="2018"></div>
          <div class="col-12 col-md-2 d-grid"><button class="btn btn-nd">{ico("busca")} Buscar</button></div>
        </div></form>
      </div>
    </div>
    <nav class="nd-atalhos" aria-label="Atalhos">
      {"".join(f'<a href="busca.html">{ico(i)} {t}</a>' for i, t in [("casa", "Casas"), ("casa", "Apartamentos"), ("area", "Terrenos"), ("pin", "Chácaras e sítios"), ("loja", "Salas comerciais"), ("carro", "Caminhonetes"), ("carro", "Carros"), ("carro", "Motos")])}
    </nav>
  </div>
</section>
<main class="container mt-4 d-grid gap-5">
  <div class="nd-banner"><b>Banner topo · 970×90 (desktop) / 320×100 (celular)</b>Espaço publicitário para construtoras e empresas locais</div>
  <section><div class="nd-secao-titulo"><h2>Imóveis em destaque <span class="selo selo-destaque align-middle">Patrocinado</span></h2><a href="busca.html">Ver todos os imóveis</a></div>{grade(IMOVEIS, "imovel")}</section>
  <section><div class="nd-secao-titulo"><h2>Veículos em destaque <span class="selo selo-destaque align-middle">Patrocinado</span></h2><a href="busca.html#veiculos">Ver todos os veículos</a></div>{grade(VEICULOS, "veiculo")}</section>
  <section><div class="nd-secao-titulo"><h2>Recém-anunciados</h2><a href="busca.html">Ver todos</a></div>
    <ul class="nav nd-abas mb-3"><li class="nav-item"><button class="nav-link active" type="button">Todos</button></li><li class="nav-item"><button class="nav-link" type="button">Imóveis</button></li><li class="nav-item"><button class="nav-link" type="button">Veículos</button></li></ul>
    {grade([IMOVEIS[1], VEICULOS[1], IMOVEIS[3], VEICULOS[3], IMOVEIS[2], VEICULOS[2], IMOVEIS[0], VEICULOS[0]], "imovel")}
    <p class="small text-suave mt-2 mb-0">Anúncios de todas as lojas, do mais novo para o mais antigo. No máximo 2 por loja nesta lista, para nenhuma empresa grande ocupar a home inteira.</p></section>
  <section><div class="nd-secao-titulo"><h2>Lojas verificadas</h2><a href="loja.html">Ver todas</a></div><div class="nd-lojas">{"".join(loja_mini(l) for l in LOJAS)}</div></section>
  <section class="nd-caixa d-flex flex-column flex-md-row align-items-md-center gap-3">
    <div class="me-auto"><h2 class="h4 mb-1">É corretor ou tem uma revenda?</h2><p class="mb-0 text-suave">Ganhe uma página própria para sua loja e anuncie a partir de R$ 49,90 por mês.</p></div>
    <a class="btn btn-ipe btn-lg" href="painel.html">Ver planos</a>
  </section>
  <section><div class="nd-secao-titulo"><h2 class="h5">Patrocinadores</h2></div>
    <div class="row row-cols-1 row-cols-md-3 g-3">{"".join('<div class="col"><div class="nd-banner"><b>Card patrocinador</b>Rodapé da home · logo + frase + link</div></div>' for _ in range(3))}</div></section>
</main>"""

# --- BUSCA -------------------------------------------------------------------
FILTROS = f"""<form class="d-grid gap-3">
  <div><label class="form-label" for="f-mod">Modalidade</label><div class="btn-group w-100" role="group"><input type="radio" class="btn-check" name="mod" id="f-mod" checked><label class="btn btn-contorno" for="f-mod">Venda</label><input type="radio" class="btn-check" name="mod" id="f-mod2"><label class="btn btn-contorno" for="f-mod2">Aluguel</label></div></div>
  <div><label class="form-label" for="f-cid">Cidade</label><select id="f-cid" class="form-select"><option>Tangará da Serra</option>{CIDADES}</select></div>
  <div><label class="form-label" for="f-bairro">Bairro</label><input id="f-bairro" class="form-control" placeholder="Qualquer bairro"></div>
  <div><span class="form-label d-block">Tipo</span>
    {"".join(f'<div class="form-check"><input class="form-check-input" type="checkbox" id="t{i}" {"checked" if i < 2 else ""}><label class="form-check-label" for="t{i}">{t}</label></div>' for i, t in enumerate(["Casa", "Apartamento", "Kitnet", "Terreno", "Chácara / Sítio", "Sala comercial"]))}</div>
  <div><span class="form-label d-block">Preço (R$)</span><div class="d-flex gap-2"><input id="f-pmin" class="form-control" placeholder="Mín." inputmode="numeric" aria-label="Preço mínimo"><input id="f-pmax" class="form-control" placeholder="Máx." inputmode="numeric" aria-label="Preço máximo"></div></div>
  <div><span class="form-label d-block">Quartos</span><div class="btn-group w-100" role="group">{"".join(f'<input type="radio" class="btn-check" name="q" id="q{n}" {"checked" if n == "2+" else ""}><label class="btn btn-contorno" for="q{n}">{n}</label>' for n in ["1+", "2+", "3+", "4+"])}</div></div>
  <div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="f-garagem"><label class="form-check-label" for="f-garagem">Com vaga de garagem</label></div>
  <button class="btn btn-nd" type="button">Aplicar filtros</button>
</form>"""

PINOS = [(22, 30, "420 mil", True), (55, 42, "1,6 mil/mês", False), (70, 22, "310 mil", False), (38, 68, "380 mil", False), (82, 63, "95 mil", False)]
MAPA_BUSCA = '<div class="nd-mapa" style="height:100%;min-height:420px">' + "".join(
    f'<span class="nd-pino{" ativo" if a else ""}" style="left:{x}%;top:{y}%">{t}</span>' for x, y, t, a in PINOS
) + '<span class="legenda">Mapa ilustrativo · versão real usa Leaflet + OpenStreetMap</span></div>'

BUSCA = f"""<main class="container mt-4">
  <nav aria-label="Trilha" class="small mb-2"><a href="home.html">Início</a> › Imóveis à venda › Tangará da Serra</nav>
  <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
    <h1 class="h3 m-0 me-auto">Imóveis à venda em Tangará da Serra <span class="text-suave fs-6 fw-normal tabular">128 resultados</span></h1>
    <button class="btn btn-contorno d-lg-none" data-bs-toggle="offcanvas" data-bs-target="#filtros" type="button">{ico("filtro")} Filtros</button>
    <div class="btn-group" role="group" aria-label="Visualização">
      <input type="radio" class="btn-check" name="vis" id="v-lista" checked><label class="btn btn-contorno" for="v-lista">{ico("lista")} Lista</label>
      <input type="radio" class="btn-check" name="vis" id="v-mapa"><label class="btn btn-contorno" for="v-mapa">{ico("pin")} Mapa</label>
    </div>
    <select class="form-select w-auto" aria-label="Ordenar"><option>Mais recentes</option><option>Menor preço</option><option>Maior preço</option></select>
  </div>
  <div class="d-flex flex-wrap gap-2 mb-3 small">
    <span class="badge rounded-pill text-bg-light border">Venda ✕</span><span class="badge rounded-pill text-bg-light border">Casa, Apartamento ✕</span><span class="badge rounded-pill text-bg-light border">2+ quartos ✕</span><a href="#" class="ms-1">Limpar tudo</a>
  </div>
  <div class="row g-4">
    <aside class="col-lg-3">
      <div class="offcanvas-lg offcanvas-start" tabindex="-1" id="filtros">
        <div class="offcanvas-header"><h2 class="h5 m-0">Filtros</h2><button type="button" class="btn-close" data-bs-dismiss="offcanvas" data-bs-target="#filtros" aria-label="Fechar"></button></div>
        <div class="offcanvas-body"><div class="nd-caixa w-100">{FILTROS}</div></div>
      </div>
    </aside>
    <div class="col-lg-9">
      <div class="row g-3">
        <div class="col-xl-7">
          <div class="nd-banner mb-3 text-start d-flex gap-3 align-items-center"><span class="selo selo-destaque">Patrocinado</span><span><b class="d-inline">Residencial Vale do Sepotuba</b> · lotes a partir de R$ 89 mil · anúncio nativo (topo dos resultados)</span></div>
          {grade(IMOVEIS * 2, "imovel", "row-cols-1 row-cols-sm-2")}
          <nav class="mt-4" aria-label="Páginas"><ul class="pagination justify-content-center"><li class="page-item active"><a class="page-link" href="#">1</a></li><li class="page-item"><a class="page-link" href="#">2</a></li><li class="page-item"><a class="page-link" href="#">3</a></li><li class="page-item"><a class="page-link" href="#">Próxima</a></li></ul></nav>
        </div>
        <div class="col-xl-5 d-none d-xl-block"><div style="position:sticky;top:90px;height:calc(100vh - 120px)">{MAPA_BUSCA}</div></div>
      </div>
    </div>
  </div>
</main>"""

# --- ANÚNCIO -----------------------------------------------------------------
FICHA = [("Tipo", "Casa"), ("Área construída", "180 m²"), ("Área do terreno", "360 m²"), ("Quartos", "3 (1 suíte)"),
         ("Banheiros", "2"), ("Vagas", "2 cobertas"), ("Modalidade", "Venda"), ("Código", "ND-IM-10482")]
ANUNCIO = f"""<main class="container mt-4">
  <nav aria-label="Trilha" class="small mb-2"><a href="home.html">Início</a> › <a href="busca.html">Imóveis</a> › Tangará da Serra › Jardim Europa</nav>
  <div class="row g-4">
    <div class="col-lg-8 d-grid gap-3">
      <div class="nd-foto f1 rounded-3" style="aspect-ratio:16/10">{ico("casa", "ico marca-foto")}<div class="selos"><span class="selo selo-destaque">Destaque</span></div><span class="qtd">1 / 10 fotos</span></div>
      <div class="nd-miniaturas">{"".join(f'<div class="nd-foto f{i}">{ico("casa", "ico marca-foto")}</div>' for i in [1, 3, 2, 4, 6])}</div>
      <div class="nd-caixa">
        <div class="d-flex flex-wrap align-items-start gap-2">
          <div class="me-auto"><h1 class="h3 mb-1">Casa 3 quartos com área gourmet</h1><p class="text-suave mb-0">{ico("pin")} Jardim Europa, Tangará da Serra · MT</p></div>
          <button class="btn btn-contorno btn-sm" type="button">{ico("coracao")} Favoritar</button>
          <button class="btn btn-contorno btn-sm" type="button">{ico("share")} Compartilhar</button>
        </div>
        <dl class="nd-ficha mt-3 mb-0">{"".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in FICHA)}</dl>
      </div>
      <div class="nd-caixa"><h2 class="h5">Descrição</h2>
        <p>Casa térrea em rua asfaltada, a duas quadras da avenida principal. Três quartos, sendo uma suíte com closet, sala integrada à cozinha, área gourmet com churrasqueira e pia, lavanderia coberta e quintal com grama. Forro de PVC, piso porcelanato e portão eletrônico.</p>
        <p class="mb-0">Aceita financiamento bancário. Documentação em dia, escritura registrada.</p></div>
      <div class="nd-caixa"><h2 class="h5">Localização</h2>
        <div class="nd-mapa" style="height:280px"><span class="nd-raio-aprox" style="left:48%;top:52%"></span><span class="legenda">Localização aproximada · o endereço exato é passado pelo anunciante</span></div></div>
      <p class="small text-suave mb-0">{ico("olho")} 412 visualizações · publicado em 02/10/2026 · <a href="#">Denunciar este anúncio</a></p>
    </div>
    <aside class="col-lg-4">
      <div class="nd-contato d-grid gap-3">
        <div class="nd-caixa d-grid gap-3">
          <div><div class="text-suave small">Valor de venda</div><div class="nd-titulo tabular" style="font-size:34px;color:var(--nd-petroleo)">R$ 420.000</div><div class="small text-suave tabular">IPTU R$ 1.180/ano</div></div>
          <a class="btn btn-zap btn-lg" href="#">{ico("zap")} Chamar no WhatsApp</a>
          <button class="btn btn-contorno" type="button">Ver telefone</button>
          <p class="small text-suave mb-0">Mensagem pronta: “Olá! Vi no Negócios Diários o anúncio ND-IM-10482 e quero mais informações.”</p>
        </div>
        <a class="nd-caixa d-flex gap-3 align-items-center text-decoration-none text-reset" href="loja.html">
          <span class="nd-monograma" style="background:#0e4a57">SI</span>
          <span class="me-auto"><b class="d-block">Serra Imóveis</b><span class="selo selo-verificado mt-1">{ico("verificado")} CRECI verificado</span></span>
          <span class="small">Ver loja ›</span></a>
        <div class="nd-banner"><b>Dica de segurança</b>Visite o imóvel antes de pagar qualquer valor. Desconfie de sinal por Pix.</div>
      </div>
    </aside>
  </div>
  <section class="mt-5"><div class="nd-secao-titulo"><h2>Mais anúncios da Serra Imóveis</h2><a href="loja.html">Ver loja</a></div>{grade(IMOVEIS, "imovel")}</section>
</main>"""

# --- LOJA --------------------------------------------------------------------
LOJA = f"""<div class="nd-capa"></div>
<main class="container">
  <div class="nd-loja-cab d-flex flex-column flex-md-row gap-3 align-items-md-end">
    <span class="nd-monograma nd-loja-logo" style="background:#0e4a57">SI</span>
    <div class="me-auto pb-md-2">
      <h1 class="h2 mb-1">Serra Imóveis</h1>
      <div class="d-flex flex-wrap gap-2 align-items-center small"><span class="selo selo-verificado">{ico("verificado")} CRECI verificado</span><span class="text-suave">Imobiliária · desde 2011 · Tangará da Serra</span></div>
    </div>
    <div class="d-flex gap-2 pb-md-2"><a class="btn btn-zap" href="#">{ico("zap")} WhatsApp da loja</a><button class="btn btn-contorno" type="button">{ico("share")}</button></div>
  </div>
  <div class="row g-4 mt-1">
    <aside class="col-lg-3 d-grid gap-3 align-content-start">
      <div class="nd-caixa"><h2 class="h6">Sobre a loja</h2><p class="small mb-0">Venda e locação de casas, apartamentos e chácaras em Tangará da Serra e região. Avaliação gratuita do seu imóvel.</p></div>
      <div class="nd-caixa small d-grid gap-2">
        <div>{ico("pin")} Av. Brasil, 1.250 · Centro</div>
        <div>{ico("relogio")} Seg a sex 8h–18h · Sáb 8h–12h</div>
        <div class="nd-mapa" style="height:140px"><span class="nd-pino ativo" style="left:50%;top:55%">Serra Imóveis</span></div>
      </div>
      <div class="nd-caixa small"><div class="d-flex justify-content-between"><span>Anúncios ativos</span><b class="tabular">38</b></div><div class="d-flex justify-content-between"><span>Vendas</span><b class="tabular">27</b></div><div class="d-flex justify-content-between"><span>Aluguel</span><b class="tabular">11</b></div></div>
    </aside>
    <div class="col-lg-9">
      <div class="d-flex flex-wrap gap-2 mb-3">
        <div class="btn-group" role="group"><input type="radio" class="btn-check" name="lf" id="lf1" checked><label class="btn btn-contorno btn-sm" for="lf1">Todos (38)</label><input type="radio" class="btn-check" name="lf" id="lf2"><label class="btn btn-contorno btn-sm" for="lf2">Venda (27)</label><input type="radio" class="btn-check" name="lf" id="lf3"><label class="btn btn-contorno btn-sm" for="lf3">Aluguel (11)</label></div>
        <input class="form-control form-control-sm ms-auto" style="max-width:240px" placeholder="Buscar nesta loja" aria-label="Buscar nesta loja">
      </div>
      {grade(IMOVEIS + IMOVEIS[:2], "imovel", "row-cols-1 row-cols-sm-2 row-cols-xl-3")}
    </div>
  </div>
  <p class="small text-suave mt-4 mb-0">Endereço desta página: <b>negociosdiarios.com.br/loja/serra-imoveis</b> · ao compartilhar no WhatsApp aparece logo, nome e quantidade de anúncios.</p>
</main>"""

# --- PAINEL ------------------------------------------------------------------
MEUS = [("f1", "Casa 3 quartos com área gourmet", "ND-IM-10482", "publicado", "Publicado", 412, 37),
        ("f3", "Chácara 2 ha com represa e pomar", "ND-IM-10477", "expira", "Expira em 5 dias", 268, 21),
        ("f2", "Apartamento 2 quartos no Centro", "ND-IM-10501", "moderacao", "Em análise", 0, 0),
        ("f4", "Sala comercial 40 m² Av. Brasil", "ND-IM-10390", "pausado", "Pausado", 96, 4)]
LINHAS = "".join(f"""<tr><td><div class="nd-foto {f} mini">{ico("casa", "ico marca-foto")}</div></td>
  <td><b class="d-block">{t}</b><span class="small text-suave">{c}</span></td>
  <td><span class="status st-{s}">{r}</span></td><td class="tabular text-end">{v}</td><td class="tabular text-end">{z}</td>
  <td class="text-end"><div class="btn-group btn-group-sm"><button class="btn btn-contorno" type="button">Editar</button><button class="btn btn-contorno" type="button">{"Renovar" if s == "expira" else ("Reativar" if s == "pausado" else "Pausar")}</button></div></td></tr>""" for f, t, c, s, r, v, z in MEUS)
PAINEL = f"""<main class="container mt-4">
  <div class="row g-4">
    <aside class="col-lg-3">
      <div class="nd-caixa">
        <div class="d-flex gap-2 align-items-center mb-3"><span class="nd-monograma" style="background:#0e4a57;width:44px;height:44px;font-size:16px">SI</span><div><b class="d-block">Serra Imóveis</b><a class="small" href="loja.html">Ver minha loja ›</a></div></div>
        <nav class="nd-lateral d-grid gap-1"><a class="ativo" href="#">{ico("lista")} Meus anúncios</a><a href="#">{ico("mais")} Novo anúncio</a><a href="#">{ico("grafico")} Estatísticas</a><a href="painel-loja.html">{ico("loja")} Página da loja</a><a href="#">{ico("plano")} Meu plano</a><a href="#">{ico("fatura")} Faturas</a><a href="#">{ico("verificado")} Meus dados (LGPD)</a><a href="#">{ico("sair")} Sair</a></nav>
      </div>
    </aside>
    <div class="col-lg-9 d-grid gap-4">
      {ajuda(["Aqui você acompanha todos os seus anúncios, o uso do plano e as faturas.",
              "<b>Anúncios no plano</b>: publicados + em análise. Pausados não contam no limite.",
              "Anúncios expiram em 60 dias. Clique em <b>Renovar</b> para mais 60 dias, sem custo.",
              "<b>Cliques no WhatsApp</b>: quantas vezes visitantes tocaram no botão de contato do anúncio."])}
      <div class="alert d-flex gap-3 align-items-center mb-0" style="background:var(--nd-ipe-claro);border:1px solid #f0d77a" role="status">
        {ico("alerta")}<div class="me-auto"><b>Fatura de novembro vence em 15/11/2026.</b> Plano Profissional mensal · R$ 99,90</div><button class="btn btn-sm btn-nd" type="button">Pagar com Pix</button></div>
      <div class="row row-cols-1 row-cols-sm-2 row-cols-xl-4 g-3">
        <div class="col"><div class="nd-kpi"><div class="rotulo">Anúncios no plano</div><div class="valor">18 <span class="fs-6 text-suave">/ 25</span></div><div class="progress mt-2" role="progressbar" aria-valuenow="72" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:72%"></div></div></div></div>
        <div class="col"><div class="nd-kpi"><div class="rotulo">Visualizações · 30 dias</div><div class="valor">3.940</div><div class="small text-success">+18% vs. mês anterior</div></div></div>
        <div class="col"><div class="nd-kpi"><div class="rotulo">Cliques no WhatsApp</div><div class="valor">212</div><div class="small text-suave">5,4% das visualizações</div></div></div>
        <div class="col"><div class="nd-kpi"><div class="rotulo">Plano</div><div class="valor" style="font-size:22px">Profissional</div><a class="small" href="#">Mudar para Premium (50)</a></div></div>
      </div>
      <div class="nd-caixa p-0">
        <div class="d-flex flex-wrap gap-2 align-items-center p-3"><h1 class="h5 m-0 me-auto">Meus anúncios</h1><a class="btn btn-ipe btn-sm" href="#">{ico("mais")} Novo anúncio</a></div>
        <div class="table-responsive"><table class="table nd-tabela mb-0">
          <thead class="small text-suave"><tr><th></th><th>Anúncio</th><th>Situação</th><th class="text-end">Visualiz.</th><th class="text-end">WhatsApp</th><th></th></tr></thead>
          <tbody>{LINHAS}</tbody></table></div>
      </div>
      <p class="small text-suave mb-0">Ao atingir 25 anúncios o botão “Novo anúncio” é bloqueado e aparece a oferta de upgrade. Anúncios pausados não contam no limite.</p>
    </div>
  </div>
</main>"""

# --- PAINEL › PÁGINA DA LOJA (o anunciante edita logo, capa e dados públicos) ---
def lateral(ativo: str) -> str:
    """Menu lateral do painel — vira _painel_menu.html no Django."""
    itens = [("anuncios", "lista", "Meus anúncios", "painel.html"), ("novo", "mais", "Novo anúncio", "#"),
             ("estat", "grafico", "Estatísticas", "#"), ("loja", "loja", "Página da loja", "painel-loja.html"),
             ("plano", "plano", "Meu plano", "#"), ("faturas", "fatura", "Faturas", "#"),
             ("lgpd", "verificado", "Meus dados (LGPD)", "#"), ("sair", "sair", "Sair", "#")]
    links = "".join(f'<a class="{"ativo" if k == ativo else ""}" href="{h}">{ico(i)} {t}</a>' for k, i, t, h in itens)
    return f"""<div class="nd-caixa">
  <div class="d-flex gap-2 align-items-center mb-3"><span class="nd-monograma" style="background:#0e4a57;width:44px;height:44px;font-size:16px">SI</span><div><b class="d-block">Serra Imóveis</b><a class="small" href="loja.html">Ver minha loja ›</a></div></div>
  <nav class="nd-lateral d-grid gap-1">{links}</nav></div>"""


def campo(id_, rotulo, valor="", ajuda="", tipo="text", col="col-12"):
    a = f'<div class="form-text">{ajuda}</div>' if ajuda else ""
    return f'<div class="{col}"><label class="form-label" for="{id_}">{rotulo}</label><input id="{id_}" type="{tipo}" class="form-control" value="{valor}">{a}</div>'


PAINEL_LOJA = f"""<main class="container mt-4">
  <div class="row g-4">
    <aside class="col-lg-3">{lateral("loja")}</aside>
    <div class="col-lg-9">
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3"><h1 class="h4 m-0 me-auto">Página da loja</h1><a class="btn btn-contorno btn-sm" href="loja.html">Ver como o cliente vê ›</a></div>
      <div class="mb-3">{ajuda(["Esta é a vitrine da sua empresa no site. Tudo aqui aparece para os visitantes.",
              "<b>Logo</b>: quadrada, mínimo 400×400 px, até 2 MB (PNG, JPG ou WebP). Aparece na loja e nos anúncios.",
              "<b>Capa</b>: 1600×400 px (proporção 4:1), até 4 MB. Evite texto nas bordas: no celular elas são cortadas.",
              "As imagens são convertidas e otimizadas automaticamente. Dados de localização das fotos são removidos.",
              "CRECI e CNPJ não podem ser alterados aqui porque passaram por verificação. Fale com o suporte."], aberta=True)}</div>
      <div class="row g-4">
        <form class="col-xl-7 d-grid gap-3" id="form-loja">
          <div class="nd-caixa d-grid gap-3">
            <h2 class="h6 m-0">Logo e capa</h2>
            <div class="d-flex gap-3 align-items-center flex-wrap">
              <span class="nd-monograma" id="logo-mini" style="background:#0e4a57;width:88px;height:88px;font-size:30px;background-size:cover;background-position:center">SI</span>
              <div class="d-grid gap-1" style="min-width:0"><label class="btn btn-contorno btn-sm" for="logo">Enviar logo</label><input id="logo" type="file" accept="image/png,image/jpeg,image/webp" class="d-none">
                <span class="form-text m-0">Quadrada, mínimo 400×400 px, até 2 MB. PNG, JPG ou WebP.</span></div>
            </div>
            <div><label class="btn btn-contorno btn-sm" for="capa">Enviar capa</label><input id="capa" type="file" accept="image/png,image/jpeg,image/webp" class="d-none">
              <span class="form-text ms-2">1600×400 px. Sem capa, usamos a cor abaixo.</span></div>
            <div class="d-flex align-items-center gap-2"><input id="cor" type="color" class="form-control form-control-color" value="#0e4a57"><label for="cor" class="m-0">Cor da loja (capa e logo sem imagem)</label></div>
          </div>
          <div class="nd-caixa row g-3 mx-0">
            <h2 class="h6 m-0 col-12 px-0">Dados públicos</h2>
            {campo("nome", "Nome da loja", "Serra Imóveis")}
            <div class="col-12"><label class="form-label" for="slug">Endereço da página</label><div class="input-group"><span class="input-group-text small">negociosdiarios.com.br/loja/</span><input id="slug" class="form-control" value="serra-imoveis"></div><div class="form-text">Só letras minúsculas, números e hífen. Mudar quebra links já compartilhados.</div></div>
            <div class="col-12"><label class="form-label" for="sobre">Sobre a loja</label><textarea id="sobre" class="form-control" rows="3" maxlength="500">Venda e locação de casas, apartamentos e chácaras em Tangará da Serra e região. Avaliação gratuita do seu imóvel.</textarea><div class="form-text"><span id="sobre-n">0</span>/500 caracteres</div></div>
            {campo("zap", "WhatsApp", "(65) 9 0000-0000", "Recebe os contatos dos anúncios.", "tel", "col-md-6")}
            {campo("tel", "Telefone fixo (opcional)", "", "", "tel", "col-md-6")}
            {campo("end", "Endereço da loja", "Av. Brasil, 1.250 · Centro · Tangará da Serra", "", "text", "col-12")}
            <div class="col-12 form-check form-switch ms-2"><input class="form-check-input" type="checkbox" id="mapa" checked><label class="form-check-label" for="mapa">Mostrar a loja no mapa</label></div>
            {campo("hor", "Horário", "Seg a sex 8h–18h · Sáb 8h–12h")}
            {campo("insta", "Instagram (opcional)", "@serraimoveis", "", "text", "col-md-6")}
            {campo("site", "Site (opcional)", "", "", "url", "col-md-6")}
          </div>
          <div class="nd-caixa d-flex flex-wrap gap-2 align-items-center">
            <span class="small text-suave me-auto">{ico("verificado")} Imobiliária · CRECI verificado. Para alterar CRECI ou CNPJ, fale com o suporte.</span>
            <button class="btn btn-nd" type="submit">Salvar alterações</button>
          </div>
          <div id="salvo" class="alert alert-success py-2 mb-0" role="status" hidden>Alterações salvas. Sua página já está atualizada.</div>
        </form>
        <div class="col-xl-5">
          <div style="position:sticky;top:90px" class="d-grid gap-2">
            <span class="form-label m-0">Prévia</span>
            <div class="nd-caixa p-0 overflow-hidden">
              <div id="prev-capa" style="height:96px;background:#0e4a57;background-size:cover;background-position:center"></div>
              <div class="px-3 pb-3" style="margin-top:-36px">
                <span class="nd-monograma" id="prev-logo" style="background:#0e4a57;width:72px;height:72px;font-size:26px;border:3px solid var(--nd-papel);background-size:cover;background-position:center">SI</span>
                <b class="d-block mt-2 nd-titulo fs-5" id="prev-nome">Serra Imóveis</b>
                <span class="selo selo-verificado mt-1">{ico("verificado")} CRECI verificado</span>
                <p class="small text-suave mt-2 mb-0" id="prev-url">negociosdiarios.com.br/loja/serra-imoveis</p>
              </div>
            </div>
            <span class="form-label m-0 mt-2">Como aparece nos anúncios</span>
            <div class="nd-caixa py-2 small d-flex align-items-center gap-2"><span class="nd-monograma" id="prev-logo2" style="background:#0e4a57;width:28px;height:28px;font-size:11px;border-radius:6px;background-size:cover;background-position:center">SI</span><span id="prev-nome2">Serra Imóveis</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</main>""" + """
<script>
/* Prévia ao vivo (protótipo). No Django: upload vai para o servidor, que redimensiona e remove EXIF. */
(function () {
  const $ = (id) => document.getElementById(id);
  const logos = ["logo-mini", "prev-logo", "prev-logo2"].map($);
  function imagem(input, aplicar) {
    input.addEventListener("change", () => {
      const f = input.files[0]; if (!f) return;
      if (f.size > 2 * 1024 * 1024) { input.value = ""; $("salvo").hidden = false; $("salvo").className = "alert alert-warning py-2 mb-0"; $("salvo").textContent = "Imagem maior que 2 MB. Reduza o tamanho e envie de novo."; return; }
      const r = new FileReader(); r.onload = () => aplicar(r.result); r.readAsDataURL(f);
    });
  }
  imagem($("logo"), (url) => logos.forEach((el) => { el.style.backgroundImage = `url(${url})`; el.textContent = ""; }));
  imagem($("capa"), (url) => { $("prev-capa").style.backgroundImage = `url(${url})`; });
  $("cor").addEventListener("input", (e) => { $("prev-capa").style.backgroundColor = e.target.value; logos.forEach((el) => { el.style.backgroundColor = e.target.value; }); });
  $("nome").addEventListener("input", (e) => { $("prev-nome").textContent = e.target.value || "Nome da loja"; $("prev-nome2").textContent = e.target.value || "Nome da loja"; });
  $("slug").addEventListener("input", (e) => { e.target.value = e.target.value.toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").replace(/[^a-z0-9-]/g, "-"); $("prev-url").textContent = "negociosdiarios.com.br/loja/" + e.target.value; });
  const n = () => { $("sobre-n").textContent = $("sobre").value.length; }; $("sobre").addEventListener("input", n); n();
  $("form-loja").addEventListener("submit", (e) => { e.preventDefault(); const s = $("salvo"); s.className = "alert alert-success py-2 mb-0"; s.textContent = "Alterações salvas. Sua página já está atualizada."; s.hidden = false; });
})();
</script>"""

# --- ADMIN › CIDADES ATENDIDAS (Daniel libera estados e cidades) ---------------
def lateral_admin(ativo: str) -> str:
    """Menu do painel do administrador."""
    itens = [("resumo", "grafico", "Resumo do dia"), ("aprov", "verificado", "Aprovações <span class='badge text-bg-warning ms-auto'>4</span>"),
             ("anuncios", "lista", "Anúncios"), ("denuncias", "alerta", "Denúncias <span class='badge text-bg-danger ms-auto'>1</span>"),
             ("anunciantes", "loja", "Anunciantes"), ("planos", "plano", "Planos e preços"), ("faturas", "fatura", "Faturas"),
             ("pub", "olho", "Publicidade"), ("cidades", "pin", "Cidades atendidas"), ("ajuda", "lista", "Textos de ajuda"),
             ("equipe", "verificado", "Equipe e permissões"), ("config", "filtro", "Identidade do site")]
    links = "".join(f'<a class="{"ativo" if k == ativo else ""}" href="{ {"cidades": "admin-cidades.html", "config": "admin-site.html"}.get(k, "#") }">{ico(i)} {t}</a>' for k, i, t in itens)
    return f"""<div class="nd-caixa"><div class="mb-3"><b class="d-block">Administração</b><span class="small text-suave">Daniel · superusuário</span></div>
  <nav class="nd-lateral d-grid gap-1">{links}</nav></div>"""


ESTADOS = [("MT", "Mato Grosso", True, "5 de 142"), ("RO", "Rondônia", False, "—"), ("MS", "Mato Grosso do Sul", False, "—"), ("GO", "Goiás", False, "—")]
CIDADES_MT = [("Tangará da Serra", "Região de Tangará", True, 96), ("Barra do Bugres", "Região de Tangará", True, 14),
              ("Nova Olímpia", "Região de Tangará", True, 8), ("Campo Novo do Parecis", "Região de Tangará", True, 22),
              ("Denise", "Região de Tangará", True, 0), ("Arenápolis", "—", False, 0), ("Cuiabá", "—", False, 0), ("Sinop", "—", False, 0)]

ADMIN_CIDADES = f"""<main class="container mt-4">
  <div class="row g-4">
    <aside class="col-lg-3">{lateral_admin("cidades")}</aside>
    <div class="col-lg-9 d-grid gap-4">
      <h1 class="h4 m-0">Cidades atendidas</h1>
      {ajuda(["Todas as cidades do Brasil já estão cadastradas (tabela do IBGE), mas só aparecem no site as que você <b>liberar</b>.",
              "Com só um estado liberado, o site não mostra a escolha de estado: o visitante vê direto as cidades de MT.",
              "Ao liberar um segundo estado, o seletor de estado aparece sozinho na busca, nos filtros e no cadastro.",
              "<b>Regiões</b> agrupam cidades no filtro (ex.: “Região de Tangará”). Você cria e edita as regiões.",
              "Anunciante de cidade não liberada pode se cadastrar, mas o pedido cai em <b>Solicitações</b> para você decidir."], aberta=True)}
      <div class="nd-caixa p-0">
        <div class="d-flex align-items-center p-3 gap-2"><h2 class="h6 m-0 me-auto">Solicitações de liberação</h2><span class="badge text-bg-warning">2 pendentes</span></div>
        <div class="table-responsive"><table class="table nd-tabela mb-0 small">
          <tbody>
            <tr><td><b>Auto Center Fronteira</b><br><span class="text-suave">Revenda · cadastro em 10/10/2026</span></td><td>Pontes e Lacerda · MT</td><td><span class="status st-moderacao">Cidade não liberada</span></td>
              <td class="text-end"><div class="btn-group btn-group-sm"><button class="btn btn-nd" type="button">Liberar cidade</button><button class="btn btn-contorno" type="button">Recusar</button></div></td></tr>
            <tr><td><b>Imobiliária Vale do Guaporé</b><br><span class="text-suave">Imobiliária · cadastro em 09/10/2026</span></td><td>Vilhena · RO</td><td><span class="status st-expira">Estado não liberado</span></td>
              <td class="text-end"><div class="btn-group btn-group-sm"><button class="btn btn-nd" type="button">Liberar RO + cidade</button><button class="btn btn-contorno" type="button">Recusar</button></div></td></tr>
          </tbody></table></div>
      </div>
      <div class="nd-caixa p-0">
        <div class="d-flex align-items-center p-3"><h2 class="h6 m-0 me-auto">Estados</h2><span class="small text-suave">1 de 27 liberado</span></div>
        <div class="table-responsive"><table class="table nd-tabela mb-0">
          <thead class="small text-suave"><tr><th>UF</th><th>Estado</th><th>Cidades liberadas</th><th class="text-end">No site</th></tr></thead>
          <tbody>{"".join(f'<tr><td><b>{uf}</b></td><td>{n}</td><td class="tabular">{c}</td><td class="text-end"><div class="form-check form-switch d-inline-block m-0"><input class="form-check-input" type="checkbox" id="uf-{uf}" {"checked" if a else ""} aria-label="Liberar {n}"></div></td></tr>' for uf, n, a, c in ESTADOS)}</tbody></table></div>
      </div>
      <div class="nd-caixa p-0">
        <div class="d-flex flex-wrap gap-2 align-items-center p-3"><h2 class="h6 m-0 me-auto">Cidades de Mato Grosso</h2>
          <input class="form-control form-control-sm" style="max-width:220px" placeholder="Buscar cidade" aria-label="Buscar cidade">
          <select class="form-select form-select-sm w-auto" aria-label="Mostrar"><option>Todas</option><option>Liberadas</option><option>Não liberadas</option></select>
          <button class="btn btn-contorno btn-sm" type="button">{ico("mais")} Nova região</button></div>
        <div class="table-responsive"><table class="table nd-tabela mb-0">
          <thead class="small text-suave"><tr><th>Cidade</th><th>Região</th><th class="text-end">Anúncios</th><th class="text-end">No site</th></tr></thead>
          <tbody>{"".join(f'<tr><td>{c}</td><td><span class="small text-suave">{r}</span></td><td class="text-end tabular">{q}</td><td class="text-end"><div class="form-check form-switch d-inline-block m-0"><input class="form-check-input" type="checkbox" id="c{i}" {"checked" if a else ""} aria-label="Liberar {c}"></div></td></tr>' for i, (c, r, a, q) in enumerate(CIDADES_MT))}</tbody></table></div>
        <p class="small text-suave p-3 mb-0">Cidade com anúncios não pode ser desligada: primeiro os anúncios são pausados ou transferidos.</p>
      </div>
    </div>
  </div>
</main>"""


# --- SOBRE (textos vêm do painel: Configurações › Identidade do site) ---------
VALORES = [("verificado", "Confiança", "Só anunciam corretores com CRECI e empresas com CNPJ verificados."),
           ("pin", "Proximidade", "Feito em Mato Grosso, por gente que conhece as cidades e os bairros."),
           ("olho", "Transparência", "Preço à vista no anúncio e contato direto com quem vende, sem intermediário."),
           ("alerta", "Respeito aos seus dados", "Coletamos o mínimo e seguimos a LGPD. Visitante não precisa de cadastro."),
           ("lista", "Simplicidade", "Encontrar, comparar e chamar no WhatsApp em poucos toques.")]
SOBRE = f"""<section class="nd-sobre-hero">
  <div class="container py-5">
    <span class="selo selo-destaque mb-3">Sobre nós</span>
    <h1 class="display-6 fw-bold mb-3" style="max-width:20ch">Os melhores negócios da sua região, todos os dias.</h1>
    <p class="lead mb-0" style="max-width:60ch">O Negócios Diários reúne imóveis e veículos anunciados por profissionais verificados de Mato Grosso, em um só lugar, com contato direto pelo WhatsApp.</p>
  </div>
</section>
<main class="container mt-5 d-grid gap-5">
  <section class="row g-4 align-items-start">
    <div class="col-lg-6"><h2 class="h3">Quem somos</h2>
      <p>Nascemos em Tangará da Serra para resolver um problema simples: os bons negócios da região ficavam espalhados em grupos, sites nacionais e placas na rua. Aqui, imobiliárias, corretores e revendas da região mostram seu estoque com fotos, mapa e preço, e você fala direto com quem vende.</p>
      <p class="mb-0">Somos uma iniciativa da D'Rocha Soluções.</p></div>
    <div class="col-lg-6 d-grid gap-3">
      <div class="nd-caixa nd-mvv"><span class="rotulo">Missão</span><p class="mb-0">Aproximar quem quer comprar ou alugar de quem vende com seriedade, com anúncios de profissionais verificados e contato direto.</p></div>
      <div class="nd-caixa nd-mvv"><span class="rotulo">Visão</span><p class="mb-0">Ser a referência em imóveis e veículos no interior de Mato Grosso, lembrada pela confiança de quem compra e pelos resultados de quem anuncia.</p></div>
    </div>
  </section>
  <section><h2 class="h3 mb-3">Nossos valores</h2>
    <div class="row row-cols-1 row-cols-sm-2 row-cols-lg-5 g-3">{"".join(f'<div class="col"><div class="nd-caixa h-100 d-grid gap-2 align-content-start"><span class="nd-valor-ico">{ico(i)}</span><b>{t}</b><span class="small text-suave">{d}</span></div></div>' for i, t, d in VALORES)}</div></section>
  <section class="row g-4">
    <div class="col-md-6"><div class="nd-caixa h-100"><h2 class="h5">Para quem procura</h2><ol class="mb-0 d-grid gap-1"><li>Pesquise por cidade, preço e tipo, sem cadastro.</li><li>Veja fotos, ficha completa e a região no mapa.</li><li>Chame o anunciante no WhatsApp e combine a visita.</li></ol></div></div>
    <div class="col-md-6"><div class="nd-caixa h-100"><h2 class="h5">Para quem anuncia</h2><ol class="mb-0 d-grid gap-1"><li>Cadastre sua imobiliária ou revenda e envie o CRECI ou CNPJ.</li><li>Após a verificação, ganhe sua página própria e publique.</li><li>Acompanhe visualizações e contatos no painel.</li></ol><a class="btn btn-ipe mt-3" href="painel.html">Ver planos</a></div></div>
  </section>
  <section class="nd-caixa d-flex flex-wrap gap-3 align-items-center"><div class="me-auto"><h2 class="h5 mb-1">Fale com a gente</h2><span class="text-suave">contato@negociosdiarios.com.br · Tangará da Serra, MT</span></div><a class="btn btn-zap" href="#">{ico("zap")} WhatsApp do suporte</a></section>
</main>"""

# --- ADMIN › IDENTIDADE DO SITE (logo, textos institucionais, contatos) -------
def upload(id_, rotulo, ajuda_txt, previa):
    return f"""<div class="col-md-6"><div class="nd-upload"><div class="nd-upload-previa">{previa}</div>
      <div class="d-grid gap-1" style="min-width:0"><b class="small">{rotulo}</b><span class="form-text m-0">{ajuda_txt}</span>
      <label class="btn btn-contorno btn-sm justify-self-start" for="{id_}" style="justify-self:start">Trocar arquivo</label><input id="{id_}" type="file" class="d-none" accept="image/svg+xml,image/png,image/webp"></div></div></div>"""

ADMIN_SITE = f"""<main class="container mt-4">
  <div class="row g-4">
    <aside class="col-lg-3">{lateral_admin("config")}</aside>
    <form class="col-lg-9 d-grid gap-4" onsubmit="event.preventDefault();document.getElementById('ok-site').hidden=false">
      <h1 class="h4 m-0">Identidade do site</h1>
      {ajuda(["Aqui você troca o logo do Negócios Diários e os textos da página <b>Sobre</b>, sem programar.",
              "Prefira <b>SVG</b> para os logos: fica nítido em qualquer tela. PNG também é aceito (fundo transparente).",
              "O <b>símbolo</b> vira o ícone da aba do navegador (favicon) e o ícone ao salvar o site na tela do celular.",
              "A <b>imagem de compartilhamento</b> aparece quando alguém envia o link do site no WhatsApp ou Facebook.",
              "Toda troca fica no histórico: dá para voltar à versão anterior."], aberta=True)}
      <div class="nd-caixa d-grid gap-3"><h2 class="h6 m-0">Logos e ícones</h2>
        <div class="row g-3">
          {upload("lg-escuro", "Símbolo para fundo escuro (cabeçalho e rodapé)", "Quadrado, SVG ou PNG 512×512, até 500 KB.", '<span class="nd-previa-escura"><img src="img/simbolo-ipe.svg" width="44" height="44" alt=""></span>')}
          {upload("lg-claro", "Símbolo para fundo claro (e-mails, documentos, favicon)", "Quadrado, SVG ou PNG 512×512, até 500 KB.", '<img src="img/simbolo.svg" width="44" height="44" alt="">')}
          {upload("lg-compl", "Logo completo (opcional)", "Símbolo + nome numa imagem só. Se enviado, substitui o símbolo + texto no cabeçalho. Altura 80 px, até 500 KB.", '<span class="small text-suave">Não enviado</span>')}
          {upload("og", "Imagem de compartilhamento", "1200×630 px, JPG ou PNG, até 1 MB.", '<span class="nd-og">Negócios Diários</span>')}
        </div></div>
      <div class="nd-caixa row g-3 mx-0"><h2 class="h6 m-0 col-12 px-0">Nome e slogan</h2>
        {campo("s-nome", "Nome do site", "Negócios Diários", "", "text", "col-md-6")}
        {campo("s-regiao", "Linha abaixo do nome", "Imóveis e veículos de Mato Grosso", "Muda quando você liberar outros estados.", "text", "col-md-6")}
        {campo("s-slogan", "Slogan", "Os melhores negócios da sua região, todos os dias.")}
      </div>
      <div class="nd-caixa row g-3 mx-0"><h2 class="h6 m-0 col-12 px-0">Página Sobre</h2>
        <div class="col-12"><label class="form-label" for="s-quem">Quem somos</label><textarea id="s-quem" class="form-control" rows="4">Nascemos em Tangará da Serra para resolver um problema simples: os bons negócios da região ficavam espalhados em grupos, sites nacionais e placas na rua.</textarea></div>
        <div class="col-md-6"><label class="form-label" for="s-missao">Missão</label><textarea id="s-missao" class="form-control" rows="3">Aproximar quem quer comprar ou alugar de quem vende com seriedade, com anúncios de profissionais verificados e contato direto.</textarea></div>
        <div class="col-md-6"><label class="form-label" for="s-visao">Visão</label><textarea id="s-visao" class="form-control" rows="3">Ser a referência em imóveis e veículos no interior de Mato Grosso, lembrada pela confiança de quem compra e pelos resultados de quem anuncia.</textarea></div>
        <div class="col-12"><span class="form-label d-block">Valores <span class="text-suave fw-normal text-lowercase">(arraste para ordenar)</span></span>
          <div class="d-grid gap-2">{"".join(f'<div class="input-group"><span class="input-group-text">⋮⋮</span><input class="form-control" style="max-width:200px" value="{t}" aria-label="Valor"><input class="form-control" value="{d}" aria-label="Descrição do valor"></div>' for _, t, d in VALORES)}
          <button class="btn btn-contorno btn-sm" type="button" style="justify-self:start">{ico("mais")} Adicionar valor</button></div></div>
      </div>
      <div class="nd-caixa row g-3 mx-0"><h2 class="h6 m-0 col-12 px-0">Contatos do site</h2>
        {campo("s-zap", "WhatsApp do suporte", "(65) 9 0000-0000", "", "tel", "col-md-6")}
        {campo("s-email", "E-mail de contato", "contato@negociosdiarios.com.br", "", "email", "col-md-6")}
        {campo("s-priv", "E-mail de privacidade (LGPD)", "privacidade@negociosdiarios.com.br", "Canal obrigatório para pedidos dos titulares de dados.", "email", "col-md-6")}
        {campo("s-insta", "Instagram", "@negociosdiarios", "", "text", "col-md-6")}
      </div>
      <div class="d-flex gap-2 justify-content-end"><a class="btn btn-contorno" href="sobre.html">Ver página Sobre</a><button class="btn btn-nd" type="submit">Salvar alterações</button></div>
      <div id="ok-site" class="alert alert-success py-2 mb-0" role="status" hidden>Alterações salvas. O site já mostra a nova versão.</div>
    </form>
  </div>
</main>"""

PAGINAS = {"sobre.html": ("Sobre nós", "", SOBRE), "admin-site.html": ("Identidade do site · Admin", "", ADMIN_SITE),
           "admin-cidades.html": ("Cidades atendidas · Admin", "", ADMIN_CIDADES),
           "painel-loja.html": ("Página da loja", "", PAINEL_LOJA),"home.html": ("Início", "", HOME), "busca.html": ("Imóveis à venda", "imoveis", BUSCA),
           "anuncio.html": ("Casa 3 quartos", "imoveis", ANUNCIO), "loja.html": ("Serra Imóveis", "lojas", LOJA),
           "painel.html": ("Painel do anunciante", "", PAINEL)}

if __name__ == "__main__":
    for arquivo, (titulo, ativo, corpo) in PAGINAS.items():
        (PASTA / arquivo).write_text(pagina(titulo, ativo, corpo), encoding="utf-8")
        print("gerado:", arquivo)
