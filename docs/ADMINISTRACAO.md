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
| **Administrador** | Usuários: ver, criar, editar · Grupos: ver · Estados e cidades: ver, editar (liberar no site) · Tentativas de login bloqueadas: ver, apagar (= desbloquear) · Histórico do admin: ver · Anunciantes: ver, cadastrar, editar, aprovar/suspender, histórico · Identidade do site, valores e textos de ajuda: ver, editar · Regiões e bairros: ver, criar, editar · Solicitações de cidade: ver, liberar/recusar · Planos: ver, criar, editar · Assinaturas: ver, criar, editar, pagamento manual · Pedidos de plano: ver, aprovar/recusar · Anúncios: ver, histórico · Fila de moderação: aprovar/recusar · Faturas e e-mails de cobrança: como o Financeiro · **Privacidade: documentos legais e pedidos dos titulares (ver, criar, editar, marcar atendido)** (Sprint 7B) · Denúncias: como o Moderador · **Guia de Negócios: tudo do grupo Guia + categorias e grupos (criar, editar, apagar só sem perfis), termos do guia, pedidos dos perfis e configuração do guia** | Tudo dos modelos novos |
| Moderador | Estados e cidades, regiões e bairros: ver · Anunciantes: ver, aprovar/suspender (com motivo), histórico · Solicitações de cidade: ver · Planos, assinaturas e pedidos: ver · Anúncios: ver, histórico · Fila de moderação: aprovar/recusar · **Denúncias: ver, aceitar (pausar/remover) ou descartar; recebe o e-mail de anúncio pausado por golpe** (Sprint 7B parte 2) · Guia: perfis (ver) e pedidos dos perfis (ver, responder) | — |
| Financeiro | Estados e cidades, regiões e bairros: ver · Anunciantes: ver · Planos: ver, criar, editar (preços e limites) · Assinaturas: ver, criar, editar, pagamento manual · Pedidos de plano: ver, aprovar/recusar (recebe o e-mail de pedido novo) · Anúncios: ver · **Faturas: ver, painel de cobrança, confirmar pagamento, recusar comprovante, cancelar, editar link do boleto/observação (recebe o e-mail de comprovante novo) · E-mails de cobrança: ver, editar** (Sprint 6) · Publicidade: patrocinadores e campanhas (ver) | Relatórios |
| Comercial | Estados e cidades, regiões e bairros: ver · Anunciantes: ver · Planos, assinaturas e pedidos: ver · Anúncios: ver · **Publicidade: patrocinadores, campanhas e peças (ver, criar, editar), painel e CSV, gerar fatura; recebe o aviso de campanha terminando** (Sprint 7A) | Relatório mensal ao patrocinador |
| **Guia** (G1, `guia/migrations/0002`) | Guia de Negócios: perfis (ver, cadastrar, editar, enviar convite pelo WhatsApp, aceite em papel, publicar, pausar, revogar aceite) · categorias, termos, aceites e convites: ver | Pedidos do titular e lista de convites (G3) |

Financeiro e Comercial **não veem nada do guia**. Equipe demo: `guia@demo.invalid` (grupo Guia).
Ligar o guia no site: Admin › Guia de Negócios › Configuração do guia › "guia no ar" (desligado, a equipe
logada vê as páginas como pré-visualização). Lá também: nome da aba, mínimo de empresas para o Google indexar
e contatos revelados por hora por visitante.

Ninguém além do superusuário pode:
- **apagar usuário ou anunciante** (exclusão é lógica: anunciante é suspenso, nunca apagado);
  plano, assinatura, pedido de plano, anúncio e fatura também não se apagam (nem pelo superusuário, no
  admin; fatura se cancela, com motivo);
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
- **Denúncias (Sprint 7B parte 2):** Moderação › Denúncias: abra o anúncio pelo link, decida e use
  **Aceitar** (pausar: o anunciante corrige e reativa; remover: sai de vez; o motivo vai por e-mail, sem
  dizer quem denunciou) ou **Descartar**. Com 3 denúncias de golpe de origens diferentes (Identidade do
  site) o anúncio já sai do ar "em revisão" e chega e-mail: decida esses primeiro. A decisão vale para
  todas as denúncias pendentes do anúncio.
- **Privacidade (Sprint 7B):** Privacidade › Pedidos dos titulares: confira todo dia os "prazo vencido"; pedido
  por e-mail = adicionar com o contato e o tipo (o prazo de 15 dias se calcula sozinho) e, ao responder, usar
  "Marcar como atendido" com o que foi feito. Exportação e exclusão feitas pelo próprio anunciante já aparecem
  atendidas. Documentos legais: para mudar Termos ou Política, adicione uma **versão nova** (com "o que mudou" e a
  data de vigência); a versão em vigor não pode ser editada. O advogado revisa na Sprint 9 (desmarcar "revisão
  jurídica pendente").
- **Painel de publicidade (Sprint 7A):** Publicidade › Campanhas › "Painel de publicidade": campanhas no ar,
  terminando em breve, impressões, cliques e CTR por campanha no período, com Exportar CSV. Vender: cadastre o
  patrocinador, crie a campanha com as peças (situação "ativa" para ir ao ar no início) e use "Gerar fatura
  (Pix)": o patrocinador recebe o link de pagamento; a confirmação é em Cobrança › Faturas.
- **Painel de cobrança (Sprint 6):** Cobrança › Faturas › "Painel de cobrança": a receber no mês,
  recebido no mês, vencendo em 7 dias, vencidas e aguardando confirmação. Rotina do Financeiro:
  1. abrir "Aguardando confirmação", abrir cada comprovante e conferir no extrato (valor e identificador
     `NDFT…` da fatura);
  2. selecionar e usar **Confirmar pagamento** (escolher a forma) ou **Recusar comprovante** (motivo vai
     por e-mail ao anunciante);
  3. pagamento combinado fora do site: Assinaturas › "Registrar pagamento manual" (baixa a fatura).
  Textos dos e-mails automáticos: Cobrança › E-mails de cobrança (variáveis entre chaves).
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
