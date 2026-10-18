# Guia de Negócios — especificação

> Documento para o Claude Code seguir. Leia junto com CLAUDE.md, ARQUITETURA.md, SEGURANCA.md, LGPD.md,
> GUIA_LGPD_E_TERMO.md e docs/guia/categorias_iniciais.csv.
> Status: G1 (base) e G2 (páginas públicas) feitas em 2026-10-18. Ordem decidida em 2026-10-18: o guia vem antes da Sprint 8 (adiada).

## 1. O que é

Aba do Negócios Diários: diretório **gratuito** de serviços, profissionais e comércios de Mato Grosso.
O visitante escolhe **cidade + tipo de serviço**, vê a lista e o mapa e chama pelo WhatsApp.

Nome exibido da aba: vem de `ConfiguracaoGuia.nome_guia` (padrão "Guia de Negócios"). Nunca escrever o nome fixo no HTML.

### Por quê
- Dá conteúdo ao site no lançamento e atrai tráfego do Google (busca por serviço é mais frequente que por imóvel).
- Uma página por cidade + categoria (`/guia/mt/tangara-da-serra/vidracarias/`) é ótima para SEO local.
- Receita indireta futura: destaque pago, banner por categoria, upgrade para anunciar imóveis ou veículos.

### Princípios
1. **Nada vai ao ar sem autorização registrada** do responsável (aceite eletrônico simples).
2. **Dado mínimo**: só o que ajuda a pessoa a contratar (nome, contato, local ou área de atendimento, horário).
3. **Sem endereço residencial público.** Quem atende em casa ou a domicílio usa "área de atendimento".
4. **Gratuito e neutro na V1**: sem avaliações, sem comentários, sem destaque pago.
5. **Isolado dos classificados**: app Django próprio (`guia`), URLs próprias, para poder virar outro site um dia.

## 2. Escopo

### Entra na V1
- Cadastro assistido: Daniel cadastra pelo celular, no admin, e envia link de aceite pelo WhatsApp.
- Aceite eletrônico com registro (quem, quando, versão do termo).
- Páginas públicas: escolher cidade, categorias, lista com mapa, ficha da empresa.
- Contagem de visualizações e de cliques (WhatsApp, telefone) por empresa.
- Pedido de alteração ou remoção pelo próprio titular, direto na ficha.
- Convites para empresas do projeto antigo (lista de contatos, sem publicar nada antes do aceite).
- Dados demo.

### Fica para depois (não fazer agora)
- Avaliações e comentários.
- Destaque pago e banner por categoria (preparar apenas o conceito, sem campos sem uso).
- Painel do próprio titular com relatórios (V1: Daniel manda os números por WhatsApp quando pedirem).
- Consulta automática de CNPJ na Receita.
- Envio automático e em massa de mensagens.

### Autocadastro (etapa G4, opcional)
Depois das primeiras 50 a 100 empresas: "Cadastre sua empresa grátis". A pessoa cria conta, preenche, aceita o termo na hora
e entra na fila de aprovação do admin. Reaproveita `contas` e `AceiteDocumento`.

## 3. Como encaixa no sistema

| Reaproveita | Como |
|---|---|
| `core` | Estado, Cidade (IBGE), cidades liberadas, `Configuracao`, TextoAjuda |
| `contas` | Equipe e grupos de permissão; no autocadastro, o Usuario |
| Mapa (Leaflet local) | Mesmo componente da busca de imóveis, com `ponto_publico` |
| `estatisticas` | Mesma ideia de contagem sem IP e redirecionamento de clique |
| Imagens (Celery) | Logo passa pelo mesmo tratamento das fotos: WebP, sem EXIF |
| `privacidade` | Pedidos do titular, prazos e rotina de limpeza |
| `publicidade` | V2: posições de banner por categoria |

**Importante:** o guia NÃO reaproveita o modelo `Anunciante`. A empresa listada não tem login e nem sempre vira cliente.
`PerfilGuia` tem um vínculo opcional (`anunciante`) para quando a mesma empresa também anunciar imóveis ou veículos.

## 4. Modelo de dados (app `guia`)

Nomes em português, DecimalField para dinheiro (não usado aqui), telefones em E.164, fuso do estado.

