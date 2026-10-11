# App `anuncios`

**Responsabilidade:** o anúncio (imóvel agora; veículo na Sprint 4), as fotos, o ciclo de vida
(rascunho → análise → publicado → pausado/expirado → excluído) e a moderação. Usa a trava do
plano do app `planos` para publicar e reage aos sinais de atraso e pagamento.

**Modelos:**
- `Anuncio`: base comum (anunciante, categoria, código público `ND-IM-00001`, título, slug, descrição,
  preço, cidade, bairro, situação, `pausado_por`, moderação, publicado_em, expira_em, destaque_ate,
  `demo`, histórico). Proxy `AnuncioEmModeracao` = fila de moderação no admin.
- `DetalheImovel` (1:1): tipo, modalidade, quartos, banheiros, vagas, áreas, IPTU, endereço e ponto
  **privados**, `exibir_localizacao` (padrão aproximada).
- `Foto`: ordem (a primeira é a capa), WebP 1600 e 400; o envio original é apagado.

**Serviços (`services.py`):**
- Consultas: `anuncios_do_dono` (sempre a partir do dono: sem IDOR), `contar_no_plano`, `ids_no_plano`,
  `precisa_moderacao`, `pendencias`.
- Criar/editar: `criar_anuncio_imovel`, `atualizar_anuncio`, `ponto`.
- Ciclo de vida: `enviar_para_publicacao` (via `planos.services.reservar_vaga`), `aprovar`, `recusar`,
  `pausar`, `reativar`, `pode_renovar`, `renovar`, `excluir` (lógica), `expirar_vencidos`.
- Planos: `pausar_por_atraso`, `reativar_apos_pagamento` (ligados em `receptores.py`), `pausar_por_downgrade`.
- Fotos: `vagas_de_foto`, `adicionar_fotos`, `processar_foto`, `reordenar_fotos`, `mover_foto`, `excluir_foto`.
- Demo: `apagar_anuncios_demo`.

**Tarefas (`tasks.py`):** `processar_foto` (a cada envio) e `expirar_anuncios` (Celery beat, 3h).

**Telas:** `/painel/anuncios/novo/` e `/painel/anuncios/<codigo>/editar/` (+ `localizacao/`, `fotos/`,
`revisao/`), ações `/painel/anuncios/<codigo>/<pausar|reativar|renovar|excluir>/` (POST). Página
pública do anúncio: Sprint 3, parte B.
