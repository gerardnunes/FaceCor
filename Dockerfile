FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data MODELS_DIR=/app/models_onnx

RUN apt-get update && apt-get install -y --no-install-recommends curl libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelos de reconhecimento facial (OpenCV Zoo, licença MIT/Apache) — baixados uma única vez no build
RUN mkdir -p /app/models_onnx \
 && curl -fsSL -o /app/models_onnx/face_detection_yunet_2023mar.onnx \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
 && curl -fsSL -o /app/models_onnx/face_recognition_sface_2021dec.onnx \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx \
 && test $(stat -c %s /app/models_onnx/face_detection_yunet_2023mar.onnx) -gt 100000 \
 && test $(stat -c %s /app/models_onnx/face_recognition_sface_2021dec.onnx) -gt 1000000

COPY . .
# Migrações e estáticos gerados no build (DATA_DIR temporário: nenhum segredo entra na imagem)
RUN SECRET_KEY=build DATA_DIR=/tmp/build python manage.py makemigrations core \
 && SECRET_KEY=build DATA_DIR=/tmp/build python manage.py collectstatic --noinput \
 && rm -rf /tmp/build \
 && useradd -r -u 10001 app && mkdir /data && chown app /data && chmod +x entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
