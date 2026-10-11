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
- Clique passa por `/pub/<id>/clique/` → registra → redireciona.
- Relatório mensal em PDF/página enviado por e-mail ao anunciante.

## Modelo de dados (app `publicidade`)
```
Patrocinador (nome, CNPJ, contato, anunciante_vinculado opcional)
  └─N Contrato (vaga, cidade, secao, inicio, fim, valor, status)
        └─N Peca (imagem_desktop, imagem_celular, texto, link)
              └─N MetricaDiaria (data, impressoes, cliques)
```
Cobrança: fatura avulsa via Pix (mesma camada de `pagamentos`).

## Venda
- Alvos: construtoras, loteadoras, material de construção, móveis, despachantes,
  autopeças, seguradoras, cooperativas de crédito, cartórios/escritórios de advocacia imobiliária.
- Ferramenta: página **"Anuncie sua marca"** com números de acesso e preços (mídia kit).
- Primeiro mês com desconto para os 3 primeiros patrocinadores (prova social).
