"""Rotas do app contas (login, logout e recuperação de senha do cliente)."""

from django.urls import path

from contas import views

app_name = "contas"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("sair/", views.SairView.as_view(), name="sair"),
    path("entrar/esqueci/", views.EsqueciSenhaView.as_view(), name="esqueci"),
    path("entrar/esqueci/enviado/", views.EsqueciSenhaEnviadoView.as_view(), name="esqueci_enviado"),
    path("entrar/redefinir/<uidb64>/<token>/", views.RedefinirSenhaView.as_view(), name="redefinir"),
    path(
        "entrar/redefinir/concluido/", views.RedefinirSenhaConcluidoView.as_view(), name="redefinir_concluido"
    ),
]
