"""Admin do Django com login simples e verificação de navegador novo.

Login: só e-mail e senha (com o bloqueio do django-axes após 5 erros).
Em produção, com `ADMIN_CODIGO_EMAIL` ligado, um navegador que ainda não é
confiável cai numa segunda tela que pede o código de 6 dígitos enviado por
e-mail; acertando, o navegador fica confiável por 30 dias. Em dev nada disso
acontece. As regras ficam em `contas/services.py`; aqui só se orquestra.
Ligado como site padrão por `config.apps.AdminConfigND` (INSTALLED_APPS).
"""

from urllib.parse import urlencode

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from contas.forms import CodigoAcessoForm
from contas.services import (
    acesso_verificado,
    enviar_codigo_email,
    gravar_navegador_confiavel,
    marcar_acesso_verificado,
    mascarar_email,
    navegador_confiavel,
    verificar_codigo,
)

AVISOS_ENVIO = {
    "enviado": (messages.SUCCESS, "Enviamos um código de 6 dígitos para {email}."),
    "aguarde": (messages.WARNING, "Um código foi enviado há pouco. Aguarde 1 minuto para pedir outro."),
    "falhou": (
        messages.ERROR,
        "Não conseguimos enviar o e-mail agora. Tente reenviar em instantes ou use o código de emergência.",
    ),
}


def encaminhar_equipe(request: HttpRequest, destino: str | None = None) -> HttpResponseRedirect:
    """Depois da senha certa de alguém da equipe (no login do admin OU na tela /entrar/): mesma regra.

    Sessão já verificada ou navegador confiável → admin. Senão, manda o código por e-mail e leva à tela
    "Confirme que é você". O admin só abre com a sessão verificada (`AdminSiteND.has_permission`): não há
    atalho que pule o código, venha o login de onde vier.
    """
    destino = destino or reverse("admin:index")
    if acesso_verificado(request):
        return HttpResponseRedirect(destino)
    if navegador_confiavel(request, request.user):
        marcar_acesso_verificado(request)
        return HttpResponseRedirect(destino)
    nivel, texto = AVISOS_ENVIO[enviar_codigo_email(request.user)]
    messages.add_message(request, nivel, texto.format(email=mascarar_email(request.user.email)))
    return HttpResponseRedirect(f"{reverse('admin:verificar')}?{urlencode({'next': destino})}")


class AdminSiteND(admin.AdminSite):
    """Site do admin: equipe logada e, quando exigido, com o navegador verificado."""

    site_header = "Negócios Diários · administração"
    site_title = "Admin Negócios Diários"
    index_title = "Painel"

    def has_permission(self, request: HttpRequest) -> bool:
        """Além de ser da equipe, a sessão precisa ter passado pela verificação (se exigida)."""
        return super().has_permission(request) and acesso_verificado(request)

    def get_urls(self):
        """Acrescenta a tela de verificação (fora do `admin_view`, que exigiria já estar verificado)."""
        return [path("verificar/", self.verificar, name="verificar"), *super().get_urls()]

    def login(self, request: HttpRequest, extra_context: dict | None = None) -> HttpResponse:
        """Login com e-mail e senha; navegador novo segue para a tela do código."""
        if self._falta_verificar(request):
            # Já passou pela senha nesta sessão (ex.: voltou ao login): só falta o código.
            return self._ir_para_verificacao(request, enviar=False)

        resposta = super().login(request, extra_context)

        if request.method == "POST" and self._falta_verificar(request):
            if navegador_confiavel(request, request.user):
                marcar_acesso_verificado(request)
                return resposta
            return encaminhar_equipe(request, self._destino(request))
        return resposta

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def verificar(self, request: HttpRequest) -> HttpResponse:
        """Tela "Confirme que é você": pede o código por e-mail e marca o navegador como confiável."""
        if not self._equipe_logada(request):
            return redirect("admin:login")
        destino = self._destino(request)
        if acesso_verificado(request):
            return HttpResponseRedirect(destino)

        form = CodigoAcessoForm()
        if request.method == "POST" and "reenviar" in request.POST:
            self._avisar_envio(request, enviar_codigo_email(request.user))
            return HttpResponseRedirect(request.get_full_path())
        if request.method == "POST":
            form = CodigoAcessoForm(request.POST)
            if form.is_valid() and verificar_codigo(request.user, form.cleaned_data["codigo"]):
                marcar_acesso_verificado(request)
                resposta = HttpResponseRedirect(destino)
                gravar_navegador_confiavel(resposta, request.user)
                return resposta
            form.add_error(
                "codigo", "Código errado, vencido ou já usado. Confira o e-mail mais recente ou peça outro."
            )

        contexto = {
            **self.each_context(request),
            "title": "Confirme que é você",
            "form": form,
            "email_mascarado": mascarar_email(request.user.email),
            "next": destino,
        }
        return TemplateResponse(request, "admin/verificar_acesso.html", contexto)

    # --- apoio ---------------------------------------------------------------------------

    @staticmethod
    def _equipe_logada(request: HttpRequest) -> bool:
        """Usuário autenticado, ativo e da equipe (o que a senha sozinha garante)."""
        usuario = request.user
        return usuario.is_authenticated and usuario.is_active and usuario.is_staff

    def _falta_verificar(self, request: HttpRequest) -> bool:
        """Passou pela senha mas a sessão ainda não foi verificada."""
        return self._equipe_logada(request) and not acesso_verificado(request)

    @staticmethod
    def _destino(request: HttpRequest) -> str:
        """Para onde ir depois de verificar: o `next` pedido, se for deste site; senão, o painel."""
        destino = request.POST.get("next") or request.GET.get("next") or ""
        if url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
            return destino
        return reverse("admin:index")

    def _ir_para_verificacao(self, request: HttpRequest, enviar: bool) -> HttpResponse:
        """Redireciona para a tela do código (enviando um código novo, se pedido)."""
        if enviar:
            self._avisar_envio(request, enviar_codigo_email(request.user))
        consulta = urlencode({"next": self._destino(request)})
        return HttpResponseRedirect(f"{reverse('admin:verificar')}?{consulta}")

    @staticmethod
    def _avisar_envio(request: HttpRequest, resultado: str) -> None:
        """Mostra na tela o resultado do envio do código."""
        nivel, texto = AVISOS_ENVIO[resultado]
        messages.add_message(request, nivel, texto.format(email=mascarar_email(request.user.email)))