### GrupoCategoria e CategoriaServico
- `GrupoCategoria`: nome, slug, ordem.
- `CategoriaServico`: grupo, nome, slug (único), ordem, ativa, `regulamentada` (bool), `rotulo_registro` (ex.: "CRM", "OAB"),
  `sinonimos` (texto, usado na busca e no SEO).
- Carga inicial: `docs/guia/categorias_iniciais.csv` por comando `carregar_categorias_guia` (idempotente, upsert por slug).
- Editável no admin. Categoria com empresas não pode ser apagada, só desativada.

### PerfilGuia (a empresa ou o profissional listado)
- Identificação: `nome_publico`, `slug` (único, inclui a cidade), `tipo` (empresa | autonomo | profissional_regulamentado),
  `frase` (até 160 caracteres, sem links, texto puro).
- Documento (privado, nunca exibido):
  - empresa: `cnpj` (validado), `cnpj_verificado_em` (data em que o admin conferiu a situação ativa);
  - autônomo: **CPF não é guardado em claro**; guardar `cpf_hash` (HMAC com chave do .env, só para evitar duplicidade) e `cpf_final` (2 últimos dígitos, para conferência);
  - regulamentado: `registro_profissional` (ex.: "CRM-MT 1234"), exibido na ficha.
- `responsavel_nome` (quem autorizou), `responsavel_contato` (privado).
- Contato público: `whatsapp` e `telefone` (E.164), mostrados por botões com contagem (ver §7).
- Local: `cidade` (FK IBGE), `bairro`, e UM dos dois modos:
  - `atende_em_endereco`: endereço público + `ponto` (PointField);
  - `atende_a_domicilio`: `area_atendimento` (texto, ex.: "Tangará da Serra e região") e **sem endereço**; o mapa usa só a cidade.
- `ponto_publico`: calculado (aproximado quando necessário), é o único ponto que sai do servidor.
- `horarios` (por dia da semana, com intervalos) e `fuso` (do estado; padrão America/Cuiaba).
- `logo` (opcional).
- `categorias`: M2M, **máximo 3** (validar no modelo e no formulário).
- `status`: rascunho | aguardando_aceite | publicado | pausado | removido.
- `origem`: cadastro_assistido | autocadastro | lista_antiga.
- `anunciante` (FK opcional), `cadastrado_por` (Usuario da equipe), datas, `MarcaDemo`, simple-history.

### TermoGuia
- `versao`, `texto` (editável no admin), `vigente_desde`, `rascunho_juridico` (bool, true até o advogado revisar).
- Versão em vigor fica travada; mudar = criar versão nova (mesmo padrão dos Termos de Uso).

### ConviteAceite
- `perfil`, `token` (`secrets.token_urlsafe(32)`), `criado_em`, `expira_em` (padrão 15 dias, configurável), `usado_em`, `canal` (whatsapp | email | presencial).
- Uso único. Depois de usado ou expirado, mostra "link já utilizado" sem revelar dados.

### AceitePublicacao
- `perfil`, `termo` (FK para a versão), `nome_digitado`, `aceito_em`, `ip_truncado` (último octeto zerado) e `agente_resumido`, `convite`.
- Guardar por todo o tempo em que o perfil existir e mais o prazo de prova configurável (padrão 5 anos). Decisão a validar com o advogado.
- Revogar o aceite = despublicar na hora e registrar a data da revogação.

### EstatisticaGuiaDia
- `perfil`, `dia`, `visualizacoes`, `cliques_whatsapp`, `cliques_telefone`. Sem IP e sem cookie; mesma regra anti-robô das estatísticas.

### PedidoDoPerfil
- Pedido de alteração, remoção ou outro, feito na ficha pública (sem login): `perfil`, `tipo`, `descricao`, `contato`, `criado_em`,
  `prazo_ate` (15 dias), `status`, `decidido_por`. Aparece junto com os pedidos do titular já existentes em `privacidade`.

### ConfiguracaoGuia (registro único)
- `ativo` (liga e desliga a aba inteira), `nome_guia`, `max_categorias` (3), `limite_frase` (160),
  limites de tamanho da logo (leem de `Configuracao`), `dias_validade_convite` (15), `minimo_empresas_indexar` (3).

## 5. Regras de negócio

