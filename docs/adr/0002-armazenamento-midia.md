# ADR 0002 — Armazenamento de mídia: pasta local em dev, Cloudflare R2 em produção
**Status:** aceito (2026-10-11, Sprint 0 etapa 6)

**Contexto:** a arquitetura previa MinIO em dev para imitar o S3. A imagem
`minio/minio` deixou de ser publicada no Docker Hub, e manter um "S3 de mentira"
no PC custa memória e configuração sem ganho real para 1 desenvolvedor. Em
produção as fotos precisam ficar fora da VPS (disco pequeno, backup, CDN).

**Decisão:**
- Variável `ARMAZENAMENTO=local|s3` escolhe o storage (`config/settings.py`,
  função `armazenamento_de_midia`); qualquer outro valor impede o Django de subir.
- `local` (dev): `FileSystemStorage` na pasta `media/` (fora do Git), servida
  pelo Django em `/media/` só nesse modo.
- `s3` (produção): `django-storages` (`S3Storage`) apontando para o **Cloudflare R2**
  (sem custo de saída de dados), região `auto`, sem ACL, `file_overwrite=False`.
  Com `S3_DOMINIO_PUBLICO` (ex.: `midia.negociosdiarios.com.br`) as URLs são públicas
  e cacheáveis por 1 ano; sem ele, saem assinadas e temporárias.
- MinIO removido do `docker-compose.yml`.

**Consequências:**
- Dev mais leve e sem dependência de imagem externa.
- O código sempre usa `default_storage`/`FileField`, nunca caminho de disco: trocar
  de R2 para S3, Spaces ou B2 é só mudar variáveis.
- O caminho S3 não é exercitado em dev; os testes montam e conferem a configuração
  (`core/tests/test_armazenamento.py`) e a etapa 8 testa o upload real no R2.
- Fotos sempre reprocessadas e sem EXIF antes de gravar (Sprint 3), em qualquer storage.
