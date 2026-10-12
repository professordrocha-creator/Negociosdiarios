# Pagamentos

## Resumo (decisão da Sprint 6, 2026-10-12)
- **V1 = cobrança manual assistida, sem gateway.** O sistema gera as faturas, mostra um **Pix estático**
  (copia e cola + QR Code com o valor e o identificador da fatura), recebe o **comprovante** enviado pelo
  anunciante e a equipe **confirma no admin**. Sem API externa, sem webhook, sem taxa de intermediação.
- **V2 = integração com Mercado Pago** (ou outro gateway): Pix com confirmação automática por webhook e
  cartão recorrente. Fica para depois da validação do negócio (ver "V2" abaixo).

## V1 — como funciona (app `pagamentos`)
| Passo | O que acontece |
|---|---|
| 1. Fatura | A rotina diária (Celery beat, 6h) gera a fatura do próximo ciclo **X dias antes** do vencimento da assinatura (`Configuracao.fatura_antecedencia_dias`, padrão 10) e manda o e-mail "fatura disponível". Uma fatura por ciclo (`assinatura` + `competência`). |
| 2. Pagamento | Painel › Faturas: valor, vencimento, **Pix copia e cola** (botão Copiar) e **QR Code**. Opcional: a equipe cola um **link de boleto** na fatura. |
| 3. "Já paguei" | O anunciante envia o comprovante (PDF, JPG, PNG ou WebP; limite `Configuracao.limite_comprovante_kb`). A fatura fica **aguardando confirmação** e o Financeiro recebe e-mail. |
| 4. Confirmação | Admin › Cobrança › Faturas: **Confirmar pagamento** (forma + observação) renova a assinatura e, se estava em atraso, **reativa os anúncios**; **Recusar comprovante** (motivo por e-mail) devolve a fatura para aberta/vencida. |
| 5. Atraso | Fatura sem pagamento vira **vencida** no dia seguinte ao vencimento. Passada a carência (`Configuracao.carencia_dias`, padrão 5), a assinatura fica **em atraso** e os anúncios são **pausados** (nunca apagados). Comprovante aguardando confirmação segura a pausa até a equipe decidir. |
| 6. Régua | E-mails automáticos: fatura disponível, 3 dias antes, no dia, 1 e 3 dias depois; mais "pagamento confirmado" e "comprovante recusado". **Textos editáveis** no admin (Cobrança › E-mails de cobrança), com variáveis `{loja}`, `{valor}`, `{vencimento}`, `{competencia}`, `{codigo}`, `{link}`, `{motivo}`, `{site}`. |

Situações da fatura: `aberta` → (`aguardando_confirmacao`) → `paga`; ou `vencida`; ou `cancelada` (ação do
admin, com motivo). Nada se apaga. O "Registrar pagamento manual" da assinatura baixa a fatura em aberto
(ou cria a do ciclo e baixa), para pagamentos combinados fora do site.

### Pix estático (BR Code)
- Gerado em `pagamentos/pix.py` pelo padrão EMV do Banco Central (Manual de Padrões para Iniciação do Pix):
  campos ID + tamanho + valor, conta `br.gov.bcb.pix` + chave, valor (campo 54), nome (até 25) e cidade
  (até 15) sem acento, identificador da fatura no campo 62-05 (ex.: `NDFT00012`) e **CRC16-CCITT** no fim.
  Teste contra o exemplo oficial do Banco Central (CRC `1D3D`).
- Configuração no `.env`: `PIX_CHAVE` (CPF/CNPJ só dígitos, e-mail, celular com +55 ou chave aleatória),
  `PIX_NOME` e `PIX_CIDADE`. Vazios = a tela avisa "Pix ainda não disponível" (sem QR Code).
- QR Code com `segno` (SVG embutido como `data:`; a CSP libera `data:` só em imagens).
- O Pix estático **não confirma sozinho**: o banco do recebedor mostra o identificador no extrato e a equipe
  confere antes de confirmar. Por isso o comprovante e a confirmação manual.

### Comprovantes (dado pessoal: ver docs/LGPD.md)
- Guardados no armazenamento **privado** (`STORAGES["privado"]`): pasta `privado/` fora da mídia pública em
  dev; bucket próprio sem domínio público (`S3_BUCKET_PRIVADO`, URLs assinadas) em produção.
- Só saem por views que conferem quem pede: o dono da fatura (painel) ou a equipe com permissão de ver
  faturas (admin). Resposta sem cache, `nosniff` e CSP `sandbox`.
- Imagem: tipo real conferido pelo Pillow e regravada sem EXIF. PDF: precisa ser PDF inteiro e sem conteúdo
  ativo (JavaScript, Launch, arquivos embutidos). Nome aleatório (nunca o nome enviado).

## V2 — Mercado Pago (depois da validação)
- **Dá para integrar** com a conta Mercado Pago atual. A API de Assinaturas cobra mensal ou anual
  automaticamente; cobrança **recorrente automática** é no **cartão** e o Pix funciona como pagamento
  **avulso por ciclo** (QR Code dinâmico a cada vencimento, confirmado por webhook).
- O código usará uma **camada de gateway** (`pagamentos/gateways/`), para trocar de conta (CPF → CNPJ) ou de
  provedor (Asaas, Pagar.me) sem mexer no resto. A `Fatura` da V1 continua sendo a cobrança; o gateway só
  passa a confirmar o pagamento (o mesmo `confirmar_pagamento`).
- Fluxo do webhook (obrigatório):
  1. Receber POST → validar `x-signature` → responder 200 rápido.
  2. Gravar o evento bruto em `EventoPagamento` (id único = idempotência).
  3. Celery consulta o pagamento **na API** (nunca confiar só no corpo recebido).
  4. Aprovado → `confirmar_pagamento` (fatura paga → assinatura renovada → anúncios reativados).

## Atenção: conta no CPF (não é conselho jurídico/contábil)
- Os clientes são imobiliárias e revendas: **vão pedir nota fiscal**.
- Receita de empresa recebida no CPF pode cair no carnê-leão com tributação alta.
- Antes de cobrar o 1º cliente: falar com um contador sobre abrir CNPJ
  (verificar se a atividade cabe no MEI ou se precisa ME no Simples Nacional).
- A chave Pix do `.env` deve ser a da empresa (CNPJ) quando ela existir.
