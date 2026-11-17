# Health Insurance Chatbot

A demo AI assistant for a health insurer, built to be shown to insurers and employers.

- **Members** chat with the assistant to book and cancel clinic visits, file and follow complaints, ask about clinics and doctors, and ask policy questions answered from an uploaded knowledge base.
- **Admins** manage locations, specialties, clinics, doctors, slots, visits, complaints and the knowledge-base documents.

The model never writes data. Every booking, cancellation or complaint happens only when the member clicks a button on a card that the assistant proposes.

Version **0.1.0**. The design lives in [`docs/spec/`](docs/spec/) and the build log and decisions are in [`docs/progress.md`](docs/progress.md).

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Services](#services)
- [Repository layout](#repository-layout)
- [Configuration](#configuration)
- [Run locally with Docker](#run-locally-with-docker)
- [Develop without Docker for the app](#develop-without-docker-for-the-app)
- [Tests and checks](#tests-and-checks)
- [Evals](#evals)
- [Run in production](#run-in-production)
- [Observability](#observability)
- [Further reading](#further-reading)

---

## Features

| Area | What it does |
|---|---|
| Chat | Token-by-token streamed answers (Server-Sent Events over a POST), Markdown output, starter cards, chat history per session |
| Booking | Finds doctors by specialty, location and date, offers up to three as cards, books atomically on click (a slot can't be double-booked) |
| Cancellations | Offers the member's scheduled visits as cards and frees the slot on confirm |
| Complaints | Files a complaint about a completed visit, lets the member follow admin replies |
| Clinic questions | Answers from the database through read-only tools |
| Policy questions | Retrieval-augmented answers from uploaded PDF, DOCX and TXT documents, with the excerpts used; says so when the documents don't cover a question |
| Admin panel | CRUD for the catalog and slots, visit status, complaint replies, KB upload, re-index and delete |
| Guard rails | Per-user rate limits and message size limits, session cookies, the acting user always comes from the session |
| Observability | Prometheus metrics, four Grafana dashboards, optional Langfuse traces per turn |
| Evals | Offline suites for ingestion, routing, retrieval, answers and tool use against real models |

## Architecture

```mermaid
flowchart TB
    browser(["Browser"])

    subgraph compose["Docker Compose"]
        caddy["<b>caddy</b> (production only)<br/>HTTPS, certificates, HSTS"]
        frontend["<b>frontend</b> (nginx, non-root)<br/>serves the React app<br/>proxies /api to the backend"]

        subgraph backend["backend (FastAPI)"]
            routes["auth, routes, SSE"]
            ingestion["KB ingestion job"]
            chatbot_ai["chatbot_ai package"]
        end

        postgres[("<b>postgres</b><br/>users, catalog, slots,<br/>visits, complaints, chats")]
        qdrant[("<b>qdrant</b><br/>KB chunks<br/>dense + BM25")]
        exporter["postgres-exporter"]
        prometheus["prometheus"]
        grafana["grafana"]
    end

    models["<b>model APIs</b><br/>chat, router, rewrite,<br/>embedding, judge"]

    browser -- "HTTPS" --> caddy
    caddy --> frontend
    frontend --> backend
    backend --> postgres
    chatbot_ai --> qdrant
    chatbot_ai -- "OpenAI API shape" --> models
    exporter -.-> postgres
    prometheus -. "/metrics" .-> backend
    prometheus -.-> exporter
    grafana -.-> prometheus

    classDef client fill:#475569,stroke:#94a3b8,color:#ffffff
    classDef app fill:#2563eb,stroke:#93c5fd,color:#ffffff
    classDef store fill:#0f766e,stroke:#5eead4,color:#ffffff
    classDef observe fill:#7c3aed,stroke:#c4b5fd,color:#ffffff
    classDef external fill:#b45309,stroke:#fcd34d,color:#ffffff

    class browser client
    class frontend,routes,ingestion,chatbot_ai app
    class postgres,qdrant store
    class exporter,prometheus,grafana observe
    class models external

    style compose fill:transparent,stroke:#64748b,stroke-width:1px,stroke-dasharray:5 4,color:#64748b
    style backend fill:transparent,stroke:#3b82f6,stroke-width:1.5px,color:#3b82f6
    linkStyle default stroke:#64748b,stroke-width:1.5px
```

- **One agent per turn.** A small router model classifies each turn and hands it to one agent: scheduling, complaints, knowledge or a plain responder. Routing is invisible to the conversation history.
- **The AI package is isolated.** `packages/chatbot_ai` has no database, web-framework or Prometheus code. The backend implements its tool ports and calls `run_turn` and `ingest`. It runs inside the backend container; there is no separate AI service.
- **Knowledge pipeline.** Docling parses uploads, chunks are embedded and stored only in Qdrant, and queries are rewritten into several searches fused with RRF (dense + BM25). A reranker sits behind a Protocol and is off by default.
- **Ingestion** runs as a background job in a child process, one job at a time. Duplicates are rejected by file hash.

## Tech stack

| Layer | Technologies |
|---|---|
| Frontend | React, Vite, TypeScript (strict), React Router, TanStack Query, Tailwind CSS, served by nginx |
| Backend | Python 3.14, FastAPI (built-in `fastapi.sse` for streaming), SQLAlchemy (async, asyncpg) + Alembic, Pydantic settings, argon2 password hashing, session cookies, one uvicorn worker |
| AI | OpenAI Python SDK (Chat Completions and embeddings), one provider config per role, Docling (PDF and DOCX parsing), fastembed BM25 sparse vectors, Langfuse tracing |
| Data | PostgreSQL 17, Qdrant 1.13 |
| Observability | Prometheus 3, Grafana 13, postgres-exporter |
| Tooling | uv workspace (one lockfile), npm, ruff, mypy `--strict`, oxlint, tsc, pytest + httpx, Vitest + Testing Library, Playwright |
| Delivery | Docker Compose, Caddy (automatic Let's Encrypt HTTPS), GitHub Actions CI |

## Services

All services are defined in [`docker-compose.yml`](docker-compose.yml). There is no Redis and no model container; models are called over the network.

| Service | Image | Port (local) | Purpose |
|---|---|---|---|
| `frontend` | built from `frontend/Dockerfile` (`nginxinc/nginx-unprivileged:1.30-alpine`, listens on 8080 as a non-root user) | `80` (not published in production) | the web app, proxies `/api` to the backend |
| `backend` | built from `backend/Dockerfile` (Python 3.14) | internal `8000` | API, chat stream, KB jobs, `/metrics`; runs migrations on start |
| `postgres` | `postgres:18.7` | `127.0.0.1:5432` (not published in production) | relational data |
| `qdrant` | `qdrant/qdrant:v1.20.2` | `127.0.0.1:6333` (not published in production) | vector and BM25 search |
| `prometheus` | `prom/prometheus:v3.16.0` | `127.0.0.1:9090` | metrics, 15 days retention |
| `grafana` | `grafana/grafana:13.3.1` | `127.0.0.1:3000` | dashboards (provisioned from `observability/`) |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter:v0.20.1` | internal | Postgres metrics |
| `caddy` | `caddy:2.11.9-alpine` | `80`, `443` (TCP and UDP) | production only: HTTPS in front of the frontend, gets and renews its own certificate |

Volumes: `pgdata`, `qdrant_data`, `kb_data` (uploaded originals), `prometheus_data`, `grafana_data`, and in production `caddy_data` (the certificates) and `caddy_config`.

Networks: each service joins only the networks of the services it talks to. `edge` (Caddy and the frontend), `app` (frontend and backend, no route out), `data` (backend, Postgres, Qdrant, the exporter; no route out in production), `metrics` (backend, Qdrant, exporter, Prometheus, Grafana; the scrape targets) and `egress` (the backend's way out to the model APIs and Langfuse). The frontend cannot reach the databases or the dashboards.

Compose files:

| File | Use |
|---|---|
| `docker-compose.yml` | the base stack, local and production |
| `docker-compose.prod.yml` | production overlay: Caddy for HTTPS, restart policies, no published frontend or database ports, the data network cut off from the internet, required Postgres password |
| `docker-compose.stack-test.yml` | test overlay: adds a fake OpenAI-compatible server so the stack runs without real models |

## Repository layout

```
.
├── backend/                 FastAPI app: auth, DB models, routes, KB jobs, metrics
│   ├── alembic/             database migrations
│   └── tests/
├── packages/chatbot_ai/     AI package: router, agents, RAG, ingestion, evals
│   └── src/chatbot_ai/evals/kb_fixtures/   synthetic policy documents for demos
├── frontend/                React app, nginx configs, Vitest and Playwright specs
├── observability/           prometheus.yml, Grafana provisioning and dashboards
├── scripts/                 create_admin, seed, certificate, smoke and coverage tools
├── testkit/                 fake OpenAI-compatible server used by tests
├── tests/                   cross-cutting tests and rule coverage
├── docs/
│   ├── spec/                plan, schema, rules, wireframes, API, AI design
│   ├── deployment.md        production guide
│   ├── demo.md              ten-minute demo script
│   └── progress.md          build log and decisions
├── docker-compose*.yml
├── Makefile
└── pyproject.toml / uv.lock uv workspace root
```

## Configuration

All configuration is read from environment variables, normally from a `.env` file at the repo root. Start from the example:

```bash
cp .env.example .env
```

`.env` is git-ignored. Never commit it.

### Required

| Variable | Notes |
|---|---|
| `GRAFANA_ADMIN_PASSWORD` | Compose refuses to start without it |
| `OPENAI_API_KEY` | needed for chat and KB ingestion. Without AI settings the app still runs, but chat turns and ingestion report that the AI is not configured |
| `DATABASE_URL` | only for running the backend outside Docker. Compose sets it for the container |
| `POSTGRES_PASSWORD` | production only. Letters and digits (for example `openssl rand -hex 24`). Set it before the first start: Postgres stores it when the volume is created. Locally it defaults to `chatbot` |

### Models (one config per role)

Each role is `CHAT`, `ROUTER`, `REWRITE`, `EMBEDDING`, `RERANK` or `JUDGE`.

| Variable | Default | Notes |
|---|---|---|
| `AI_<ROLE>_MODEL` | – | the model name; see `.env.example` for the tested choices |
| `AI_<ROLE>_BASE_URL` | `https://api.openai.com/v1` | any OpenAI-compatible endpoint |
| `AI_<ROLE>_API_KEY` | falls back to `OPENAI_API_KEY` | per-role key |
| `AI_<ROLE>_REASONING_EFFORT` | unset | chat, router, rewrite and judge |
| `AI_EMBEDDING_DIMENSIONS` | – | required; must match the embedding model (1536 for `text-embedding-3-small`) |
| `AI_RERANK_PROVIDER` | `none` | the reranker is a placeholder in v0.1.0 |
| `AI_RERANK_MIN_SCORE` | unset | below this score the assistant replies that it couldn't find the answer |

Retrieval and limits can be tuned too (`AI_QUERY_COUNT`, `AI_RETRIEVAL_MODE`, `AI_PREFETCH_K`, `AI_FUSED_K`, `AI_CONTEXT_K`, `AI_CHUNK_MAX_TOKENS`, `AI_MAX_TOOL_ROUNDS`, `AI_CHAT_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_S`, `AI_MAX_RETRIES`, `INGEST_TIMEOUT_S`). Their defaults are in [`packages/chatbot_ai/src/chatbot_ai/settings.py`](packages/chatbot_ai/src/chatbot_ai/settings.py).

### Application

| Variable | Default | Notes |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Compose sets `http://qdrant:6333` |
| `KB_STORAGE_DIR` | `./data/kb` | Compose sets `/data/kb` on the `kb_data` volume |
| `KB_MAX_UPLOAD_BYTES` | `10485760` (10 MB) | |
| `SESSION_LIFETIME_DAYS` | `7` | |
| `RATE_LIMIT_MESSAGES_PER_MINUTE` | `6` | per user |
| `RATE_LIMIT_MESSAGES_PER_DAY` | `100` | per user, admins exempt |
| `RATE_LIMIT_MESSAGE_MAX_CHARS` | `1000` | |

### Tracing (optional)

| Variable | Notes |
|---|---|
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | tracing turns on when all three are set. Each chat turn is one trace with session id `chat-<session id>` |

### Production

| Variable | Notes |
|---|---|
| `DOMAIN` | the public host name, for example `chat.example.com` |
| `LETSENCRYPT_EMAIL` | address for certificate expiry notices |

## Run locally with Docker

Requirements: Docker with the Compose plugin. An OpenAI API key for the real assistant.

1. **Configure.** Copy `.env.example` to `.env` and set at least `OPENAI_API_KEY` and `GRAFANA_ADMIN_PASSWORD`.

2. **Start the stack.**

   ```bash
   docker compose up -d --build
   ```

   The first build downloads the Docling and BM25 models into the backend image, so it takes a few minutes. The backend runs the database migrations on start. Open http://localhost.

3. **Create an admin and the demo data.**

   ```bash
   docker compose exec backend sh -c 'python scripts/create_admin.py --database-url "$DATABASE_URL" --username admin1 --password <password> --name "Admin One" --location Cairo'
   docker compose exec backend sh -c 'python scripts/seed.py --database-url "$DATABASE_URL"'
   ```

   The seed adds three locations, five specialties, clinics, doctors, slots for the rest of the month and two sample members: `user1` / `userpass1` and `user2` / `userpass2`.

4. **Upload the knowledge base.** Log in as the admin, open **KB documents** and upload policy files (PDF, DOCX or TXT, up to 10 MB). The synthetic fixtures in `packages/chatbot_ai/src/chatbot_ai/evals/kb_fixtures/` work well for a demo. Wait until each one shows **Ready**.

5. **Chat.** Log out, log in as `user1`, and try "I need a dermatologist" or "How much is the co-pay for an outpatient visit?". [`docs/demo.md`](docs/demo.md) has a full script.

Useful commands:

```bash
docker compose logs -f backend    # follow the backend logs
docker compose down               # stop, keep the data
docker compose down -v            # stop and delete all volumes (database, vectors, uploads)
```

**No API key?** Run the stack against the bundled fake model server instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.stack-test.yml up -d --build
```

Answers are canned, but booking, cards, streaming, ingestion and the dashboards all work.

## Develop without Docker for the app

Run Postgres and Qdrant in Docker and the backend and frontend on the host for hot reload.

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.14), Node.js 22, Docker, and `make` with bash (on Windows use Git Bash or WSL).

```bash
uv sync --all-packages
(cd frontend && npm ci && npx playwright install chromium)
cp .env.example .env              # its DATABASE_URL and QDRANT_URL point at localhost
docker compose up -d postgres qdrant
```

Backend on http://localhost:8000:

```bash
uv run alembic -c backend/alembic.ini upgrade head
uv run uvicorn backend.app:app --reload
```

Frontend on http://localhost:5173 (Vite proxies `/api` to port 8000):

```bash
cd frontend && npm run dev
```

Create the admin and seed data from the host with the same scripts:

```bash
uv run python scripts/create_admin.py --database-url "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot" --username admin1 --password <password> --name "Admin One" --location Cairo
uv run python scripts/seed.py --database-url "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"
```

New migration after a model change:

```bash
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe the change"
```

## Tests and checks

Tests use real Postgres and Qdrant (start them with `docker compose up -d postgres qdrant`). They never call a real model: they use a fake OpenAI-compatible server (`testkit/fake_openai.py`) with deterministic hash embeddings.

| Command | What it does | Costs money |
|---|---|---|
| `make check` | ruff, oxlint, mypy (strict), tsc, pytest, Vitest and the Playwright specs that mock the API (set `E2E_PORT` if Grafana already holds port 3000) | no |
| `make lint` / `make typecheck` / `make test` | the parts of `make check` on their own | no |
| `make smoke` | builds the compose stack with the fake model server and checks health, private `/metrics`, non-root containers, network isolation, the production Caddyfile with Caddy in front of nginx (HTTPS, HSTS, redirect, client address), streaming through both proxies, Prometheus targets and the Grafana dashboards | no |
| `make e2e` | the smoke checks plus the full Playwright scenario on the stack | no |
| `make smoke-models` | a short run against the real models configured in `.env` | a little |

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs `make check`, the stack smoke test and the stack e2e test on every push to `main`. It never runs the evals.

## Evals

The eval module measures the AI side against real models, so every run costs money. `make evals` only prints the usage.

```bash
uv run python -m chatbot_ai.evals <ingest|routing|retrieval|answers|tools|all> [--smoke] [--set KEY=VALUE]
```

`--smoke` runs a small subset, and `--set` overrides a setting for the run (for example `--set AI_CONTEXT_K=8`). Results for v0.1.0 are in [`docs/evals/`](docs/evals/).

## Run in production

The demo is designed to run as one Compose stack on a single VM behind HTTPS. The full guide is [`docs/deployment.md`](docs/deployment.md); the short version:

1. **VM.** 4 vCPU, 8 GB RAM, 50 GB SSD on a current Ubuntu LTS with Docker and the Compose plugin. Open ports 22, 80 and 443 only.
2. **DNS.** Point an `A` record (and `AAAA` for IPv6) for your domain at the VM.
3. **Configure.** Clone the repo, `cp .env.example .env`, and set `OPENAI_API_KEY`, the `AI_*` model settings, a long random `GRAFANA_ADMIN_PASSWORD`, `POSTGRES_PASSWORD` (letters and digits, set before the first start), `DOMAIN` and `LETSENCRYPT_EMAIL`.
4. **Start.**

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

   Caddy (configured in [`Caddyfile`](Caddyfile)) gets the Let's Encrypt certificate for `DOMAIN` on its first start and renews it on its own. HTTP redirects to HTTPS, and responses carry HSTS.

5. **First admin and data.** Run `create_admin.py` (and `seed.py` for demo data) as in the local steps, with `-f docker-compose.yml -f docker-compose.prod.yml` on each `docker compose` command. Change or remove the seeded sample members before sharing the link.

Operating it:

```bash
P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$P logs -f backend                                       # logs
git pull && $P up -d --build                             # update; migrations run on start
$P exec postgres pg_dump -U chatbot chatbot | gzip > backup-$(date +%F).sql.gz   # backup
```

Back up the `kb_data` volume too (the uploaded originals). Qdrant can be rebuilt by re-indexing every document from the admin page. Every service restarts on its own after a reboot.

In production only Caddy is published. Postgres and Qdrant are not published on the host and have no route to the internet, and `/metrics` is not reachable through Caddy or nginx.

## Observability

- **Grafana** at http://localhost:3000 (user `admin`, password `GRAFANA_ADMIN_PASSWORD`) with four provisioned dashboards: **Demo overview**, **Chat and LLM**, **API health** and **KB ingestion**.
- **Prometheus** at http://localhost:9090 scrapes the backend and the Postgres exporter.
- Both listen on 127.0.0.1 only. From another machine use an SSH tunnel:

  ```bash
  ssh -L 3000:127.0.0.1:3000 <host>
  ```

- **Langfuse** traces each chat turn (classify, tool calls, generate) when its keys are set.

## Further reading

| Document | Contents |
|---|---|
| [`docs/spec/plan.md`](docs/spec/plan.md) | phases, steps and the tests that prove each step |
| [`docs/spec/rules.md`](docs/spec/rules.md) | behavior rules with stable IDs (B to I) |
| [`docs/spec/schema.dbml`](docs/spec/schema.dbml) | tables and enums |
| [`docs/spec/api.md`](docs/spec/api.md) | API conventions, error codes, auth, chat stream, card actions |
| [`docs/spec/ai.md`](docs/spec/ai.md) | the `chatbot_ai` package: routing, knowledge pipeline, ingestion, evals |
| [`docs/spec/wireframes.md`](docs/spec/wireframes.md) | every screen and its states |
| [`docs/deployment.md`](docs/deployment.md) | production deployment and operations |
| [`docs/demo.md`](docs/demo.md) | ten-minute demo script |
| [`docs/progress.md`](docs/progress.md) | build log, decisions and deviations |
