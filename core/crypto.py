"""Criptografia em repouso (Fernet/AES) para credenciais AWS e vetores faciais."""
from cryptography.fernet import Fernet
from django.conf import settings

_f = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


def encrypt(texto: str) -> str:
    return _f.encrypt(texto.encode()).decode()


def decrypt(token: str) -> str:
    return _f.decrypt(token.encode()).decode()


def encrypt_bytes(dados: bytes) -> bytes:
    return _f.encrypt(dados)


def decrypt_bytes(token: bytes) -> bytes:
    return _f.decrypt(bytes(token))
