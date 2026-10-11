"""Testes do armazenamento de mídia por ARMAZENAMENTO=local|s3 (docs/adr/0002)."""

import environ
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from storages.backends.s3 import S3Storage

from config.settings import BASE_DIR, armazenamento_de_midia

R2 = {
    "S3_BUCKET": "midia",
    "S3_ENDPOINT_URL": "https://conta.r2.cloudflarestorage.com",
    "S3_ACCESS_KEY": "chave",
    "S3_SECRET_KEY": "segredo",
}


@pytest.fixture
def variaveis_r2(monkeypatch):
    """Variáveis de ambiente de um bucket R2 de mentira (nada é acessado na rede)."""
    for nome, valor in R2.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.delenv("S3_DOMINIO_PUBLICO", raising=False)
    return monkeypatch


def test_local_grava_na_pasta_media():
    """Em dev: arquivos na pasta media/ do projeto, servidos em /media/."""
    storages, media_url, media_root = armazenamento_de_midia("local", environ.Env(), BASE_DIR)

    assert storages["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    assert media_url == "/media/"
    assert media_root == BASE_DIR / "media"


def test_s3_com_dominio_publico_gera_urls_publicas(variaveis_r2):
    """Produção (R2) com domínio próprio: URLs públicas e cacheáveis, sem assinatura."""
    variaveis_r2.setenv("S3_DOMINIO_PUBLICO", "midia.negociosdiarios.com.br")

    storages, media_url, _ = armazenamento_de_midia("s3", environ.Env(), BASE_DIR)
    opcoes = storages["default"]["OPTIONS"]

    assert storages["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert opcoes["bucket_name"] == "midia"
    assert opcoes["endpoint_url"] == "https://conta.r2.cloudflarestorage.com"
    assert opcoes["region_name"] == "auto"
    assert opcoes["querystring_auth"] is False
    assert opcoes["file_overwrite"] is False
    assert media_url == "https://midia.negociosdiarios.com.br/"

    url = S3Storage(**opcoes).url("anuncios/foto.webp")  # monta a URL sem acessar a rede
    assert url == "https://midia.negociosdiarios.com.br/anuncios/foto.webp"


def test_s3_sem_dominio_publico_gera_urls_assinadas(variaveis_r2):
    """Sem domínio público, cada URL sai assinada e temporária."""
    storages, _, _ = armazenamento_de_midia("s3", environ.Env(), BASE_DIR)

    assert storages["default"]["OPTIONS"]["querystring_auth"] is True


def test_s3_sem_variavel_obrigatoria_nao_sobe(variaveis_r2):
    """Esquecer o bucket (ou a chave) derruba a subida, em vez de falhar no primeiro upload."""
    variaveis_r2.delenv("S3_BUCKET")

    with pytest.raises(ImproperlyConfigured):
        armazenamento_de_midia("s3", environ.Env(), BASE_DIR)


@pytest.mark.parametrize("valor", ["", "minio", "S3", "Local"])
def test_valor_invalido_nao_sobe(valor):
    """Erro de digitação em ARMAZENAMENTO não pode gravar fotos no lugar errado."""
    with pytest.raises(ImproperlyConfigured):
        armazenamento_de_midia(valor, environ.Env(), BASE_DIR)


def test_storage_local_grava_le_e_apaga(settings, tmp_path):
    """O storage padrão (local) funciona de ponta a ponta numa pasta temporária."""
    settings.MEDIA_ROOT = tmp_path

    nome = default_storage.save("teste/ola.txt", ContentFile(b"ola"))

    assert (tmp_path / nome).read_bytes() == b"ola"
    assert default_storage.url(nome) == f"/media/{nome}"
    default_storage.delete(nome)
    assert not (tmp_path / nome).exists()
