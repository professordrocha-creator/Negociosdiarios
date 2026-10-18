"""Views do app contas: login, logout e "esqueci minha senha" do cliente (anunciante).

A equipe usa o login do admin (endereço secreto + código por e-mail); estas telas são
só para clientes e pedem apenas e-mail e senha (com o bloqueio do django-axes).
"""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from contas.forms import EntrarForm, EsqueciSenhaForm, NovaSenhaForm
from core.services import configuracao, limite_por_ip_excedido, textos_ajuda


class EntrarView(auth_views.LoginView):
    """Tela /entrar/: e-mail e senha; quem já está logado vai direto ao painel."""

    template_name = "contas/entrar.html"
    form_class = EntrarForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs) -> dict:
        """Acrescenta a caixa "Sobre esta tela"."""
        contexto = super().get_context_data(**kwargs)
        contexto.update(tela="entrar", ajuda_itens=textos_ajuda("entrar"))
        return contexto

    def form_valid(self, form) -> HttpResponse:
        """Entrou: equipe vai ao admin (com a verificação); cliente com versão nova dos Termos/Política sem
        aceite passa antes pelo aceite (Sprint 7B)."""
        resposta = super().form_valid(form)
        if form.get_user().is_staff:  # equipe: mesmo caminho do login do admin (código em navegador novo)
            from config.admin_site import encaminhar_equipe

            return encaminhar_equipe(self.request)
        from privacidade.services import pendencias_de_aceite

        if pendencias_de_aceite(form.get_user()):
            proximo = urlencode({"next": self.get_success_url()})
            return redirect(reverse("privacidade:aceitar") + "?" + proximo)
        return resposta


class SairView(auth_views.LogoutView):
    """Sai da conta (só por POST, como exige o Django) e volta para a página inicial."""


class EsqueciSenhaView(auth_views.PasswordResetView):
    """Pede o link de nova senha (vale PASSWORD_RESET_TIMEOUT e uma vez só). Limite por IP."""

    template_name = "contas/esqueci.html"
    form_class = EsqueciSenhaForm
    email_template_name = "emails/redefinir_senha.txt"
    subject_template_name = "emails/redefinir_senha_assunto.txt"
    success_url = reverse_lazy("contas:esqueci_enviado")
    extra_context = {"tela": "esqueci"}

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Conta o pedido no limite por IP antes de mandar e-mail."""
        if limite_por_ip_excedido(request, "pedido_email", settings.LIMITE_PEDIDOS_EMAIL_POR_HORA):
            return render(request, "anunciantes/muitas_tentativas.html", {"tela": "esqueci"}, status=429)
        return super().post(request, *args, **kwargs)

    def get_extra_email_context(self) -> dict:
        """Validade do link em horas, para o texto do e-mail."""
        return {"horas": settings.PASSWORD_RESET_TIMEOUT // 3600, "site_nome": configuracao().nome}


class EsqueciSenhaEnviadoView(auth_views.PasswordResetDoneView):
    """Confirmação genérica (não revela se o e-mail tem conta)."""

    template_name = "contas/esqueci_enviado.html"
    extra_context = {"tela": "esqueci"}


class RedefinirSenhaView(auth_views.PasswordResetConfirmView):
    """Link do e-mail: escolhe a nova senha. Trocar a senha encerra as outras sessões."""

    template_name = "contas/redefinir.html"
    form_class = NovaSenhaForm
    success_url = reverse_lazy("contas:redefinir_concluido")
    extra_context = {"tela": "redefinir"}


class RedefinirSenhaConcluidoView(auth_views.PasswordResetCompleteView):
    """Senha trocada: leva ao /entrar/."""

    template_name = "contas/redefinir_concluido.html"
    extra_context = {"tela": "redefinir"}
