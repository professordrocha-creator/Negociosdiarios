# Manual do Administrador — Negócios Diários

Este manual explica, passo a passo, como cuidar do site pelo painel administrativo (o "admin"). Ele descreve só
o que existe hoje no sistema. Os nomes entre aspas são exatamente os que aparecem na tela.

> Dica: este mesmo manual abre dentro do site, para quem é da equipe, no link **Ajuda** no topo do painel
> administrativo (endereço `/painel/ajuda/`).

## Sumário

1. [Primeiro acesso](#1-primeiro-acesso)
2. [Visão geral do painel](#2-visao-geral-do-painel)
3. [Configurações gerais do site](#3-configuracoes-gerais-do-site)
4. [Anúncios](#4-anuncios)
5. [Lojas e anunciantes](#5-lojas-e-anunciantes)
6. [Faturas e pagamentos manuais](#6-faturas-e-pagamentos-manuais)
7. [Publicidade](#7-publicidade)
8. [Denúncias](#8-denuncias)
9. [LGPD: pedidos, exclusão e termos](#9-lgpd-pedidos-exclusao-e-termos)
10. [Guia de Negócios](#10-guia-de-negocios)
11. [Equipe e permissões](#11-equipe-e-permissoes)
12. [Rotinas automáticas](#12-rotinas-automaticas)
13. [Rotina do administrador (checklist)](#13-rotina-do-administrador-checklist)
14. [Dados de demonstração](#14-dados-de-demonstracao)
15. [Glossário e perguntas frequentes](#15-glossario-e-perguntas-frequentes)

---

## 1. Primeiro acesso

O painel administrativo fica num **endereço secreto** (definido no arquivo `.env` do servidor, no item
`ADMIN_URL`). Não existe `/admin/`: quem tenta esse endereço recebe "página não encontrada". Guarde o endereço
secreto só com quem é da equipe.

### Entrar pelo endereço secreto

1. **Onde clicar:** abra o navegador e digite o endereço secreto do admin.
2. **O que preencher:** seu e-mail e sua senha. Clique em "Acessar".
3. **O que acontece depois:** se o navegador já é conhecido, o painel abre. Se é um navegador novo (e o código
   por e-mail está ligado, como em produção), aparece a tela "Este navegador ainda não é conhecido".

### Entrar pela Área do anunciante

1. **Onde clicar:** na página inicial do site, botão "Área do anunciante".
2. **O que preencher:** o mesmo e-mail e a mesma senha da equipe.
3. **O que acontece depois:** contas da equipe são levadas ao painel administrativo, com as mesmas proteções do
   endereço secreto (código por e-mail em navegador novo e bloqueio por tentativas erradas). Clientes comuns vão
   para o painel da loja deles. Já logado, o topo do site mostra "Painel administrativo" para a equipe.

### Código por e-mail (navegador novo)

1. **Onde clicar:** na tela "Este navegador ainda não é conhecido".
2. **O que preencher:** o código de 6 dígitos que chegou no seu e-mail. Clique em "Entrar".
3. **O que acontece depois:** o navegador fica confiável por 30 dias (não pede código de novo nesse período).
   Não chegou? Veja o spam ou clique em "reenviar o código" (espere 1 minuto entre um pedido e outro). Para
   trocar de conta, "Sair e entrar com outra conta".

### Se esquecer a senha

1. **Onde clicar:** no computador do servidor (ou no seu, com o projeto), abra o terminal na pasta do projeto.
2. **O que preencher:** `docker compose exec web python manage.py changepassword SEU-EMAIL` e digite a senha
   nova duas vezes (nada aparece enquanto digita; é normal).
3. **O que acontece depois:** entre com a senha nova. Trocar a senha também cancela os navegadores confiáveis.

### Se travar (bloqueio por senha errada)

Na **5ª senha errada** o login daquele e-mail, naquele endereço de internet, fica bloqueado por **1 hora**.

1. **Onde clicar:** espere 1 hora, **ou** peça a outro Administrador: "Axes" › "Tentativas de acesso", marque a
   linha do seu e-mail e apague (isso desbloqueia), **ou** no terminal do servidor rode
   `docker compose exec web python manage.py axes_reset`.
2. **O que preencher:** nada além do comando.
3. **O que acontece depois:** o login volta a funcionar.

Sem acesso ao e-mail do código: no terminal do servidor,
`docker compose exec web python manage.py redefinir_acesso SEU-EMAIL` desbloqueia e mostra um **código de
emergência** de uso único, que serve na tela do código no lugar do código por e-mail.

### Se der errado

- "Página não encontrada" no `/admin/`: use o endereço secreto (está no `.env` do servidor).
- O código não chega: confira o spam; em último caso use `redefinir_acesso` (acima).
- "E-mail ou senha incorretos": a senha diferencia maiúsculas. Depois de 5 erros, veja "Se travar".

---

## 2. Visão geral do painel

Depois de entrar, a página "Painel" mostra no topo a caixa **"Pendências"**: denúncias pendentes, pedidos de
privacidade do site, pedidos do Guia de Negócios, comprovantes aguardando confirmação e lojas pendentes de
aprovação. Cada número abre a lista já filtrada, e cada pessoa vê só os contadores do que o grupo dela pode ver.
Abaixo vêm os grupos de menus. Cada pessoa vê só o que o grupo dela permite
(capítulo 11). No topo: "Ajuda" (este manual), "Ver o site", "Alterar senha" e "Encerrar sessão".

| Menu | Para que serve |
|---|---|
| Anunciantes | Lojas e corretores ("Anunciantes") e os pedidos de cidade nova ("Solicitações de cidade") |
| Anúncios | Todos os anúncios (só leitura) e a "Fila de moderação" (aprovar ou recusar) |
| Catálogo de veículos | Marcas, modelos e versões da Tabela FIPE (só esconder o que não deve aparecer) |
| Faturas e pagamentos | "Faturas" (com o "Painel de cobrança") e os "E-mails de cobrança" |
| Contas | "Usuários": equipe e clientes |
| Guia de Negócios | Perfis do guia, categorias, termos, pedidos dos titulares, lista de convites e configuração |
| Moderação | "Denúncias" de anúncios |
| Núcleo | "Configurações do site" (limites, prazos, contatos e textos), estados, cidades, regiões, bairros, textos de ajuda, valores da empresa |
| Planos e assinaturas | Planos (preços e limites), assinaturas das lojas e pedidos de troca de plano |
| Privacidade (LGPD) | Termos de Uso e Política de Privacidade (com versões) e pedidos dos titulares |
| Publicidade | Patrocinadores e campanhas (com as peças e o "Painel de publicidade") |
| Autenticação e Autorização | "Grupos" (só leitura para a equipe) |
| Axes | "Tentativas de acesso" (logins bloqueados) |

Quase nada é apagado de verdade: lojas são suspensas, faturas são canceladas, perfis são pausados ou removidos.
Toda mudança importante tem "Histórico" (botão no canto da ficha).

### Se der errado

- Um menu não aparece: seu grupo não tem permissão (capítulo 11). Peça ao Administrador.
- "Ajuda" não aparece no topo: recarregue com Ctrl+F5.

---

## 3. Configurações gerais do site

Quase todos os limites, prazos e textos ficam em **"Núcleo" › "Configurações do site"** (um registro só). O Guia
de Negócios tem a sua própria em **"Guia de Negócios" › "Configuração do guia"** (capítulo 10).

### Mudar um limite, prazo ou texto

1. **Onde clicar:** "Núcleo" › "Configurações do site" (abre direto o formulário).
2. **O que preencher:** o campo desejado. Os blocos são:
   - **Nome e textos:** "nome do site", "linha da região", "slogan", "frase do rodapé", "empresa responsável",
     "cidade-sede".
   - **Logo, símbolos e imagem de compartilhamento:** troca do logo e dos símbolos (o favicon é gerado sozinho).
   - **Contatos:** "WhatsApp", "e-mail de contato", **"e-mail de privacidade (LGPD)"** (é o canal do Encarregado),
     **"encarregado de dados (DPO)"** (nome do Encarregado), "endereço", "CNPJ" (aparece no rodapé só se
     preenchido), "Instagram".
   - **Página Sobre:** quem somos, missão, visão.
   - **Limites de mídia** e **Anúncios: fotos e textos:** tamanho e número de fotos, caracteres do título e da
     descrição.
   - **Publicidade:** tamanhos dos banners e "aviso de fim de campanha (dias antes)".
   - **Regras do negócio:** "carência de pagamento (dias)" (padrão 5), "fatura gerada (dias antes do
     vencimento)" (10), "limite do comprovante de pagamento (KB)", "prazo para responder ao titular (dias)" (15),
     "guarda de faturas e comprovantes (anos)" (5), **"denúncias de golpe para pausar"** (3), "denúncias por
     visitante por dia" (5), "guarda do contato da denúncia (dias)" (365), "validade do anúncio (dias)" (60),
     "mostrar botão Renovar a partir de (dias antes)" (5; só mostra o botão no painel do anunciante, não manda e-mail) e "anúncios que passam por moderação" ("Só o primeiro anúncio de
     cada loja", "Todos os anúncios" ou "Nenhum (publicação direta)").
3. **O que acontece depois:** clique em "Salvar". Vale a partir do próximo uso, para todas as lojas.

### Textos "Sobre esta tela"

1. **Onde clicar:** "Núcleo" › "Textos de ajuda" › a tela desejada.
2. **O que preencher:** um item por linha, sem HTML. Em branco, a caixa some.
3. **O que acontece depois:** a caixa "Sobre esta tela" daquela página muda na hora.

### Ligar e desligar recursos

- **Cidades no site:** "Núcleo" › "Cidades", marque "liberada" (ou ação "Liberar cidades selecionadas").
  Estados: "Núcleo" › "Estados" › "liberado". O seletor de estado aparece sozinho com 2 ou mais liberados.
- **Guia de Negócios:** "Guia de Negócios" › "Configuração do guia" › "guia no ar" (capítulo 10).
- **E-mails de cobrança:** "Faturas e pagamentos" › "E-mails de cobrança", desmarque "enviar" (coluna "ativo") no e-mail
  que não quer mandar.

### Se der errado

- Mudou e nada aconteceu no site: limpe o cache do navegador (Ctrl+F5). A configuração é lida na hora.
- "Este campo é obrigatório": alguns contatos são obrigatórios (e-mail de contato e de privacidade).

---

## 4. Anúncios

### Revisar e aprovar (fila de moderação)

1. **Onde clicar:** "Anúncios" › "Fila de moderação". Os mais antigos ficam no topo, com a capa.
2. **O que preencher:** abra o anúncio para ver fotos grandes, ficha, endereço e ponto (privados). Volte à lista,
   marque os anúncios e escolha a ação "Aprovar selecionados (publica e avisa por e-mail)" ou "Recusar
   selecionados (motivo enviado por e-mail)". Na recusa, escreva o motivo e confirme.
3. **O que acontece depois:** aprovado vai ao ar e o anunciante recebe e-mail; recusado volta para ele corrigir,
   com o motivo.

Quais anúncios passam pela fila: "Núcleo" › "Configurações do site" › "anúncios que passam por moderação".

### Consultar todos os anúncios

1. **Onde clicar:** "Anúncios" › "Anúncios". Filtros por situação, categoria e cidade; busca por código
   (ND-IM-…, ND-VE-…), título ou loja.
2. **O que preencher:** nada: o conteúdo é só leitura (o anúncio é do anunciante). Só o "destaque até" é
   editável (veja "Destaques").
3. **O que acontece depois:** use "Histórico" para ver quem mudou o quê.

### Pausar, reativar ou remover um anúncio

1. **Onde clicar:** "Anúncios" › "Anúncios", marque os anúncios e escolha a ação:
   - "Pausar (motivo obrigatório; avisa o anunciante)": só anúncios publicados;
   - "Reativar (só os pausados pela equipe; respeita o plano)";
   - "Remover do site (motivo obrigatório; nada é apagado)".
2. **O que preencher:** o motivo na tela seguinte e "Aplicar".
3. **O que acontece depois:** o anunciante recebe e-mail com o motivo; o histórico guarda quem fez, quando e por
   quê. Pausado pela equipe, o anunciante corrige e reativa no painel (ou a equipe reativa). Removido some do site
   e do painel, mas o registro fica. Só Administrador e Moderador têm essas ações.

O anunciante também pausa, reativa e exclui os próprios anúncios no painel. Anúncios saem do ar sozinhos na
expiração e quando a loja fica em atraso. Pausa por denúncia sai pela fila de denúncias (capítulo 8).

### Planos

1. **Onde clicar:** "Planos e assinaturas" › "Planos".
2. **O que preencher:** direto na lista: limite de anúncios, preço mensal, preço anual, ordem e "ativo" (à venda).
   Clique em "Salvar" no rodapé da lista.
3. **O que acontece depois:** a página `/planos/` mostra os valores novos. Planos não se apagam (desmarque "ativo").

Pedidos de troca de plano: "Planos e assinaturas" › "Pedidos de troca de plano" › ações "Aprovar selecionados
(aplica o plano e avisa por e-mail)" ou "Recusar selecionados (motivo enviado por e-mail)".

### Destaques

1. **Onde clicar:** "Anúncios" › "Anúncios" › abra o anúncio.
2. **O que preencher:** "destaque até": data e hora do fim do destaque (ex.: o fim do período pago). Em branco =
   sem destaque. "Salvar".
3. **O que acontece depois:** até essa data o anúncio aparece na seção "Destaques" da página inicial (com o selo
   "Patrocinado"), enquanto estiver publicado. A seção mostra "Em breve" quando não há destaques. A coluna
   "destaque até" da lista mostra quem está em destaque.

### Se der errado

- Anúncio não aparece no site: confira a situação (Publicado?), a validade, se a loja está "Ativo" e se a cidade
  está liberada.
- A ação não aparece: só o Administrador e o Moderador moderam.

---

## 5. Lojas e anunciantes

### Verificar (aprovar) um cadastro

1. **Onde clicar:** "Anunciantes" › "Anunciantes". Use o filtro de aprovação para ver quem já confirmou o e-mail
   (esses estão prontos).
2. **O que preencher:** abra o cadastro, confira o CRECI ou o CNPJ nos sites oficiais. Volte à lista, marque e use
   "Aprovar selecionados (CRECI/CNPJ conferido)". O motivo é opcional.
3. **O que acontece depois:** a loja fica "Ativo" e o anunciante pode entrar no painel. A loja só é aprovada em
   cidade liberada.

### Bloquear (suspender)

1. **Onde clicar:** "Anunciantes" › "Anunciantes", marque a loja.
2. **O que preencher:** ação "Suspender selecionados (motivo obrigatório)" e o motivo.
3. **O que acontece depois:** a loja some do site e o anunciante não entra no painel. Nada é apagado; para voltar,
   aprove de novo.

### Contatar

1. **Onde clicar:** abra o cadastro da loja.
2. **O que preencher:** nada. Use o e-mail do usuário, o e-mail público e o WhatsApp mostrados na ficha.
3. **O que acontece depois:** o contato é feito fora do sistema (e-mail ou WhatsApp). O sistema não manda
   mensagens avulsas.

### Pedido de cidade nova

1. **Onde clicar:** "Anunciantes" › "Solicitações de cidade".
2. **O que preencher:** ação "Liberar a cidade das solicitações selecionadas" ou "Recusar selecionadas (motivo
   enviado por e-mail)".
3. **O que acontece depois:** liberada, a cidade aparece no site e a loja pode ser aprovada.

### Se der errado

- Não consigo aprovar: a cidade da loja não está liberada.
- Anunciante diz que não entra: veja a situação (Pendente, Suspenso, Encerrado) e se confirmou o e-mail.

---

## 6. Faturas e pagamentos manuais

As faturas das lojas **nascem sozinhas**: a rotina das 6h gera a fatura X dias antes do vencimento ("fatura gerada
(dias antes do vencimento)"). A fatura de publicidade nasce na campanha (capítulo 7). Pagamento é por Pix
(copia e cola e QR Code) ou boleto (link digitado pela equipe).

### Ver o panorama

1. **Onde clicar:** "Faturas e pagamentos" › "Faturas" › botão "Painel de cobrança".
2. **O que preencher:** nada.
3. **O que acontece depois:** mostra a receber no mês, recebido no mês, vencendo em 7 dias, vencidas e aguardando
   confirmação. Cada número abre a lista filtrada.

### Enviar o link de pagamento

1. **Onde clicar:** "Faturas e pagamentos" › "Faturas" › abra a fatura.
2. **O que preencher:** se for boleto, o "link do boleto". Copie o "link de pagamento" mostrado na ficha.
3. **O que acontece depois:** mande o link pelo WhatsApp a quem pedir. A loja também vê a fatura no painel
   ("Faturas"); o patrocinador recebe o link por e-mail.

### Conferir o comprovante e dar baixa

1. **Onde clicar:** "Faturas e pagamentos" › "Faturas", filtro "Aguardando confirmação"; abra a fatura e clique no
   comprovante.
2. **O que preencher:** confira valor e data no extrato. Na lista, marque e use "Confirmar pagamento (renova a
   assinatura e reativa os anúncios)", escolhendo a forma e uma observação. Se o comprovante não confere: "Recusar
   comprovante (motivo enviado por e-mail)".
3. **O que acontece depois:** paga, a assinatura renova e os anúncios pausados por atraso voltam. Recusado, a
   fatura volta a aberta ou vencida e o cliente recebe o motivo.

### Pagamento que chegou por fora (sem comprovante no site)

1. **Onde clicar:** "Planos e assinaturas" › "Assinaturas", marque a assinatura.
2. **O que preencher:** ação "Registrar pagamento manual (baixa a fatura, renova e reativa)" e o motivo.
3. **O que acontece depois:** a fatura em aberto é baixada (ou criada já paga), a assinatura renova e os anúncios
   voltam.

### Cancelar uma fatura

Marque na lista e use "Cancelar fatura (com motivo)". Faturas nunca são apagadas.

### Se der errado

- O cliente pagou e continua em atraso: confirme o pagamento da fatura **vencida** (não de outra).
- Não vejo faturas: só Financeiro e Administrador veem cobrança.
- O Pix não aparece: falta configurar `PIX_CHAVE`, `PIX_NOME` e `PIX_CIDADE` no `.env` do servidor.

---

## 7. Publicidade

### Cadastrar o patrocinador

1. **Onde clicar:** "Publicidade" › "Patrocinadores" › "Adicionar".
2. **O que preencher:** nome da empresa, contato (nome, e-mail, WhatsApp), CNPJ e, se for uma loja do site, a
   loja.
3. **O que acontece depois:** salve. O e-mail recebe a fatura e os avisos.

### Criar a campanha e as peças

1. **Onde clicar:** "Publicidade" › "Campanhas" › "Adicionar".
2. **O que preencher:** patrocinador, nome da campanha, **posições** (Home: banner no topo; Busca: banner no
   topo; Busca: anúncio nativo no topo dos resultados; Página do anúncio: banner; Rodapé da home: card
   patrocinador), cidades (vazio = todo o site), início, fim, valor e situação. Embaixo, as **peças**: formato,
   imagens (o tamanho certo aparece na ajuda do campo), texto alternativo, título/texto, link e "ativo".
3. **O que acontece depois:** salve. As imagens são processadas em segundo plano (a prévia aparece em instantes).

### Ligar e pausar

1. **Onde clicar:** abra a campanha.
2. **O que preencher:** "situação": "Ativa" para ligar; "Pausada" para tirar do ar. Para tirar só uma peça,
   desmarque "ativo" nela.
3. **O que acontece depois:** "Ativa" fica no ar só entre início e fim. Depois do fim, a rotina das 5h marca
   "Encerrada" e avisa a equipe X dias antes ("aviso de fim de campanha").

### Cobrar a campanha

Na lista de campanhas, marque e use "Gerar fatura (Pix) e enviar ao patrocinador". A cobrança segue o capítulo 6.

### Relatório de impressões e cliques

1. **Onde clicar:** "Publicidade" › "Campanhas" › botão "Painel de publicidade".
2. **O que preencher:** o período (padrão: últimos 30 dias).
3. **O que acontece depois:** mostra campanhas no ar, a vencer, impressões, cliques e CTR. Há exportação em CSV
   para mandar ao patrocinador. Robôs não contam e nenhum dado pessoal é guardado.

### Se der errado

- Peça não aparece: confira a situação "Ativa", as datas, a posição, as cidades e o "ativo" da peça.
- "Imagem com tamanho errado": use exatamente o tamanho da ajuda do campo.

---

## 8. Denúncias

Qualquer visitante denuncia um anúncio pelo botão "Denunciar" (sem cadastro). O anunciante **nunca** sabe quem
denunciou.

### Atender a fila

1. **Onde clicar:** "Moderação" › "Denúncias". Pendentes primeiro, as mais antigas no topo. A coluna "anúncio
   está" mostra "Em revisão (fora do ar)" quando houve pausa automática.
2. **O que preencher:** abra a denúncia e o anúncio (link). Na lista, marque e escolha:
   - "Aceitar: pausar ou remover o anúncio (avisa o anunciante)": escolha pausar ou remover e escreva o motivo
     (vai ao anunciante);
   - "Descartar (se estava em revisão, o anúncio volta ao ar)".
3. **O que acontece depois:** a decisão vale para todas as denúncias pendentes daquele anúncio. Pausado, o
   anunciante corrige e reativa; removido, sai de vez.

### Pausa automática

Quando um anúncio recebe **"denúncias de golpe para pausar"** (padrão 3) de visitantes diferentes, ele sai do ar
"em revisão" sozinho e a equipe recebe e-mail. O anunciante não consegue reativar até a equipe decidir. O número
fica em "Núcleo" › "Configurações do site" › "Regras do negócio". No começo, um número mais alto evita que um
concorrente derrube anúncios.

### Se der errado

- Anúncio "em revisão" sem motivo aparente: veja as denúncias dele e descarte se forem infundadas.
- O e-mail e o texto de quem denunciou somem depois de "guarda do contato da denúncia (dias)" (LGPD).

---

## 9. LGPD: pedidos, exclusão e termos

### Pedidos dos titulares do site

O anunciante baixa os próprios dados e exclui a conta sozinho no painel ("Meus dados"); esses pedidos já nascem
atendidos. Os que chegam por e-mail a equipe registra:

1. **Onde clicar:** "Privacidade (LGPD)" › "Pedidos dos titulares (LGPD)" › "Adicionar".
2. **O que preencher:** tipo (acesso, portabilidade, correção, exclusão, outro), origem, contato e descrição. O
   prazo se preenche sozinho (15 dias). Para fechar: marque e use "Marcar como atendido (com o que foi feito)".
3. **O que acontece depois:** a lista mostra o prazo e "prazo vencido". A lista também avisa quantos pedidos do
   Guia de Negócios estão em aberto (e vice-versa).

### Exclusão de conta

Feita pelo próprio anunciante em "Meus dados" › "Excluir minha conta" (senha + a palavra EXCLUIR). O sistema
anonimiza a conta e a loja, remove os anúncios e as fotos e cancela a assinatura. Faturas e comprovantes ficam
pela guarda fiscal ("guarda de faturas e comprovantes (anos)") e depois a rotina das 4h apaga.

### Termos de Uso e Política de Privacidade (versões)

1. **Onde clicar:** "Privacidade (LGPD)" › "Documentos legais (termos e privacidade)" › "Adicionar".
2. **O que preencher:** documento, versão (ex.: 2026-11), "em vigor a partir de", "o que mudou" (resumo),
   texto (## título, - item), "publicado" e "rascunho: revisão jurídica pendente".
3. **O que acontece depois:** a partir da data, quem entra no painel vê o resumo e aceita a versão nova. Em vigor,
   o texto fica travado: para mudar, crie outra versão. O aviso amarelo de rascunho aparece só no admin.

### Registro de aceites

Cada aceite (documento, versão, data e hora) fica em "Contas" › "Usuários" › ficha do usuário, sem IP. O
aceite do Guia de Negócios fica na ficha do perfil do guia (capítulo 10).

### Se der errado

- Pedido de exclusão por e-mail: confirme a identidade antes; a exclusão em si é feita pelo próprio titular no
  painel, ou registrada aqui com o que foi feito.
- Prazo vencido: responda o quanto antes; o prazo legal é de 15 dias.

---

## 10. Guia de Negócios

Diretório gratuito de serviços e comércios. Nada vai ao ar sem a **autorização registrada** do responsável.

### Ligar o guia

1. **Onde clicar:** "Guia de Negócios" › "Configuração do guia".
2. **O que preencher:** marque "guia no ar". Ali também: "nome da aba", "máximo de categorias por perfil" (3),
   "limite da frase", "validade do link de aceite (dias)" (15), "prazo para aceitar um termo novo (dias)" (30),
   "pedidos "Esta é minha empresa" por hora", "mínimo de empresas para o Google indexar" (3), "guarda do aceite
   após a remoção (anos)" (5), "contatos revelados por hora".
3. **O que acontece depois:** o guia aparece no menu do site (com o selo "Novo"), na página inicial e no rodapé.
   Desligado, só a equipe logada vê as páginas (com a faixa "Guia desligado").

### Cadastrar um perfil pelo celular

1. **Onde clicar:** "Guia de Negócios" › "Perfis do guia" › "Adicionar".
2. **O que preencher, na ordem:**
   - **1. Quem é:** tipo (empresa, autônomo, regulamentado), nome público, categorias (até 3; com * é
     regulamentada), frase (não vale para regulamentada) e logo.
   - **2. Contato:** WhatsApp e/ou telefone, com DDD.
   - **3. Onde atende:** cidade, bairro e "como atende": "Tem endereço" (endereço comercial + toque no mapa) ou
     "Atende a domicílio" (área de atendimento; o endereço de casa nunca é pedido).
   - **4. Horário:** um campo por dia, ex.: `8:00-12:00, 14:00-18:00`.
   - **5. Documento e responsável:** CNPJ (empresa), CPF (autônomo; não é guardado, só um resumo), registro
     (regulamentado), nome e contato do responsável.
3. **O que acontece depois:** "Salvar". O perfil fica em rascunho. Se aparecer "Possível cadastro repetido",
   confira (não bloqueia).

### Convite por WhatsApp (autorização)

1. **Onde clicar:** na ficha do perfil, painel "Publicação" no topo, botão "Enviar por WhatsApp".
2. **O que preencher:** nada; confira a mensagem e toque em "Abrir o WhatsApp com a mensagem".
3. **O que acontece depois:** o responsável abre o link, confere a prévia, digita o nome e marca "Autorizo". O
   perfil **publica sozinho**. O link vale 15 dias e uma vez só; gerar outro cancela o anterior. O botão
   "Publicar" fica desabilitado sem a autorização (a explicação aparece embaixo).

### Aceite em papel

1. **Onde clicar:** na ficha, "Aceite em papel".
2. **O que preencher:** nome de quem assinou, foto do termo assinado e a caixa "Conferi".
3. **O que acontece depois:** "Registrar aceite e publicar". A foto fica em área privada (nunca no site).

### Fila "Esta é minha empresa" (prazo de 15 dias)

1. **Onde clicar:** "Guia de Negócios" › "Pedidos dos perfis (titulares)". Filtro "prazo": "Prazo vencido" ou
   "Em aberto, no prazo". A coluna "vencido" marca os atrasados.
2. **O que preencher:** para pedidos que chegaram por e-mail ou WhatsApp, "Adicionar" (perfil, tipo, origem,
   descrição, contato). Para decidir, marque e escolha "Atender: remover o perfil (apaga contatos e logo;
   confirma por e-mail)", "Marcar como atendido (com o que foi feito)" ou "Recusar (com o motivo)".
3. **O que acontece depois:** a equipe (Moderador e Administrador) recebe e-mail de cada pedido novo. Pedido de
   remoção vindo do contato cadastrado do responsável pode ser atendido na hora.

### Remoção

1. **Onde clicar:** pela fila de pedidos (acima) ou em "Perfis do guia", ação "Remover (pedido do titular: apaga
   contatos e logo)".
2. **O que preencher:** o motivo (obrigatório).
3. **O que acontece depois:** sai do ar na hora; logo, WhatsApp, telefone e contato do responsável são apagados
   (também no histórico). Ficam só o registro da autorização e do pedido por 5 anos; depois a rotina das 4h30
   apaga tudo.

### Revogar a autorização

Na ficha do perfil, lista "aceites", link "revogar", escreva o motivo e confirme. Sai do ar na hora; a data fica
registrada.

### Termo novo

1. **Onde clicar:** "Guia de Negócios" › "Termos do guia (autorização de publicação)" › "Adicionar".
2. **O que preencher:** versão, "em vigor desde", texto e "rascunho: revisão jurídica pendente".
3. **O que acontece depois:** com a versão em vigor, cada perfil publicado ganha um link de aceite válido até o
   fim do prazo (30 dias); quem tem e-mail como contato recebe o aviso. Acompanhe em "Perfis do guia" › botão
   "Termo: quem falta" (dias que faltam e se tem link). Passado o prazo, a rotina pausa quem não aceitou (nunca
   apaga).

### Importar a lista de convites (CSV)

1. **Onde clicar:** "Guia de Negócios" › "Lista de convites" › botão "Importar CSV".
2. **O que preencher:** o arquivo com as colunas `nome, whatsapp, cidade, categoria` e a origem. Clique em "Ver a
   prévia".
3. **O que acontece depois:** a prévia mostra os erros com o número da linha e o que fica de fora (repetidos e
   "não contatar"). Clique em "Importar N contato(s)": só as linhas certas entram.

### Interessados ("Quero ser listado")

Empresas e profissionais pedem para entrar no guia pelo botão "Quero ser listado" do site. Nada é publicado: o
pedido cai na "Lista de convites", com origem "Formulário do site (Quero ser listado)", e a caixa "Pendências" do
painel mostra "Interessados no Guia".

1. **Onde clicar:** "Pendências" › "Interessados no Guia" (ou "Guia de Negócios" › "Lista de convites", filtros
   origem "Formulário do site" e situação "Novo").
2. **O que preencher:** fale com a pessoa pelo WhatsApp informado (ela autorizou o contato). Depois, marque o
   contato e use "Marcar como contatado (já falei com a pessoa)". Se ela quiser seguir, marque só esse contato e use
   "Criar ficha a partir deste contato (marque um)": abre o cadastro assistido já preenchido (nome, WhatsApp,
   cidade, categoria e pessoa de contato) para completar e mandar o link de aceite. Se não quiser: "Marcar: não
   contatar".
3. **O que acontece depois:** a ficha só vai ao ar com a autorização pelo link. Pedido de número que já estava em
   "não contatar" chega com um alerta na observação e um e-mail para a equipe: não contate sem conferir. Quem
   não vira ficha é apagado sozinho depois de 180 dias (LGPD).

O texto da faixa "Quero ser listado" fica em "Configuração do guia" › "texto do aviso "Quero ser listado"" (evite
"Anuncie": o guia é grátis e não se confunde com os classificados).

### Convidar e a lista "não contatar"

1. **Onde clicar:** na "Lista de convites", link "convidar" da linha.
2. **O que preencher:** confira a mensagem e clique em "Marcar como convidado e abrir o WhatsApp" e depois "Abrir o
   WhatsApp com a mensagem". Um por vez; não há envio em massa.
3. **O que acontece depois:** disse "sim": link "criar perfil" (vira rascunho; complete e envie o link de
   autorização). Disse "não": marque e use a ação "Marcar: não contatar (bloqueia novos convites)" (ou "Marcar:
   recusou"). Número bloqueado não recebe nenhum convite, nem link de autorização.

### Pausa em lote, reativar e exportar CSV

- **Pausar por cidade ou categoria:** "Perfis do guia" › botão "Pausar em lote" › escolha a cidade e/ou a
  categoria › "Ver quem será pausado" › "Confirmar: pausar N".
- **Pausar os marcados:** ação "Pausar os selecionados (com confirmação)".
- **Reativar:** ação "Reativar os selecionados (só com aceite vigente)".
- **Exportar CSV:** ação "Exportar CSV dos selecionados" (sem documentos nem o contato do responsável).
- **Filas rápidas:** botões "Aguardando aceite", "Link vencido" e "Repetidos" no topo da lista, e o filtro "fila".

### Painel de estatísticas

1. **Onde clicar:** "Perfis do guia" › botão "Estatísticas".
2. **O que preencher:** "7 dias" ou "30 dias".
3. **O que acontece depois:** visualizações e cliques no WhatsApp e no telefone, por categoria e por perfil.
   "Exportar CSV" baixa a tabela. Sem dados pessoais; robôs não contam.

### Se der errado

- "Enviar por WhatsApp" desabilitado: falta algo no cadastro (a lista aparece no painel "Publicação").
- O link "já foi utilizado ou expirou": gere outro pelo mesmo botão.
- Perfil não aparece no site: o guia está ligado? O perfil está "Publicado"? A cidade está liberada?

---

## 11. Equipe e permissões

### Grupos

| Grupo | O que vê e faz |
|---|---|
| Administrador | Tudo do dia a dia: usuários, configurações, anunciantes, anúncios, moderação, cobrança, publicidade, privacidade, denúncias e o Guia de Negócios inteiro (inclui categorias, termos e configuração do guia) |
| Moderador | Aprova e suspende anunciantes, modera anúncios (inclui pausar, reativar, remover e destaque) e denúncias; no guia, vê os perfis e cuida dos pedidos dos titulares |
| Guia | Só o Guia de Negócios: cadastra perfis, envia convites e autorizações, publica, pausa, remove, importa e convida a lista, exporta e vê estatísticas |
| Financeiro | Faturas e pagamentos (faturas, e-mails de cobrança), planos e assinaturas; publicidade só para ver. Não vê o guia |
| Comercial | Publicidade (patrocinadores, campanhas, peças, painel, fatura). Não vê o guia |

O superusuário (o dono) é o único que muda permissões avulsas e mexe nos códigos de acesso.

### Colocar alguém na equipe

1. **Onde clicar:** "Contas" › "Usuários" › "Adicionar" (ou abra a pessoa).
2. **O que preencher:** e-mail, nome e senha; marque "Membro da equipe" e escolha o grupo.
3. **O que acontece depois:** a pessoa entra com e-mail e senha; em produção, cada navegador novo pede o código
   enviado ao e-mail dela (por isso o e-mail tem de ser só dela).

### Tirar alguém da equipe

Abra o usuário e desmarque "Membro da equipe" (ou "Ativo"). Usuários não são apagados.

### Se der errado

- A pessoa não vê um menu: confira o grupo.
- Não consigo editar a conta do dono: só o superusuário edita a conta de superusuário.

---

## 12. Rotinas automáticas

Rodam sozinhas no servidor (Celery), no horário de Cuiabá:

| Horário | O que faz |
|---|---|
| A cada 5 minutos | "Batimento": só prova que o agendador está vivo (aparece no registro do worker) |
| 3h00 | Expira os anúncios que passaram da validade (saem do ar; nunca são apagados) |
| 4h00 | LGPD: apaga comprovantes e anotações de faturas que passaram da guarda fiscal |
| 4h15 | Apaga o e-mail e os detalhes das denúncias decididas há mais que a guarda |
| 4h30 | **Guia de Negócios:** links do termo novo, pausa de quem não aceitou no prazo, limpeza dos perfis removidos depois de 5 anos e dos interessados sem ficha depois de 180 dias |
| 5h00 | Publicidade: campanhas que passaram do fim saem do ar; aviso à equipe antes do fim |
| 6h00 | Cobrança: gera as faturas, marca as vencidas, põe em atraso quem passou da carência e manda os lembretes |

Todos os e-mails do site também saem por essa fila (não travam a página).

### Como saber se parou

1. **Onde clicar:** no terminal do servidor, `docker compose ps` (o serviço `worker`, que também agenda as
   rotinas, deve estar "Up") e `docker compose logs --tail 50 worker` (deve aparecer o batimento a cada 5
   minutos).
2. **O que preencher:** nada.
3. **O que acontece depois:** se não estiverem rodando, `docker compose up -d`. Sinais no dia a dia: faturas não
   aparecem, e-mails não chegam, anúncios vencidos continuam no ar.

### Se der errado

- E-mails não chegam: o worker parou ou o SMTP do `.env` está errado.
- Rodou atrasado: as rotinas recuperam no dia seguinte; nada se perde.

---

## 13. Rotina do administrador (checklist)

**Todo dia**

1. A caixa "Pendências" no topo do painel: o que estiver com número amarelo.
   "Anúncios" › "Fila de moderação": aprovar ou recusar.
2. "Moderação" › "Denúncias": pendentes, principalmente "Em revisão (fora do ar)".
3. "Faturas e pagamentos" › "Faturas" › "Painel de cobrança": "aguardando confirmação".
4. "Anunciantes" › "Anunciantes": cadastros pendentes que já confirmaram o e-mail.
5. "Guia de Negócios" › "Pedidos dos perfis (titulares)": filtro "Prazo vencido".

**Toda semana**

6. "Privacidade (LGPD)" › "Pedidos dos titulares (LGPD)": prazos.
7. "Guia de Negócios" › "Perfis do guia": "Link vencido" (reenviar) e "Repetidos".
8. "Perfis do guia" › "Termo: quem falta" (quando houver termo novo).
9. "Publicidade" › "Campanhas" › "Painel de publicidade": campanhas a vencer.
10. "Anunciantes" › "Solicitações de cidade" e, no servidor, se o batimento das rotinas aparece (capítulo 12).

---

## 14. Dados de demonstração

Antes do lançamento, o site usa dados fictícios para testar todas as telas.

### Como identificar

- No admin, as listas têm a coluna e o filtro **"demonstração"**.
- E-mails terminam em **@demo.invalid** e os nomes do guia terminam em "(demo)".
- No site (só em desenvolvimento), uma faixa amarela avisa "Dados de demonstração".
- Usuários da equipe demo: `moderador@demo.invalid`, `financeiro@demo.invalid`, `comercial@demo.invalid` e
  `guia@demo.invalid` (senha: `DEMO_SENHA` do `.env`).

### Como apagar antes do lançamento

1. **Onde clicar:** terminal do servidor, na pasta do projeto.
2. **O que preencher:** `docker compose exec web python manage.py apagar_dados_demo` e digite **sim** para
   confirmar.
3. **O que acontece depois:** tudo que é demonstração some de uma vez (lojas, anúncios, faturas, campanhas,
   denúncias, pedidos, perfis do guia, convites, o termo demo) e as cidades ligadas só pela demonstração são
   desligadas. Contas e dados reais não são tocados. Os dados demo só podem ser criados em desenvolvimento.

### Se der errado

- Recriar os dados de teste (só em desenvolvimento): `criar_dados_demo`. Atenção: ele redefine as senhas dos
  usuários demo para `DEMO_SENHA`.

---

## 15. Glossário e perguntas frequentes

### Glossário

- **Admin / painel administrativo:** a área da equipe, no endereço secreto.
- **Painel (do anunciante):** a área do cliente, em `/painel/`.
- **Moderação:** revisão do anúncio antes de ir ao ar.
- **Carência:** dias depois do vencimento antes de pausar a loja por atraso.
- **Titular:** a pessoa dona dos dados (LGPD).
- **Encarregado (DPO):** quem responde pelos dados pessoais; o canal é o "e-mail de privacidade (LGPD)".
- **Aceite:** registro de que a pessoa concordou com um termo (versão, data e hora).
- **Perfil do guia:** a ficha de uma empresa ou profissional no Guia de Negócios.
- **Não contatar:** número que pediu para não receber convites; fica bloqueado.
- **Demo:** dado fictício de demonstração.

### Perguntas frequentes

**Posso apagar um anúncio, uma loja ou uma fatura?** Não. Pause, suspenda ou cancele; tudo fica no histórico.

**Mudei um preço e a loja continua pagando o antigo?** O preço novo vale para as próximas faturas.

**Como sei quem mudou algo?** Abra o registro e clique em "Histórico".

**O cliente não recebeu o e-mail.** Confira o spam dele e se as rotinas estão rodando (capítulo 12).

**O guia não aparece no menu.** "Configuração do guia" › "guia no ar".

**Esqueci o endereço do admin.** Está no `.env` do servidor (`ADMIN_URL`). Logado como equipe, o botão
"Painel administrativo" no topo do site leva até ele.
