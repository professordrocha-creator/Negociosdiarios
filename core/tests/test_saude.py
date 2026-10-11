"""Testes da rota /saude/."""

from unittest import mock

import pytest
from django.db import OperationalError
from django.urls import reverse


@pytest.mark.django_db
def test_saude_ok_quando_banco_responde(client):
    """Com o banco de pé, /saude/ devolve 200 e não pode ser guardada em cache."""
    resposta = client.get(reverse("core:saude"))

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
    assert "no-cache" in resposta["Cache-Control"]


@pytest.mark.django_db
def test_saude_503_quando_banco_falha(client):
    """Se o banco cair, /saude/ devolve 503 (para o monitor alertar) sem detalhes do erro."""
    with mock.patch("core.services.connection") as conexao:
        conexao.cursor.side_effect = OperationalError("host=db senha=x")
        resposta = client.get(reverse("core:saude"))

    assert resposta.status_code == 503
    assert "senha" not in resposta.content.decode()


def test_saude_so_aceita_get(client):
    """POST em /saude/ é recusado com 405."""
    resposta = client.post(reverse("core:saude"))

    assert resposta.status_code == 405
