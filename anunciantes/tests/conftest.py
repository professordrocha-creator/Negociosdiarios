"""Fixtures dos testes de anunciantes: cidade liberada e fábrica de anunciantes."""

import pytest
from django.contrib.gis.geos import Point

from anunciantes.models import Anunciante
from contas.models import Usuario
from core.models import Cidade, Estado

SENHA = "Senha-Cliente-Forte-1"


@pytest.fixture
def tangara(db):
    """Tangará da Serra liberada (MT liberado)."""
    mt = Estado.objects.create(uf="MT", nome="Mato Grosso", liberado=True)
    return Cidade.objects.create(
        codigo_ibge=5107958,
        nome="Tangará da Serra",
        slug="tangara-da-serra",
        uf=mt,
        liberada=True,
        ponto=Point(-57, -14),
    )


@pytest.fixture
def criar_anunciante(tangara):
    """Fábrica: cria usuário + anunciante (revenda com CNPJ válido, ou corretor com CRECI)."""
    cnpjs = iter(["90000001000129", "90000002000173", "90000003000118", "90000004000162"])

    def _criar(
        email: str, nome: str, status: str = Anunciante.Status.ATIVO, corretor: bool = False, **campos
    ):
        usuario = Usuario.objects.create_user(email=email, password=SENHA, nome=nome)
        documento = ("creci", "CRECI/MT 12345-F") if corretor else ("cnpj", next(cnpjs))
        return Anunciante.objects.create(
            usuario=usuario,
            tipo=Anunciante.Tipo.CORRETOR_AUTONOMO if corretor else Anunciante.Tipo.REVENDA,
            nome_publico=nome,
            slug=nome.lower().replace(" ", "-"),
            documento_tipo=documento[0],
            documento_numero=documento[1],
            whatsapp="+5565999990001",
            cidade=tangara,
            status=status,
            **campos,
        )

    return _criar
