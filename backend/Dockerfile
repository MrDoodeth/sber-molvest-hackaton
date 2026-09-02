FROM python:3.11-slim-bookworm AS bge-model

ARG BGE_M3_REVISION=5617a9f61b028005a4858fdac845db406aefb181

RUN pip install --no-cache-dir --upgrade pip==25.2 \
    && pip install --no-cache-dir huggingface-hub==0.34.4 \
    && mkdir -p /opt/models/bge-m3 \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-m3', revision='${BGE_M3_REVISION}', local_dir='/opt/models/bge-m3', allow_patterns=['config.json', 'config_sentence_transformers.json', 'modules.json', 'sentence_bert_config.json', 'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', 'sentencepiece.bpe.model', 'pytorch_model.bin', 'sparse_linear.pt', 'colbert_linear.pt', '1_Pooling/config.json'])"

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_MODEL_PATH=/opt/models/bge-m3 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY certs/russian_trusted_root_ca_pem.crt \
    certs/russian_trusted_sub_ca_pem.crt \
    /usr/local/share/ca-certificates/russian-trusted/
RUN update-ca-certificates

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY --from=bge-model /opt/models/bge-m3 /opt/models/bge-m3
RUN pip install --upgrade pip==25.2 \
    && pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.8.0 torchvision==0.23.0 \
    && pip install .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/var/storage \
    && chown -R appuser:appuser /app /opt/models
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
