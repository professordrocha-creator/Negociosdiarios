# Progresso (checkpoint)

**Em andamento:** Guia, "Quero ser listado" com "Outra cidade" / "Outra (escrever)", aguardando conferência e commit.

**Feito:** `ContatoConvite.cidade` opcional + `cidade_informada` e `categoria_informada` (migration guia 0009);
formulário com as opções "Outra" e o texto limpo (sem HTML, sem link, até 80; `forms.limpar_texto_livre`);
static/js/quero-ser-listado.js mostra o texto só com "Outra"; admin com "Cidade/Categoria informada" e o filtro
"Pedidos de outra cidade"; `criar_perfil_do_contato` recusa contato sem cidade atendida; apagamento de 180 dias
cobre os campos novos (teste). Docs: LGPD, ARQUITETURA, guia/README.
Antes (sem commit ainda): ajustes da publicidade (imagem única, escolhas simples, aviso de pagamento).

**Falta:** Daniel decidir se liga pedido de outra cidade à demanda de cidade (SolicitacaoCidade é só de anunciante).

**Último comando que passou:** `pytest -q guia` → 100 passed (com os 6 testes novos); `ruff check guia` limpo.
