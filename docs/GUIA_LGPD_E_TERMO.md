# Guia de Negócios — LGPD e termo de autorização

> **RASCUNHO. Revisão jurídica pendente.** Este texto não é parecer jurídico. O advogado revisa na Sprint 9,
> junto com os Termos de Uso e a Política de Privacidade. Até lá, o termo carrega o marcador `rascunho_juridico = true`.

## 1. Tratamento de dados do Guia

| Item | Definição |
|---|---|
| Quem são os titulares | Responsáveis por empresas, autônomos e profissionais listados |
| Finalidade | Divulgar gratuitamente o serviço, para que clientes encontrem e entrem em contato |
| Base legal | Consentimento (LGPD, art. 7º, I), dado pelo aceite registrado |
| Dados públicos | Nome público, categoria, WhatsApp, telefone, endereço ou área de atendimento, horário, logo, frase, registro profissional (se regulamentada) |
| Dados privados | Nome do responsável, contato do responsável, CNPJ, final do CPF e hash do CPF, registro do aceite, anotações do admin |
| Nunca guardar | CPF completo em claro, endereço residencial público, documentos além do necessário |
| Quem acessa | Equipe com o grupo Guia, Moderador (pedidos do titular) e Administrador |
| Retenção | Perfil ativo: enquanto publicado. Removido: dados de contato e logo apagados; fica só o aceite e o pedido pelo prazo de prova (padrão 5 anos) |
| Direitos | Confirmação, acesso, correção, remoção e revogação do consentimento, pelo mesmo canal do cadastro |
| Canal | Link "Esta é minha empresa" na ficha e o e-mail do Encarregado (campo da Configuração) |
| Prazos | Meta interna: 2 dias úteis para remover. Máximo: 15 dias |
| Compartilhamento | Nenhum com terceiros, exceto os provedores de infraestrutura (hospedagem, e-mail) |
| Transferência internacional | Informar na política, conforme a hospedagem escolhida |

Atualizar também `docs/LGPD.md` com esta tabela e o registro de operações de tratamento.

## 2. Fluxo do aceite

1. A equipe cadastra o perfil e gera o convite (link de uso único, 15 dias).
2. O responsável abre o link e vê **exatamente** como a ficha vai aparecer.
3. Lê o termo (versão e data visíveis), digita o próprio nome e marca a caixa "Autorizo a publicação".
4. Ao confirmar, o sistema registra: nome digitado, data e hora, versão do termo, IP truncado e resumo do navegador.
5. O perfil é publicado e o responsável recebe a confirmação (e-mail, se informado) com o caminho para pedir alteração ou remoção.

Plano B (presencial): termo impresso e assinado (assinatura pelo gov.br é opcional). A equipe anexa a foto no storage privado e marca `canal = presencial`.

Base legal do aceite eletrônico: Lei 14.063/2020 e MP 2.200-2/2001, art. 10, §2º (as partes podem admitir outro meio de comprovação). Não exigir gov.br.

## 3. Texto do termo (modelo)

**TERMO DE AUTORIZAÇÃO DE PUBLICAÇÃO NO {{nome_guia}}**
Versão {{versao}}, em vigor desde {{vigente_desde}}.

**1. Quem somos.** O {{nome_guia}} é um serviço gratuito do Negócios Diários, mantido por {{razao_social_ou_nome}}
({{cnpj_ou_documento}}), em {{cidade_sede}}. Contato do Encarregado de dados: {{email_encarregado}}.

**2. O que será publicado.** Com a sua autorização, publicaremos no site: nome público, categoria(s), telefone e WhatsApp
de contato, endereço comercial ou área de atendimento, horário de funcionamento, logomarca e frase de apresentação,
exatamente como mostrado na prévia desta página. Se for profissional de área regulamentada, também o número de registro.

**3. O que NÃO será publicado.** Seu CPF, seu endereço residencial (se atender em casa) e qualquer outro dado que não esteja na prévia.

**4. Gratuidade.** A publicação é gratuita. Não há cobrança nem obrigação de contratar outro serviço.
Podemos, no futuro, oferecer recursos pagos opcionais; nenhum será ativado sem o seu pedido.

