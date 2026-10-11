# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versões: `AAAA.MM.N`.

## [Não lançado]
### Adicionado
- Layout base (topo, rodapé, ajuda) convertido do protótipo, home provisória com cidades atendidas, página Sobre e favicon. Fontes hospedadas localmente (sem Google Fonts).
- Estados e cidades do IBGE (`Estado`, `Cidade` com ponto PostGIS), CSV em `core/dados/`, comando `carregar_municipios` idempotente e admin com liberação em massa.
- App `contas`: usuário próprio com login por e-mail (sem username), senhas em Argon2, admin de usuários.
- Esqueleto Django 5.2 (settings por variáveis de ambiente, fuso America/Cuiaba), Dockerfile sem root, dependências com uv e rota `/saude/`.
- Documentação inicial: arquitetura, segurança, LGPD, pagamentos, publicidade, administração, boas práticas, runbook.
- Protótipo navegável (7 telas, incluindo admin de cidades) em `prototipo/`.
- Docker Compose de desenvolvimento.
- Importador de anúncios (XML ZAP/VivaReal e planilha) planejado na Sprint 8; etapa de validação do negócio antes da Sprint 0.
- Sistema pronto para vários estados (cidades IBGE liberadas pelo admin, UF na URL); ajuda em todas as telas; docs/TELAS.md com limites de mídia.
- Logo novo (símbolo SVG claro/escuro); tela Admin › Identidade do site; página Sobre (missão, visão, valores); home com atalhos por categoria e Recém-anunciados.
