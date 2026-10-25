"""Armazenamento de fotos: AWS S3 (quando configurada pela interface) ou disco local como fallback.

Cada foto guarda uma 'referência' no banco: "s3|bucket|chave" ou "local|chave", de modo que
trocar a configuração depois não quebra fotos antigas.
"""
import logging
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from .models import AWSConfig

log = logging.getLogger(__name__)


def _client(access_key, secret_key, regiao):
    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=regiao,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}, connect_timeout=5, read_timeout=15),
    )


def _client_atual(cfg):
    ak, sk = cfg.credenciais
    return _client(ak, sk, cfg.regiao)


def _caminho_local(chave):
    raiz = Path(settings.MEDIA_ROOT).resolve()
    destino = (raiz / chave).resolve()
    if raiz not in destino.parents:
        raise ValueError("Caminho inválido")
    return destino


def nova_chave(prefixo):
    return f"{prefixo}/{uuid.uuid4().hex}.jpg"


def salvar(chave, dados: bytes) -> str:
    cfg = AWSConfig.carregar()
    if cfg.ativo and cfg.configurada:
        _client_atual(cfg).put_object(
            Bucket=cfg.bucket, Key=chave, Body=dados, ContentType="image/jpeg", ServerSideEncryption="AES256"
        )
        return f"s3|{cfg.bucket}|{chave}"
    destino = _caminho_local(chave)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
    return f"local|{chave}"


def carregar(ref: str) -> bytes:
    if ref.startswith("s3|"):
        _, bucket, chave = ref.split("|", 2)
        cfg = AWSConfig.carregar()
        if not cfg.credenciais:
            raise RuntimeError("AWS não configurada")
        return _client_atual(cfg).get_object(Bucket=bucket, Key=chave)["Body"].read()
    _, chave = ref.split("|", 1)
    return _caminho_local(chave).read_bytes()


def apagar(ref: str):
    if not ref:
        return
    try:
        if ref.startswith("s3|"):
            _, bucket, chave = ref.split("|", 2)
            _client_atual(AWSConfig.carregar()).delete_object(Bucket=bucket, Key=chave)
        else:
            _, chave = ref.split("|", 1)
            _caminho_local(chave).unlink(missing_ok=True)
    except Exception:
        log.exception("Falha ao apagar %s", ref)


def testar_conexao(access_key, secret_key, regiao, bucket, criar_bucket=False):
    """Retorna (ok, mensagem). Valida credenciais, bucket e permissões de escrita/leitura/remoção."""
    try:
        c = _client(access_key, secret_key, regiao)
        try:
            c.head_bucket(Bucket=bucket)
        except ClientError as e:
            codigo = str(e.response.get("Error", {}).get("Code", ""))
            if codigo in ("404", "NoSuchBucket"):
                if not criar_bucket:
                    return False, "O bucket não existe. Marque 'criar bucket' ou informe um bucket existente."
                args = {} if regiao == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": regiao}}
                c.create_bucket(Bucket=bucket, **args)
                c.put_public_access_block(
                    Bucket=bucket,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    },
                )
            elif codigo in ("403", "AccessDenied"):
                return False, "Acesso negado ao bucket. Verifique as permissões da chave (s3:ListBucket, PutObject, GetObject, DeleteObject)."
            elif codigo in ("301", "400", "PermanentRedirect"):
                return False, "Região incorreta para este bucket."
            else:
                raise
        chave = f".cor-teste/{uuid.uuid4().hex}"
        c.put_object(Bucket=bucket, Key=chave, Body=b"ok", ServerSideEncryption="AES256")
        c.get_object(Bucket=bucket, Key=chave)["Body"].read()
        c.delete_object(Bucket=bucket, Key=chave)
        return True, f"Conexão OK com o bucket '{bucket}' ({regiao}): gravação, leitura e remoção funcionaram."
    except ClientError as e:
        erro = e.response.get("Error", {})
        return False, f"Erro da AWS: {erro.get('Code', '?')} — {erro.get('Message', '')[:200]}"
    except (BotoCoreError, ValueError) as e:
        return False, f"Falha de conexão: {str(e)[:200]}"
