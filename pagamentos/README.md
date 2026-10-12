# App `pagamentos`

**Responsabilidade:** cobrança manual assistida da V1 (Sprint 6; docs/PAGAMENTOS.md): faturas das
assinaturas, Pix estático (copia e cola + QR Code), comprovante do anunciante ("Já paguei"), confirmação
pela equipe, régua de e-mails e o atraso ligado à fatura vencida. Sem gateway (Mercado Pago na V2).

**Modelos:**
- `Fatura`: assinatura (PROTECT), código `ND-FT-00001`, competência e fim do período, descrição
  ("Profissional · mensal"), valor (Decimal), vencimento, situação (aberta | aguardando_confirmacao | paga |
  vencida | cancelada), pago em, forma, link do boleto (opcional), comprovante (armazenamento **privado**),
  enviado em, observação, motivo da recusa, confirmado por, `avisos_enviados`, `demo`, histórico.
  Única por assinatura + competência (cancelada não conta).
- `ModeloEmailCobranca`: assunto e texto de cada e-mail automático (editáveis no admin; variáveis
  `{loja}`, `{valor}`, `{vencimento}`, `{competencia}`, `{codigo}`, `{link}`, `{motivo}`, `{site}`).

**Pix (`pix.py`):** `br_code(chave, nome, cidade, valor, identificador)` (EMV do Banco Central + CRC16),
`qr_code_svg(codigo)` (segno, data URI). Chave, nome e cidade vêm de `PIX_CHAVE`, `PIX_NOME`, `PIX_CIDADE`.

**Serviços (`services.py`):**
- Rotina diária `rotina_de_cobranca(hoje)` (tarefa `tasks.rotina_de_cobranca`, Celery beat às 6h):
  `gerar_faturas` (X dias antes: `Configuracao.fatura_antecedencia_dias`) → `marcar_vencidas` →
  `planos.services.processar_atrasos` (fatura a pagar vencida além da carência pausa os anúncios) →
  `enviar_avisos` (3 dias antes, no dia, 1 e 3 dias depois; uma vez por fatura).
- `dados_pix(fatura)`, `faturas_da_loja(anunciante)` (sempre filtrado pela loja: sem IDOR), `faturas_em_aberto`.
- `comprovante_limpo` / `enviar_comprovante(fatura, arquivo, recado)`: valida (limite da Configuracao; imagem
  regravada sem EXIF; PDF sem conteúdo ativo), guarda e avisa o Financeiro.
- `confirmar_pagamento` (renova a assinatura uma vez só; reativa os anúncios se estava em atraso),
  `recusar_comprovante`, `cancelar_fatura`, `registrar_pagamento_manual` (ação da assinatura no admin),
  `atualizar_fatura_aberta` (troca de plano), `resumo_cobranca` (painel do admin).
- `criar_faturas_demo` / `apagar_faturas_demo`: chamados pelo `criar/apagar_dados_demo` do core.

**Armazenamento (`armazenamento.py`):** `STORAGES["privado"]` (pasta `privado/` em dev; bucket
`S3_BUCKET_PRIVADO` sem domínio público em produção). O arquivo só sai pelas views com permissão.

**Publicidade (Sprint 7A):** `Fatura` também pode ser de uma `campanha` (`gerar_fatura_campanha`); o
patrocinador paga pela página pública `/fatura/<token>/` (`fatura_publica`, `fatura_publica_ja_paguei`).
Confirmar a fatura de campanha não mexe em assinatura.

**Telas:** `/painel/faturas/` (abertas com Pix, aguardando confirmação e histórico),
`/painel/faturas/<codigo>/ja-paguei/` (POST) e `/painel/faturas/<codigo>/comprovante/`.
**Admin:** Cobrança › Faturas (filtros, "Painel de cobrança", ações Confirmar pagamento / Recusar
comprovante / Cancelar, comprovante pelo admin) e Cobrança › E-mails de cobrança.

**Testes:** `tests/test_pix.py` (exemplo do Banco Central, CRC, campos), `tests/test_cobranca.py` (regras,
régua, atraso, demo) e `tests/test_telas.py` (painel, IDOR, comprovante, admin e permissões).
