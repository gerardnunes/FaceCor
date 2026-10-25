"""Reconhecimento facial local com OpenCV (detector YuNet + reconhecedor SFace, modelos ONNX).

Nenhuma imagem sai do servidor para reconhecimento. Os vetores (128 floats) são guardados criptografados.
"""
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from django.conf import settings
from django.db.models import Count, Max

_lock = threading.Lock()
_det = None
_rec = None
_cache = None  # (stamp, ids, matriz)

DETECTOR = "face_detection_yunet_2023mar.onnx"
RECONHECEDOR = "face_recognition_sface_2021dec.onnx"


@dataclass
class Resultado:
    vetor: np.ndarray
    rostos: int


def _carregar():
    global _det, _rec
    if _det is None:
        d = settings.MODELS_DIR
        _det = cv2.FaceDetectorYN.create(str(d / DETECTOR), "", (320, 320), 0.85, 0.3, 5000)
        _rec = cv2.FaceRecognizerSF.create(str(d / RECONHECEDOR), "")


def decodificar(dados: bytes, lado_max=960):
    img = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) > lado_max:
        f = lado_max / max(h, w)
        img = cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
    return img


def para_jpeg(img, qualidade=82) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, qualidade])  # reencode remove EXIF
    return buf.tobytes()


def extrair(img):
    """Detecta o maior rosto e devolve seu vetor. None se não houver rosto."""
    with _lock:
        _carregar()
        h, w = img.shape[:2]
        _det.setInputSize((w, h))
        _, rostos = _det.detect(img)
        if rostos is None or len(rostos) == 0:
            return None
        maior = max(rostos, key=lambda r: r[2] * r[3])
        alinhado = _rec.alignCrop(img, maior)
        vetor = _rec.feature(alinhado).flatten().astype(np.float32)
        return Resultado(vetor=vetor, rostos=len(rostos))


def _base():
    global _cache
    from .models import Pessoa

    qs = Pessoa.objects.filter(ativo=True)
    agg = qs.aggregate(n=Count("id"), m=Max("atualizado_em"))
    stamp = (agg["n"], agg["m"])
    if _cache and _cache[0] == stamp:
        return _cache[1], _cache[2]
    ids, vetores = [], []
    for p in qs:
        v = p.obter_embedding()
        ids.append(p.pk)
        vetores.append(v / np.linalg.norm(v))
    matriz = np.vstack(vetores) if vetores else np.empty((0, 128), np.float32)
    _cache = (stamp, ids, matriz)
    return ids, matriz


def identificar(vetor, ignorar_id=None):
    """Retorna (pessoa_id | None, similaridade). Similaridade cosseno contra todas as pessoas ativas."""
    ids, matriz = _base()
    if not ids:
        return None, 0.0
    sims = matriz @ (vetor / np.linalg.norm(vetor))
    if ignorar_id is not None:
        for i, pid in enumerate(ids):
            if pid == ignorar_id:
                sims[i] = -1.0
    i = int(np.argmax(sims))
    s = float(sims[i])
    return (ids[i] if s >= settings.FACE_THRESHOLD else None), s
