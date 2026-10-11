"""Fixtures dos testes de planos. Os 3 planos vêm da migration planos/0002 (como em produção)."""

import pytest

from planos.models import Periodicidade, Plano
from planos.services import criar_assinatura


@pytest.fixture
def plano(db):
    """Devolve o plano pelo slug (basico, profissional, premium)."""
    return lambda slug: Plano.objects.get(slug=slug)


@pytest.fixture
def assinante(criar_anunciante, plano):
    """Fábrica: anunciante ativo com assinatura ativa (padrão: Básico mensal)."""

    def _criar(
        email="loja@exemplo.com", nome="Loja Alfa", slug_plano="basico", periodicidade=Periodicidade.MENSAL
    ):
        anunciante = criar_anunciante(email, nome)
        criar_assinatura(anunciante, plano(slug_plano), periodicidade)
        return anunciante

    return _criar
