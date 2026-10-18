# App `moderacao`

**Responsabilidade:** denúncias de anúncios (Sprint 7B parte 2): formulário público sem login, proteção contra
abuso (honeypot e limite por dia, sem IP), pausa automática por golpe e a fila de decisão no admin.

**Modelo:** `Denuncia` (anúncio, motivo, detalhes e e-mail opcionais, origem = resumo do visitante no dia,
situação, ação, motivo da decisão, quem decidiu e quando; histórico). Nunca mostrada ao anunciante.

**Serviços (`services.py`):** `origem_do_visitante`, `denunciar` (limite `Configuracao.denuncias_por_dia`;
repetição da mesma origem no mesmo anúncio e dia não cria outra), `pausar_se_golpe` (X origens diferentes,
`Configuracao.denuncias_golpe_para_pausar`), `aceitar` (pausar = `PausadoPor.MODERACAO`, o anunciante reativa;
remover = exclusão lógica; motivo por e-mail), `descartar` (anúncio "em revisão" volta), `limpar_denuncias_antigas`
(tarefa diária às 4h15), `criar_denuncias_demo` / `apagar_denuncias_demo`.

**Telas:** `/denunciar/` (botão em cada anúncio com `?anuncio=<codigo>`). **Admin:** Moderação › Denúncias
(Moderador e Administrador). **Testes:** `tests/test_denuncias.py`.
