"""Healthcheck do container web em produção (docker-compose.prod.yml): chama /saude/ como se viesse do nginx.

Usa o primeiro domínio de DJANGO_ALLOWED_HOSTS no cabeçalho Host (senão o Django recusa "localhost") e
X-Forwarded-Proto https (senão o SECURE_SSL_REDIRECT responderia com redirecionamento).
Sai com 0 se o site e o banco estão de pé (200), com 1 em qualquer outro caso.
"""

import os
import sys
import urllib.request

host = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")[0].strip()
pedido = urllib.request.Request(
    "http://127.0.0.1:8000/saude/", headers={"Host": host, "X-Forwarded-Proto": "https"}
)
try:
    with urllib.request.urlopen(pedido, timeout=5) as resposta:  # noqa: S310 (endereço fixo, local)
        sys.exit(0 if resposta.status == 200 else 1)
except Exception:  # qualquer erro = não saudável
    sys.exit(1)
