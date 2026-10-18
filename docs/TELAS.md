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
| Foto de anúncio | JPG, PNG, WebP e HEIC/HEIF (iPhone) | qualquer proporção; recusa só abaixo de 200×150 (ícone); abaixo de 800×600 é aceita com aviso "Foto pequena"; prefira deitada | 15 MB (rede de segurança: o navegador reduz antes de enviar para no máx. 2560 px) | WebP 1600 px + miniatura 400 px, sem EXIF, rotação aplicada, nunca amplia |
| Fotos por anúncio | — | até 10 (1ª = capa; ordem por arrastar) | — | — |
| Logo da loja | JPG, PNG, WebP | quadrada, mín. 400×400 | 2 MB | WebP 400 e 96 px |
| Capa da loja | JPG, PNG, WebP | 1600×400 (4:1); área segura central 1200×300 | 4 MB | WebP 1600 e 800 px |
| Banner (home, busca, anúncio) | JPG, PNG, WebP (sem animação) | 970×90 computador **e** 320×100 celular (maior na mesma proporção é reduzido) | 1 MB cada | WebP no tamanho exato, sem EXIF |
| Card patrocinador (rodapé da home, 3 vagas) | logo + frase | logo 400×400; frase até 80 caracteres | 1 MB | WebP |
| Anúncio nativo (topo dos resultados da busca) | texto + link | título 60; texto 120 caracteres | — | — |
| Título do anúncio | texto | 10 a 80 caracteres (máx. 120) | — | — |
| Descrição do anúncio | texto puro | até 3.000 caracteres | — | — |
| Sobre a loja | texto puro | até 500 caracteres | — | — |
| Logo do site (admin) | SVG ou PNG transparente | quadrado 512×512 | 500 KB | favicon 32/180/512 px |
| Imagem de compartilhamento | JPG, PNG | 1200×630 | 1 MB | — |
| Importação (arquivo) | XML, CSV, XLSX | até 500 linhas por envio | 20 MB | — |

