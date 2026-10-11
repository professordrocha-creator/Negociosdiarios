#!/usr/bin/env python
"""Utilitário de linha de comando do Django (migrate, runserver, comandos próprios)."""

import os
import sys


def main() -> None:
    """Aponta para as configurações do projeto e executa o comando pedido."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
