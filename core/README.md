# App `core`

**Responsabilidade:** o que é comum ao site inteiro: verificação de saúde,
configuração do site, cidades/estados (IBGE) e páginas institucionais.

**Modelos:** nenhum por enquanto (`Estado` e `Cidade` entram na etapa 4 da Sprint 0).

**Serviços (`services.py`):**
- `banco_disponivel()` — testa a conexão com o banco; usado por `/saude/`.

**Rotas:**
- `GET /saude/` — `200 {"status": "ok"}` ou `503` se o banco não responder.
  Usada pelo healthcheck do Docker e pelo monitor de uptime.
