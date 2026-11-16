FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY packages/chatbot_ai/pyproject.toml packages/chatbot_ai/pyproject.toml
RUN uv sync --frozen --no-dev --package backend --no-install-workspace

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/models/hf \
    FASTEMBED_CACHE_PATH=/app/models/fastembed \
    KB_STORAGE_DIR=/data/kb

RUN docling-tools models download layout tableformer \
    && python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

COPY backend/src backend/src
COPY packages/chatbot_ai/src packages/chatbot_ai/src
RUN uv sync --frozen --no-dev --package backend

COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY scripts scripts

EXPOSE 8000

CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && exec uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 1"]
