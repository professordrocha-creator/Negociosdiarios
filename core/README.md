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
- `cidades_atendidas()`: cidades que aparecem no site (liberadas, de estados
  liberados), agrupadas por estado e em ordem alfabética. Usado pela home.
- `email_para_fila(mensagem)` / `enviar_email_agora(dados)`: transformam um e-mail do
  Django em dados simples para a fila e o enviam de verdade no worker (anexos ainda não).

## E-mail e tarefas (Celery)
- `email.py`: `CeleryEmailBackend` (o `EMAIL_BACKEND` do projeto). Todo `send_mail()`
  vira uma tarefa na fila; a página não espera o SMTP.
- `tasks.py`: `enviar_email` (envia com `EMAIL_BACKEND_REAL`; 5 novas tentativas se o
  SMTP falhar) e `batimento` (exemplo; o beat roda a cada 5 minutos).

## Comandos
```bash
docker compose exec web python manage.py carregar_municipios
# opções: --estados ARQ --municipios ARQ --uf-liberada MT
docker compose exec web python manage.py testar_celery   # fila + worker funcionando?
```

## Admin
- **Estados:** liga/desliga `liberado`; mostra quantas cidades estão liberadas.
- **Cidades:** busca por nome ou código IBGE, filtros por UF e "liberada",
  ação em massa **"Liberar cidades selecionadas"** (avisa se o estado não está liberado).
- Estados e cidades não podem ser criados nem apagados no admin: vêm só da carga.

## Rotas
- `GET /`: home provisória (busca visual, "em breve" para Destaques e Recém-anunciados, cidades atendidas).
- `GET /sobre/`: quem somos, missão, visão e valores (texto fixo até a Sprint 1).
- `GET /favicon.ico`: redireciona para `static/img/favicon.ico`.
- `GET /saude/`: `200 {"status": "ok"}` ou `503` se o banco não responder.

## Layout e identidade
- Templates em `templates/`: `base.html` + parciais `_topo.html`, `_rodape.html`,
  `_ajuda.html` (caixa "Sobre esta tela") e `_icones.html` (sprite SVG).
  Convertidos de `prototipo/_gerar.py`; a pasta `prototipo/` não é usada pelo Django.
- Ícones: `{% load nd %}` e `{% icone "casa" %}` (`templatetags/nd.py`).
- Context processor `site` (`context_processors.py`): `{{ site.nome }}`, `slogan`,
  `linha_regiao`, `email_contato`, `email_privacidade`, `empresa`, `cidade_sede`.
  Também expõe `mostrar_link_admin` (`services.mostrar_link_admin`): o rodapé só mostra
  o atalho "Admin" em dev (DEBUG) ou para a equipe logada; o endereço do admin é secreto.
  Por enquanto lê `SITE_*`
  do settings; na Sprint 1 passa a ler o modelo `Configuracao`.
- `static/`: Bootstrap 5.3.3 (CSS e JS locais, licença MIT), `nd.css` e os
  símbolos SVG do protótipo. Favicons (`favicon.ico`, `favicon-32.png`,
  `apple-touch-icon.png`, `icone-512.png`) desenhados a partir de `simbolo.svg`;
  na Sprint 1 serão gerados automaticamente quando o admin trocar o símbolo.
- `nd.css` só tem estilos usados pelos templates atuais. Card de anúncio, mapa,
  vitrine e painel voltam de `prototipo/css/nd.css` quando as telas existirem.
- Fontes em `static/fonts/` (woff2, subconjunto latin, versões variáveis):
  Bricolage Grotesque (títulos, pesos 600–800) e Figtree (texto, 400–700).
  Hospedadas no próprio site, sem Google Fonts: o IP do visitante não vai para
  terceiros (LGPD) e a CSP não precisa liberar outro domínio. Ambas sob a
  **SIL Open Font License 1.1** (OFL), que permite usar e redistribuir desde que
  a licença acompanhe os arquivos: ver `static/fonts/OFL-BricolageGrotesque.txt`
  e `static/fonts/OFL-Figtree.txt`. Origem: repositório `google/fonts`.

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
