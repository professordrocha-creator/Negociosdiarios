"""Middlewares do app core: IP real do visitante atrás do proxy e o "noindex" do servidor de teste.

IP real (docs/DEPLOY.md, docs/SEGURANCA.md): em produção o Django recebe as requisições do nginx interno
(nd_nginx), não do visitante. O nd_nginx já resolve o IP verdadeiro (módulo realip, só confiando nos proxies
da rede Docker) e o manda no cabeçalho X-Real-IP. Aqui o REMOTE_ADDR só é trocado por esse cabeçalho quando a
conexão veio de um proxy confiável (PROXIES_CONFIAVEIS); de qualquer outro lugar, o cabeçalho é ignorado.
Assim o visitante não forja o IP: o axes, o limite por IP, o hash das denúncias e o IP truncado do aceite do
guia continuam lendo só o REMOTE_ADDR, que passa a ser o certo.
"""

import ipaddress

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def _redes_confiaveis() -> list:
    """Redes (CIDR) dos proxies confiáveis (vazio = nenhum: em dev o REMOTE_ADDR já é o certo)."""
    return [
        ipaddress.ip_network(rede.strip(), strict=False)
        for rede in settings.PROXIES_CONFIAVEIS
        if rede.strip()
    ]


def ip_real(request: HttpRequest) -> str:
    """O IP do visitante: X-Real-IP só se a conexão veio de um proxy confiável e o valor for um IP válido."""
    remoto = request.META.get("REMOTE_ADDR", "")
    real = request.META.get("HTTP_X_REAL_IP", "").strip()
    if not real:
        return remoto
    try:
        origem = ipaddress.ip_address(remoto)
        ipaddress.ip_address(real)
    except ValueError:
        return remoto
    if any(origem in rede for rede in _redes_confiaveis()):
        return real
    return remoto


class IPRealMiddleware:
    """Troca o REMOTE_ADDR pelo IP real (ver a docstring do módulo). Tem de ser o primeiro da lista."""

    def __init__(self, get_response):
        """Padrão do Django."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Ajusta o IP antes de qualquer outro middleware (axes, limites) olhar para ele."""
        request.META["REMOTE_ADDR"] = ip_real(request)
        return self.get_response(request)


class NoindexMiddleware:
    """SITE_NOINDEX=True (servidor de teste): toda resposta sai com X-Robots-Tag "noindex, nofollow,
    noarchive", sobrescrevendo o que a página tiver. Desligado (lançamento), não faz nada."""

    CABECALHO = "noindex, nofollow, noarchive"

    def __init__(self, get_response):
        """Padrão do Django."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Marca a resposta quando a chave estiver ligada."""
        resposta = self.get_response(request)
        if settings.SITE_NOINDEX:
            resposta["X-Robots-Tag"] = self.CABECALHO
        return resposta
