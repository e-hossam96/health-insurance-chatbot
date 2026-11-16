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
| 6 | AI package | done | 6e |
| 7 | Observability | not started | - |
| 8 | Hardening and demo | not started | - |

Status values: not started, in progress, done, blocked (say why below).

## Next step

Phase 7, step 7.1 (metrics) on branch `phase-7`.

## Needs confirmation

Questions for the user that do not block the current step. Format: `- [phase.step] question (options, your recommendation)`.

- [6e] The gpt-6 sol and astra models reject function tools in Chat Completions with any reasoning effort ("use /v1/responses or set reasoning_effort to 'none'", and they do not accept 'none'). The chat role therefore runs gpt-5.5 with reasoning effort none. Options: keep Chat Completions and gpt-5.5 (current, works), or move the tool loops to the Responses API, which unlocks gpt-6.1-sol and gpt-6-astra for chat but changes the ai.md decision and the provider-neutral API shape (I11). Recommendation: keep Chat Completions for v1; the eval run at 8.3 shows whether quality needs more.

## Gates

- [x] Gate 1 real model calls: API key, model names per role, embedding dimensions (2026-11-16)
- [x] Gate 2 eval datasets and fixtures approved (2026-11-16, as drafted)
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
- [6c] (user decision, 2026-11-16) torch and torchvision come from the CPU-only PyTorch index (`torch 2.15.0+cpu`), so no CUDA packages are installed and the backend image stays much smaller. The index is declared in the root `pyproject.toml` as `[[tool.uv.index]] pytorch-cpu` with `explicit = true`, and `[tool.uv.sources]` in `chatbot_ai` pins only those two packages to it; the dependency lines and the lockfile came from `uv add`.
- [5.3] (user decision, 2026-11-16) When the first turn of a new chat stores nothing (stream error or client disconnect), the chat route deletes that `chat_session` row in its `finally`, inside a shielded cancel scope so it also runs on disconnect; a failed turn in an existing session keeps the session. The frontend then drops the session id and returns to /chat, so Retry or a resend starts a new session.
- [5.3] (user decision, 2026-11-16) A chat message over 1000 characters returns 422 `validation_error`, not 429: waiting does not help, so it is validation, not a rate limit. api.md updated.
- [Gate 1] (2026-11-16, user: "use your recommended models") Models in `.env`: chat `gpt-5.5` (reasoning effort none), router and rewrite `gpt-6-luna` (reasoning effort none), embedding `text-embedding-3-small` at 1536 dimensions, judge `gpt-6.1-sol` (reasoning effort low). Chosen from the key's model list and OpenAI's current models and pricing pages. gpt-6.1-sol was the first pick for chat but rejects tools in Chat Completions; gpt-6.1-terra was avoided because OpenAI's pages disagree on its API availability.
- [Gate 1] Added `AI_<ROLE>_REASONING_EFFORT` (chat, router, rewrite, judge; omitted from requests when unset) and `AI_ROUTER_MAX_OUTPUT_TOKENS` (512) and `AI_REWRITE_MAX_OUTPUT_TOKENS` (1024). The first real run showed that reasoning tokens count against `max_completion_tokens`, so the old fixed caps of 20 and 200 failed every router and rewrite call; a failed router then silently sent every turn to the responder.
- [Gate 1] `scripts/smoke_real_models.py` (`make smoke-models`, paid, never in `make check` or CI) runs the six starter-card routings, a knowledge turn on the DOCX fixture with real embeddings, and a booking turn with fake ports. Gate 1 result: routing 6/6; the knowledge turn retrieved the pre-authorization table and answered "3 working days"; the booking turn called list_specialties then recommend_doctors, showed 3 doctor cards in the D5 order and named each option with its time in UTC. The 6e real-model smoke run is done.
- [Gate 1] Backend tests never read the real AI settings: an autouse fixture makes `load_ai_settings` return None, and tests inject fake-server settings.
- [6 review] Independent review findings fixed: the C7 boundary (a slot at exactly now is not offered); D5 ties broken by slot id; G8 against real kb_document rows; G2 exact-limit upload and the nginx limit; G3 duplicate starts no job; G4 dense and BM25 vectors on every point and a matching content_hash; G5 one job at a time in a child process with 'processing' visible and the upload returning while the job is blocked; G9 points, then file, then row, and the row kept when the file cannot be removed; I4 and I14 shared blocks for every agent and the knowledge answer request; I6 reranker inputs, order and top K inside a real turn; I7 identical text in two documents stored twice and shown once; I8 the passing-score and no-score cases; I11 a wider model-name scan; I12 the killed child's pid and exit code; I13 the retrieval-mode and rerank-provider switches through full turns. Weak assertions were replaced. `KbJobRunner.completed` now holds `JobRecord`s with the child pid and exit code.
- [6 review] ai.md: the router's 6-row window is counted over all stored rows, tool rows included; tool rows are then left out of the router request.
- [6 review] The AP1 polling test fakes only `setInterval`/`clearInterval`; `shouldAdvanceTime` let real time trigger extra polls under load and made it flaky.
- [6e] The chat route runs the real `run_turn` with the SQL ports (bound to the acting profile and the injected clock), the app-wide `RoleClients` (closed at shutdown) and `AISettings`. `TurnRequest.profile.location_name` is now the profile's location name. `app.state.turn_runner` still overrides the runner, which the phase-5 chat tests use to keep running the stub; without AI settings a turn fails with the `error` event (and the empty new session is removed).
- [6e] The walkthrough test (`backend/tests/test_walkthrough.py`) runs on the fake server with real Postgres and Qdrant: a booking turn with two tool rounds and doctor cards carrying the seeded slot ids, the card click (POST /me/visits), then a knowledge question answered from a ready KB document with the synthetic `search_kb` rows. It checks the SSE events, the stored rows, the label, the history the agent receives (I4), and the F11 transcript.
- [6d] The knowledge agent runs rewrite, then embed (all queries in one call, dense plus BM25), one Qdrant search per query, RRF merge (k = 60) to `AI_FUSED_K`, dedupe by point id and then by `content_hash`, rerank to `AI_CONTEXT_K`, grounding, and answer (I6, I7). Each search filters on the ready document ids from a new `KnowledgePort.ready_document_ids()` (G8), because a document's points can exist while it is 'processing' or before a re-index has cleared them. `Ports` now has `scheduling`, `complaints` and `knowledge`.
- [6d] `AI_RETRIEVAL_MODE` dense or sparse queries a single named vector; hybrid sends both prefetches and fuses server-side with RRF (I13). With `AI_QUERY_COUNT=1` the rewrite schema has no `alternates`. A rewrite failure searches with the raw message.
- [6d] Grounding (I8): no ready documents, no collection, no candidates, or a best rerank score below `AI_RERANK_MIN_SCORE` gives "I couldn't find that in the documents." with no chat call. With the passthrough reranker the scores are None, so the threshold never applies, as ai.md says.
- [6d] Retrieval is stored as an assistant row with a synthetic `search_kb(query=<standalone>)` call and a tool row `{"excerpts": [{"section", "content"}]}` (I6). The answer model gets the excerpts in its system prompt, each labelled with its breadcrumb.
- [6d] `TargetReranker.rerank` raises `NotImplementedError("Reranker provider not chosen yet")`; with `AI_RERANK_PROVIDER=target` a knowledge turn fails with the error event until it is implemented.
- [6d] `RoleClients` also holds one lazily created Qdrant client and closes it with the model clients. `AgentResult.stages` carries rewrite, embed, search and rerank times into `Done.timings`.
- [6d] Draft eval datasets for Gate 2: `retrieval.jsonl` (16 questions with `expected_phrases` and the expected document), `answers.jsonl` (8 answerable with `must_include`, 4 unanswerable), `tools.jsonl` (7 scenarios, including scheduling, then knowledge, then scheduling). `routing.jsonl` from 6a (26 items). Schemas are in `chatbot_ai/evals/schemas.py`, and a test checks that every phrase and fact exists in the fixtures. The retrieval, answers and tools suites themselves are built with the ablation in 8.3.
- [6c] Added `docling` and `fastembed` to `chatbot_ai` (both named in the stack and ai.md). Both are imported lazily inside the parse and BM25 functions, so the API process starts without loading them.
- [6c] Docling runs with OCR off (`PdfPipelineOptions(do_ocr=False)`), so a scanned PDF yields no text and fails with "No extractable text (scanned PDFs are not supported)" (ai.md). Docling reports every PDF section header at level 1, so the breadcrumb depth comes from the heading number when there is one ("2.1 Outpatient care" is level 2), else from Docling's level. Document titles are left out of breadcrumbs. A table that Docling splits at a page break becomes two tables, each with the header, and each is chunked on its own.
- [6c] Token budgets are estimated as characters / 4 (no tokenizer dependency). Text under one breadcrumb is merged up to `AI_CHUNK_MAX_TOKENS`; an over-long paragraph is split at sentence ends, then at words. Tables render as Markdown; a table over the budget is split into row groups with the header repeated.
- [6c] Collection name `kb_<embedding model slug>_<dimensions>` with a payload index on `document_id`. Point ids are UUIDv5 of `document_id:chunk_index`. Sparse vectors come from fastembed `Qdrant/bm25` (queries use `query_embed`) with the collection's IDF modifier. If the upsert fails, the document's points are deleted.
- [6c] Public sync API in `chatbot_ai.ingest`: `ingest`, `delete_document`, `ensure_collection`, plus async `delete_document_async` and `ensure_collection_once` for the API process. `IngestResult` carries `chunk_count`, `table_chunks` and the parse, chunk, embed and upsert timings.
- [6c] `backend.kb_jobs.KbJobRunner` keeps one asyncio queue and one worker, so one job runs at a time. Each job runs `ingest` in a `spawn` child process; the parent waits up to `INGEST_TIMEOUT_S`, then kills it and stores "Ingestion timed out after N s". Any exception text becomes `error_message`. At startup it resets 'processing' to 'uploaded' and queues every 'uploaded' row in id order (G7). If a document is deleted while its job runs, the finished job deletes the points again.
- [6c] The backend runs without AI settings until Gate 1: `create_app` loads `AISettings` from the environment and, if they are incomplete, logs a warning, skips `ensure_collection`, and KB jobs fail with "The AI service is not configured (AI settings are missing)." Compose passes `.env` to the backend when it exists.
- [6c] Upload contract: raw request body with `?filename=` (see api.md, Admin KB documents), because Starlette's multipart parser reads the whole file before the handler runs. A `Content-Length` over the limit is refused up front; otherwise bytes are counted while streaming. New error code `kb_index_unavailable` (503) when Qdrant fails during delete. Re-index from 'uploaded' or 'processing' is a no-op.
- [6c] KB originals are stored as `<uuid>.<ext>` in `KB_STORAGE_DIR` (`/data/kb` on the `kb_data` volume in compose; `./data/kb` locally). nginx `client_max_body_size` is 11m so that the backend, not nginx, answers an over-limit upload with the 413 message.
- [6c] The backend image downloads the Docling layout and table models and the BM25 model at build time into `/app/models` (`HF_HOME`, `FASTEMBED_CACHE_PATH`).
- [6c] The AP1 page polls every 3 s while a row is 'uploaded' or 'processing', confirms deletes inline (no browser dialog), checks the size limit before sending, and names the file and reason for each rejected upload. Playwright `e2e/kb.spec.ts` mocks the API like the chat specs and runs in `make check`.
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
- [6 close-out] plan.md, phase 6 scope and tests/rule_scope.yaml - F7 moved from phase 6 to phase 7 only - phase 6 listed "F5 to F9", but F7 is the Langfuse session id, which step 7.4 builds and phase 7 already lists.
- [6c] CLAUDE.md (Scaffolding: never edit dependency lists by hand) - the `[[tool.uv.index]]` block with `explicit = true` and the two `[tool.uv.sources]` lines for torch were written by hand, because `uv add --index` cannot mark an index explicit and a non-explicit index captures other packages (it broke the resolve). The dependency entries and `uv.lock` were still produced by `uv add`.

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
