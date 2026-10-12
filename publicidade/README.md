# App `publicidade`

**Responsabilidade:** publicidade vendida direto a empresas da região (Sprint 7A; docs/PUBLICIDADE.md): cadastro de
patrocinadores e campanhas, peças (banner, card patrocinador, anúncio nativo), exibição com rodízio, clique contado,
métricas por dia sem dado pessoal, rotina diária e painel do admin com CSV. Sem AdSense.

**Modelos:** `Patrocinador` → `Campanha` (posições, cidades, início, fim, valor, situação; histórico) → `Banner`
(a peça; imagens WebP geradas pelo Celery) → `MetricaDiaria` (impressões e cliques por peça e dia). Nada se apaga.

**Serviços (`services.py`):**
- `tamanhos`, `validar_imagem`, `processar_banner` (tarefa `tasks.processar_banner`): tamanho e peso da
  `Configuracao`, recorte central na proporção, WebP sem EXIF, original apagado.
- `no_ar`, `escolher(posicao, cidade, quantos)` (rodízio por sorteio, uma peça por campanha), `registrar`
  (impressão/clique do dia, sem robôs e sem HTMX), `link_seguro` (só http/https).
- `conferir_patrocinador` (loja do site só compra com assinatura ativa).
- `rotina_de_publicidade` (tarefa diária às 5h): `encerrar_vencidas` e `avisar_fim_proximo` (e-mail à equipe).
- `painel(de, ate)` e `painel_csv` (células protegidas contra fórmula).
- `criar_publicidade_demo` / `apagar_publicidade_demo` (chamados pelo `criar/apagar_dados_demo` do core).

**Exibição:** `{% load publicidade %}{% publicidade "home_topo" %}` (com cidade: `{% publicidade "busca_topo" cidade %}`),
parcial `templates/publicidade/_espaco.html`. **Clique:** `/publicidade/clique/<id>/`.

**Admin:** Patrocinadores, Campanhas (peças na mesma tela, ação "Gerar fatura (Pix)"), Painel de publicidade e CSV.
A fatura da campanha é a `pagamentos.Fatura` (página pública `/fatura/<token>/` para o patrocinador pagar).

**Testes:** `tests/test_publicidade.py`.
