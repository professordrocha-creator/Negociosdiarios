"""Fixtures compartilhadas por todos os testes."""

import pytest

from contas.services import SESSAO_ACESSO_VERIFICADO


@pytest.fixture
def entrar_no_admin(client):
    """Devolve uma função que loga o usuário no client **já com o navegador verificado**.

    Assim os testes de telas do admin funcionam com ou sem o código por e-mail
    ligado. Para testar o login em si, ver contas/tests/test_acesso_admin.py.
    """

    def _entrar(usuario):
        client.force_login(usuario)
        sessao = client.session
        sessao[SESSAO_ACESSO_VERIFICADO] = usuario.pk
        sessao.save()
        return client

    return _entrar
