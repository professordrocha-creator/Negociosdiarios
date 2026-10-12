# Telas do sistema e limites

Toda tela tem:
1. Caixa **"Sobre esta tela"** (para que serve, regras, limites), com textos no modelo
   `TextoAjuda`, editáveis pelo admin sem deploy.
2. `help_text` em **todo** campo de formulário que tenha limite, formato ou consequência.
3. Mensagens de erro que dizem o que fazer ("Imagem maior que 8 MB. Reduza e envie de novo.").

## 1. Limites de mídia e texto
Valores ficam no modelo `Configuracao` (admin). Os números abaixo são o **padrão inicial**.

| Item | Formato aceito | Tamanho / proporção | Peso máx. | O sistema gera |
|---|---|---|---|---|
| Foto de anúncio | JPG, PNG, WebP (HEIC do iPhone chega como JPG) | mín. 800×600; ideal 1600×1200 (4:3, horizontal) | 8 MB | WebP 1600 px + miniatura 400 px, sem EXIF, rotação aplicada |
| Fotos por anúncio | — | até 10 (1ª = capa; ordem por arrastar) | — | — |
| Logo da loja | JPG, PNG, WebP | quadrada, mín. 400×400 | 2 MB | WebP 400 e 96 px |
| Capa da loja | JPG, PNG, WebP | 1600×400 (4:1); área segura central 1200×300 | 4 MB | WebP 1600 e 800 px |
| Banner topo | JPG, PNG, WebP (sem animação) | 970×90 desktop **e** 320×100 celular | 1 MB cada | WebP |
| Card patrocinador | logo + texto | logo 400×400; texto até 80 caracteres | 1 MB | WebP |
| Anúncio nativo | texto + link | título 60; texto 120 caracteres | — | — |
| Título do anúncio | texto | 10 a 80 caracteres (máx. 120) | — | — |
| Descrição do anúncio | texto puro | até 3.000 caracteres | — | — |
| Sobre a loja | texto puro | até 500 caracteres | — | — |
| Logo do site (admin) | SVG ou PNG transparente | quadrado 512×512 | 500 KB | favicon 32/180/512 px |
| Imagem de compartilhamento | JPG, PNG | 1200×630 | 1 MB | — |
| Importação (arquivo) | XML, CSV, XLSX | até 500 linhas por envio | 20 MB | — |

## 2. Telas públicas
| Tela | URL | Para que serve |
|---|---|---|
| Início | `/` | Busca rápida, destaques, vitrine de lojas, publicidade |
| Busca | `/imoveis/mt/tangara-da-serra/` | Filtros, lista, mapa, anúncio nativo |
| Anúncio | `/anuncio/<codigo>-<slug>/` | Galeria (deslizar no celular com encaixe; setas, contador e miniaturas no `galeria.js`), ficha, descrição, preço/IPTU, mapa conforme `exibir_localizacao` (exata: marcador; aproximada: círculo de ~300 m com centro deslocado; só o bairro: só o nome, sem mapa), WhatsApp por `/anuncio/<codigo>/whatsapp/` (conta o clique; mensagem pronta com o código; número fora do HTML), loja com selo CRECI/CNPJ, dica de segurança, "Mais desta loja", "Denunciar" (página em breve) e visualizações. SEO: title com preço e cidade, description, canonical, Open Graph com JPEG 1200×630 da capa, schema.org `Offer`; no sitemap. Slug antigo ou só o código: 301 para a URL atual. O dono vê a própria página em qualquer situação (pré-visualização, noindex, sem contar visita) |
| Anúncio fora do ar | (mesma URL) | Pausado, expirado, excluído ou de loja suspensa: "Este anúncio não está mais disponível" com parecidos (mesma cidade e tipo), noindex, status 404 (410 se excluído). Nunca publicado ou demo com MOSTRAR_DEMO desligado: 404 comum |
| Loja | `/loja/<slug>/` | Vitrine da empresa: capa, logo ou monograma, selo verificado, sobre, horário, endereço (se a loja permitir), WhatsApp (sem número no HTML) e anúncios. SEO: title, description, canonical, Open Graph, schema.org; 404 se não estiver ativa |
| Lojas | `/lojas/` | Lojas verificadas, filtro por tipo e cidade, 24 por página |
| Sitemap e robots | `/sitemap.xml`, `/robots.txt` | Páginas públicas e lojas ativas; robots esconde painel e login |
| Anuncie sua marca | `/anuncie/` | Mídia kit para patrocinadores |
| Planos | `/planos/` | Planos à venda, lidos do banco (`planos.Plano`, editável no admin) |
| Sobre | `/sobre/` | Quem somos, missão, visão, valores (textos do painel) |
| Institucionais | `/privacidade/`, `/termos/`, `/cookies/` | Documentos legais (rascunhos até a revisão do advogado) |
| Contato | `/contato/` | WhatsApp, e-mails e endereço do site |
| Entrar | `/entrar/` | Login do anunciante (e-mail e senha; só loja ativa; equipe usa o admin) |
| Esqueci a senha | `/entrar/esqueci/` → e-mail → `/entrar/redefinir/<uid>/<token>/` | Nova senha por link de uso único (só clientes) |
| Cadastro | `/cadastro/` | Conta + loja + aceite dos Termos e da Privacidade; nasce pendente. Mostra todas as cidades do estado liberado (atendidas primeiro; as outras marcadas "ainda não atendida", que geram solicitação) |
| Cadastro recebido | `/cadastro/obrigado/` | Próximos passos (confirmar e-mail, análise, aprovação) |
| Confirmar e-mail | `/cadastro/confirmar/<token>/` | Link do e-mail (48 h, uso único); vencido: pede outro |
| Em breve | `/imoveis/`, `/veiculos/`, `/lojas/`, `/denunciar/` | Páginas ainda em construção (nunca 404) |

