FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY packages/chatbot_ai/pyproject.toml packages/chatbot_ai/pyproject.toml
COPY backend/src backend/src
COPY packages/chatbot_ai/src packages/chatbot_ai/src

RUN uv sync --frozen --no-dev --package backend

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
