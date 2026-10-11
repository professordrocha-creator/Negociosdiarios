"""Views do app contas: login e logout do cliente (anunciante).

A equipe usa o login do admin (endereço secreto + código por e-mail); este aqui é só
para anunciantes ativos e pede apenas e-mail e senha (com o bloqueio do django-axes).
"""

from django.contrib.auth.views import LoginView, LogoutView

from contas.forms import EntrarForm
from core.services import textos_ajuda


class EntrarView(LoginView):
    """Tela /entrar/: e-mail e senha; quem já está logado vai direto ao painel."""

    template_name = "contas/entrar.html"
    form_class = EntrarForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs) -> dict:
        """Acrescenta a caixa "Sobre esta tela"."""
        contexto = super().get_context_data(**kwargs)
        contexto.update(tela="entrar", ajuda_itens=textos_ajuda("entrar"))
        return contexto


class SairView(LogoutView):
    """Sai da conta (só por POST, como exige o Django) e volta para a página inicial."""
