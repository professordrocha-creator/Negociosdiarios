# App `guia` — Guia de Negócios

**Responsabilidade:** diretório gratuito de serviços, profissionais e comércios (docs/GUIA.md). Isolado dos
classificados: não usa `Anunciante` (a empresa listada não tem login). Nada vai ao ar sem a autorização
registrada do responsável (docs/GUIA_LGPD_E_TERMO.md).

Etapas feitas: **G1 (base)** e **G2 (páginas públicas)**. Os pedidos do titular pela ficha, o termo novo e a
lista de convites chegam na G3.

## Modelos
- `GrupoCategoria`, `CategoriaServico`: carga pelo `carregar_categorias_guia` (CSV em `docs/guia/`, upsert por
  slug). Com perfis, a categoria só é desativada (nunca apagada). `regulamentada`: ficha restrita, sem frase.
- `PerfilGuia` (MarcaDemo + histórico): empresa, autônomo ou regulamentado. Máximo de categorias da
  configuração (3), validado no formulário e no sinal do muitos-para-muitos (`signals.py`). CPF **nunca** em
  claro: só `cpf_hash` (HMAC com `GUIA_CPF_CHAVE`) e `cpf_final`. Só o `ponto_publico` sai do servidor (a
  domicílio = centro da cidade).
- `TermoGuia` (histórico): versão; em vigor = texto travado; `rascunho_juridico` avisa no admin.
- `ConviteAceite`: token de 32 bytes, uso único, validade (15 dias), canal.
- `AceitePublicacao` (histórico): nome digitado, data e hora, versão, IP truncado, navegador resumido; foto do
  termo em papel no storage **privado**; revogação.
- `EstatisticaGuiaDia` (visualizações e cliques por dia, sem IP), `PedidoDoPerfil` (MarcaDemo; formulário público na G3),
  `ConfiguracaoGuia` (registro único).

## Serviços (`services.py`)
- `pendencias` / `publicar` / `pausar`: publicar só com aceite vigente, categoria, cidade liberada, contato E.164
  e local ou área. `PublicacaoRecusada` lista o que falta.
- `gerar_convite`, `mensagem_convite`, `url_whatsapp`, `convite_valido`, `aceitar_convite` (trava o convite e
  publica), `registrar_aceite_presencial`, `revogar_aceite` (despublica na hora).
- `resumo_cpf`, `duplicidades` (CNPJ, CPF, WhatsApp: alerta, não bloqueia), `previa`, `blocos_do_termo`.
- Público (G2): `pode_ver` (guia no ar ou prévia da equipe), `perfis_visiveis`, `grupos_da_cidade`, `rodizio`,
  `aberto_agora` (fuso do estado, `FUSO_POR_UF`), `filtrar_lista`, `indexavel`, `pontos_do_mapa`, `buscar_no_guia`
  (`unaccent` + `pg_trgm`), `registrar_evento`, `contato_liberado`, `link_whatsapp_perfil`, `schema_da_ficha`,
  `paginas_do_sitemap`.
- `carregar_categorias`, `criar_guia_demo` / `apagar_guia_demo` (chamados por `criar_dados_demo` /
  `apagar_dados_demo`).

## Telas
- Admin (grupo **Guia**): cadastro assistido em uma coluna com mapa, painel de publicação, "Enviar por WhatsApp",
  "Aceite em papel", revogar. Moderador vê os pedidos; Financeiro e Comercial não veem o guia.
- Público: `/guia/aceite/<token>/` (noindex, no-referrer, CSRF, campo-armadilha, limite por hora); `/guia/`,
  `/guia/<uf>/<cidade>/`, `/guia/<uf>/<cidade>/<categoria>/`, `/guia/empresa/<slug>/` e os contatos
  `/guia/contato/<id>/whatsapp|telefone/`. Menu, cartão da home e rodapé por `guia.context_processors.guia`.