## 2. Telas públicas
| Tela | URL | Para que serve |
|---|---|---|
| Início | `/` | Busca rápida, destaques, vitrine de lojas, publicidade (banner no topo e até 3 cards de patrocinador antes das cidades; rótulo "Publicidade") |
| Busca | `/imoveis/`, `/veiculos/`, `/imoveis/mt/tangara-da-serra/`, `/veiculos/mt/tangara-da-serra/` | Convertida de prototipo/busca.html (Sprint 4B). Filtros num formulário GET (funciona sem JS); com HTMX a lista se atualiza sozinha e a URL limpa vai para a barra de endereço. No celular, os filtros ficam num painel (offcanvas) aberto pelo botão "Filtros". Busca por texto com ou sem acento. Cidade no caminho; imóvel: negócio, tipo, bairro (com cidade), preço, quartos, vagas, área; veículo: tipo, marca → modelo (só com anúncio), ano, preço, km, câmbio, combustível. Ordenar (recentes, menor e maior preço), 24 por página, chips dos filtros ativos com ✕ e "Limpar tudo", lista vazia com sugestão de ampliar. "Sobre esta tela". Mapa (Sprint 5): no celular/tablet, botão Lista | Mapa; no computador, mapa ao lado da lista. Marcadores com o preço, agrupados quando perto; ao clicar, card com foto, preço, título e link. Imóvel no ponto público (exata = o ponto; aproximada = deslocado; só o bairro fica fora, com o aviso "X anúncios sem localização no mapa"); veículos: as lojas que mostram o endereço, com quantos veículos de cada uma. "Buscar nesta área" ao mover o mapa (mantém os outros filtros; chip "Área do mapa"). Anúncio patrocinado: Sprint 7 |
| Anúncio | `/anuncio/<codigo>-<slug>/` | Veículo (`ND-VE-…`, Sprint 4A): ficha do catálogo (marca, modelo, versão, ano, km, câmbio, combustível, cor, portas, final da placa), opcionais, sem mapa ("Onde ver": endereço da loja só se ela permitir), schema.org `Car`/`Motorcycle` com vendedor `AutoDealer`. Imóvel: galeria (deslizar no celular com encaixe; setas, contador e miniaturas no `galeria.js`), ficha, descrição, preço/IPTU, mapa conforme `exibir_localizacao` (exata: marcador; aproximada: círculo de ~300 m com centro deslocado; só o bairro: só o nome, sem mapa), WhatsApp por `/anuncio/<codigo>/whatsapp/` (conta o clique; mensagem pronta com o código; número fora do HTML), loja com selo CRECI/CNPJ, dica de segurança, "Mais desta loja", "Denunciar" (página em breve) e visualizações. SEO: title com preço e cidade, description, canonical, Open Graph com JPEG 1200×630 da capa, schema.org `Offer`; no sitemap. Slug antigo ou só o código: 301 para a URL atual. O dono vê a própria página em qualquer situação (pré-visualização, noindex, sem contar visita) |
| Anúncio fora do ar | (mesma URL) | Pausado, expirado, excluído ou de loja suspensa: "Este anúncio não está mais disponível" com parecidos (mesma cidade e tipo), noindex, status 404 (410 se excluído). Nunca publicado ou demo com MOSTRAR_DEMO desligado: 404 comum |
| Loja | `/loja/<slug>/` | Vitrine da empresa: capa, logo ou monograma, selo verificado, sobre, horário, endereço (se a loja permitir), WhatsApp (sem número no HTML), mapa com o ponto da loja (só se ela permitir; Sprint 5) e anúncios. SEO: title, description, canonical, Open Graph, schema.org; 404 se não estiver ativa |
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
| Guia de Negócios | `/guia/` | G2. Só com o guia no ar (desligado: 404; a equipe logada vê com a faixa "Guia desligado", noindex). Nome da aba vem de `ConfiguracaoGuia.nome_guia`. Menu: primeiro item, com o selo "Novo" (no celular, no menu sanduíche); cartão abaixo da busca na home; link no rodapé (Buscar). Busca por texto (nome, categoria, sinônimos; sem acento e com erro de digitação; noindex) e cidades por estado (seletor de estado só com 2+). "Sobre esta tela" (`guia_inicio`) |
| Guia: cidade | `/guia/mt/tangara-da-serra/` | Grupos e categorias com empresas na cidade e a contagem; busca dentro da cidade. `guia_cidade` |
| Guia: categoria | `/guia/mt/tangara-da-serra/eletricista/` | Lista + mapa (Lista \| Mapa no celular; lado a lado no computador; pinos agrupados; só quem tem endereço, no ponto público; aviso de quantos atendem a domicílio). Filtros "Aberto agora" e bairro num formulário GET (sem JS) e com HTMX. Ordem sorteada por dia. 24 por página. Title/description por cidade + categoria, canonical, Open Graph; menos de `minimo_empresas_indexar` (3) ou filtrada: noindex, follow e fora do sitemap. `guia_categoria` |
| Guia: ficha | `/guia/empresa/<slug>/` | Nome, selos "CNPJ verificado" / "Profissional autônomo", categorias, frase, logo, endereço com mapa OU área de atendimento, horário da semana com "Aberto agora" (fuso do estado). Regulamentado: só nome, especialidade, registro, contato e local. Botões "Chamar no WhatsApp" e "Ver telefone" (número fora do HTML). schema.org `LocalBusiness` (sem telefone), canonical, Open Graph. Fora do ar: 404. `guia_empresa` |
| Guia: telefone | `/guia/contato/<id>/telefone/` | Sem JS: página só com o número (noindex); com HTMX troca o botão. Limite por hora |
| Aceite do Guia | `/guia/aceite/<token>/` | Guia de Negócios (G1): prévia exata da ficha, termo com versão e data, nome completo e "Autorizo a publicação"; confirmado, registra o aceite e publica. Link de uso único e com validade; usado ou vencido: "Este link já foi utilizado ou expirou" (410, sem dados). noindex, no-referrer, sem cache, CSRF, campo-armadilha e limite por hora. "Sobre esta tela" (`guia_aceite`) |
| Em breve | `/denunciar/` | Páginas ainda em construção (nunca 404) |