1. **Publicar** exige: aceite válido da versão vigente, ao menos 1 categoria, cidade liberada, WhatsApp ou telefone válido, e local OU área de atendimento.
2. Máquina de estados: rascunho → aguardando_aceite → publicado ⇄ pausado → removido. Só o aceite leva a `publicado` (o admin não pula essa etapa; botão desabilitado com explicação).
3. **Termo novo** não despublica ninguém: empresas publicadas recebem o convite para aceitar a nova versão e têm prazo de 30 dias. Passado o prazo sem aceite, o perfil é pausado (nunca apagado).
4. **Categorias reguladas** (saúde, advocacia, contabilidade, engenharia, corretagem, personal): a ficha mostra só nome, especialidade, registro e contato.
   Sem frase promocional (o campo some do formulário), sem destaque futuro e com o aviso padrão do conselho quando existir.
5. **Duplicidade**: alertar o admin se o mesmo CNPJ, `cpf_hash` ou WhatsApp já existir. O alerta não bloqueia; o admin decide.
6. **Selo "CNPJ verificado"** só aparece se o admin marcou `cnpj_verificado_em`. Autônomo recebe o selo "Profissional autônomo".
7. **Aberto agora**: calculado no fuso do estado da cidade. Sem horário cadastrado, não mostra nada.
8. **Remoção**: despublicar e apagar logo e dados de contato conforme o pedido; manter só o aceite e o registro do pedido pelo prazo de prova.
9. **Cidade desligada pelo admin**: perfis da cidade ficam pausados, não apagados.
10. **Rodízio justo na lista**: ordem aleatória estável por dia (semente = data), nunca ordem de cadastro. Sem destaque pago na V1.

## 6. Páginas e URLs (todas com UF)

| URL | O que mostra |
|---|---|
| `/guia/` | Escolher estado (se houver mais de um liberado) e cidade; busca por texto |
| `/guia/<uf>/<cidade>/` | Grupos e categorias da cidade, com contagem |
| `/guia/<uf>/<cidade>/<categoria>/` | Lista + mapa (alternar Lista / Mapa), filtros: "Aberto agora", bairro |
| `/guia/empresa/<slug>/` | Ficha da empresa |
| `/guia/aceite/<token>/` | Tela de conferência e autorização |
| `/guia/contato/<id>/whatsapp/` | Conta o clique e redireciona para `wa.me` |
| `/guia/pedido/<slug>/` | Formulário "Esta é minha empresa: alterar ou remover" |

- Toda tela tem "Sobre esta tela" (TextoAjuda). Mobile primeiro.
- SEO: `<title>` e description por cidade + categoria, canonical, Open Graph, schema.org `LocalBusiness` na ficha,
  entrada no `sitemap.xml` (separado por seção).
- **Página fina não é indexada**: cidade + categoria com menos de `minimo_empresas_indexar` empresas recebe `noindex, follow` e fica fora do sitemap.
- A ficha publicada pode ser indexada; perfil pausado, removido ou aguardando aceite devolve 404 (nunca mostra dados).
- Busca por texto: nome, categoria e sinônimos, com `unaccent` e `pg_trgm` (tolerância a erro de digitação).

## 7. Contato sem expor dados

- WhatsApp: botão que passa por `/guia/contato/<id>/whatsapp/` (conta o clique e redireciona). O número não fica em texto no HTML.
- Telefone: botão "Ver telefone" (HTMX) que revela o número e conta o clique. Sem JavaScript, leva a uma página que mostra o número.
- Robôs não contam. Limite de requisições por visitante.

## 8. Cadastro assistido (fluxo do Daniel em campo)

Tela do admin pensada para **celular**, rápida, em uma coluna, com TextoAjuda em cada campo:
1. Escolher cidade e categoria(s). Digitar nome, WhatsApp, horário, frase. Subir a logo (opcional).
2. Escolher "tem endereço" (marcar o pino no mapa) ou "atende a domicílio" (área de atendimento).
3. Salvar → status "aguardando aceite" → botão **Enviar por WhatsApp**: abre `wa.me` com mensagem pronta e o link `/guia/aceite/<token>/`.
4. O responsável abre o link, confere a prévia da ficha, digita o nome, marca "Autorizo a publicação" e toca em confirmar.
5. Publicado automaticamente, e o admin vê o registro do aceite.
6. Alternativa presencial: o admin marca "aceite em papel", anexa a foto do termo (storage privado) e publica. O registro mostra `canal = presencial`.

