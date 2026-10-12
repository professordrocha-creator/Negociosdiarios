# App `planos`

**Responsabilidade:** planos de assinatura, a assinatura de cada anunciante e as regras que
dependem dela (limite de anúncios, downgrade, atraso e renovação). Faturas e cobrança: app `pagamentos`. Não conhece o modelo de
anúncio: recebe funções de quem chama ou dispara sinais (ARQUITETURA §5).

**Modelos:**
- `Plano`: nome, slug, limite de anúncios, preço mensal e anual (Decimal), à venda, ordem,
  histórico. Os 3 iniciais vêm da migration `0002`; depois só mudam no admin.
- `Assinatura` (1:1 com o anunciante): plano, periodicidade (mensal | anual), início, vencimento,
  situação (ativa | em_atraso | cancelada), `demo`, histórico.
- `PedidoTrocaPlano`: pedido do painel (plano atual → novo, periodicidade), status
  (pendente | aprovado | recusado), motivo, quem decidiu e quando.

**Serviços (`services.py`):**
- `planos_a_venda()`, `assinatura_de(anunciante)`, `uso_do_plano(anunciante)` (publicados + em análise,
  contados por `anuncios.services.contar_no_plano`).
- `pode_publicar(anunciante)`: resposta rápida para a tela.
- `reservar_vaga(anunciante, contar, publicar)`: a decisão que vale; trava a assinatura com
  `select_for_update` (sem corrida entre dois cliques). Levanta `SemAssinaturaAtiva` ou `LimiteDoPlano`.
- `aplicar_downgrade(assinatura, plano_novo, anuncios, manter, pausar)`: pausa o que não foi escolhido.
- `proximo_vencimento`, `criar_assinatura`, `renovar_assinatura` (chamada por
  `pagamentos.services.confirmar_pagamento`: empurra o vencimento; em atraso volta a ativa e dispara
  `assinatura_regularizada`).
- `processar_atrasos()`: assinatura com **fatura** a pagar vencida há mais que `Configuracao.carencia_dias`
  → em_atraso, sinal `assinatura_em_atraso` e e-mail. Roda dentro da rotina diária de cobrança
  (`pagamentos.tasks.rotina_de_cobranca`, Celery beat, 6h).
- `pedir_troca`, `aprovar_pedido` (a fatura ainda aberta passa a cobrar o plano novo), `recusar_pedido`:
  pedidos de plano com e-mails (equipe: superusuários + Financeiro; anunciante).
- `precisa_escolher_anuncios`, `escolher_anuncios_para_manter`: plano menor que o uso; a escolha fica em
  `PedidoTrocaPlano.anuncios_manter` e a aprovação pausa o resto (`anuncios.services.pausar_por_downgrade`).
- `criar_assinaturas_demo` / `apagar_assinaturas_demo`: chamados pelo `criar/apagar_dados_demo` do core.

**Sinais (`sinais.py`):** `assinatura_em_atraso` e `assinatura_regularizada` (argumento `assinatura`).

**Telas:** `/painel/plano/` (Meu plano), `/painel/plano/escolher-anuncios/` e o card `templates/planos/_resumo_plano.html` (também no painel).
