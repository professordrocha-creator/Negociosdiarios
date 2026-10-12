# App `estatisticas`

**Responsabilidade:** contar visualizações e cliques no WhatsApp de cada anúncio, **sem dado pessoal**
(docs/LGPD.md). O anunciante vê os números no painel.

**Modelo:** `EstatisticaDiaria` (anúncio, dia, visualizações, cliques no WhatsApp, `demo`): só totais.

**Serviços (`services.py`):**
- `registrar(request, anuncio, evento)`: conta `visualizacoes` ou `cliques_whatsapp` uma vez por visitante
  por dia. O visitante vira um hash SHA-256 (sal aleatório do dia + IP + navegador) guardado só no cache
  até o fim do dia; o sal expira em 2 dias. Robôs (`e_robo`, pelo User-Agent, inclusive prévias de link do
  WhatsApp/Facebook) e o dono do anúncio não contam. Nunca derruba a página.
- `totais_por_anuncio(ids)`, `totais_da_loja(anunciante_id, dias=30)`, `total_de_visualizacoes(anuncio)`.

**Quem chama:** `anuncios.views_publicas` (página do anúncio e redirecionamento do WhatsApp) e o painel.
