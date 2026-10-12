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
- `DetalheVeiculo` (1:1, Sprint 4): versão do `catalogo` (FIPE), anos, km, combustível, câmbio, cor,
  portas, final da placa (1 dígito, opcional) e opcionais. `Anuncio.detalhe` devolve a ficha da categoria.
- `Foto`: ordem (a primeira é a capa), WebP 1600 e 400 e JPEG 1200×630 de compartilhamento; o envio original
  é apagado.

**Serviços (`services.py`):**
- Consultas: `anuncios_do_dono` (sempre a partir do dono: sem IDOR), `contar_no_plano`, `ids_no_plano`,
  `precisa_moderacao`, `pendencias`.
- Criar/editar: `criar_anuncio_imovel`, `criar_anuncio_veiculo` (título em branco = `titulo_do_veiculo`),
  `atualizar_anuncio`, `ponto`.
- Ciclo de vida: `enviar_para_publicacao` (via `planos.services.reservar_vaga`), `aprovar`, `recusar`,
  `pausar`, `reativar`, `pode_renovar`, `renovar`, `excluir` (lógica), `expirar_vencidos`.
- Planos: `pausar_por_atraso`, `reativar_apos_pagamento` (ligados em `receptores.py`), `pausar_por_downgrade`.
- Fotos: `vagas_de_foto`, `adicionar_fotos`, `processar_foto`, `reordenar_fotos`, `mover_foto`, `excluir_foto`.
- Vitrine pública: `anuncios_visiveis` (publicado, loja visível, cidade liberada), `visivel`, `url_publica`,
  `localizacao_publica` (exata, círculo aproximado com centro deslocado, ou nada), `mensagem_whatsapp`,
  `link_whatsapp`, `para_vitrine` (card), `mais_da_loja`, `parecidos`.
- Demo: `apagar_anuncios_demo`; `demo.py` cria os imóveis do demo.json no banco com fotos desenhadas pelo Pillow.

**Tarefas (`tasks.py`):** `processar_foto` (a cada envio) e `expirar_anuncios` (Celery beat, 3h).

**Telas:** `/painel/anuncios/novo/` e `/painel/anuncios/<codigo>/editar/` (+ `localizacao/`, `fotos/`,
`revisao/`), ações `/painel/anuncios/<codigo>/<pausar|reativar|renovar|excluir>/` (POST).
Públicas (`views_publicas.py`): `/anuncio/<codigo>-<slug>/` (página, "não está mais disponível" ou
prévia do dono) e `/anuncio/<codigo>/whatsapp/` (conta o clique e redireciona ao wa.me).