## 3. Painel do anunciante (`/painel/`)
Só anunciante `ativo` (equipe, pendente e suspenso recebem 403 com explicação). Hoje:
dados da loja, card do plano com dados reais (`templates/planos/_resumo_plano.html`: plano, uso X de Y,
valor, vencimento, situação; aviso de "em atraso: anúncios pausados" e de "sem plano"), visualizações e
cliques no WhatsApp dos últimos 30 dias, meus anúncios (do banco) e dados da loja; itens do menu ainda sem
tela aparecem como "em breve".

| Tela | Para que serve |
|---|---|
| Meus anúncios (no `/painel/`) | Lista do banco (capa, código, situação, "Expira em X dias"), ações por POST: Editar/Continuar, Pausar, Reativar, Renovar, Excluir (confirmação; exclusão lógica). Aviso de plano no limite com link de upgrade. Título leva à página pública (ou à pré-visualização). Colunas de visualizações e cliques no WhatsApp (total desde a publicação; visitante único por dia, sem robôs nem o dono) |
| Novo/editar anúncio (`/painel/anuncios/novo/`, `/painel/anuncios/<codigo>/editar/`) | 4 etapas, cada uma com "Sobre esta tela": **Dados** (título, tipo, venda/aluguel, preço e áreas no formato brasileiro, quartos, IPTU, descrição); **Localização** (`…/editar/localizacao/`: cidade liberada, bairro, endereço privado, ponto no mapa Leaflet, o que o público vê); **Fotos** (`…/editar/fotos/`: várias de uma vez, arrastar ou setas, excluir); **Revisão** (`…/editar/revisao/`: pendências, Salvar como rascunho / Enviar para publicação; no limite o envio é bloqueado com oferta de upgrade). Em análise não é editável |
| Importar anúncios | Envio de XML/planilha, prévia com erros, confirmação |
| Estatísticas | Visualizações e cliques no WhatsApp por anúncio e por período |
| Página da loja (`/painel/loja/`) | Logo e capa (validados; WebP pelo Celery), cor (paleta), nome, endereço da página, sobre, WhatsApp, horário, endereço e "mostrar no mapa", Instagram, site; prévia ao vivo (`static/js/painel-loja.js`). CRECI/CNPJ só leitura |
| Meu plano (`/painel/plano/`) | Card do plano, pedido em análise e pedido de troca (plano + mensal/anual; sem pagamento online: vai para o admin e envia e-mail). Carência vem da `Configuracao`. Pedido para plano menor que o uso leva a **Escolher anúncios** (`/painel/plano/escolher-anuncios/`: marca até o novo limite; os outros são pausados na aprovação) |
| Faturas | Histórico, Pix, comprovantes, notas fiscais |
| Meus dados (LGPD) | Ver, baixar e excluir dados; encerrar conta |

## 4. Painel do administrador (Daniel)
| Tela | Para que serve |
|---|---|
| Resumo do dia | Pendências, faturas vencendo, receita do mês, contratos de publicidade vencendo |
| Aprovações | Cadastros (CRECI/CNPJ) em Anunciantes; anúncios em **Anúncios › Fila de moderação** (mais antigos primeiro, capa na lista, fotos grandes, ficha, endereço e ponto privados; ações Aprovar e Recusar com motivo, os dois com e-mail). **Anúncios** lista todos (filtros por situação, categoria, cidade), só leitura |
| Anúncios / Anunciantes | Busca, edição, suspensão (com motivo) |
| Denúncias | Fila de denúncias com decisão registrada |
| Regras do negócio (em Identidade do site) | Carência de pagamento, validade do anúncio, aviso de expiração e quais anúncios passam por moderação |
| Planos e preços | Planos: preço mensal/anual, limite, ordem e "à venda" editáveis na lista (com histórico; sem apagar). Assinaturas: filtro por situação/periodicidade/plano, ação "Registrar pagamento manual" (motivo). Pedidos de troca: Aprovar / Recusar (motivo), com e-mail. Carência em Identidade do site › Regras do negócio |
| Faturas | Status, baixa manual com motivo, inadimplentes |
| Publicidade | Patrocinadores, contratos, peças, métricas |
| **Cidades atendidas** | Liberar estados/cidades; regiões (`Regiao`); bairros por cidade (`Bairro`, também dentro da cidade); "Solicitações de cidade" com as ações Liberar cidade e Recusar (motivo + e-mail) |
| Textos de ajuda | Editar os textos "Sobre esta tela" (`TextoAjuda`: chave da tela + um item por linha; em branco = sem caixa) |
| Equipe e permissões | Usuários de equipe e seus perfis |
| **Identidade do site** | Registro único `Configuracao`: nome, linha da região, slogan, empresa, cidade-sede, símbolos claro/escuro (SVG seguro ou PNG; favicon gerado sozinho), imagem de compartilhamento (sem EXIF), contatos (WhatsApp, e-mails, endereço, CNPJ, Instagram), textos da Sobre, limites de tamanho. **Valores da empresa** (`ValorEmpresa`, ordem editável na lista) |
| Configurações | Limites de mídia, prazos de expiração, contatos, redes, nome da região no slogan |
