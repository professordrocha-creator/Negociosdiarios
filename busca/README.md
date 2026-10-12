# App `busca`

**Responsabilidade:** as páginas de busca `/imoveis/` e `/veiculos/` (todas as cidades e por cidade,
`/imoveis/mt/tangara-da-serra/`): filtros, busca por texto, ordem, paginação, chips, SEO, sitemap e o
mapa (Sprint 5: JSON dos pontos, cartões dos marcadores e "Buscar nesta área").
Não tem modelo próprio: lê os anúncios visíveis (`anuncios.services.anuncios_visiveis`) e usa o índice
de texto do `Anuncio` (`anuncios/indice.py`).

**Formulários (`forms.py`):** `FiltrosImovel` e `FiltrosVeiculo` (GET). A ordem dos campos é a ordem
dos parâmetros na URL limpa. Valor inválido é descartado (`VariasEscolhas` mantém os válidos de uma lista).
`area` (`CampoArea`, oculto): "oeste,sul,leste,norte" do mapa, normalizado em 5 casas.

**Serviços (`services.py`):**
- `cidades_liberadas`, `cidade_da_url`, `cidade_escolhida`, `caminho`.
- `opcoes(categoria, cidade, marca)`: bairros, marcas e modelos que têm anúncio no ar.
- `buscar(categoria, cidade, filtros)`: filtros + texto (`websearch` em `pt_unaccent` OU semelhança
  pg_trgm) + ordem (com texto e sem ordem: relevância).
- `querystring`, `url`, `url_canonica` (sem ordem e página), `indexavel` (sem texto e até 2 filtros).
- `titulo`, `descricao`, `chips`, `rotulos`, `paginas_do_sitemap`.
- Mapa: `dados_do_mapa(categoria, cidade, filtros)` (imóvel: `ponto_publico` por anúncio; veículo: uma
  loja com `mostrar_no_mapa` por ponto), `url_do_mapa`, `preco_curto`, `limite_de_pontos`
  (`settings.MAPA_LIMITE_PONTOS`); filtro de área com `Polygon.from_bbox` (sempre o ponto público).

**View (`views.py`):** `busca` — sem JS redireciona para a URL limpa; com HTMX responde direto e manda
a URL limpa em `HX-Push-Url` (o template troca `#resultados` e, por `hx-select-oob`, o bairro/modelo).
`mapa` (JSON, cache de 60 s, noindex), `cartao_anuncio` e `cartao_loja` (HTML do card do marcador; 404
se não visível). O mapa fica fora de `#resultados` e o `static/js/mapa-busca.js` recarrega os pontos
pela `data-mapa-url` do `#resultados` novo a cada troca do HTMX.

**Testes:** `tests/test_busca.py` (filtros, texto, HTMX, chips, SEO, sitemap, home) e
`tests/test_desempenho.py` (2.000 anúncios gerados no teste; consultas e tempo por página; índices) e
`tests/test_mapa.py` (JSON, ponto real nunca exposto, só bairro, limite, área, cartões, lojas, CSP).
