# Administração da plataforma

## Quem administra
**Daniel é o administrador geral (superusuário).** Tem acesso total: anunciantes,
anúncios, planos, faturas, publicidade, moderação, relatórios e configurações.

Mesmo assim, o sistema já nasce com **perfis (grupos do Django)**. Assim, se um
dia entrar um ajudante, ele recebe só o que precisa, sem a senha do superusuário:

| Perfil | Pode | Não pode |
|---|---|---|
| **Administrador** (Daniel) | Tudo | — |
| Moderador | Aprovar/rejeitar anunciantes e anúncios, tratar denúncias | Ver faturas, mudar preços, excluir contas |
| Financeiro | Ver e baixar faturas, marcar pagamento manual, relatórios | Moderar, mudar planos |
| Comercial | Cadastrar patrocinadores e contratos de publicidade | Moderar, financeiro de assinaturas |

### Grupos no sistema (permissões atuais)
Criados pela migration de dados `contas/migrations/0002_grupos_permissao.py`, só com
permissões de modelos que **já existem**. Cada modelo novo (anunciante, anúncio,
fatura, publicidade...) vem com uma migration que acrescenta as permissões dele ao
grupo certo, seguindo a tabela acima. Teste: `contas/tests/test_grupos.py`.

| Grupo | Permissões hoje | Chega depois |
|---|---|---|
| **Administrador** | Usuários: ver, criar, editar · Grupos: ver · Estados e cidades: ver, editar (liberar no site) · Tentativas de login bloqueadas: ver, apagar (= desbloquear) · Histórico do admin: ver | Tudo dos modelos novos |
| Moderador | Estados e cidades: ver | Anunciantes, anúncios e denúncias (Sprints 1, 3 e 7) |
| Financeiro | Estados e cidades: ver | Planos, faturas e pagamentos (Sprints 2 e 6) |
| Comercial | Estados e cidades: ver | Patrocinadores e contratos (Sprint 7) |

Ninguém além do superusuário pode:
- **apagar usuário** (exclusão é lógica, nunca de verdade);
- **mexer nos códigos de acesso** (`otp_email`/`otp_static`): quem altera o código ou o
  e-mail de envio de outra pessoa consegue entrar como ela;
- **ligar `is_superuser` ou dar permissões avulsas**: no admin esses campos ficam só
  leitura para quem não é superusuário;
- **editar a conta do superusuário** (nem trocar a senha dela).

### Colocar alguém na equipe
1. Admin → Usuários → criar (ou abrir) a pessoa, marcar **Membro da equipe** e escolher o grupo.
2. A pessoa entra com e-mail e senha. Em produção (com o código por e-mail ligado),
   cada navegador novo dela recebe um código no e-mail cadastrado; por isso o e-mail
   da conta tem de ser um que só ela lê.

## Onde administra
- **V1:** Django Admin personalizado (tema `django-unfold`), em URL secreta e com código para navegador novo.
  Já entrega listas, filtros, busca e edição sem programar telas.
- Página inicial do admin com o resumo do dia:
  - cadastros e anúncios aguardando aprovação;
  - denúncias abertas;
  - faturas vencendo hoje / vencidas;
  - receita do mês (assinaturas + publicidade);
  - contratos de publicidade que vencem em 7 dias.
- **V2:** telas próprias só para o que o admin padrão fizer mal (ex.: fila de moderação com fotos grandes).

## Regras de segurança do admin
- Endereço secreto (`ADMIN_URL` no `.env`); `/admin/` dá 404.
- Login com e-mail e senha. Navegador novo confirma com um código de 6 dígitos enviado
  por e-mail (10 minutos, uso único) e fica confiável por 30 dias. Em dev o e-mail chega
  no Mailpit (http://localhost:8025); dá para desligar em dev com `ADMIN_CODIGO_EMAIL=False`.
  Decisão de 2026-10-11 (troca do app autenticador por este fluxo, mais simples): ver
  `docs/SEGURANCA.md`.
- 5 senhas erradas seguidas (mesmo e-mail e mesmo IP) bloqueiam o login por 1 hora.
- Procedimentos (primeiro acesso, desbloqueio, sem acesso ao e-mail): `docs/RUNBOOK.md`.
- Superusuário só para o Daniel.
- Ações sensíveis (suspender conta, estornar, excluir) pedem **motivo** e ficam no histórico.
- Admin nunca vê senha nem dado de cartão; CPF aparece mascarado.
- Se precisar entrar "como o anunciante" para dar suporte: só leitura, e fica registrado.
