"""Formulários do admin de publicidade: campanha (posições e regra da loja assinante) e peça (imagens com
tamanho e peso da Configuracao, mostrados na ajuda de cada campo)."""

from django import forms
from django.core.exceptions import ValidationError

from core.services import configuracao
from publicidade import services
from publicidade.models import Banner, Campanha, Formato, Posicao, validar_link


class CampanhaForm(forms.ModelForm):
    """Posições em caixas de marcar; ativar campanha de loja sem assinatura é recusado."""

    posicoes = forms.MultipleChoiceField(
        label="Posições",
        choices=Posicao.choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="No máximo 3 espaços por página. Banner: home, busca e anúncio; card: rodapé da home; "
        "nativo (texto): topo dos resultados da busca.",
    )

    class Meta:
        model = Campanha
        fields = ["patrocinador", "nome", "posicoes", "cidades", "inicio", "fim", "valor", "situacao"]

    def clean(self) -> dict:
        """Regra 4 do PUBLICIDADE.md: loja do site só anuncia se tiver assinatura ativa."""
        dados = super().clean()
        if dados.get("patrocinador") and dados.get("situacao"):
            try:
                services.conferir_patrocinador(
                    Campanha(patrocinador=dados["patrocinador"], situacao=dados["situacao"])
                )
            except ValidationError as erro:
                self.add_error("situacao", erro)
        return dados


class BannerForm(forms.ModelForm):
    """Peça: imagens enviadas (validadas aqui, processadas no Celery), textos e link."""

    # Link digitado sem esquema vira https:// (o padrão do Django 6); só http/https (validar_link).
    link = forms.URLField(
        label="Link",
        max_length=500,
        assume_scheme="https",
        validators=[validar_link],
        help_text="Para onde o clique leva (site ou WhatsApp do patrocinador). Só https:// ou http://.",
    )
    envio_imagem = forms.FileField(
        label="Imagem (computador / logo do card)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    envio_imagem_celular = forms.FileField(
        label="Imagem do celular (só banner)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )

    class Meta:
        model = Banner
        fields = [
            "formato",
            "envio_imagem",
            "envio_imagem_celular",
            "texto_alternativo",
            "titulo",
            "texto",
            "link",
            "ativo",
        ]

    def __init__(self, *args, **kwargs):
        """Ajuda com os tamanhos e o peso atuais da Configuracao (editáveis no admin)."""
        super().__init__(*args, **kwargs)
        t = services.tamanhos()
        peso = configuracao().limite_banner_kb
        self.fields["envio_imagem"].help_text = (
            f"Banner: {t['banner']} px (computador). Card: logo quadrado {t['card']} px. "
            f"JPG, PNG ou WebP, até {peso} KB. Maior na mesma proporção é reduzido; sem EXIF."
        )
        self.fields[
            "envio_imagem_celular"
        ].help_text = f"Banner no celular: {t['banner_celular']} px. JPG, PNG ou WebP, até {peso} KB."
        self.fields["link"].widget.attrs["placeholder"] = "https://"

    def clean(self) -> dict:
        """Cada imagem no tamanho do seu formato; nativo sem imagem; texto alternativo quando há imagem."""
        dados = super().clean()
        formato = dados.get("formato")
        imagem, celular = dados.get("envio_imagem"), dados.get("envio_imagem_celular")
        tem_imagem = bool(imagem or (self.instance.pk and self.instance.imagem))
        if formato == Formato.NATIVO:
            if imagem or celular:
                self.add_error("formato", "O anúncio nativo é só texto: tire as imagens.")
            return dados
        for campo, arquivo, no_celular in (
            ("envio_imagem", imagem, False),
            ("envio_imagem_celular", celular, True),
        ):
            if not arquivo:
                continue
            if no_celular and formato != Formato.BANNER:
                self.add_error(campo, "Imagem do celular é só para o formato banner.")
                continue
            try:
                services.validar_imagem(arquivo, services.tamanho_da_imagem(formato, no_celular))
            except ValidationError as erro:
                self.add_error(campo, erro)
        if not tem_imagem:
            self.add_error("envio_imagem", "Envie a imagem.")
        if formato == Formato.BANNER and not (celular or (self.instance.pk and self.instance.imagem_celular)):
            self.add_error("envio_imagem_celular", "O banner precisa da imagem do celular.")
        if tem_imagem and not dados.get("texto_alternativo"):
            self.add_error("texto_alternativo", "Descreva a imagem (leitores de tela).")
        return dados

    def save(self, commit: bool = True) -> Banner:
        """Guarda os envios como originais (o Celery gera os WebP e apaga os originais)."""
        banner = super().save(commit=False)
        for campo, destino in (
            ("envio_imagem", "imagem_original"),
            ("envio_imagem_celular", "imagem_celular_original"),
        ):
            arquivo = self.cleaned_data.get(campo)
            if arquivo:
                getattr(banner, destino).save(arquivo.name, arquivo, save=False)
        if commit:
            banner.save()
        return banner


class PeriodoForm(forms.Form):
    """Período do painel de publicidade (padrão: últimos 30 dias)."""

    de = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ate = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