Fila do admin: aguardando aceite (reenviar link, ver quem expirou), publicados, pausados, pedidos do titular, duplicidades.
Ações em lote: pausar por cidade ou categoria. Exportar CSV (neutralizar fórmulas que começam com = + - @).

## 9. Convites para o projeto antigo

- Os dados antigos entram como **lista de contatos** (CSV: nome, WhatsApp, cidade, categoria) em um modelo separado, sem página pública.
- Daniel envia o convite pelo WhatsApp, um a um, a partir do admin (botão `wa.me`). **Nada de envio automático em massa.**
- Quem aceitar vira `PerfilGuia` com `origem = lista_antiga`. Quem pedir para sair vai para uma lista de "não contatar" que bloqueia novos convites.
- Não copiar dados do Google Maps, de outros sites ou por robô.

## 10. Segurança

- Token de aceite: 32 bytes aleatórios, uso único, expira, nunca o id. Página com `noindex` e `Referrer-Policy: no-referrer`.
- Formulários públicos (pedido, aceite): CSRF, honeypot, limite por visitante e por hora (hash de IP com sal diário; sem gravar IP).
- Texto livre (frase, descrição, nome) é sempre escapado. Sem links nem HTML na frase.
- Logo: mesmo tratamento das fotos (tipo real do arquivo, EXIF removido, WebP, tamanho limitado).
- Telefone validado e normalizado em E.164. Mensagem do `wa.me` montada no servidor.
- Permissões: grupo **Guia** (novo) cadastra e publica; Moderador resolve pedidos do titular; Financeiro e Comercial não veem o guia.
- Testes obrigatórios: publicar sem aceite falha; token reutilizado falha; token expirado falha; perfil pausado dá 404;
  categoria regulada não aceita frase; no máximo 3 categorias; CPF nunca aparece em claro no banco nem no HTML.

## 11. LGPD (resumo; detalhes em GUIA_LGPD_E_TERMO.md)

- Base legal: **consentimento** da pessoa responsável, registrado.
- Direito de alterar e remover a qualquer momento, pela ficha pública ou por e-mail. Meta interna: remover em até 2 dias úteis; prazo máximo: 15 dias.
- Minimização: sem CPF em claro, sem endereço residencial, sem dados que a ficha não usa.
- Atualizar `docs/LGPD.md`: novo tratamento, finalidade, base legal, retenção e quem acessa.

## 12. Etapas de implementação

Cada etapa termina com testes, TextoAjuda, docs, CHANGELOG, `docs/PROGRESSO.md` e commit feito por Daniel.

- **G1 — Base:** modelos, migrações, carga de categorias, admin do guia, cadastro assistido, termo, convite e aceite, publicação.
- **G2 — Público:** páginas de cidade, categoria e ficha, lista + mapa, busca, "aberto agora", SEO, sitemap, contagem de cliques.
- **G3 — LGPD e operação:** pedidos do titular, revogação, termo novo, lista de convites e "não contatar", fila e ações em lote, dados demo.
- **G4 — Opcional:** autocadastro com aprovação, selo de verificação, ajustes de uso.

## 13. Dados demo

- 3 cidades, 12 categorias, cerca de 60 perfis fictícios com e-mails `@demo.invalid` e telefones inexistentes, marcados com `MarcaDemo`.
- Misturar: empresa com CNPJ, autônomo, regulamentado, domicílio, endereço, sem horário e pausado.
- Apagados junto com o restante pelo `apagar_dados_demo`. `MOSTRAR_DEMO` segue proibido com `DEBUG=False`.

## 14. Decisões em aberto (valores padrão adotados)

| Tema | Padrão adotado | Quem decide |
|---|---|---|
| Nome da aba | "Guia de Negócios" (editável) | Daniel |
| Gratuito | 100% na V1 | Daniel |
| Profissionais liberais | Entram, com ficha restrita | Daniel |
| IP truncado no aceite | Guardar | Advogado |
| Prazo de guarda do aceite | 5 anos | Advogado |
| Texto do termo | Rascunho | Advogado |
