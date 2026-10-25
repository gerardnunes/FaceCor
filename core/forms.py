from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from . import face
from .models import Pessoa, User


class LoginForm(forms.Form):
    usuario = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    senha = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class SetupForm(forms.Form):
    token = forms.CharField(label="Token de configuração", widget=forms.PasswordInput)
    usuario = forms.CharField(label="Usuário master", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)
    senha = forms.CharField(label="Senha (mín. 12 caracteres)", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    senha2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        d = super().clean()
        if d.get("senha") and d.get("senha") != d.get("senha2"):
            self.add_error("senha2", "As senhas não conferem.")
        elif d.get("senha"):
            try:
                password_validation.validate_password(d["senha"], User(username=d.get("usuario", "")))
            except ValidationError as e:
                self.add_error("senha", e)
        return d


class PessoaForm(forms.ModelForm):
    foto = forms.ImageField(label="Foto do rosto", required=False, help_text="Rosto de frente, bem iluminado, uma pessoa só.")

    class Meta:
        model = Pessoa
        fields = ["nome", "matricula", "setor", "cargo", "ativo"]

    def __init__(self, *args, foto_obrigatoria=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["foto"].required = foto_obrigatoria
        self.vetor = None
        self.jpeg = None

    def clean_foto(self):
        arq = self.cleaned_data.get("foto")
        if not arq:
            return arq
        if arq.size > 6 * 1024 * 1024:
            raise ValidationError("Imagem muito grande (máx. 6 MB).")
        img = face.decodificar(arq.read())
        if img is None:
            raise ValidationError("Não foi possível ler a imagem.")
        res = face.extrair(img)
        if res is None:
            raise ValidationError("Nenhum rosto detectado. Tente outra foto, de frente e com boa luz.")
        if res.rostos > 1:
            raise ValidationError("A foto tem mais de um rosto. Use uma foto com apenas uma pessoa.")
        outro, _ = face.identificar(res.vetor, ignorar_id=self.instance.pk)
        if outro:
            nome = Pessoa.objects.filter(pk=outro).values_list("nome", flat=True).first()
            raise ValidationError(f"Este rosto já está cadastrado para {nome}.")
        self.vetor, self.jpeg = res.vetor, face.para_jpeg(img)
        return arq


class UsuarioForm(forms.ModelForm):
    senha = forms.CharField(label="Senha (mín. 12 caracteres)", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "first_name", "email", "papel"]
        labels = {"username": "Usuário", "first_name": "Nome", "email": "E-mail", "papel": "Papel"}

    def clean(self):
        d = super().clean()
        if d.get("senha"):
            try:
                password_validation.validate_password(d["senha"], User(username=d.get("username", "")))
            except ValidationError as e:
                self.add_error("senha", e)
        return d


class SenhaForm(forms.Form):
    senha = forms.CharField(label="Nova senha (mín. 12 caracteres)", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_senha(self):
        s = self.cleaned_data["senha"]
        password_validation.validate_password(s, self.usuario)
        return s


class AWSForm(forms.Form):
    access_key = forms.CharField(label="Access Key ID", required=False, max_length=128, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    secret_key = forms.CharField(
        label="Secret Access Key", required=False, max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}, render_value=False),
        help_text="Deixe em branco para manter a chave já salva.",
    )
    regiao = forms.CharField(label="Região", max_length=30, initial="sa-east-1")
    bucket = forms.RegexField(
        label="Bucket S3", max_length=63, regex=r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$",
        error_messages={"invalid": "Nome de bucket inválido (minúsculas, números, hífens e pontos; 3–63 caracteres)."},
    )
    criar_bucket = forms.BooleanField(label="Criar o bucket se não existir (privado)", required=False)
    ativo = forms.BooleanField(label="Usar a AWS S3 para guardar as fotos", required=False)


class RegistroManualForm(forms.Form):
    pessoa = forms.ModelChoiceField(queryset=Pessoa.objects.filter(ativo=True), label="Pessoa")
    tipo = forms.ChoiceField(choices=[("E", "Entrada"), ("S", "Saída")], label="Tipo")
    motivo = forms.CharField(label="Motivo", max_length=200)
