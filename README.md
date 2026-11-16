# Health Insurance Chatbot

A demo AI chatbot for a health insurer. Members book and cancel clinic visits, file and follow complaints, ask about clinics and doctors, and ask policy questions answered from an uploaded knowledge base. Admins manage the catalog, slots, visits, complaints and the knowledge base. Brand colors are the Midnight Sky palette with #6A9BD1 as the accent.

Version 0.1.0. The design lives in `docs/spec/` (start with `plan.md` and `rules.md`); the build log and decisions are in `docs/progress.md`.

## What is inside

| Part | Stack |
|---|---|
| Frontend | React, Vite, TypeScript, React Router, Tailwind; served by nginx |
| Backend | FastAPI (SSE chat stream), SQLAlchemy + Alembic, Postgres, argon2 sessions |
| AI package (`packages/chatbot_ai`) | OpenAI Chat Completions per role, router plus scheduling, complaints, knowledge and responder agents, Docling ingestion, Qdrant hybrid search (dense + BM25, RRF), offline eval module |
| Observability | Prometheus, Grafana (four dashboards), Postgres exporter, optional Langfuse tracing |

The model never writes data: bookings, cancellations and complaints happen only when the member clicks a card.

## Run it

Requirements: Docker with Compose, and an OpenAI API key for the real assistant.

1. Copy `.env.example` to `.env` and set at least `OPENAI_API_KEY` and `GRAFANA_ADMIN_PASSWORD`. The example lists the model per role (`AI_CHAT_MODEL`, `AI_ROUTER_MODEL`, `AI_REWRITE_MODEL`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIMENSIONS`, `AI_JUDGE_MODEL`). Without AI settings the app still runs, but chat turns and KB ingestion report that the AI is not configured.
2. Start everything:

   ```bash
   docker compose up -d --build
   ```

   The backend runs the database migrations on start. The app is on http://localhost.
3. Create an admin and the demo data:

   ```bash
   docker compose exec backend sh -c 'python scripts/create_admin.py --database-url "$DATABASE_URL" --username admin1 --password <password> --name "Admin One" --location Cairo'
   docker compose exec backend sh -c 'python scripts/seed.py --database-url "$DATABASE_URL"'
   ```

   The seed adds three locations, five specialties, clinics, doctors, slots for the rest of the month and two sample members (`user1` / `userpass1`, `user2` / `userpass2`).
4. Log in as the admin, open **KB documents** and upload the policy files (pdf, docx or txt, up to 10 MB). The synthetic fixtures in `packages/chatbot_ai/src/chatbot_ai/evals/kb_fixtures/` work well for a demo.

Grafana and Prometheus listen on 127.0.0.1 only (ports 3000 and 9090). From another machine use an SSH tunnel, for example `ssh -L 3000:127.0.0.1:3000 <host>`, then log in to Grafana as `admin` with `GRAFANA_ADMIN_PASSWORD`. `/metrics` is not reachable through nginx.

Langfuse tracing turns on when `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` are set; each chat turn is one trace with session id `chat-<session id>`.

## Develop

The Python side is a uv workspace (Python 3.14); the frontend uses npm.

```bash
uv sync --all-packages
(cd frontend && npm ci && npx playwright install chromium)
docker compose up -d postgres qdrant
make check
```

`make check` runs ruff, oxlint, mypy (strict) and tsc, then pytest against real Postgres and Qdrant, Vitest, and the Playwright specs that mock the API. Tests never call a real model: they use a fake OpenAI-compatible server (`testkit/fake_openai.py`) with deterministic hash embeddings.

| Command | What it does |
|---|---|
| `make check` | lint, strict types, all tests that cost nothing |
| `make smoke` | builds the compose stack with the fake model server and checks health, private `/metrics`, token-by-token streaming through nginx, Prometheus targets and retention, and the Grafana dashboards |
| `make e2e` | the smoke checks plus the Playwright full scenario on the stack |
| `make smoke-models` | a short run against the real models in `.env` (costs a little) |
| `uv run python -m chatbot_ai.evals <suite\|all> [--smoke] [--set KEY=VALUE]` | the offline eval suites (ingest, routing, retrieval, answers, tools); real models, costs money. `make evals` only prints this usage |

Run the API locally with `uv run alembic -c backend/alembic.ini upgrade head` and `uv run uvicorn backend.app:app --reload`, and the frontend with `cd frontend && npm run dev` (it proxies `/api` to port 8000).

CI (`.github/workflows/ci.yml`) runs `make check` and the stack smoke and e2e tests on pushes to `main`. It never runs the evals.

## Demo

`docs/demo.md` walks through a ten-minute demo.
