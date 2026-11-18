# Health Insurance Chatbot - Project Guide

Version: v0.1.0. Every spec file carries the same version line.

A demo of an AI chatbot for a health insurer, shown to insurers and employers. It books clinic visits, files and checks complaints, answers questions about clinics from the database, and answers policy questions from an uploaded knowledge base. The AI side is meant to show a modern RAG and agent stack, and to be measured by an eval module.

## Read in this order

1. `docs/progress.md` - state file: what is done, decisions made, questions waiting for the user.
2. `docs/spec/plan.md` - the phases, steps and the tests that prove each step.
3. `docs/spec/schema.dbml` - tables, enums and migration notes (the A-items).
4. `docs/spec/rules.md` - behavior rules B to I. IDs (D6, F12, H2, I1, ...) are stable. Cite them, never restate them.
5. `docs/spec/wireframes.md` - every screen, its states, and the endpoints it calls.
6. `docs/spec/api.md` - conventions, error codes, auth, the chat stream, card actions.
7. `docs/spec/ai.md` - the `chatbot_ai` package: interface, routing, knowledge pipeline, ingestion, provider config, eval module.

Read the whole of items 1 to 2 at the start of a session. Read only the spec files and rule IDs that the current step lists.

## Stack

- Frontend: React, Vite, TypeScript, React Router, TanStack Query, Tailwind with the app's own component classes (no shadcn/ui). The chat stream is read with fetch because it is a POST. English only. Assistant text is Markdown without raw HTML.
- Backend: Python, FastAPI (use the built-in `fastapi.sse` for streaming), Postgres, SQLAlchemy + Alembic, argon2 password hashing, session cookies.
- AI package: OpenAI SDK against the OpenAI API shape (Chat Completions, embeddings), one provider config per role (I11). Closed-source OpenAI models first. Docling parses PDF and DOCX. Reranker sits behind a Protocol; the provider is a placeholder (`ai.md`).
- Retrieval: Qdrant (dense + BM25, RRF fusion). Chunks live only in Qdrant.
- Tracing: Langfuse (use `chat-<session id>` as the session id). Metrics: Prometheus + Grafana.
- Docker Compose services: postgres, qdrant, backend, frontend (nginx, non-root), prometheus, grafana, postgres exporter, and caddy in production only (HTTPS). Each service joins only the networks it needs (edge, app, data, metrics, egress). No Redis and no model containers. KB originals sit on a local Docker volume.
- Testing: pytest and httpx with real Postgres and Qdrant; Vitest and Testing Library; Playwright; ruff and mypy (strict); oxlint and tsc. Equivalent tools may be substituted. Log the choice in `docs/progress.md`.

## Repo layout (to create)

```
repo/
  CLAUDE.md
  docs/
    spec/                 # schema.dbml, rules.md, wireframes.md, api.md, ai.md, plan.md
    progress.md           # state file
  pyproject.toml          # uv workspace root, one lockfile
  frontend/
  backend/                # FastAPI app: auth, DB, routes, transactions
  packages/
    chatbot_ai/           # the AI package (agents, RAG, ingestion, evals); layout in ai.md
  observability/          # prometheus.yml, Grafana provisioning, dashboard JSON
  scripts/                # create_admin, seed, rule_coverage, smoke and stack checks, eval fixtures
  testkit/                # fake OpenAI-compatible server, fake ports, Qdrant and embedding helpers for tests
  tests/                  # cross-cutting tests, rule_scope.yaml, rule_coverage_exemptions.md
  docs/deployment.md, docs/demo.md, docs/evals/   # operations guide, demo script, eval reports
  Caddyfile, docker-compose.yml, docker-compose.prod.yml, docker-compose.stack-test.yml
```

Frontend, backend and `chatbot_ai` all start at version 0.1.0 (package.json, pyproject.toml). Docker builds use the repo root as the context so the backend image can include `packages/`. The AI package runs inside the backend container; there is no separate AI service.

## Ground rules

- `chatbot_ai` has no Postgres access, no web-framework code and no Prometheus code (it does call the model providers and Qdrant). The backend implements its Ports (tools) and calls `run_turn` and `ingest`. The package returns timings as plain values (H2).
- The model never writes data. Every write is an endpoint called by a card click (D9).
- The acting profile comes from the session, never from the request body or the model (B6, I4).
- Routing is per turn and invisible to history (I1 to I3). One agent answers each turn (I14).
- No semantic cache (I10) and no runtime answer self-check (I9). Both are deliberately out of v1.
- All times are UTC (C8). One uvicorn worker (H5). Abuse counters are in memory (F15).
- KB ingestion is a background job in a child process, one job at a time. `ingest(document_id, file_path, file_type, settings)` reads from disk. The backend checks duplicates by hash before calling it (G3, G5, G6, I12).
- When a decision changes, update the file that owns it and keep rule IDs stable. When the app version changes, update the Version line in every spec file.

## Code and commit conventions

