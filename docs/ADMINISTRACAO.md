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

## Onde administra
- **V1:** Django Admin personalizado (tema `django-unfold`), em URL secreta e com 2FA.
  Já entrega listas, filtros, busca e edição sem programar telas.
- Página inicial do admin com o resumo do dia:
  - cadastros e anúncios aguardando aprovação;
  - denúncias abertas;
  - faturas vencendo hoje / vencidas;
  - receita do mês (assinaturas + publicidade);
  - contratos de publicidade que vencem em 7 dias.
- **V2:** telas próprias só para o que o admin padrão fizer mal (ex.: fila de moderação com fotos grandes).

## Regras de segurança do admin
- Superusuário só para o Daniel; uso diário com 2FA.
- Ações sensíveis (suspender conta, estornar, excluir) pedem **motivo** e ficam no histórico.
- Admin nunca vê senha nem dado de cartão; CPF aparece mascarado.
- Se precisar entrar "como o anunciante" para dar suporte: só leitura, e fica registrado.
