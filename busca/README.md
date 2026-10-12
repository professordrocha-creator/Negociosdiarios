# App `busca`

**Responsabilidade:** as páginas de busca `/imoveis/` e `/veiculos/` (todas as cidades e por cidade,
`/imoveis/mt/tangara-da-serra/`): filtros, busca por texto, ordem, paginação, chips, SEO e sitemap.
Não tem modelo próprio: lê os anúncios visíveis (`anuncios.services.anuncios_visiveis`) e usa o índice
de texto do `Anuncio` (`anuncios/indice.py`).

**Formulários (`forms.py`):** `FiltrosImovel` e `FiltrosVeiculo` (GET). A ordem dos campos é a ordem
dos parâmetros na URL limpa. Valor inválido é descartado (`VariasEscolhas` mantém os válidos de uma lista).

**Serviços (`services.py`):**
- `cidades_liberadas`, `cidade_da_url`, `cidade_escolhida`, `caminho`.
- `opcoes(categoria, cidade, marca)`: bairros, marcas e modelos que têm anúncio no ar.
- `buscar(categoria, cidade, filtros)`: filtros + texto (`websearch` em `pt_unaccent` OU semelhança
  pg_trgm) + ordem (com texto e sem ordem: relevância).
- `querystring`, `url`, `url_canonica` (sem ordem e página), `indexavel` (sem texto e até 2 filtros).
- `titulo`, `descricao`, `chips`, `rotulos`, `paginas_do_sitemap`.

**View (`views.py`):** `busca` — sem JS redireciona para a URL limpa; com HTMX responde direto e manda
a URL limpa em `HX-Push-Url` (o template troca `#resultados` e, por `hx-select-oob`, o bairro/modelo).

**Testes:** `tests/test_busca.py` (filtros, texto, HTMX, chips, SEO, sitemap, home) e
`tests/test_desempenho.py` (2.000 anúncios gerados no teste; consultas e tempo por página; índices).
