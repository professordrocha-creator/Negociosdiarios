# App `core`

**Responsabilidade:** o que é comum ao site inteiro: verificação de saúde,
estados e cidades do IBGE (abrangência geográfica) e, depois, configuração do
site e páginas institucionais.

## Modelos
- `Estado`: `uf` (única), `nome`, `liberado`.
- `Cidade`: `codigo_ibge` (único), `nome`, `slug` (único **dentro da UF**),
  `uf` (FK para `Estado.uf`; no banco a coluna guarda a sigla), `liberada`,
  `ponto` (PostGIS, SRID 4326, sede do município).

O site mostra só cidades `liberada=True` de estados `liberado=True`
(docs/ARQUITETURA.md §9). `Regiao`, `Bairro` e `SolicitacaoCidade` entram na Sprint 1.

## Serviços (`services.py`)
- `banco_disponivel()`: testa a conexão com o banco; usado por `/saude/`.
- `carregar_municipios()`: carrega ou atualiza estados e cidades dos CSVs.
  É **idempotente**: atualiza só os dados do IBGE (nome, slug, UF, ponto) e
  nunca mexe em `liberado`/`liberada`. Na primeira carga, só MT nasce liberado
  e nenhuma cidade. Roda numa transação: com uma linha errada, nada é gravado.
- `liberar_cidades(queryset)`: libera cidades e devolve quantas mudaram.

## Comando
```bash
docker compose exec web python manage.py carregar_municipios
# opções: --estados ARQ --municipios ARQ --uf-liberada MT
```

## Admin
- **Estados:** liga/desliga `liberado`; mostra quantas cidades estão liberadas.
- **Cidades:** busca por nome ou código IBGE, filtros por UF e "liberada",
  ação em massa **"Liberar cidades selecionadas"** (avisa se o estado não está liberado).
- Estados e cidades não podem ser criados nem apagados no admin: vêm só da carga.

## Rotas
- `GET /saude/`: `200 {"status": "ok"}` ou `503` se o banco não responder.

## Dados: `core/dados/`
| Arquivo | Colunas | Registros |
|---|---|---|
| `estados.csv` | `codigo_ibge, uf, nome` | 27 |
| `municipios.csv` | `codigo_ibge, nome, uf, latitude, longitude` | 5.571 (MT: 142, inclui Boa Esperança do Norte, instalado em 2025) |

**Fonte:** repositório [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros)
(commit `503e2f7`, de 10/12/2025), que compila os códigos e nomes oficiais do
[IBGE](https://www.ibge.gov.br/explica/codigos-dos-municipios.php) com as coordenadas da sede de cada município.
Convertido para o formato acima (só as colunas usadas, UF em sigla, ordenado pelo código).

**Licença:** MIT, © 2016 Kelvin S. do Prado (texto completo em
`core/dados/LICENSE-municipios-brasileiros.txt`). Permite uso, cópia e modificação,
inclusive comercial, desde que se mantenha o aviso de copyright e da licença.
Os códigos e nomes de municípios são dados públicos do IBGE.

**Atualizar:** quando o IBGE criar ou renomear municípios, baixe a versão nova
da fonte, gere os CSVs no mesmo formato e rode `carregar_municipios` de novo.
A API de localidades do IBGE não fornece coordenadas, por isso não há comando
automático de atualização.
