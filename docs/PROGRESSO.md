# Progresso (checkpoint)

**Em andamento:** ajustes no cadastro de publicidade (admin), aguardando conferência e commit do Daniel.

**Feito:** Prévia da peça com as duas imagens + "arquivo atual"; banner com UMA imagem (celular gerado por corte
central; imagem própria do celular em "Avançado", campo `Banner.celular_propria`, migration 0003 marca as peças
antigas); campos escondidos por formato (static/js/publicidade-admin.js); "Onde aparece" em 3 escolhas simples
(forms.POSICOES_DA_ESCOLHA, páginas da faixa em "Avançado"); Valor opcional (padrão 0) com ajuda da fatura Pix;
aviso "Pagamento confirmado: ative a campanha" (services.paga_e_em_rascunho); ajuda nova de Cidades. Rodízio igual.

**Depois:** campanha Domínio não aparecia: o worker (Celery não recarrega código) rodava a versão antiga e gerou só
a imagem do computador. Worker reiniciado, peça 8 reprocessada; a Prévia agora avisa peça incompleta (+1 teste).

**Falta:** Daniel conferir no navegador (Ctrl+F5 por causa do JS novo) e decidir se campanha com cidade aparece na home.

**Arquivos:** publicidade/{admin,forms,models,services,README}.py/md, migrations/0003, tests/test_publicidade.py,
static/js/publicidade-admin.js, docs/ARQUITETURA.md.

**Último comando que passou:** `pytest -q publicidade` → 39 passed; `ruff check publicidade` limpo; makemigrations --check ok.
