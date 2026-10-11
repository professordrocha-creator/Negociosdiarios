"""Formulários do app anunciantes."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from anunciantes.models import Anunciante
from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from contas.services import normalizar_email
from core.models import Cidade


class MotivoStatusForm(forms.Form):
    """Motivo da aprovação/suspensão no admin (fica no cadastro e no histórico)."""

    motivo = forms.CharField(
        label="Motivo",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
        help_text="Até 500 caracteres. Fica registrado no cadastro e no histórico do anunciante.",
    )

    def __init__(self, *args, obrigatorio: bool = True, **kwargs):
        """Na suspensão o motivo é obrigatório; na aprovação, opcional ("Documento conferido.")."""
        super().__init__(*args, **kwargs)
        self.fields["motivo"].required = obrigatorio


class CidadeCadastroField(forms.ModelChoiceField):
    """Cidades dos estados liberados; as ainda não atendidas aparecem marcadas (ARQUITETURA §9, regra 3)."""

    def label_from_instance(self, cidade: Cidade) -> str:
        """Ex.: "Tangará da Serra" ou "Sinop — ainda não atendida"."""
        return cidade.nome if cidade.liberada else f"{cidade.nome} — ainda não atendida"


class CadastroForm(forms.Form):
    """Cadastro público de anunciante (/cadastro/): conta, loja e aceite dos documentos.

    Valida tudo o que o modelo exige (documento x tipo, CNPJ/CRECI, WhatsApp, cidade
    liberada, e-mail e documento sem repetir) para devolver mensagens ao lado de cada
    campo. `site_empresa` é o campo-armadilha (honeypot): fica escondido de pessoas;
    robôs que preenchem tudo caem nele.
    """

    # Conta
    nome = forms.CharField(label="Seu nome", max_length=150, help_text="Nome do responsável pela loja.")
    email = forms.EmailField(label="E-mail", help_text="Será o seu login. Enviaremos um link de confirmação.")
    senha = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mínimo de 8 caracteres; não use só números nem senhas comuns.",
    )
    senha_confirmacao = forms.CharField(
        label="Repita a senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    # Loja
    tipo = forms.ChoiceField(label="Você é", choices=Anunciante.Tipo.choices)
    nome_publico = forms.CharField(
        label="Nome da loja", max_length=80, help_text="Como a loja vai aparecer no site. Até 80 caracteres."
    )
    documento = forms.CharField(
        label="CRECI ou CNPJ",
        max_length=25,
        help_text="Corretor autônomo: CRECI (ex.: CRECI/MT 12345-F). Imobiliárias e revendas: CNPJ.",
    )
    whatsapp = forms.CharField(label="WhatsApp", max_length=20, help_text="Com DDD, ex.: (65) 99999-0000.")
    cidade = CidadeCadastroField(
        label="Cidade da loja",
        queryset=Cidade.objects.none(),
        empty_label="Escolha a cidade",
        help_text=(
            "Sua cidade ainda não é atendida? Escolha mesmo assim: "
            "avaliamos a liberação e avisamos por e-mail."
        ),
    )
    aceite = forms.BooleanField(
        label="Li e aceito os Termos de Uso e a Política de Privacidade",
        error_messages={
            "required": "Para se cadastrar, é preciso aceitar os Termos e a Política de Privacidade."
        },
    )
    # Armadilha para robôs (honeypot): escondido por CSS, sem rótulo visível para pessoas.
    site_empresa = forms.CharField(required=False, label="Deixe este campo vazio")

    def __init__(self, *args, **kwargs):
        """Cidades liberadas e classes do Bootstrap nos campos."""
        super().__init__(*args, **kwargs)
        # Atendidas primeiro, depois as demais do(s) estado(s) liberado(s), em ordem alfabética.
        self.fields["cidade"].queryset = (
            Cidade.objects.filter(uf__liberado=True).select_related("uf").order_by("-liberada", "nome")
        )
        for nome, campo in self.fields.items():
            if nome == "aceite":
                campo.widget.attrs["class"] = "form-check-input"
            elif nome != "site_empresa":
                campo.widget.attrs.setdefault(
                    "class", "form-select" if nome in ("tipo", "cidade") else "form-control"
                )
        self.fields["email"].widget.attrs.update(autocomplete="email")
        self.fields["site_empresa"].widget.attrs.update(autocomplete="off", tabindex="-1")

    @property
    def e_robo(self) -> bool:
        """Preencheu o campo-armadilha (pessoas não o veem)."""
        return bool(self.data.get("site_empresa", "").strip())

    def clean_email(self) -> str:
        """E-mail normalizado e ainda sem conta."""
        email = normalizar_email(self.cleaned_data["email"])
        if get_user_model().objects.filter(email=email).exists():
            raise forms.ValidationError(
                'Já existe uma conta com este e-mail. Use "Esqueci minha senha" em Entrar.'
            )
        return email

    def clean_whatsapp(self) -> str:
        """WhatsApp em E.164."""
        return normalizar_whatsapp(self.cleaned_data["whatsapp"])

    def clean(self) -> dict:
        """Senhas iguais e fortes; documento certo para o tipo, válido e ainda não cadastrado."""
        dados = super().clean()
        senha, repetida = dados.get("senha"), dados.get("senha_confirmacao")
        if senha and repetida and senha != repetida:
            self.add_error("senha_confirmacao", "As duas senhas não são iguais.")
        elif senha:
            provisorio = get_user_model()(email=dados.get("email", ""), nome=dados.get("nome", ""))
            try:
                validate_password(senha, provisorio)
            except forms.ValidationError as erro:
                self.add_error("senha", erro)

        tipo, documento, cidade = dados.get("tipo"), dados.get("documento"), dados.get("cidade")
        if tipo and documento:
            documento_tipo = Anunciante.DOCUMENTO_POR_TIPO.get(tipo, Anunciante.DocumentoTipo.CNPJ)
            try:
                if documento_tipo == Anunciante.DocumentoTipo.CNPJ:
                    numero = normalizar_cnpj(documento)
                else:
                    numero = normalizar_creci(documento, uf_padrao=cidade.uf_id if cidade else "MT")
            except forms.ValidationError as erro:
                self.add_error("documento", erro)
            else:
                if Anunciante.objects.filter(documento_tipo=documento_tipo, documento_numero=numero).exists():
                    rotulo = Anunciante.DocumentoTipo(documento_tipo).label
                    self.add_error(
                        "documento", f"Já existe uma loja com este {rotulo}. Se ela é sua, fale com a gente."
                    )
                dados["documento_tipo"], dados["documento_numero"] = documento_tipo, numero
        return dados
