FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Package weights at build time; cold starts never download the model.
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41', local_dir='/opt/embedding-model', allow_patterns=['*.json', '*.txt', 'model.safetensors'])"

COPY . .

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    EMBEDDING_MODEL=/opt/embedding-model HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MALLOC_ARENA_MAX=2

EXPOSE 8080

# Run database migrations separately before deploying a new revision.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --workers 1 --host 0.0.0.0 --port ${PORT:-8080}"]
