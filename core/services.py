"""Regras e verificações do app core."""

import logging

from django.db import DatabaseError, connection

logger = logging.getLogger(__name__)


def banco_disponivel() -> bool:
    """Testa a conexão com o banco executando um `SELECT 1`.

    Retorna False (sem lançar exceção) se o banco não responder, e registra
    no log só o tipo do erro, sem a mensagem, que pode conter host e usuário.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as erro:
        logger.error("Banco indisponível na verificação de saúde: %s", type(erro).__name__)
        return False
    return True