**5. Seus direitos.** Você pode, a qualquer momento, pedir alteração ou remoção da publicação, ou revogar esta autorização,
pelo link "Esta é minha empresa" na sua ficha ou pelo e-mail do Encarregado. Atendemos o pedido o mais rápido possível
e, no máximo, em 15 dias. Revogar não gera multa nem prejuízo.

**6. Seus dados no nosso sistema.** Guardamos o registro desta autorização (nome digitado, data, hora e versão) pelo tempo
necessário para comprovar que você autorizou. Os demais dados são apagados quando a publicação for removida.

**7. Responsabilidade.** Você declara ser o responsável pelo negócio ou profissional indicado e que as informações são verdadeiras.
Você é responsável pelo conteúdo informado. Podemos pausar ou remover fichas com informações falsas ou que violem a lei.

**8. Alterações deste termo.** Se mudarmos o termo, pediremos uma nova autorização. Sem ela, a ficha poderá ser pausada.

**Autorizo a publicação** (marque e digite seu nome completo): [ ] ____________________

Data e hora: {{aceito_em}}

## 4. Mensagem de convite (WhatsApp, enviada manualmente)

> Olá, {{nome}}! Aqui é o Daniel, do Negócios Diários, de Tangará da Serra. Estou montando um guia gratuito de serviços e comércios da região
> e queria incluir {{nome_publico}}, sem custo. Antes de publicar, você confere como vai aparecer e autoriza por este link: {{link}}
> Se preferir não participar, é só responder "não" e eu não entro em contato de novo.

Regras: um convite por vez, enviado pela equipe, sem automação em massa. Quem responde "não" entra na lista "não contatar".

## 5. Página "Esta é minha empresa"

Formulário simples na ficha (`/guia/pedido/<slug>/`): tipo (alterar, remover, outro), descrição, contato para resposta.
Mostra o prazo e o canal alternativo (e-mail do Encarregado). Honeypot e limite por hora. Entra na fila do admin com prazo de 15 dias.
Para pedidos de **remoção** feitos pelo e-mail cadastrado do responsável, a equipe pode despublicar de imediato e confirmar depois.

## 7. Interessados pelo site ("Quero ser listado")

| Item | Definição |
|---|---|
| Quem | Empresa ou profissional que pede para entrar no guia em `/guia/quero-ser-listado/` |
| Dados | Nome da empresa ou do serviço, categoria, cidade, WhatsApp, nome da pessoa de contato e a data em que marcou a autorização. **Sem CPF e sem endereço** |
| Finalidade | A equipe entrar em contato para montar a ficha. Nada é publicado: a ficha só vai ao ar com o aceite do termo pelo link |
| Base legal | Consentimento (art. 7º, I): caixa obrigatória "Autorizo o Negócios Diários a entrar em contato comigo por este número para montar a ficha" |
| Quem acessa | Grupo Guia e Administrador (lista de convites no admin) |
| Retenção | Virou ficha: segue as regras do perfil. **Não virou ficha: apagado depois de 180 dias** (`ConfiguracaoGuia.dias_guarda_interessados`) pela rotina diária do guia (4h30), também no histórico. Quem pediu para não ser contatado continua na lista "não contatar" |
| Número já na lista "não contatar" | O pedido fica registrado sem nenhuma ação (alerta na observação) e a equipe é avisada por e-mail; o convite continua bloqueado |

## 6. Pendências para o advogado

- Validar consentimento como base legal única, ou se há base mais adequada para empresas com CNPJ (dados de pessoa jurídica).
- Validar guardar IP truncado e o prazo de prova do aceite.
- Regras de propaganda dos conselhos (CFM, CRO, OAB, CRC, CRECI, CREF etc.) para as fichas restritas.
- Texto final do termo, da política e do convite.
- Alterar a Política de Privacidade para incluir o tratamento do Guia.
- Validar o texto da autorização do "Quero ser listado" e a guarda de 180 dias dos interessados.
