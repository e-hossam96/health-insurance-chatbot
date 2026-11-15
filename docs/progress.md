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
| 5 | Chat shell with a stub | done | 5.5 |
| 6 | AI package | in progress | 6b |
| 7 | Observability | not started | - |
| 8 | Hardening and demo | not started | - |

Status values: not started, in progress, done, blocked (say why below).

## Next step

Phase 6, step 6c (ingestion and KB admin) on branch `phase-6`.

## Needs confirmation

Questions for the user that do not block the current step. Format: `- [phase.step] question (options, your recommendation)`.

- [5.3] A message over 1000 characters gets 429 `rate_limited` today (F15 lists it among the abuse limits). api.md uses 429 for rate limits with Retry-After and 422 `validation_error` for validation. Options: keep 429 `rate_limited` without Retry-After (current), or 422 `validation_error`. Recommendation: 422, because waiting does not help and the client should not retry. The tests pin the current 429 until you decide.
- [5.3] The first message creates the `chat_session` row before the turn runs (F1), so a first turn that fails (F3) or is stopped (F16) leaves an empty session that shows in the sidebar as "New chat" with no subtitle. Options: keep it (current), delete the row when a first turn stores nothing, or hide sessions with no messages from GET /me/sessions. Recommendation: delete the row when a first turn stores nothing, so F16's "store nothing" also covers the session.

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
- [5.3] F16 server side is tested against a live uvicorn server in a thread (`backend/tests/test_chat_disconnect.py`): read the first token, close the connection, wait on a cancellation event with a deadline, assert no `chat_message` rows. Proven to fail when the turn is shielded from cancellation.
- [5.3] The turn runner is injected through `app.state.turn_runner` (`TurnRunnerDep`, default `run_stub_turn`; `TurnRunner` type in `chatbot_ai.interface`). The F16 test injects a turn that hangs after one token; phase 6e swaps in the real `run_turn` here.
- [5.3] Disconnect cancellation relies on Starlette: uvicorn 0.54 reports ASGI spec 2.3, so the streaming response listens for `http.disconnect` and cancels the generator, which cancels the turn. The route no longer swallows `CancelledError` and no longer polls `is_disconnected()`. If a uvicorn upgrade moves to spec 2.4 (disconnect seen only on the next write), the F16 test fails and the route needs its own disconnect watcher.
- [5.3] The chat route streams with `fastapi.sse` (`EventSourceResponse`, `ServerSentEvent`; FastAPI 0.163). The endpoint body is the generator and the 200 headers go out before it runs, so everything that can fail with a status code (length cap, rate limits, profile, session create or validate, history load) moved into the `prepare_turn` dependency. FastAPI also adds a `: ping` keep-alive comment every 15 s, which the frontend parser ignores.
- [5 conventions] Removed every docstring (41 files) and collapsed multi-line comment blocks to one line. `tests/test_conventions.py` guards it in `make check`: `ast` for docstrings and `tokenize` for runs of standalone comment lines in Python, and a string-aware scan for `/*` and runs of `//` lines in the frontend `.ts` and `.tsx`. It has its own detector tests, and failed on a deliberate docstring and block comment before they were reverted. `backend/alembic/` is excluded because Alembic generates those files (edit generated files minimally).
- [6b] The Port Protocols moved to `chatbot_ai/tools/ports.py` (re-exported from `interface.py`) and return Pydantic models from `tools/models.py` (`NamedRef`, `ClinicInfo`, `DoctorInfo`, `DoctorCard`, `VisitCard`, `VisitInfo`, `ComplaintInfo`) instead of dicts. Ports return data only. Each tool in `tools/registry.py` turns that data into the JSON text the model reads and, for propose tools, the `Cards` payload. Port methods: `list_locations`, `list_specialties`, `search_clinics`, `search_doctors`, `available_slots`, `recommend_doctors`, `my_visits`, `scheduled_visits`, `my_complaints`, `eligible_visits`; none writes (D9).
- [6b] Tool arguments are Pydantic models with `extra="forbid"`, so a model-supplied `profile_id` is rejected and reported back to the model before any port is called (B6). Ids are typed integers; ports raise `InvalidArgument` for unknown catalog ids, which the tool returns to the model as `{"error": ...}` (I5).
- [6b] Card limits: `recommend_doctors` and `get_availability` show at most 3 cards; `get_availability` also lists up to 10 slot times as text. `recommend_doctors` gives one card per doctor (that doctor's earliest available future slot), ranked by profile location (or the given location), then earliest slot, then slot id (D5); the SQL port uses `DISTINCT ON`.
- [6b] The tool loop runs up to `AI_MAX_TOOL_ROUNDS` rounds that offer tools, then one final request without tools, so the reply is always text. Tool calls returned in that final request are not executed. A call to a tool the current agent does not have returns an "is not available here" error and runs nothing (I4, I14). Cards from the last propose tool are emitted once, after the final reply's tokens (F12).
- [6b] Tool results are stored as `tool` rows with the JSON the model saw, including the offered options, so the model can name them later (F9). The F12 backend test was corrected to check that no stored row holds the `cards` event payload, instead of checking that no row mentions a doctor's name.
- [6b] The backend's ports are `backend.ai_ports` (`SqlSchedulingPort`, `SqlComplaintsPort`, `make_ports(db, profile_id, profile_location_id, clock)`), tested against real Postgres. The chat route still runs the stub until 6e.
- [6a] `AISettings` (pydantic-settings) has `AI_<ROLE>_BASE_URL`, `_API_KEY`, `_MODEL` for chat, router, rewrite, embedding, rerank and judge (I11). Base URLs default to OpenAI's, keys fall back to `OPENAI_API_KEY`, and models have no default, so a role without `AI_<ROLE>_MODEL` raises `RoleNotConfigured` when first used. Global `AI_TIMEOUT_S` (60) and `AI_MAX_RETRIES` (2). `AI_<ROLE>_OUTPUT_TOKEN_PARAM` (`max_completion_tokens` default, or `max_tokens`) for the chat-completion roles is the one provider difference handled in `clients.py`.
- [6a] Added `AI_ROUTER_HISTORY_ROWS` (default 6) so the I1 window size is config, not a literal.
- [6a] The router sees only the conversation text in its window (user rows and final assistant rows); tool rows and tool-call-only rows are dropped, because the router sends no tools. The window is the last 6 rows cut to start at the first user row; with no user row the window is empty.
- [6a] Any router failure (API error, rate limit, unparseable or out-of-enum reply) gives no intent: the turn falls back to the responder and no `Intent` event is sent, so the backend's `needs_label` stays true and the next successful turn sets the label (F6, I1).
- [6a] `run_turn(req, ports, settings, clients=None, agents=None, clock=time.monotonic)` lives in `chatbot_ai.orchestrator` and is exported from the package; the placeholder in `interface.py` was removed. `clients` lets the backend reuse one `RoleClients` per process; `agents` lets tests inject a registry. An intent whose agent is not registered raises `AgentNotAvailable` (scheduling, complaints and knowledge arrive in 6b and 6d).
- [6a] `Done.usage` sums the router call and the agent's calls.
- [6a] Prompts are Markdown files in `chatbot_ai/prompts/`: `shared_persona`, `shared_rules` (F5, F8, F17, C8, foreign tool calls, D9, I14), `shared_profile`, `router` and one per agent. `agent_system_prompt` joins the shared blocks, the profile block and the agent's prompt (I4).
- [6a] Routing eval scaffold: `python -m chatbot_ai.evals routing [--smoke] [--set KEY=VALUE]` writes a Markdown and a JSON report (config snapshot without keys, accuracy, per-class recall, confusion matrix, mistakes, latency) to `chatbot_ai/evals/reports/` (git-ignored). `--langfuse` and the other suites report "not implemented yet". The draft `datasets/routing.jsonl` has 26 items (six starter cards, follow-ups with history, off-topic, mixed) and waits for Gate 2; the target is about 60.
- [6.0] Test helpers live in a top-level `testkit/` package (importable through the root `pythonpath`), because the fake OpenAI server uses FastAPI and `chatbot_ai` must hold no web-framework code. It is type-checked with mypy strict and scanned by the conventions guard.
- [6.0] `testkit.fake_openai` is a real HTTP server (uvicorn in a thread, `testkit.live_server`) that the OpenAI SDK talks to. Replies are scripted in a FIFO queue, optionally per model (router vs chat). It serves streaming and non-streaming Chat Completions with tool calls, `json_schema` structured outputs checked against the request schema, and `include_usage`. Embeddings are deterministic feature-hashing vectors (`testkit.embeddings.hash_embedding`), float or base64. Every request is recorded for call-count assertions (I9, I10, I8 grounding).
- [6.0] `testkit.fake_ports` implements `SchedulingPort` and `ComplaintsPort` over an in-memory catalog with the profile bound in. 6b replaces the dict returns with typed results and the real SQLAlchemy ports.
- [6.0] Qdrant tests use the real compose/CI server through `testkit.qdrant` (one throwaway collection per test). The client (qdrant-client 1.20) is newer than the pinned server image (v1.13.6), so `check_compatibility=False`; hybrid dense + sparse RRF queries are verified against the real server.
- [6.0] Added `openai` and `qdrant-client` to `chatbot_ai` (both in the stack).
- [6.0] `scripts/generate_kb_fixtures.py` writes the synthetic KB fixtures to `chatbot_ai/evals/kb_fixtures/` with the standard library only (raw PDF objects and a minimal DOCX zip), so no PDF or Word writer dependency outside the stack was added. Output is byte-for-byte deterministic and committed; a test fails if the committed files are stale. Fixtures: `policy_handbook.pdf` (headings, a 5-row table and a 60-row fee table across pages with the header repeated), `member_guide.docx` (Heading 1/2 styles, a 4-row and a 45-row table) and `scanned_notice.pdf` (a page with shapes and no text, for the G-rule scanned-PDF error). The first Docling parse of them happens in 6c.
- [6.0] Ruff treats the repo root as first-party (`src` includes `.`), so `testkit` and `scripts` imports sort with the project's own modules.
- [5 review] Card actions (book, cancel, complaint) given another user's or a missing chat session now return 404 `not_found` instead of 403, matching api.md (404 "not found, or not yours").
- [5 review] Any exception from the turn runner (not only the stub's) rolls back and sends the `error` event (F3, ai.md section 1). Proven by a turn that fails after streaming a token and by a turn whose rows fail to insert.
- [5 review] Stored tool results are capped at 8000 characters plus the `[truncated]` placeholder (`cap_stored_tool_result`, F4); replayed old results stay capped at 500.
- [5 review] `to_openai_messages` in `chatbot_ai.context` turns history rows into Chat Completions messages (F10); phase 6 uses it.
- [5 review] Vitest runs with `TZ=Asia/Tokyo` and Playwright with `timezoneId: America/New_York`, so a local-time formatter fails the C8 tests even on UTC CI runners.
- [5 review] Independent review findings fixed: exact row and transcript assertions (F3, F11), live history capture and the 40-row window (F4, F10), page load and New chat (F1), card actions with another user's session (F2), failed and per-user rate limits, UTC date rollover, admin exemption past 100, the 1000-character boundary, and the auth limits keyed by proxy IP (F15), the aborted request on Stop (F16), cards gone after reopening (F12), and the locked open complaint form (F13).
- [5 review] The rule coverage scan now includes `frontend/e2e` and only counts an ID that is not part of a longer word (`UTF8` no longer covers F8).
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
- openai 3.51 (Chat Completions and embeddings), qdrant-client 1.20 against Qdrant server 1.13.6
- Fake OpenAI-compatible server in `testkit/` (FastAPI + uvicorn in a thread) for every model call in tests
