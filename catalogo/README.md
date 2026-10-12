# App `catalogo`

**Responsabilidade:** catálogo de veículos (tipo → marca → modelo → versão) usado no anúncio de
veículo. Nunca texto livre (docs/BOAS_PRATICAS.md §1). Preço FIPE não é guardado nem mostrado
por enquanto.

**Fonte dos dados:** Tabela FIPE — Fundação Instituto de Pesquisas Econômicas, consulta pública em
<https://veiculos.fipe.org.br/> (API `ConsultarTabelaDeReferencia`, `ConsultarMarcas` e
`ConsultarModelos`). O arquivo `dados/fipe.csv` foi gerado da tabela de **outubro/2026**
(código 338; ver `dados/fipe_referencia.txt`): 11.422 versões de carros, caminhonetes, motos e caminhões.

**Modelos:**
- `Marca` (nome, slug único, ativo): uma marca serve a vários tipos (Toyota faz carro e caminhonete).
- `Modelo` (marca, tipo, nome, slug, ativo): único por marca + tipo + slug.
- `Versao` (modelo, nome, código FIPE, ativo): única por modelo + nome.

**Como a FIPE vira catálogo (`services.py`):**
- A FIPE não separa modelo e versão ("Hilux CD SRV 4x4 2.8 TDI Diesel Aut."): o modelo é a 1ª palavra,
  ou as 2 primeiras quando a 1ª sozinha não identifica ("Grand Siena", "Range Rover", "Classe C").
- A FIPE junta picapes e carros: as picapes conhecidas (`PICAPES`, marca RAM) viram "caminhonete".
- Marcas em CAIXA ALTA (motos, caminhões) ficam legíveis; "GM - Chevrolet" → "Chevrolet",
  "VW - VolksWagen" → "Volkswagen" (assim a marca de carro, moto e caminhão é um registro só).

**Comandos:**
- `python manage.py carregar_catalogo [--arquivo X]`: carrega o CSV no banco, em lote. Idempotente:
  atualiza sem duplicar, nunca apaga (anúncios antigos apontam para as versões) e não reativa o que
  o admin escondeu. Rodar depois do `migrate` num banco novo.
- `python manage.py atualizar_catalogo_fipe [--pausa 1.5]` (opcional): baixa a tabela do mês da FIPE
  e reescreve `dados/fipe.csv` e `dados/fipe_referencia.txt` (não mexe no banco). Uma requisição por
  marca (~240), com pausa e espera progressiva se a FIPE pedir (HTTP 429); leva uns 10 minutos.
  Depois: conferir o diff, rodar `carregar_catalogo` e commitar o CSV.

**Serviços para o formulário:** `marcas_do_tipo`, `modelos_da_marca`, `versoes_do_modelo` (selects
encadeados do anúncio de veículo, via HTMX em `anuncios:catalogo`).

**Admin:** consulta e "ativo" editável na lista (esconder do formulário); sem criar nem apagar.
