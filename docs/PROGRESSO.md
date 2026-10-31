# Progresso (checkpoint)

**Em andamento:** atalhos de "Liberar cidade" (Guia), aguardando conferência e commit.

**Feito:** core.services.liberar_cidade (estado junto, tira marca da demo, LogEntry com quem/quando); botão
"Liberar <cidade>" ao lado da pendência na ficha do Guia (só Administrador/superusuário, confirmação em
templates/admin/core/liberar_cidade.html); "Liberar cidade e vincular" na fila de convites (cidades_do_ibge,
escolha entre homônimas, liga todos os contatos que pediram a mesma cidade); "Cidades" no menu do dia a dia logo
depois de "Solicitações de cidade" (config/menu_admin.py, JUNTO_DE). Testes: guia/tests/test_liberar_cidade.py (7).
Docs: MANUAL_ADMIN, core/README, guia/README.
Antes (sem commit ainda): publicidade, Guia "Outra cidade", CSRF strict-origin, mapa e logo do Guia.

**Falta:** conferir no navegador e fazer o commit.

**Último comando que passou:** `pytest guia/tests/test_liberar_cidade.py core/tests/test_painel_hoje.py` → 25 passed; ruff limpo.
