# Pagamentos — Mercado Pago

## Resumo
- **Dá para integrar** com a conta Mercado Pago atual. A API de Assinaturas
  cobra mensal ou anual automaticamente.
- Cobrança **recorrente automática** é feita no **cartão**. Pix funciona como
  pagamento **avulso por ciclo** (gera QR Code a cada vencimento).
- O código usa uma **camada de gateway** (`pagamentos/gateways/`), então trocar
  de conta (CPF → CNPJ) ou de provedor (Asaas, Pagar.me) não muda o resto do sistema.

## Fases
| Versão | Como funciona |
|---|---|
| V1 | Fatura gerada pelo sistema; anunciante paga Pix (QR Code via API de Pagamentos); webhook confirma e libera o plano. Sem cartão ainda. |
| V2 | Assinatura com cartão (`preapproval`) + Pix por ciclo como alternativa; renovação automática; régua de cobrança (aviso 3 dias antes, no dia, 3 dias depois). |

## Fluxo do webhook (obrigatório)
1. Receber POST → validar `x-signature` → responder 200 rápido.
2. Gravar evento bruto em `EventoPagamento` (id único = idempotência).
3. Celery consulta o pagamento **na API** (nunca confiar só no corpo recebido).
4. Aprovado → marca fatura paga → reativa anunciante/anúncios.

## Atenção: conta no CPF (não é conselho jurídico/contábil)
- Os clientes são imobiliárias e revendas: **vão pedir nota fiscal**.
- Receita de empresa recebida no CPF pode cair no carnê-leão com tributação alta.
- Antes de cobrar o 1º cliente: falar com um contador sobre abrir CNPJ
  (verificar se a atividade cabe no MEI ou se precisa ME no Simples Nacional).
- Para testar e desenvolver, a conta CPF + credenciais de teste bastam.
