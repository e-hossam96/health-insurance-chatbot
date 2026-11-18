# Health Insurance Chatbot

A demo AI assistant for a health insurer, built to be shown to insurers and employers.

## What it is

The app has two kinds of users.

- **Members** chat with the assistant. They can:
  - book and cancel clinic visits,
  - file complaints and follow the replies,
  - ask about clinics and doctors,
  - ask policy questions, answered from an uploaded knowledge base.
- **Admins** manage the data behind it: locations, specialties, clinics, doctors, slots, visits, complaints and the knowledge-base documents.

One rule shapes the whole design: **the model never writes data.** The assistant only proposes cards. A booking, cancellation or complaint happens only when the member clicks a button on one of those cards.

Where to find more:

- The design lives in [`docs/spec/`](docs/spec/).
- The build log and the decisions made along the way are in [`docs/progress.md`](docs/progress.md).

## Start here

| If you want to... | Read |
| --- | --- |
| see what the app can do | [Features](#features) |
| understand how the pieces fit | [Architecture](#architecture), then [Services](#services) |
| run it on your machine | [Configuration](#configuration), then [Run locally with Docker](#run-locally-with-docker) |
| change the code | [Develop without Docker for the app](#develop-without-docker-for-the-app), then [Tests and checks](#tests-and-checks) |
| measure the AI | [Evals](#evals) |
| put it on a server | [Run in production](#run-in-production) |
| watch it run | [Observability](#observability) |
| go deeper | [Further reading](#further-reading) |

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
- [License](#license)

---

## Features

### For members (in the chat)

| Area | What it does |
| --- | --- |
| Chat | Answers stream in token by token (Server-Sent Events over a POST). Output is Markdown. Starter cards help with the first message. Each chat session keeps its own history. |
| Booking | Finds doctors by specialty, location and date and offers up to three as cards. Booking on click is atomic, so a slot can't be double-booked. |
| Cancellations | Offers the member's scheduled visits as cards. Confirming a cancellation frees the slot. |
| Complaints | Files a complaint about a completed visit. The member can then follow the admin's replies. |
| Clinic questions | Answered from the database through read-only tools. |
| Policy questions | Answered from uploaded PDF, DOCX and TXT documents (retrieval-augmented), showing the excerpts used. When the documents don't cover a question, the assistant says so. |

### For admins and operators

| Area | What it does |
| --- | --- |
| Admin panel | Create, edit and delete the catalog and slots. Set visit status. Reply to complaints. Upload, re-index and delete KB documents. |
| Guard rails | Per-user rate limits and message size limits. Session cookies. The acting user always comes from the session. |
| Observability | Prometheus metrics, four Grafana dashboards, and optional Langfuse traces for each turn. |
| Evals | Offline suites for ingestion, routing, retrieval, answers and tool use, run against real models. |

---

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

How to read the diagram: a request goes from the browser through Caddy (production only) to the frontend's nginx, which forwards `/api` calls to the backend. The backend talks to Postgres directly. Its `chatbot_ai` package talks to Qdrant and to the model APIs. The dotted lines are monitoring: Prometheus scrapes the backend and the exporter, and Grafana reads from Prometheus.

Four ideas explain most of the design:

1. **One agent per turn.**
   - A small router model classifies each turn and hands it to exactly one agent: scheduling, complaints, knowledge, or a plain responder.
   - Routing is invisible to the conversation history.

2. **The AI package is isolated.**
   - `packages/chatbot_ai` has no database code, no web-framework code and no Prometheus code.
   - The backend implements its tool ports and calls its two entry points, `run_turn` and `ingest`.
   - It runs inside the backend container. There is no separate AI service.

3. **The knowledge pipeline.**
   - Docling parses uploaded files.
   - Chunks are embedded and stored only in Qdrant.
   - Each question is rewritten into several searches. Each search is hybrid (dense + BM25), and the results are fused with RRF.
   - A reranker sits behind a Protocol and is off by default.

4. **Ingestion runs in the background.**
   - It runs as a job in a child process, one job at a time.
   - Duplicate uploads are rejected by file hash.

---

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | React, Vite, TypeScript (strict), React Router, TanStack Query, Tailwind CSS. Served by nginx. |
| Backend | Python 3.14, FastAPI (built-in `fastapi.sse` for streaming), SQLAlchemy (async, asyncpg) + Alembic, Pydantic settings, argon2 password hashing, session cookies. Runs one uvicorn worker. |
| AI | OpenAI Python SDK (Chat Completions and embeddings) with one provider config per role, Docling (PDF and DOCX parsing), fastembed BM25 sparse vectors, Langfuse tracing |
| Data | PostgreSQL 18, Qdrant 1.20 |
| Observability | Prometheus 3, Grafana 13, postgres-exporter |
| Tooling | uv workspace (one lockfile), npm, ruff, mypy `--strict`, oxlint, tsc, pytest + httpx, Vitest + Testing Library, Playwright |
| Delivery | Docker Compose, Caddy (automatic Let's Encrypt HTTPS), GitHub Actions CI |

---

## Services

All services are defined in [`docker-compose.yml`](docker-compose.yml). There is no Redis and no model container: models are called over the network.

### What runs

| Service | Purpose | Port (local) |
| --- | --- | --- |
| `frontend` | the web app; proxies `/api` to the backend | `80` (not published in production) |
| `backend` | API, chat stream, KB jobs, `/metrics`; runs the migrations on start | internal `8000` |
| `postgres` | relational data | `127.0.0.1:5432` (not published in production) |
| `qdrant` | vector and BM25 search | `127.0.0.1:6333` (not published in production) |
| `prometheus` | metrics, kept for 15 days | `127.0.0.1:9090` |
| `grafana` | dashboards, provisioned from `observability/` | `127.0.0.1:3000` |
| `postgres-exporter` | Postgres metrics | internal |
| `caddy` | **production only**: HTTPS in front of the frontend; gets and renews its own certificate | `80`, `443` (TCP and UDP) |

### Images

| Service | Image |
| --- | --- |
| `frontend` | built from `frontend/Dockerfile`, based on `nginxinc/nginx-unprivileged:1.30-alpine`. It listens on 8080 as a non-root user. |
| `backend` | built from `backend/Dockerfile` (Python 3.14) |
| `postgres` | `postgres:18.7` |
| `qdrant` | `qdrant/qdrant:v1.20.2` |
| `prometheus` | `prom/prometheus:v3.16.0` |
| `grafana` | `grafana/grafana:13.3.1` |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter:v0.20.1` |
| `caddy` | `caddy:2.11.9-alpine` |

### Volumes

| Volume | Holds |
| --- | --- |
| `pgdata` | the Postgres database |
| `qdrant_data` | the Qdrant vectors |
| `kb_data` | the uploaded KB originals |
| `prometheus_data` | metrics history |
| `grafana_data` | Grafana state |
| `caddy_data` | production only: the certificates |
| `caddy_config` | production only: Caddy's config state |

### Networks

Each service joins only the networks of the services it talks to.

| Network | Members | Notes |
| --- | --- | --- |
| `edge` | Caddy, frontend | |
| `app` | frontend, backend | no route out |
| `data` | backend, Postgres, Qdrant, exporter | no route out in production |
| `metrics` | backend, Qdrant, exporter, Prometheus, Grafana | the scrape targets and their readers |
| `egress` | backend | the backend's way out to the model APIs and Langfuse |

The result: the frontend cannot reach the databases or the dashboards.

### Compose files

| File | Use |
| --- | --- |
| `docker-compose.yml` | the base stack, for both local and production |
| `docker-compose.prod.yml` | production overlay (see below) |
| `docker-compose.stack-test.yml` | test overlay: adds a fake OpenAI-compatible server, so the stack runs without real models |

The production overlay:

- adds Caddy for HTTPS,
- adds restart policies,
- stops publishing the frontend and database ports,
- cuts the data network off from the internet,
- makes the Postgres password required.

---

## Repository layout

```
.
├── backend/                 FastAPI app: auth, DB models, routes, KB jobs, metrics
│   ├── alembic/             database migrations
│   └── tests/
├── packages/chatbot_ai/     AI package: router, agents, RAG, ingestion, evals
│   └── src/chatbot_ai/evals/kb_fixtures/   synthetic policy documents for demos
├── frontend/                React app, nginx config, Vitest and Playwright specs
├── observability/           prometheus.yml, Grafana provisioning and dashboards
├── scripts/                 create_admin, seed, smoke, eval-fixture and coverage tools
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

Each of the three code parts has its own README with a diagram, its layout and a runnable sample:

- [`backend/README.md`](backend/README.md)
- [`frontend/README.md`](frontend/README.md)
- [`packages/chatbot_ai/README.md`](packages/chatbot_ai/README.md)

---

## Configuration

All configuration comes from environment variables, normally set in a `.env` file at the repo root. Start from the example:

```bash
cp .env.example .env
```

`.env` is git-ignored. **Never commit it.**

The variables fall into five groups: required, models, application, tracing and production.

### 1. Required

| Variable | Why it matters |
| --- | --- |
| `GRAFANA_ADMIN_PASSWORD` | Compose refuses to start without it. |
| `OPENAI_API_KEY` | Needed for chat and KB ingestion. Without the AI settings the app still runs, but chat turns and ingestion report that the AI is not configured. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` | The backend builds its database URL from these. There is no `DATABASE_URL`. |

How the Postgres variables behave:

- Compose passes them to Postgres, the backend and the exporter. It sets the host and port itself.
- The user and the database name default to `chatbot`.
- Locally, the password defaults to `chatbot`.
- **In production**, set `POSTGRES_PASSWORD` to letters and digits only (for example from `openssl rand -hex 24`). Set it, together with the user and database name, **before the first start**: Postgres stores them when its volume is created, and changing them later has no effect.

### 2. Models (one config per role)

Each model role has its own settings. The roles are `CHAT`, `ROUTER`, `REWRITE`, `EMBEDDING`, `RERANK` and `JUDGE`. Replace `<ROLE>` below with one of them.

| Variable | Default | Notes |
| --- | --- | --- |
| `AI_<ROLE>_MODEL` | – | The model name. `.env.example` lists the tested choices. |
| `AI_<ROLE>_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint. |
| `AI_<ROLE>_API_KEY` | falls back to `OPENAI_API_KEY` | A key for this role only. |
| `AI_<ROLE>_REASONING_EFFORT` | unset | For chat, router, rewrite and judge only. |
| `AI_<ROLE>_OUTPUT_TOKEN_PARAM` | `max_completion_tokens` | For chat, router, rewrite and judge only. Use `max_tokens` for servers that only know the older name. |

Settings that are not per role:

| Variable | Default | Notes |
| --- | --- | --- |
| `AI_EMBEDDING_DIMENSIONS` | – | **Required.** Must match the embedding model (1536 for `text-embedding-3-small`). |
| `AI_RERANK_PROVIDER` | `none` | The reranker is a placeholder in v0.1.0. |
| `AI_RERANK_MIN_SCORE` | unset | Below this score the assistant replies that it couldn't find the answer. |
| `OPENAI_BASE_URL` | – | Not read by the code. `.env.example` uses it as `${OPENAI_BASE_URL}` inside every role's base URL, so you can change all of them in one place. |

#### Optional tuning

You rarely need these. The defaults are in [`packages/chatbot_ai/src/chatbot_ai/settings.py`](packages/chatbot_ai/src/chatbot_ai/settings.py); the knowledge pipeline they tune is described in [`docs/spec/ai.md`](docs/spec/ai.md).

Retrieval:

| Variable | Default | What it controls |
| --- | --- | --- |
| `AI_QUERY_COUNT` | `3` | how many searches each question is rewritten into (1 to 5) |
| `AI_RETRIEVAL_MODE` | `hybrid` | `hybrid`, `dense` or `sparse` (the single modes are for evals) |
| `AI_PREFETCH_K` | `20` | candidates fetched per vector type, per search |
| `AI_FUSED_K` | `30` | candidates kept after fusion and sent to the reranker |
| `AI_CONTEXT_K` | `5` | excerpts sent to the chat model |
| `AI_QDRANT_COLLECTION` | unset | overrides the collection name derived from the embedding model; the eval runs set it |

Ingestion and embeddings:

| Variable | Default | What it controls |
| --- | --- | --- |
| `AI_CHUNK_MAX_TOKENS` | `512` | token budget per chunk |
| `AI_EMBED_BATCH` | `64` | texts per embedding request |
| `AI_EMBEDDING_QUERY_PREFIX`, `AI_EMBEDDING_DOC_PREFIX` | empty | prefixes some embedding models expect; empty for OpenAI models |
| `INGEST_TIMEOUT_S` | `600` | seconds before an ingestion job is stopped |

Agents and model calls:

| Variable | Default | What it controls |
| --- | --- | --- |
| `AI_MAX_TOOL_ROUNDS` | `4` | tool-call rounds per turn |
| `AI_ROUTER_HISTORY_ROWS` | `6` | history rows the router sees |
| `AI_CHAT_MAX_OUTPUT_TOKENS` | `800` | answer length cap |
| `AI_ROUTER_MAX_OUTPUT_TOKENS` | `512` | router output cap |
| `AI_REWRITE_MAX_OUTPUT_TOKENS` | `1024` | rewrite output cap |
| `AI_TIMEOUT_S` | `60` | seconds per model call |
| `AI_MAX_RETRIES` | `2` | retries per model call |

### 3. Application

| Variable | Default | Notes |
| --- | --- | --- |
| `QDRANT_URL` | `http://localhost:6333` | Compose sets `http://qdrant:6333`. |
| `KB_STORAGE_DIR` | `./data/kb` | Compose sets `/data/kb`, on the `kb_data` volume. |
| `KB_MAX_UPLOAD_BYTES` | `10485760` (10 MB) | |
| `SESSION_LIFETIME_DAYS` | `7` | |
| `RATE_LIMIT_MESSAGES_PER_MINUTE` | `6` | per user |
| `RATE_LIMIT_MESSAGES_PER_DAY` | `100` | per user; admins are exempt |
| `RATE_LIMIT_MESSAGE_MAX_CHARS` | `1000` | |

### 4. Tracing (optional)

| Variable | Notes |
| --- | --- |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Tracing turns on when both are set. |
| `LANGFUSE_HOST` | Optional. The SDK default is Langfuse Cloud. |

Each chat turn becomes one trace, with the session id `chat-<session id>`.

### 5. Production

| Variable | Notes |
| --- | --- |
| `DOMAIN` | the public host name, for example `chat.example.com` |
| `LETSENCRYPT_EMAIL` | the address for certificate expiry notices |

---

## Run locally with Docker

**You need:** Docker with the Compose plugin, and an OpenAI API key for the real assistant. (No key? See [the end of this section](#no-api-key).)

### Step 1. Configure

Copy `.env.example` to `.env`. Set at least `OPENAI_API_KEY` and `GRAFANA_ADMIN_PASSWORD`.

### Step 2. Start the stack

```bash
docker compose up -d --build
```

- The first build downloads the Docling and BM25 models into the backend image, so it takes a few minutes.
- The backend runs the database migrations on start.
- When it is up, open <http://localhost>.

### Step 3. Create an admin and the demo data

```bash
docker compose exec backend python scripts/create_admin.py --username admin1 --password <password> --name "Admin One" --location Cairo
docker compose exec backend python scripts/seed.py
```

The seed adds:

- three locations and five specialties,
- clinics and doctors,
- slots for the rest of the month,
- two sample members: `user1` / `userpass1` and `user2` / `userpass2`.

### Step 4. Upload the knowledge base

1. Log in as the admin.
2. Open **KB documents** and upload policy files (PDF, DOCX or TXT, up to 10 MB each). The synthetic fixtures in `packages/chatbot_ai/src/chatbot_ai/evals/kb_fixtures/` work well for a demo.
3. Wait until each document shows **Ready**.

### Step 5. Chat

Log out, log in as `user1`, and try:

- "I need a dermatologist"
- "How much is the co-pay for an outpatient visit?"

[`docs/demo.md`](docs/demo.md) has a full demo script.

### Useful commands

```bash
docker compose logs -f backend    # follow the backend logs
docker compose down               # stop, keep the data
docker compose down -v            # stop and delete all volumes (database, vectors, uploads)
```

### No API key?

Run the stack against the bundled fake model server instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.stack-test.yml up -d --build
```

The answers are canned, but booking, cards, streaming, ingestion and the dashboards all work.

---

## Develop without Docker for the app

In this setup, Postgres and Qdrant run in Docker, and the backend and frontend run on your machine with hot reload.

**You need:**

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you),
- Node.js 26,
- Docker,
- `make` with bash (on Windows, use Git Bash or WSL).

### One-time setup

```bash
uv sync --all-packages
(cd frontend && npm ci && npx playwright install chromium)
cp .env.example .env              # its POSTGRES_HOST and QDRANT_URL point at localhost
docker compose up -d postgres qdrant
```

### Run the backend (<http://localhost:8000>)

```bash
uv run alembic -c backend/alembic.ini upgrade head
uv run uvicorn backend.app:app --reload
```

### Run the frontend (<http://localhost:5173>)

Vite proxies `/api` to port 8000.

```bash
cd frontend && npm run dev
```

### Create the admin and seed data

Use the same scripts from the host. They read the `POSTGRES_*` variables from `.env`.

```bash
uv run python scripts/create_admin.py --username admin1 --password <password> --name "Admin One" --location Cairo
uv run python scripts/seed.py
```

### Add a migration after a model change

```bash
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe the change"
```

---

## Tests and checks

Two things to know before running tests:

- They use **real** Postgres and Qdrant. Start them first with `docker compose up -d postgres qdrant`.
- They **never** call a real model. They use a fake OpenAI-compatible server (`testkit/fake_openai.py`) with deterministic hash embeddings.

| Command | What it does | Costs money |
| --- | --- | --- |
| `make check` | everything below in one go: ruff, oxlint, mypy (strict), tsc, pytest, Vitest, and the Playwright specs that mock the API | no |
| `make lint` / `make typecheck` / `make test` | the parts of `make check` on their own | no |
| `make smoke` | builds the Compose stack with the fake model server and checks it (list below) | no |
| `make e2e` | the smoke checks, plus the full Playwright scenario on the stack | no |
| `make smoke-models` | a short run against the real models configured in `.env` | a little |

The mocked Playwright specs in `make check` use port 5199. Set `E2E_PORT` to change it.

What `make smoke` checks:

- service health,
- `/metrics` is private,
- containers run as non-root,
- network isolation,
- the production Caddyfile with Caddy in front of nginx: HTTPS, HSTS, the HTTP redirect and the client address,
- streaming through both proxies,
- the Prometheus targets,
- the Grafana dashboards.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs `make check`, the stack smoke test and the stack e2e test on every push to `main`. It never runs the evals.

---

## Evals

The eval module measures the AI side against **real models, so every run costs money.** For that reason `make evals` only prints the usage.

```bash
uv run python -m chatbot_ai.evals <ingest|routing|retrieval|answers|tools|all> [--smoke] [--set KEY=VALUE]
```

| Option | Effect |
| --- | --- |
| first argument | which suite to run, or `all` |
| `--smoke` | runs a small subset |
| `--set KEY=VALUE` | overrides one setting for this run, for example `--set AI_CONTEXT_K=8` |

Results for v0.1.0 are in [`docs/evals/`](docs/evals/).

---

## Run in production

The demo is designed to run as one Compose stack on a single VM behind HTTPS. The full guide is [`docs/deployment.md`](docs/deployment.md). The short version:

### Step 1. VM

4 vCPU, 8 GB RAM, 50 GB SSD, on a current Ubuntu LTS with Docker and the Compose plugin. Open ports 22, 80 and 443 only.

### Step 2. DNS

Point an `A` record (and an `AAAA` record for IPv6) for your domain at the VM.

### Step 3. Configure

Clone the repo, run `cp .env.example .env`, and set:

- `OPENAI_API_KEY` and the `AI_*` model settings,
- a long random `GRAFANA_ADMIN_PASSWORD`,
- `POSTGRES_PASSWORD` (letters and digits, **set before the first start**),
- `DOMAIN` and `LETSENCRYPT_EMAIL`.

### Step 4. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy is configured in [`Caddyfile`](Caddyfile). On its first start it gets the Let's Encrypt certificate for `DOMAIN`, and it renews it on its own. HTTP redirects to HTTPS, and responses carry HSTS.

### Step 5. First admin and data

Run `create_admin.py` (and `seed.py` if you want demo data) as in the local steps. Add `-f docker-compose.yml -f docker-compose.prod.yml` to each `docker compose` command.

**Before sharing the link,** change or remove the seeded sample members.

### Operating it

```bash
P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$P logs -f backend                                       # logs
git pull && $P up -d --build                             # update; migrations run on start
$P exec postgres pg_dump -U chatbot chatbot | gzip > backup-$(date +%F).sql.gz   # backup
```

- **Backups:** back up the `kb_data` volume too (the uploaded originals). Qdrant can be rebuilt instead: re-index every document from the admin page.
- **Reboots:** every service restarts on its own.
- **What is exposed:** only Caddy is published. Postgres and Qdrant are not published on the host and have no route to the internet. `/metrics` is not reachable through Caddy or nginx.

---

## Observability

| Tool | Where | What you get |
| --- | --- | --- |
| Grafana | <http://localhost:3000> (user `admin`, password `GRAFANA_ADMIN_PASSWORD`) | four provisioned dashboards: **Demo overview**, **Chat and LLM**, **API health** and **KB ingestion** |
| Prometheus | <http://localhost:9090> | scrapes the backend, Qdrant and the Postgres exporter every 15 s |
| Langfuse | your Langfuse project | one trace per chat turn (classify, tool calls, generate), when its keys are set |

Grafana and Prometheus listen on 127.0.0.1 only. To open them from another machine, use an SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 <host>
```

---

## Further reading

| Document | Contents |
| --- | --- |
| [`docs/spec/plan.md`](docs/spec/plan.md) | the phases, steps and the tests that prove each step |
| [`docs/spec/rules.md`](docs/spec/rules.md) | behavior rules with stable IDs (B to I) |
| [`docs/spec/schema.dbml`](docs/spec/schema.dbml) | tables and enums |
| [`docs/spec/api.md`](docs/spec/api.md) | API conventions, error codes, auth, the chat stream, card actions |
| [`docs/spec/ai.md`](docs/spec/ai.md) | the `chatbot_ai` package: routing, knowledge pipeline, ingestion, evals |
| [`docs/spec/wireframes.md`](docs/spec/wireframes.md) | every screen and its states |
| [`docs/deployment.md`](docs/deployment.md) | production deployment and operations |
| [`docs/demo.md`](docs/demo.md) | the ten-minute demo script |
| [`docs/progress.md`](docs/progress.md) | build log, decisions and deviations |

---

## License

Released under the [MIT License](LICENSE).
