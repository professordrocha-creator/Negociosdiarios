# Publicidade — venda direta

**Decisão:** só publicidade vendida direto a empresas da região.
Sem Google AdSense (paga pouco com tráfego baixo, deixa o site lento, pode
mostrar concorrentes e exige consentimento de cookies de rastreamento).

## Espaços (máx. 3 por página)
| Formato | Onde | Tamanho | Preço |
|---|---|---|---|
| Banner topo | Todas as páginas | 970×90 desktop / 320×100 celular | R$ 299–599/mês |
| Card patrocinador | Rodapé da home (3 vagas) | logo + frase + link | R$ 149–299/mês |
| Anúncio nativo | Topo dos resultados de busca | texto + link, por cidade | R$ 49,90/semana |

## Regras de negócio
1. Rótulo **"Publicidade"** sempre visível (transparência com o visitante).
2. Um contrato ativo por vaga; se houver mais de um, **rodízio** a cada carregamento.
3. Contrato com `inicio` e `fim`: entra e sai do ar sozinho (tarefa Celery diária).
4. Imobiliária, corretor ou revenda **só compra publicidade se for assinante**
   (não vender visibilidade a concorrente de quem paga plano).
5. Segmentação simples: por cidade e por seção (imóveis / veículos / home).
6. Imagens passam pelo mesmo tratamento das fotos (WebP, sem EXIF, limite de tamanho).
7. Link externo com `rel="sponsored noopener"`.

## Métricas (o que faz o cliente renovar)
- Impressões e cliques por banner, contados **sem dado pessoal** (sem IP, sem cookie).
- Clique passa por `/publicidade/clique/<id>/` → registra → redireciona (só http/https).
- Relatório mensal em PDF/página enviado por e-mail ao anunciante.

## Modelo de dados (app `publicidade`)
```
Patrocinador (nome, CNPJ, contato, anunciante_vinculado opcional)
  └─N Contrato (vaga, cidade, secao, inicio, fim, valor, status)
        └─N Peca (imagem_desktop, imagem_celular, texto, link)
              └─N MetricaDiaria (data, impressoes, cliques)
```
Cobrança: fatura avulsa via Pix (mesma camada de `pagamentos`).

## Implementado na Sprint 7A (app `publicidade`)
- Modelos: `Patrocinador` (nome, CNPJ opcional, contato, e-mail, WhatsApp, loja do site opcional) →
  `Campanha` (posições, cidades liberadas opcionais, início, fim, valor, situação rascunho | ativa | pausada |
  encerrada | cancelada, histórico) → `Banner` (a peça: formato banner | card | nativo, imagem do computador e
  do celular, texto alternativo, título, texto, link, ativo) → `MetricaDiaria` (peça, dia, impressões,
  cliques). Nada se apaga.
- Posições (no máximo 3 espaços por página): Home: banner no topo; Busca: banner no topo e anúncio nativo no
  topo dos resultados (com a cidade da busca); Página do anúncio: banner (com a cidade do anúncio); Rodapé da
  home: até 3 cards de patrocinador.
- Tamanhos e peso na `Configuracao` (seção Publicidade): banner 970×90 e 320×100, card 400×400, 1 MB; a ajuda
  dos campos de imagem no admin mostra os valores atuais. Imagem maior na mesma proporção (±10%) é recortada
  pelo centro e reduzida; o Celery grava WebP sem EXIF e apaga o original.
- Exibição: tag `{% publicidade "posicao" cidade %}`; rótulo "Publicidade" sempre visível; link pelo clique
  com `rel="sponsored noopener"`; rodízio = sorteio a cada página (uma peça por campanha). Peça demo só com
  `MOSTRAR_DEMO`. Campanha com cidades só aparece nelas; sem cidade, em todo o site.
- Métricas somadas por dia, sem IP e sem cookie; robôs e trocas parciais do HTMX não contam.
- Rotina diária (Celery beat, 5h): campanha ativa que passou do fim vira "encerrada"; a equipe (Comercial,
  Administrador, superusuários) recebe e-mail `Configuracao.campanha_aviso_dias` (padrão 7) antes do fim,
  uma vez por campanha (recupera dia perdido).
- Regra 4: patrocinador ligado a uma loja do site só ativa campanha com assinatura ativa.
- Cobrança: ação "Gerar fatura (Pix)" na lista de campanhas → `Fatura` da campanha (a mesma de `pagamentos`:
  Pix estático, comprovante, confirmação em Cobrança › Faturas, régua de e-mails). O patrocinador não tem
  login: recebe por e-mail o link `/fatura/<token>/` (token aleatório) com o QR Code, o copia e cola e o
  "Já paguei". Pagar não liga a campanha sozinho: a equipe decide a situação.
- Admin › Publicidade › Campanhas › "Painel de publicidade": campanhas no ar, terminando em breve,
  impressões, cliques e CTR por campanha no período (padrão: 30 dias), exportação CSV (separador `;`,
  células protegidas contra fórmula).
- Ainda não: relatório mensal por e-mail ao patrocinador e a página "Anuncie sua marca" com números reais.

## Venda
- Alvos: construtoras, loteadoras, material de construção, móveis, despachantes,
  autopeças, seguradoras, cooperativas de crédito, cartórios/escritórios de advocacia imobiliária.
- Ferramenta: página **"Anuncie sua marca"** com números de acesso e preços (mídia kit).
- Primeiro mês com desconto para os 3 primeiros patrocinadores (prova social).