## 3. Painel do anunciante (`/painel/`)
Só anunciante `ativo` (equipe, pendente e suspenso recebem 403 com explicação). Hoje:
dados da loja, card do plano com dados reais (`templates/planos/_resumo_plano.html`: plano, uso X de Y,
valor, vencimento, situação; aviso de "em atraso: anúncios pausados" e de "sem plano"), visualizações e
cliques no WhatsApp dos últimos 30 dias, meus anúncios (do banco) e dados da loja; itens do menu ainda sem
tela aparecem como "em breve".

| Tela | Para que serve |
|---|---|
| Meus anúncios (no `/painel/`) | Lista do banco (capa, código, situação, "Expira em X dias"), ações por POST: Editar/Continuar, Pausar, Reativar, Renovar, Excluir (confirmação; exclusão lógica). Aviso de plano no limite com link de upgrade. Título leva à página pública (ou à pré-visualização). Colunas de visualizações e cliques no WhatsApp (total desde a publicação; visitante único por dia, sem robôs nem o dono) |
| Novo anúncio (`/painel/anuncios/novo/`) | Vai direto para o formulário do ramo da loja: corretor autônomo e imobiliária → imóvel (`?categoria=imovel`); revenda, concessionária e garagem → veículo (`?categoria=veiculo`). Categoria de outro ramo na URL: aviso e o formulário certo. A tela de escolha (com "Sobre esta tela") só aparece para loja com mais de um ramo (hoje nenhuma) |
| Anúncio de veículo (`…/novo/?categoria=veiculo`, `…/<codigo>/editar/`) | 3 etapas (sem mapa): **Dados** com o catálogo FIPE em selects encadeados (tipo → marca → modelo → versão; HTMX troca o bloco ao mudar um select, sem JS o botão "Atualizar listas"), anos de fabricação/modelo, km ("98.000"), combustível, câmbio, cor, portas, final da placa (opcional, 1 dígito), opcionais (caixas), preço, cidade, título (em branco = marca + modelo + versão + ano) e descrição; **Fotos**; **Revisão**. Mesmas regras do imóvel (limite do plano, moderação, validade) |
| Novo/editar anúncio de imóvel (`…/novo/?categoria=imovel`, `/painel/anuncios/<codigo>/editar/`) | 4 etapas, cada uma com "Sobre esta tela": **Dados** (título, tipo, venda/aluguel, preço e áreas no formato brasileiro, quartos, IPTU, descrição); **Localização** (`…/editar/localizacao/`: cidade liberada, bairro, endereço privado, ponto no mapa Leaflet, o que o público vê); **Fotos** (`…/editar/fotos/`: várias de uma vez, do celular ou do computador; o navegador reduz as grandes antes de enviar (`static/js/reduzir-fotos.js`, botão "Preparando fotos…"); HEIC aceito; foto pequena aceita com selo "Foto pequena" e aviso no topo; arrastar ou setas, excluir); **Revisão** (`…/editar/revisao/`: pendências, Salvar como rascunho / Enviar para publicação; no limite o envio é bloqueado com oferta de upgrade). Em análise não é editável |
| Importar anúncios | Envio de XML/planilha, prévia com erros, confirmação |
| Estatísticas | Visualizações e cliques no WhatsApp por anúncio e por período |
| Página da loja (`/painel/loja/`) | Logo e capa (validados; WebP pelo Celery), cor (paleta), nome, endereço da página, sobre, WhatsApp, horário, endereço e "mostrar no mapa", ponto da loja no mapa (toque/arraste; "Tirar o ponto"; perto da cidade da loja; Sprint 5), Instagram, site; prévia ao vivo (`static/js/painel-loja.js`). CRECI/CNPJ só leitura |
| Meu plano (`/painel/plano/`) | Card do plano, pedido em análise e pedido de troca (plano + mensal/anual; vai para o admin e envia e-mail; o pagamento é pelas Faturas). Carência vem da `Configuracao`. Pedido para plano menor que o uso leva a **Escolher anúncios** (`/painel/plano/escolher-anuncios/`: marca até o novo limite; os outros são pausados na aprovação) |
| Termos de Uso (`/termos/`) e Política de Privacidade (`/privacidade/`) | Sprint 7B. Versão em vigor (texto do admin em blocos escapados), "Versão X · em vigor desde"; a Política termina com o Encarregado e a seção Cookies (tabela); `/cookies/` leva a ela. Rascunho: sem aviso público, só `noindex` |
| Termos atualizados (`/painel/termos-atualizados/`) | Sprint 7B. Versão nova sem aceite: no login e ao abrir o painel aparece o resumo do que mudou, link para o texto, caixa "Li e aceito" (sem marcação prévia), Continuar ou "Não aceito (sair)"; "Sobre esta tela" |
| Meus dados (`/painel/meus-dados/`) | Sprint 7B. O que guardamos, "Baixar meus dados" (senha de novo → JSON), documentos aceitos, pedidos feitos e o link para excluir; vale mesmo sem aceitar a versão nova; "Sobre esta tela" |
| Excluir minha conta (`/painel/meus-dados/excluir/`) | Sprint 7B. O que acontece e o que fica guardado, aviso de fatura em aberto (não impede), senha e a palavra EXCLUIR; depois, sai e volta à home com a confirmação |
| Denunciar anúncio (`/denunciar/?anuncio=<codigo>`) | Sprint 7B parte 2. Sem login, a partir do botão "Denunciar" do anúncio (código já preenchido) ou do rodapé: código, motivo (golpe, já vendido, preço ou dados falsos, conteúdo impróprio, dados de terceiros, outro), detalhes e e-mail opcionais, campo-armadilha escondido; enviada, volta ao anúncio com o aviso; "Sobre esta tela"; noindex |
| Fatura de publicidade (`/fatura/<token>/`) | Sprint 7A. Página pública (sem login, noindex) pelo link enviado ao patrocinador: valor, período, vencimento, QR Code e Pix copia e cola com Copiar, link do boleto, "Já paguei" com comprovante (limite por IP) e a situação (aguardando, paga, cancelada); "Sobre esta tela" |
| Faturas (`/painel/faturas/`) | Sprint 6. Faturas em aberto com valor, vencimento, período, **QR Code** e **Pix copia e cola** com botão Copiar (`static/js/copiar.js`), link do boleto se a equipe colou, aviso de vencida (carência da `Configuracao`) e de comprovante recusado (com o motivo); "Já paguei" abre o envio do comprovante (PDF/JPG/PNG/WebP, limite da `Configuracao`) e um recado opcional; fatura aguardando confirmação com link para o comprovante enviado; histórico (pagas e canceladas). Sem Pix configurado no `.env`: aviso. Notas fiscais: depois do CNPJ |
| Meus dados (LGPD) | Ver, baixar e excluir dados; encerrar conta |

