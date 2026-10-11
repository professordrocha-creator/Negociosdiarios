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
| Foto de anúncio | JPG, PNG, WebP, HEIC | mín. 800×600; ideal 1600×1200 (4:3, horizontal) | 8 MB | WebP 1600 px + miniatura 400 px, sem EXIF |
| Fotos por anúncio | — | até 10 (1ª = capa; ordem por arrastar) | — | — |
| Logo da loja | JPG, PNG, WebP | quadrada, mín. 400×400 | 2 MB | WebP 400 e 96 px |
| Capa da loja | JPG, PNG, WebP | 1600×400 (4:1); área segura central 1200×300 | 4 MB | WebP 1600 e 800 px |
| Banner topo | JPG, PNG, WebP (sem animação) | 970×90 desktop **e** 320×100 celular | 1 MB cada | WebP |
| Card patrocinador | logo + texto | logo 400×400; texto até 80 caracteres | 1 MB | WebP |
| Anúncio nativo | texto + link | título 60; texto 120 caracteres | — | — |
| Título do anúncio | texto | 10 a 80 caracteres | — | — |
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
| Anúncio | `/anuncio/<codigo>-<slug>/` | Fotos, ficha, mapa aproximado, WhatsApp, denúncia |
| Loja | `/loja/<slug>/` | Vitrine da empresa e seus anúncios |
| Anuncie sua marca | `/anuncie/` | Mídia kit para patrocinadores |
| Planos | `/planos/` | Planos e cadastro de anunciante |
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
Só anunciante `ativo` (equipe, pendente e suspenso recebem 403 com explicação). Sprint 1:
dados da loja, resumo do plano (exemplo, "em breve") e meus anúncios (demo.json até a Sprint 3);
os demais itens do menu aparecem como "em breve".

| Tela | Para que serve |
|---|---|
| Meus anúncios | Lista, situação, renovar/pausar, uso do plano, aviso de fatura |
| Novo/editar anúncio | Formulário por categoria, fotos, localização (exata/aproximada) |
| Importar anúncios | Envio de XML/planilha, prévia com erros, confirmação |
| Estatísticas | Visualizações e cliques no WhatsApp por anúncio e por período |
| Página da loja | Logo, capa, cor, dados públicos, prévia ao vivo |
| Meu plano | Plano atual, upgrade/downgrade, escolha de anúncios a manter |
| Faturas | Histórico, Pix, comprovantes, notas fiscais |
| Meus dados (LGPD) | Ver, baixar e excluir dados; encerrar conta |

## 4. Painel do administrador (Daniel)
| Tela | Para que serve |
|---|---|
| Resumo do dia | Pendências, faturas vencendo, receita do mês, contratos de publicidade vencendo |
| Aprovações | Cadastros (CRECI/CNPJ) e anúncios aguardando análise |
| Anúncios / Anunciantes | Busca, edição, suspensão (com motivo) |
| Denúncias | Fila de denúncias com decisão registrada |
| Planos e preços | Criar/editar planos, limites, preços, carência |
| Faturas | Status, baixa manual com motivo, inadimplentes |
| Publicidade | Patrocinadores, contratos, peças, métricas |
| **Cidades atendidas** | Liberar estados/cidades; regiões (`Regiao`); bairros por cidade (`Bairro`, também dentro da cidade); "Solicitações de cidade" com as ações Liberar cidade e Recusar (motivo + e-mail) |
| Textos de ajuda | Editar os textos "Sobre esta tela" (`TextoAjuda`: chave da tela + um item por linha; em branco = sem caixa) |
| Equipe e permissões | Usuários de equipe e seus perfis |
| **Identidade do site** | Registro único `Configuracao`: nome, linha da região, slogan, empresa, cidade-sede, símbolos claro/escuro (SVG seguro ou PNG; favicon gerado sozinho), imagem de compartilhamento (sem EXIF), contatos (WhatsApp, e-mails, endereço, CNPJ, Instagram), textos da Sobre, limites de tamanho. **Valores da empresa** (`ValorEmpresa`, ordem editável na lista) |
| Configurações | Limites de mídia, prazos de expiração, contatos, redes, nome da região no slogan |
