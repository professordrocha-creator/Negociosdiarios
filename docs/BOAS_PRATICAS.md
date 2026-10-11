# Boas práticas — evitar dor de cabeça depois

Checklist de decisões que são baratas agora e caras de corrigir depois.

## 1. Dados
- [ ] **Cidades** da tabela do IBGE (código + nome + UF), carregadas por comando. Nunca texto livre.
- [ ] **Bairros** cadastrados pelo admin, ligados à cidade. Anunciante sugere bairro novo → admin aprova.
- [ ] **Veículos** pelo catálogo FIPE (marca → modelo → versão), atualizado por tarefa mensal.
- [ ] **Dinheiro** em `DecimalField(max_digits=12, decimal_places=2)`. Nunca `float`.
- [ ] **Fuso:** `TIME_ZONE = "America/Cuiaba"`, `USE_TZ = True` (MT = UTC−4, uma hora a menos que Brasília).
- [ ] **Telefones** salvos em E.164 (`+5565999990000`), exibidos formatados (`django-phonenumber-field`).
- [ ] **Planos, preços, limites, prazos de expiração e carência** no banco, editáveis no admin.
- [ ] **CPF/CNPJ** salvos só com dígitos, validados pelos dígitos verificadores.

## 2. Histórico e exclusão
- [ ] `django-simple-history` em Anunciante, Anuncio, Assinatura, Fatura, Contrato de publicidade.
- [ ] Exclusão lógica (`status=removido`, `removido_em`); limpeza física de fotos por tarefa após 90 dias.
- [ ] Toda ação do admin (aprovar, suspender, estornar) registrada com autor, data e motivo.

## 3. URLs e SEO (definitivas desde o lançamento)
- `/imoveis/<uf>/<cidade>/`, `/veiculos/<uf>/<cidade>/` (UF desde já: ver ARQUITETURA §9), `/anuncio/<codigo>-<slug>/`, `/loja/<slug>/`
- [ ] Anúncio vendido/expirado: página "não está mais disponível" + similares (status 410 ou 200 com `noindex`), nunca 404 seco.
- [ ] Slug antigo de loja guardado em `SlugAntigo` → redireciona 301 para o novo.
- [ ] `sitemap.xml`, `robots.txt`, `<link rel="canonical">`.

## 4. Rotina de desenvolvimento
- [ ] Git + GitHub privado desde o 1º arquivo; commits pequenos em português ("anuncios: limite por plano").
- [ ] CI no GitHub Actions (`.github/workflows/ci.yml`): ruff + pytest em todo push.
- [ ] Dependências com versão fixa (`requirements.txt` gerado por `pip-tools` ou `uv`).
- [ ] **Migration aplicada nunca é editada.** Mudou o banco → nova migration.
- [ ] Backup antes de todo deploy (o script de deploy faz isso sozinho).
- [ ] Comando `python manage.py popular_exemplos` cria lojas/anúncios fictícios para teste e demonstração.
- [ ] `django-debug-toolbar` em dev para achar consultas lentas (N+1: usar `select_related`/`prefetch_related`).

## 5. Contas e infraestrutura
- [ ] Domínio `.com.br` no Registro.br com **renovação automática** e e-mail de contato que você lê.
- [ ] **2FA** em: Registro.br, GitHub, VPS, Mercado Pago, e-mail, Cloudflare.
- [ ] Senhas e chaves num gerenciador (Bitwarden). Códigos de recuperação do 2FA guardados fora do celular.
- [ ] E-mail transacional por provedor (Brevo, Amazon SES, Resend) com **SPF, DKIM e DMARC** no domínio.
- [ ] Busca da marca "Negócios Diários" no INPI antes de investir em divulgação.
- [ ] Alerta de disco: fotos crescem rápido; avisar com 70% de uso.

## 6. Gestão
- [ ] **Escopo da V1 congelado.** Ideia nova → `docs/IDEIAS_V2.md`, não no código.
- [ ] `CHANGELOG.md` atualizado a cada versão publicada.
- [ ] `docs/RUNBOOK.md` revisado sempre que um procedimento mudar.