## 4. Painel do administrador (Daniel)
| Tela | Para que serve |
|---|---|
| Resumo do dia | Pendências, faturas vencendo, receita do mês, contratos de publicidade vencendo |
| Aprovações | Cadastros (CRECI/CNPJ) em Anunciantes; anúncios em **Anúncios › Fila de moderação** (mais antigos primeiro, capa na lista, fotos grandes, ficha, endereço e ponto privados; ações Aprovar e Recusar com motivo, os dois com e-mail). **Anúncios** lista todos (filtros por situação, categoria, cidade), só leitura |
| Anúncios / Anunciantes | Busca, edição, suspensão (com motivo) |
| Denúncias | Fila de denúncias com decisão registrada |
| Regras do negócio (em Identidade do site) | Carência de pagamento, dias de antecedência da fatura, limite do comprovante, prazo de resposta ao titular, guarda fiscal (anos), denúncias de golpe para pausar, denúncias por visitante por dia, guarda do contato da denúncia, validade do anúncio, aviso de expiração e quais anúncios passam por moderação |
| Catálogo de veículos | Marcas, modelos e versões da Tabela FIPE (só consulta; "ativo" editável para esconder do formulário; sem criar nem apagar) |
| Planos e preços | Planos: preço mensal/anual, limite, ordem e "à venda" editáveis na lista (com histórico; sem apagar). Assinaturas: filtro por situação/periodicidade/plano, ação "Registrar pagamento manual" (motivo). Pedidos de troca: Aprovar / Recusar (motivo), com e-mail. Carência em Identidade do site › Regras do negócio |
| Faturas (Cobrança) | Sprint 6. Lista com filtros (situação, vencimento, forma), busca por código/loja e botão **Painel de cobrança** (a receber no mês, recebido no mês, vencendo em 7 dias, vencidas, aguardando confirmação; cada número abre a lista filtrada). Ações: **Confirmar pagamento** (forma + observação; renova e reativa), **Recusar comprovante** (motivo por e-mail) e **Cancelar** (motivo). Ficha: link do boleto, observação e valor (só aberta) editáveis; comprovante abre pelo admin. Sem criar nem apagar. E-mails de cobrança: assunto, texto e "enviar" editáveis |
| Denúncias (Moderação) | Sprint 7B parte 2. Fila com pendentes primeiro (as mais antigas no topo): recebida em, anúncio (link para a página), motivo, situação, como o anúncio está ("Em revisão" quando a pausa foi automática). Ficha com detalhes e e-mail de quem denunciou (nunca a origem). Ações: **Aceitar** (pausar ou remover o anúncio, motivo por e-mail ao anunciante) e **Descartar** (se estava em revisão, volta ao ar); a decisão vale para todas as pendentes do anúncio. Sem criar nem apagar; histórico |
| Privacidade (LGPD) | Sprint 7B. **Documentos legais**: tipo, versão, vigência, "o que mudou", texto (## título, - item, variáveis {site}...), publicado, "rascunho: revisão jurídica pendente" (aviso amarelo só aqui); em vigor = texto travado (crie versão nova). **Pedidos dos titulares**: recebido em, tipo, titular, origem, situação, prazo (15 dias), "prazo vencido", ação "Marcar como atendido" (com o que foi feito). Sem apagar |
| Publicidade | Sprint 7A. **Patrocinadores** (contato, loja do site opcional) e **Campanhas** (posições, cidades, início, fim, valor, situação; peças na mesma tela: formato, imagens com o tamanho e o peso da `Configuracao` na ajuda, prévia depois do processamento, texto alternativo, título/texto, link, ativo; ação "Gerar fatura (Pix)"). **Painel de publicidade** (botão na lista): no ar, terminando em breve, impressões, cliques e CTR por campanha no período, "Sobre esta tela" e Exportar CSV. Sem apagar |
| **Cidades atendidas** | Liberar estados/cidades; regiões (`Regiao`); bairros por cidade (`Bairro`, também dentro da cidade); "Solicitações de cidade" com as ações Liberar cidade e Recusar (motivo + e-mail) |
| Guia de Negócios | G1. **Perfis do guia**: cadastro assistido em uma coluna para o celular, "Sobre esta tela" (`guia_cadastro`) e help_text em cada campo; blocos Quem é, Contato, Onde atende ("tem endereço" com pino no mapa ou "a domicílio" com a área), Horário (um campo por dia), Documento e responsável (privado; CPF vira resumo). Painel de publicação no topo: situação, aceite vigente, alerta de cadastro repetido (não bloqueia), o que falta e os botões **Enviar por WhatsApp** (gera o link e mostra a mensagem com o botão do wa.me), **Aceite em papel** (foto do termo assinado, privada), **Publicar** (desabilitado com explicação sem o aceite vigente) e **Pausar**; aceites (com "revogar", que despublica na hora) e convites na mesma ficha. **Categorias** e grupos (desativar; com perfis não se apagam), **Termos do guia** (versão; aviso de rascunho jurídico; em vigor = travado), **Pedidos dos perfis** e **Configuração do guia** |
| Textos de ajuda | Editar os textos "Sobre esta tela" (`TextoAjuda`: chave da tela + um item por linha; em branco = sem caixa) |
| Equipe e permissões | Usuários de equipe e seus perfis |
| **Identidade do site** | Registro único `Configuracao`: nome, linha da região, slogan, empresa, cidade-sede, símbolos claro/escuro (SVG seguro ou PNG; favicon gerado sozinho), imagem de compartilhamento (sem EXIF), contatos (WhatsApp, e-mails, endereço, CNPJ, Instagram), textos da Sobre, limites de tamanho. **Valores da empresa** (`ValorEmpresa`, ordem editável na lista) |
| Configurações | Limites de mídia, prazos de expiração, contatos, redes, nome da região no slogan |
