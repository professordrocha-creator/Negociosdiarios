"""Modelos do app contas."""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from contas.services import normalizar_email


class UsuarioManager(BaseUserManager):
    """Cria usuários e superusuários identificados pelo e-mail (sem username)."""

    use_in_migrations = True

    def _criar(self, email: str, password: str | None, **campos) -> "Usuario":
        """Cria e salva o usuário com e-mail normalizado e senha em hash."""
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=normalizar_email(email), **campos)
        usuario.set_password(password)  # senha None vira senha inutilizável (sem login por senha)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email: str, password: str | None = None, **campos) -> "Usuario":
        """Cria um usuário comum: ativo, sem acesso ao admin."""
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._criar(email, password, **campos)

    def create_superuser(self, email: str, password: str | None = None, **campos) -> "Usuario":
        """Cria um superusuário (uso exclusivo do administrador geral; ver docs/ADMINISTRACAO.md)."""
        campos.setdefault("is_staff", True)
        campos.setdefault("is_superuser", True)
        if campos["is_staff"] is not True or campos["is_superuser"] is not True:
            raise ValueError("Superusuário precisa de is_staff=True e is_superuser=True.")
        return self._criar(email, password, **campos)

    def get_by_natural_key(self, email: str) -> "Usuario":
        """Busca pelo e-mail normalizado: o login funciona com qualquer combinação de maiúsculas."""
        return self.get(email=normalizar_email(email))


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Conta de acesso ao sistema (anunciante ou equipe), com login por e-mail.

    Visitantes não têm conta (docs/LGPD.md §2). Os campos `is_active`,
    `is_staff` e `is_superuser` mantêm os nomes do Django porque o admin e o
    sistema de permissões dependem deles.
    """

    email = models.EmailField(
        "e-mail",
        unique=True,
        help_text="Usado para entrar no sistema. Guardado em minúsculas.",
        error_messages={"unique": "Já existe uma conta com este e-mail."},
    )
    nome = models.CharField("nome", max_length=150, help_text="Nome completo, até 150 caracteres.")
    is_active = models.BooleanField(
        "ativo",
        default=True,
        help_text="Desmarque para bloquear o acesso sem apagar a conta (nada é apagado de verdade).",
    )
    is_staff = models.BooleanField(
        "equipe",
        default=False,
        help_text="Permite entrar no painel do administrador. O que pode fazer lá depende dos grupos.",
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)

    objects = UsuarioManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]  # pedido pelo `createsuperuser` além do e-mail e da senha

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["email"]

    def __str__(self) -> str:
        """Identifica o usuário pelo e-mail (é o que aparece no admin e nos logs de auditoria)."""
        return self.email

    def clean(self) -> None:
        """Normaliza o e-mail antes da validação de unicidade dos formulários."""
        super().clean()
        self.email = normalizar_email(self.email)

    def save(self, *args, **kwargs) -> None:
        """Garante e-mail normalizado mesmo quando o objeto é salvo sem passar por formulário."""
        self.email = normalizar_email(self.email)
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        """Nome completo (usado pelo Django em e-mails e no admin)."""
        return self.nome

    def get_short_name(self) -> str:
        """Primeiro nome, para saudações ("Olá, Maria")."""
        return self.nome.split(" ")[0] if self.nome else ""
