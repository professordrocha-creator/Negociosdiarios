"""Regras do app contas."""


def normalizar_email(email: str) -> str:
    """Devolve o e-mail sem espaços nas pontas e todo em minúsculas.

    O e-mail é o login: guardar sempre normalizado evita duas contas para a
    mesma pessoa ("Joao@x.com" e "joao@x.com") e faz o login não depender de
    maiúsculas. A parte local é tratada sem distinção de caixa, como fazem
    na prática todos os provedores de e-mail.
    """
    return email.strip().lower()
