"""Ponto de entrada ASGI (não usado na V1; mantido para uso futuro)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
