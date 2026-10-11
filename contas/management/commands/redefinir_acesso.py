"""Comando `redefinir_acesso`: emergência para quem ficou sem conseguir entrar no admin."""

from django.core.management.base import BaseCommand, CommandError

from contas.models import Usuario
from contas.services import normalizar_email, redefinir_acesso


class Command(BaseCommand):
    """Desbloqueia o login (axes) e gera um código de emergência de uso único."""

    help = (
        "EMERGÊNCIA (ver docs/RUNBOOK.md): desbloqueia o login do usuário e mostra um código de "
        "emergência de uso único, que serve na tela 'Confirme que é você' no lugar do código por "
        "e-mail. Para trocar a senha, use changepassword."
    )

    def add_arguments(self, parser):
        """E-mail do usuário."""
        parser.add_argument("email", help="E-mail (login) do usuário.")

    def handle(self, *args, **opcoes):
        """Redefine o acesso e imprime o código (uma vez; não vai para log)."""
        try:
            usuario = Usuario.objects.get(email=normalizar_email(opcoes["email"]))
        except Usuario.DoesNotExist as erro:
            raise CommandError("Nenhum usuário com este e-mail.") from erro
        if not usuario.is_staff:
            raise CommandError("Usuário fora da equipe (is_staff desligado): não usa o admin.")

        codigo = redefinir_acesso(usuario)

        self.stdout.write(self.style.SUCCESS("Login desbloqueado."))
        self.stdout.write(f"Código de emergência (uso único): {codigo}")
        self.stdout.write(
            "Se o admin pedir código, digite este no lugar do código do e-mail. Gerar outro invalida este."
        )
