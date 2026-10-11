"""Formulários do app core (admin da identidade do site)."""

from django import forms
from django.core.files.uploadedfile import UploadedFile

from core import imagens
from core.models import Configuracao


class ConfiguracaoForm(forms.ModelForm):
    """Identidade do site no admin: valida imagens (tipo real e tamanho) e normaliza contatos.

    Os limites de tamanho vêm da própria Configuracao (editáveis, regra do CLAUDE.md).
    """

    class Meta:
        model = Configuracao
        fields = [
            "nome",
            "linha_regiao",
            "slogan",
            "empresa",
            "cidade_sede",
            "simbolo_claro",
            "simbolo_escuro",
            "imagem_compartilhamento",
            "whatsapp",
            "email_contato",
            "email_privacidade",
            "endereco",
            "cnpj",
            "instagram",
            "sobre_quem_somos",
            "sobre_missao",
            "sobre_visao",
            "limite_simbolo_kb",
            "limite_compartilhamento_kb",
            "limite_logo_kb",
            "logo_min_px",
            "limite_capa_kb",
            "capa_min_largura_px",
            "capa_min_altura_px",
        ]

    def _limite(self, campo_limite: str) -> int:
        """Limite em KB: o digitado neste envio ou o salvo."""
        valor = self.data.get(campo_limite) or getattr(self.instance, campo_limite)
        try:
            return int(valor)
        except (TypeError, ValueError):
            return getattr(self.instance, campo_limite)

    def _imagem_nova(self, campo: str, validador, campo_limite: str):
        """Valida só arquivos recém-enviados (os já salvos passaram na validação antes)."""
        arquivo = self.cleaned_data.get(campo)
        if isinstance(arquivo, UploadedFile):
            validador(arquivo, self._limite(campo_limite))
        return arquivo

    def clean_simbolo_claro(self):
        """SVG seguro ou PNG, dentro do limite."""
        return self._imagem_nova("simbolo_claro", imagens.validar_simbolo, "limite_simbolo_kb")

    def clean_simbolo_escuro(self):
        """SVG seguro ou PNG, dentro do limite."""
        return self._imagem_nova("simbolo_escuro", imagens.validar_simbolo, "limite_simbolo_kb")

    def clean_imagem_compartilhamento(self):
        """PNG ou JPG, dentro do limite."""
        return self._imagem_nova(
            "imagem_compartilhamento", imagens.validar_compartilhamento, "limite_compartilhamento_kb"
        )

    def clean_whatsapp(self) -> str:
        """WhatsApp em E.164 (vazio continua vazio = "em breve")."""
        from anunciantes.validators import normalizar_whatsapp

        valor = self.cleaned_data.get("whatsapp", "").strip()
        return normalizar_whatsapp(valor) if valor else ""

    def clean_cnpj(self) -> str:
        """CNPJ só com dígitos e dígitos verificadores certos (vazio = "a informar")."""
        from anunciantes.validators import normalizar_cnpj

        valor = self.cleaned_data.get("cnpj", "").strip()
        return normalizar_cnpj(valor) if valor else ""

    def clean_instagram(self) -> str:
        """Só o usuário: tira @ e o endereço do Instagram, se vierem junto."""
        valor = self.cleaned_data.get("instagram", "").strip()
        for prefixo in ("https://www.instagram.com/", "https://instagram.com/", "instagram.com/", "@"):
            if valor.lower().startswith(prefixo):
                valor = valor[len(prefixo) :]
        return valor.strip("/")