- Commits: one per plan step. The message format is `[STAGE_NAME] short description`, where STAGE_NAME is the step id and title from `plan.md`, for example `[1.2 Database rules] add CHECK constraints and partial unique index`. The description is lowercase, imperative, with no trailing period.
- Comments: keep them to a minimum. A single-line comment is allowed where the reason is not obvious. No docstrings, no multi-line comment blocks, no commented-out code. Function and variable names must be descriptive enough to need no comment.
- Types: strict and complete. Python: annotate every parameter and return value, run the type checker in strict mode (mypy --strict or pyright strict), no `Any` without a one-line reason, Pydantic models at every boundary (API payloads, settings, tool arguments, events). TypeScript: `strict` on, no `any`, no non-null assertions, explicit return types on exported functions, and a type for every API payload described in `api.md`.
- Scaffolding: use commands, not hand-written files. For example `uv init`, `uv add`, `uv add --dev`, `uv sync`, `npm create vite@latest`, `npm install`, `alembic init`, `alembic revision --autogenerate`, `npx playwright install`. Never edit dependency lists or lockfiles by hand. Edit generated files minimally.
- CI: a GitHub Actions workflow in `.github/workflows/ci.yml` runs on pushes to `main` only. It runs every kind of test that costs no money and never the evals. When a step introduces a new kind of test, add it to the workflow in the same step.

## Working agreement (autonomous mode)

Work through `docs/spec/plan.md` on your own, step by step, and ask the user only in the cases listed below.

### Start of every session

1. Read `docs/progress.md` and `docs/spec/plan.md`.
2. Continue from the first unfinished step. Do not redo finished steps.
3. If `docs/progress.md` has answers to earlier questions, apply them first.

### The loop for each step

1. Read the step and the rule IDs it cites.
2. Write the tests the step lists first (or alongside the code). Name each test after the rule ID it covers, for example `test_D1_booking_is_atomic`.
3. Implement.
4. Run the step's tests, then `make check`. Fix until green.
5. If the code shows that a spec is wrong or silent, update the owning spec file (keep rule IDs) and log it under "Deviations from spec" in `docs/progress.md`.
6. Commit (one commit per step) and update `docs/progress.md`.

### Definition of done

A step is done only when all of these hold:
- its tests exist and pass;
- every rule ID in scope for the step has a test containing the ID, or an entry with a reason in `tests/rule_coverage_exemptions.md`;
- `make check` is green (lint, strict types, all tests);
- the code follows the conventions above, and any new kind of test is in the CI workflow;
- no test was deleted, skipped, marked xfail or weakened to get green;
- `docs/progress.md` is updated.

A phase is done when every step is done and also:
- `docker compose up` passes the smoke test;
- the rule coverage tool passes for the phase;
- an independent review is done: start a separate subagent that has not seen the implementation. It reads the rules in scope and the tests, and lists every rule whose tests do not really assert it. Fix its findings before moving on.

### Test rules

- Integration tests use real Postgres and Qdrant. Never mock the database.
- Tests never call real model APIs. Use the fake OpenAI-compatible server and deterministic fake embeddings (plan step 6.0).
- Evals use real models and cost money. Run them only at a gate.
- Inject the clock and randomness. Never sleep to test rate limits, slots or expiry.
- Money-critical and concurrency rules (D1, A2) need a concurrent test.

### Decide yourself, then log it in `docs/progress.md`

- Library or tool choices inside the stack above, file layout, naming, test design.
- UI details inside the wireframes (spacing, component choice, wording of error messages).
- Anything the specs leave open that does not change user-visible behavior or a contract.

### Ask the user

- A change to the schema, a rule, or an API contract that the specs do not already cover.
- A new dependency or service outside the stack above.
- Something unspecified where the options differ in what the user sees or does.
- Secrets, real API keys, paid runs, deployment, or any destructive or irreversible action.
- A step still failing after 3 genuinely different attempts.

If a question blocks the current step, ask it and wait. If it does not block, write it under "Needs confirmation" in `docs/progress.md`, continue with independent steps, and present the questions together at the next gate or phase end.

### Gates (stop and ask)

Gate 1 before any real model call (needs the API key in `.env`, model names per role, embedding dimensions). Gate 2 at the end of plan step 6d (approve eval datasets and fixtures). Gate 3 in phase 8 (branding, instance size, domain, SSL). Gate 4 before any paid eval run. Details are in `plan.md`.

### Git

- One branch per phase (`phase-N`), one commit per step (message format in Code and commit conventions), merge into `main` when the phase is done.
- Never push or open pull requests unless the user asks. CI runs on `main`, so it runs when the user pushes it.
- Never commit `.env` or real keys.

## Still open

- AI: reranker provider (implement `rerank/target.py`) and larger eval datasets and fixtures. See the last section of `ai.md`.
- Decided: branding (`wireframes.md` section 1), deployment (`docs/deployment.md`), model names per role (`.env.example`), admin payloads (`api.md`).
