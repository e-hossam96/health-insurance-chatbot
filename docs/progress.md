# Progress

State file for Claude Code. Read it at the start of every session and update it after every step. The rules for using it are in `CLAUDE.md` (Working agreement).

## Status

| Phase | Name | Status | Last step done |
|---|---|---|---|
| 0 | Skeleton and test harness | done | 0.7 |
| 1 | Data model | done | 1.3 |
| 2 | Accounts and access | done | 2.6 |
| 3 | Admin catalog and slots | done | 3.5 |
| 4 | Visits and complaints | done | 4.6 |
| 5 | Chat shell with a stub | in progress | 5.5 |
| 6 | AI package | not started | - |
| 7 | Observability | not started | - |
| 8 | Hardening and demo | not started | - |

Status values: not started, in progress, done, blocked (say why below).

## Next step

Phase 5 close-out: `docker compose up` smoke test, rule coverage for phase 5, and the independent review. Known items for the review:

- F16 server side has no real test. httpx ASGITransport buffers the whole response, so a disconnect cannot be simulated; it needs a test against a live uvicorn server that closes the stream after the `session` event and asserts no `chat_message` rows. The client side of F16 is covered (Vitest and Playwright Stop tests).
- `backend/routes/chat.py` uses `StreamingResponse` with hand-built SSE frames, not the built-in `fastapi.sse` that CLAUDE.md names (step 5.3).
- `packages/chatbot_ai/src/chatbot_ai/stub.py` carries docstrings and comments against the code conventions (step 5.1).

## Needs confirmation

Questions for the user that do not block the current step. Format: `- [phase.step] question (options, your recommendation)`.

- none

## Gates

- [ ] Gate 1 real model calls: API key, model names per role, embedding dimensions
- [ ] Gate 2 eval datasets and fixtures approved
- [ ] Gate 3 branding, instance size, domain, SSL
- [ ] Gate 4 paid eval run approved

## Decisions log

Choices made without asking. Format: `- [phase.step] decision - why`.

- [0.1] Renamed `docs/specs/` to `docs/spec/` - the CLAUDE.md references `docs/spec/`; the files were created as `docs/specs/`.
- [0.1] Removed `[build-system]` from root `pyproject.toml` - it's a workspace root, not a package; avoids the "Expected a Python module" error.
- [0.3] Using `scripts/check.sh` as the task runner instead of a Makefile - Windows has no `make`; the Makefile delegates to the script so CI (Linux) still works.
- [0.4] Added `pyyaml` as a dev dependency for the rule coverage tool.
- [0.5] Used `pydantic-settings` for config (already a FastAPI transitive dependency).
- [0.7] CI `actionlint` test replaced by a Python-based YAML parse test - `actionlint` is not installed locally; the test verifies the same constraints.
- [2.1] Using sha256 for session token hashing - simple, fast, sufficient for opaque tokens.
- [2.5] Rate limit counters use module-level singletons reset via conftest fixture between tests.
- [2.6] Using Tailwind CSS v4 with @tailwindcss/vite plugin - simpler than shadcn for now; will add shadcn components as needed.
- [2.6] Playwright e2e tests defined but run only via `make e2e` (need docker compose stack).
- [5.5] Declared `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `argon2-cffi` and `psycopg2-binary` in `backend/pyproject.toml` with `uv add`, and committed the generated `alembic.ini`, `alembic/README` and `alembic/script.py.mako` - the code used them since phase 1 but they were only installed locally, so a fresh clone could not run.
- [5.5] `react-markdown` with `skipHtml` renders assistant text (F17) - covers lists, bold and links; raw HTML is dropped and `javascript:` links are neutralised by its default URL transform.
- [5.5] `@testing-library/user-event` for typing and clicking in page tests.
- [5.5] The SSE reader is a pure parser (`createSseParser`) that keeps the event name across network chunks; tested at every split point.
- [5.5] Cards live in the transcript next to the turn that produced them, so older cards stay visible and are locked while a turn streams (F13), and are re-enabled after it ends.
- [5.5] Playwright chat specs (`e2e/chat.spec.ts`) mock the API with `page.route` and replay stub-shaped event streams for book, slot taken, complaint, cancel, Stop, and error with Retry. They need only the Vite dev server, so they run in `make check` (`test-e2e-mocked`) and in CI. The stub cannot emit complaint or cancel cards that point at real visits, which is why these specs do not use the live stack. The stack-backed `e2e/auth.spec.ts` stays under `make e2e`.
- [5 housekeeping] Phases 0 to 5 had all landed on `phase-1` and there was no `main`. Created `phase-1` at 0c41fad, `phase-2` at 886c47f, `phase-3` at 58dff7a, `phase-4` at dc102ee, and `main` at dc102ee (end of phase 4, the last finished phase, equal to fast-forward merges of phases 0 to 4). Work continues on `phase-5`. No history was rewritten.
- [5 housekeeping] Added `.gitattributes` with `* text=auto eol=lf` - a Windows clone with `core.autocrlf=true` checked out `scripts/check.sh` with CRLF and bash failed (`set: pipefail: invalid option name`).
- [5.5] HTTP errors from `POST /me/chat` (for example 429 `rate_limited`) show the server's message with Retry; stream `error` events always show "Something went wrong."

## Deviations from spec

Places where a spec file was changed because the code showed it was wrong or silent. Format: `- [phase.step] file, rule or section - what changed - why`.

- [0.1] CLAUDE.md references `docs/spec/` but files were in `docs/specs/` - renamed directory to match.

## Test and tool choices

- pytest 9.2.0 with `importlib` import mode (handles multiple `tests/` directories in workspace)
- Vitest 5.x with jsdom for frontend unit tests
- ruff 0.17.x for Python linting, oxlint for TypeScript/JS
- mypy 2.4.x in strict mode for Python type checking
- tsc with `strict: true` for TypeScript
- prometheus-client 0.26.x for metrics
- React Router v7 for frontend routing
- TanStack Query v5 for data fetching
- Tailwind CSS v4 for styling
- Playwright for e2e tests (mocked chat specs in `make check` and CI; stack-backed specs under `make e2e`)
- react-markdown 10.x for assistant Markdown
