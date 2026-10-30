"""Formulários do admin de publicidade: campanha (posições e regra da loja assinante) e peça (imagens com
tamanho e peso da Configuracao, mostrados na ajuda de cada campo)."""

from django import forms
from django.core.exceptions import ValidationError

from core.services import configuracao
from publicidade import services
from publicidade.models import Banner, Campanha, Formato, Posicao, validar_link

FAIXA, TEXTO, CARTAO = "faixa", "texto", "cartao"
# Escolhas simples do dono → posições internas (os valores gravados não mudam).
POSICOES_DA_ESCOLHA = {
    FAIXA: [Posicao.HOME_TOPO, Posicao.BUSCA_TOPO, Posicao.ANUNCIO_TOPO],
    TEXTO: [Posicao.BUSCA_NATIVO],
    CARTAO: [Posicao.RODAPE_CARD],
}


class CampanhaForm(forms.ModelForm):
    """Onde aparece em 3 escolhas simples (as páginas da faixa ficam em "Avançado"); ativar campanha de loja
    sem assinatura é recusado."""

    onde = forms.MultipleChoiceField(
        label="Onde aparece",
        choices=[
            (FAIXA, "Faixa de imagem (home, busca e anúncio)"),
            (TEXTO, "Texto na busca"),
            (CARTAO, "Cartão no rodapé da home"),
        ],
        widget=forms.CheckboxSelectMultiple,
        initial=[FAIXA],
        help_text="Com mais de uma campanha no mesmo espaço, as peças se revezam.",
    )
    paginas_da_faixa = forms.MultipleChoiceField(
        label="Páginas da faixa de imagem",
        choices=[(p.value, p.label) for p in POSICOES_DA_ESCOLHA[FAIXA]],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Opcional. Vazio = as três páginas. Marque só algumas para limitar a faixa a elas.",
    )

    class Meta:
        model = Campanha
        fields = ["patrocinador", "nome", "cidades", "inicio", "fim", "valor", "situacao"]

    def __init__(self, *args, **kwargs):
        """Campanha existente: as escolhas simples vêm das posições gravadas."""
        super().__init__(*args, **kwargs)
        self.fields["valor"].required = False
        posicoes = set(self.instance.posicoes or []) if self.instance.pk else set()
        if not posicoes:
            return
        faixa = [p for p in POSICOES_DA_ESCOLHA[FAIXA] if p in posicoes]
        self.initial["onde"] = [e for e, lista in POSICOES_DA_ESCOLHA.items() if posicoes & set(lista)]
        if faixa and len(faixa) < len(POSICOES_DA_ESCOLHA[FAIXA]):
            self.initial["paginas_da_faixa"] = faixa

    def clean_valor(self):
        """Vazio = R$ 0 (útil para teste)."""
        return self.cleaned_data.get("valor") or 0

    def clean(self) -> dict:
        """Escolhas → posições; regra 4 do PUBLICIDADE.md (loja do site só anuncia se for assinante)."""
        dados = super().clean()
        onde = dados.get("onde") or []
        posicoes = []
        for escolha, lista in POSICOES_DA_ESCOLHA.items():
            if escolha not in onde:
                continue
            if escolha == FAIXA and dados.get("paginas_da_faixa"):
                lista = [p for p in lista if p in dados["paginas_da_faixa"]]
            posicoes += [str(p) for p in lista]
        if posicoes:
            self.instance.posicoes = posicoes  # o campo do modelo não está no formulário
        else:
            if "onde" in dados:
                self.add_error("onde", "Marque onde a campanha aparece.")
            # Formulário já inválido; sem isto o clean() do modelo acusaria um campo que a tela não tem.
            self.instance.posicoes = self.instance.posicoes or [Posicao.HOME_TOPO.value]

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
        label="Imagem (banner ou logo do card)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    envio_imagem_celular = forms.FileField(
        label="Imagem própria para celular (opcional)",
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
            f"Banner: uma imagem de {t['banner']} px (ou maior, na mesma proporção); a do celular "
            f"({t['banner_celular']} px) é gerada dela com corte no centro. "
            f"Card: logo quadrado {t['card']} px. "
            f"JPG, PNG ou WebP, até {peso} KB. Sem EXIF."
        )
        self.fields["envio_imagem_celular"].help_text = (
            f"Só banner. Envie se o corte automático não ficar bom: {t['banner_celular']} px, JPG, PNG ou "
            f"WebP, até {peso} KB."
        )
        self.fields["link"].widget.attrs["placeholder"] = "https://"

    def clean(self) -> dict:
        """Cada imagem no tamanho do seu formato; diz o que falta preencher em cada formato."""
        dados = super().clean()
        formato = dados.get("formato")
        imagem, celular = dados.get("envio_imagem"), dados.get("envio_imagem_celular")
        if formato == Formato.NATIVO:
            if imagem or celular:
                self.add_error("formato", "O texto na busca (nativo) não tem imagem: tire as imagens.")
            return dados  # título e texto obrigatórios: Banner.clean()
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
        tem_imagem = bool(imagem or (self.instance.pk and self.instance.imagem))
        if self.instance.pk and "formato" in self.changed_data and not imagem:
            self.add_error("envio_imagem", "O formato mudou: envie a imagem no tamanho do novo formato.")
        elif not tem_imagem:
            o_que = "do banner" if formato == Formato.BANNER else "(logo) do cartão"
            self.add_error("envio_imagem", f"Envie a imagem {o_que}.")
        if tem_imagem and not dados.get("texto_alternativo"):
            self.add_error(
                "texto_alternativo", "Descreva a imagem em poucas palavras (para leitores de tela)."
            )
        return dados

    def save(self, commit: bool = True) -> Banner:
        """Guarda os envios como originais (o Celery gera os WebP e apaga os originais). Banner com imagem
        própria para celular passa a mantê-la; sem ela, a do celular sai da imagem principal."""
        banner = super().save(commit=False)
        for campo, destino in (
            ("envio_imagem", "imagem_original"),
            ("envio_imagem_celular", "imagem_celular_original"),
        ):
            arquivo = self.cleaned_data.get(campo)
            if arquivo:
                getattr(banner, destino).save(arquivo.name, arquivo, save=False)
        if self.cleaned_data.get("envio_imagem_celular"):
            banner.celular_propria = True
        if commit:
            banner.save()
        return banner


class PeriodoForm(forms.Form):
    """Período do painel de publicidade (padrão: últimos 30 dias)."""

    de = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ate = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
