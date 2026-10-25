import numpy as np
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from . import crypto


class User(AbstractUser):
    class Papel(models.TextChoices):
        MASTER = "master", "Master"
        GESTOR = "gestor", "Gestor"
        OPERADOR = "operador", "Operador (quiosque)"

    papel = models.CharField(max_length=10, choices=Papel.choices, default=Papel.OPERADOR)
    falhas = models.PositiveSmallIntegerField(default=0)
    bloqueado_ate = models.DateTimeField(null=True, blank=True)

    @property
    def eh_master(self):
        return self.papel == self.Papel.MASTER

    @property
    def pode_gerir(self):
        return self.papel in (self.Papel.MASTER, self.Papel.GESTOR)


class AWSConfig(models.Model):
    """Configuração única da AWS S3, preenchida pela interface (credenciais criptografadas)."""

    access_key = models.TextField(blank=True)
    secret_key = models.TextField(blank=True)
    regiao = models.CharField(max_length=30, default="sa-east-1")
    bucket = models.CharField(max_length=63, blank=True)
    ativo = models.BooleanField(default=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    @classmethod
    def carregar(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def definir_credenciais(self, access_key, secret_key):
        self.access_key = crypto.encrypt(access_key)
        self.secret_key = crypto.encrypt(secret_key)

    @property
    def credenciais(self):
        if not (self.access_key and self.secret_key):
            return None
        return crypto.decrypt(self.access_key), crypto.decrypt(self.secret_key)

    @property
    def configurada(self):
        return bool(self.access_key and self.secret_key and self.bucket)

    @property
    def chave_mascarada(self):
        c = self.credenciais
        return f"{c[0][:4]}••••••••{c[0][-4:]}" if c else ""


class Pessoa(models.Model):
    nome = models.CharField(max_length=120)
    matricula = models.CharField("matrícula", max_length=30, unique=True)
    setor = models.CharField(max_length=80, blank=True)
    cargo = models.CharField(max_length=80, blank=True)
    ativo = models.BooleanField(default=True)
    foto_ref = models.CharField(max_length=300, blank=True)
    embedding = models.BinaryField(default=b"")  # vetor facial criptografado
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.matricula})"

    def definir_embedding(self, vetor):
        self.embedding = crypto.encrypt_bytes(np.asarray(vetor, dtype=np.float32).tobytes())

    def obter_embedding(self):
        return np.frombuffer(crypto.decrypt_bytes(self.embedding), dtype=np.float32)


class Registro(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "E", "Entrada"
        SAIDA = "S", "Saída"

    class Metodo(models.TextChoices):
        FACIAL = "F", "Facial"
        MANUAL = "M", "Manual"

    pessoa = models.ForeignKey(Pessoa, null=True, blank=True, on_delete=models.SET_NULL, related_name="registros")
    nome_snapshot = models.CharField(max_length=120, blank=True)
    matricula_snapshot = models.CharField(max_length=30, blank=True)
    tipo = models.CharField(max_length=1, choices=Tipo.choices)
    metodo = models.CharField(max_length=1, choices=Metodo.choices, default=Metodo.FACIAL)
    momento = models.DateTimeField(default=timezone.now, db_index=True)
    confianca = models.FloatField(null=True, blank=True)
    foto_ref = models.CharField(max_length=300, blank=True)
    desconhecido = models.BooleanField(default=False)
    operador = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-momento"]

    @property
    def nome_exibicao(self):
        return "Desconhecido" if self.desconhecido else (self.pessoa.nome if self.pessoa else self.nome_snapshot)


class Auditoria(models.Model):
    usuario = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    usuario_texto = models.CharField(max_length=150, blank=True)
    acao = models.CharField(max_length=60)
    detalhe = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    momento = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-momento"]
        verbose_name_plural = "auditoria"
