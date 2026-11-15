# Health Insurance Chatbot - Development Plan

Version: v0.1.0

Companion to `CLAUDE.md` (the working agreement), `rules.md`, `schema.dbml`, `wireframes.md`, `api.md` and `ai.md`. The work is split into phases of vertical slices. Each phase ends with something runnable. Each step names the tests that prove it. A step is done only when those tests pass (see "Definition of done" in `CLAUDE.md`).

## How to read a step

`N.M Title - what to build. Tests: what must be proven.` Rule IDs in a step or phase header are the rules in scope. Every in-scope rule needs at least one test whose name or docstring contains its ID (for example `test_D1_booking_is_atomic`), unless it is listed in `tests/rule_coverage_exemptions.md` with a reason.

## Test conventions

- Commands (create in step 0.3): `make test` (all fast tests), `make check` (lint, types, `make test`), `make e2e` (Playwright against the Compose stack), `make evals` (real models, paid, gates only).
- Backend: pytest, httpx, real Postgres and Qdrant containers. Never mock the database.
- Frontend: Vitest and Testing Library. Playwright for the flows named in the steps.
- AI: no real model calls in tests. Use the fake OpenAI-compatible server (step 6.0) and deterministic fake embeddings.
- Time, randomness and rate-limit windows are injected (a clock fixture), never slept.
- CI: `.github/workflows/ci.yml`, main only, never runs evals. Each new kind of test is added to it in the same step.
- Claude Code may substitute equivalent tools and logs the choice in `docs/progress.md`.

---

## Phase 0 - Skeleton and test harness

Rules in scope: none (H3 and H4 are completed in phase 7).

- **0.1 Workspace.** Scaffold with commands (`uv init`, `uv add`, `npm create vite@latest`), with no hand-written dependency files. uv workspace root, `backend/`, `packages/chatbot_ai/`, `frontend/` (Vite, TypeScript), `observability/`, `scripts/`, lockfile. Tests: `uv sync` succeeds; smoke tests import the backend app and `chatbot_ai`; the frontend test runner runs one trivial test; type checks run in strict mode (a deliberate type error fails `make check`, verified once and reverted).
- **0.2 Compose.** Services postgres, qdrant, backend, frontend (nginx serving the build and proxying the API, with `client_max_body_size` from G2 and SSE buffering off). Tests: a smoke script brings the stack up, `GET /health` returns 200 through the frontend proxy, the index page loads, then the stack goes down.
- **0.3 Commands.** The Makefile (or equivalent) targets above; `make evals` prints "not available before phase 6". Tests: each target runs on a clean checkout.
- **0.4 Rule coverage tool.** `scripts/rule_coverage.py` reads rule IDs from `rules.md` (B to I) and `schema.dbml` (A), scans test files for IDs, and reads `tests/rule_scope.yaml` (phase to rule IDs, created from this plan) and the exemptions file. It fails if a completed phase has an uncovered, non-exempt ID. Tests: unit tests on fixture files for covered, uncovered, exempt and unknown IDs.
- **0.5 Config.** One settings module, `.env.example` (git-ignored `.env`), required values fail clearly. Tests: defaults load; a missing required value raises a readable error.
- **0.6 HTTP metrics.** Prometheus middleware with the route template as label, never the raw path, and `/metrics` mounted. Tests: call a route with a path parameter, scrape `/metrics`, assert the label is the template.
- **0.7 CI workflow.** `.github/workflows/ci.yml`, triggered by pushes to `main` only, with Postgres and Qdrant services, running `make check` and the Compose smoke script. Later steps add Playwright (step 2.6) and any other new kind of test. Tests: `actionlint` passes; a test parses the workflow and asserts the only trigger is a push to `main` and that no job runs `make evals`.

## Phase 1 - Data model

Rules in scope: A1 to A6, B12, B13.

- **1.1 Models and migration.** SQLAlchemy models and one Alembic migration from `schema.dbml`. Tests: migrate up on an empty database; introspection finds all 15 tables, 7 enums and the foreign keys; migrate down then up.
- **1.2 Database rules.** The A-items in the migration. Tests, one per item: a slot at 10:30 is rejected (A1); two active visits on one slot are rejected, and a cancelled visit frees the slot (A2); `file_size_bytes = 0` is rejected (A3); "Cairo" and "cairo" collide for location, specialty and username (A4); cascade and restrict behave as listed (A5); timestamps are timestamptz (A6).
- **1.3 create_admin.** Script that hashes with argon2 (minimum 8 characters), inserts the account (role admin) and its profile (B12, B13). Tests: creates both rows; stored hash is argon2 and not the password; duplicate username fails; short password fails.

## Phase 2 - Accounts and access

Rules in scope: B1 to B6, B8 to B12.

- **2.1 Sessions.** Token generation, only the hash stored, 7-day expiry, purge on login or startup (B10, B12). Tests: the raw token is never in the database; an expired session is rejected; logout deletes the row; purge removes only expired rows.
- **2.2 Auth endpoints.** signup, login, logout, `GET /auth/me`, `POST /auth/mode` (B1, B5, B10, B11). Tests: signup cannot set a role; usernames are case-insensitive; wrong user and wrong password give the same message; the cookie is HttpOnly, Secure and SameSite=Lax; state-changing routes reject non-JSON; a user cannot set mode admin.
- **2.3 Authorization.** `/admin/*` needs role and mode admin, `/me/*` needs mode user (B8, B11). Tests: a parametrized matrix generated from the app's registered routes, so a new route cannot skip it; unauthenticated gets 401, wrong role or mode gets 403.
- **2.4 Profile.** `GET /locations`, `POST /me/profile` (B2 to B4). Tests: one profile per account; the location must exist; no update or delete route exists (B4); admins have a profile and skip onboarding; there is no password reset route (B9).
- **2.5 Auth rate limits.** Sign-up 5 per hour per IP, failed logins 10 per 15 minutes per IP and username (F15), with `Retry-After`. Tests: with an injected clock, the limit trips at the threshold and resets after the window.
- **2.6 Frontend.** `/signup`, `/login`, `/onboarding`, header, mode toggle, route guards and redirects (wireframes sections 2 to 4). Tests: Vitest for form errors and a guard redirect table; Playwright for signup, onboarding and chat placeholder, admin login to `/admin/kb`, and the mode toggle.

## Phase 3 - Admin catalog and slots

Rules in scope: C1 to C6.

- **3.1 Catalog API.** CRUD for locations, specialties, clinics, doctors, and `PUT /admin/clinics/:id/specialties`. Specify the admin payloads in `api.md` as you build. Tests: duplicate names collide case-insensitively with a friendly error (A4); delete shows cascade counts; delete is blocked by visit history with `has_history` (A5); a doctor needs a clinic that has a linked specialty.
- **3.2 Slots API.** Manual add, remove (available only), month view (C1 to C4). Tests: only on-the-hour starts between 9 and 16 UTC; a duplicate is rejected; a booked slot cannot be removed.
- **3.3 Auto-fill.** Per doctor, from now to the end of the current month (C5, C6). Tests: expected counts; past hours skipped; running twice creates nothing the second time; current month only, including on the last day; the "nothing to create" result.
- **3.4 Seed script.** Locations, specialties, clinics, doctors, sample users, slots via auto-fill. Tests: idempotent on a second run; all seeded slots are on the hour between 9 and 16.
- **3.5 Frontend AP2 and AP3.** Tests: Vitest for forms and error mapping; Playwright for clinic, doctor, then auto-fill, and the slot grid showing the result.

## Phase 4 - Visits and complaints

Rules in scope: B7, D1 to D4, D6 to D8, E1 to E6, F14.

- **4.1 Booking.** `POST /me/visits {session_id, slot_id}` (D1, D6, D7). Tests: two concurrent requests on one slot give exactly one 201 and one 409 `slot_taken`; a past slot is rejected; the 4 static messages are written with the correct synthetic `book_visit` shape; a session that is not the requester's is rejected (F2); a failure leaves no messages behind.
- **4.2 Cancel.** `POST /me/visits/:id/cancel` (D2, D8). Tests: only own, scheduled visits; the slot becomes available again; with `session_id` the 4 static messages are written, without it none are; another user's visit gives 404.
- **4.3 Complete.** Admin only (D3). Tests: scheduled to completed is allowed; completed and cancelled are final; admins cannot cancel.
- **4.4 Complaints.** File (E1, E2, E6), reply and close (B7, E3 to E5). Tests: only on the requester's completed visit; one per visit; description required; static messages written; only admins reply; a reply does not change status; replies on a closed complaint are rejected.
- **4.5 Lists.** `/me/visits`, `/me/complaints` (admin replies shown as a thread), admin lists with `{items, total}`, `limit`, `offset` and filters (D4). Tests: ordering, filters, pagination bounds, and no leakage of other users' rows.
- **4.6 Frontend.** Drawer (F14), AP4, AP5. Tests: Vitest for status badges and confirm dialogs; Playwright for admin completes a visit, drawer shows it, drawer cancel works, admin replies, user sees "Support team".

## Phase 5 - Chat shell with a stub

Rules in scope: C8, F1 to F4, F10 to F13, F15 to F17.

- **5.1 AI interface and stub.** In `chatbot_ai`: `TurnRequest`, `TurnEvent`, the Port Protocols and `run_turn` as in `ai.md` section 1, plus a `StubAgent` with scripted scenarios (text only, tool call plus cards, error, slow stream). Tests: contract tests on event types and order for each scenario.
- **5.2 Context builder.** Last 40 rows, trimmed to start at a user row, never splitting a tool call from its result, old tool results truncated (F4, F10). Tests: table-driven edge cases, including a cut that would land between a call and its result.
- **5.3 Chat endpoint.** `POST /me/chat` with SSE events from `api.md` (F1 to F3, F12, F15, F16). Tests: event order; all rows stored in one transaction at `done`; an error stores nothing; a client disconnect cancels the turn and stores nothing; the session is created on the first message; another user's `session_id` gives 404; rate limits (6 per minute, 100 per day with admins exempt, 1000 characters) with an injected clock; the `intent` event appears only when the session has no label yet (F6).
- **5.4 Sessions API.** List (newest `last_message_at` first), messages (user rows and final assistant rows only, F11). Tests: ordering and filtering.
- **5.5 Chat frontend.** Layout, sidebar with intent labels, starter cards, fetch-based stream reader, Markdown without raw HTML (F17), Stop and Retry, locks (F13), the three card types with every state, static messages appended, UTC suffix (C8). Tests: Vitest for the stream parser, the label map and "a script tag is not rendered"; Playwright against stub scenarios for book, slot taken, complaint, cancel, Stop, and error with Retry.

## Phase 6 - AI package

Rules in scope: B6, C7, D5, D9, F5 to F9, G1 to G11, I1 to I14 (I9 and I10 by call-count assertions or exemption).

- **6.0 Test infrastructure.** A fake OpenAI-compatible server (chat completions with streaming, tool calls, JSON-schema outputs and usage; embeddings with deterministic hash vectors), fake ports, a Qdrant fixture, and a script that generates synthetic PDF and DOCX fixtures with tables. Tests: the server's own tests; the OpenAI SDK talks to it.
- **6a Routing.** Settings and clients per role (I11), classifier (I1), responder, orchestration with `needs_label` (I2, I3, F6). Tests: scripted classifications map to the right agent; the router call is absent from `new_rows`; a classifier failure falls back to the responder with no `Intent` event and the label is set by the next successful turn; the 6-row window starts at a user row; the routing eval scaffold runs on a draft dataset.
- **6b Scheduling and complaints.** Agents, tools and the backend's SQLAlchemy ports (I4, I5, D5, D9, C7, B6, F5, F8, F9, I14). Tests: availability tools return only available future slots; ranking follows D5; model-supplied arguments cannot carry a profile id; the tool registry has no write tool; cards match the shapes in `api.md`; the loop stops at the round limit; prompt blocks contain the F5, F8, F9 and foreign-tool-call notes; cross-agent scenarios (scheduling, knowledge, scheduling) call only the current agent's tools.
- **6c Ingestion and KB admin.** `ensure_collection`, parse with Docling, chunking, embedding, upsert, delete, child process with timeout kill (G1 to G11, I12, B7). Tests: tables stay whole or split with the header repeated; breadcrumbs present; no empty chunks; deterministic ids make re-ingest idempotent; a file with no text fails with the scanned-PDF message; an upload over the limit gives 413 and the partial file is removed; the same hash gives 409; status transitions; startup recovery resets `processing`; delete order; a slow parser is killed at the timeout; Playwright for the AP1 upload flow.
- **6d Knowledge pipeline.** Rewrite, hybrid search, merge, dedupe, rerank interface with passthrough and the `TargetReranker` placeholder, grounding, answer (I6 to I10, I13, G8). Tests: RRF and dedupe unit tests; with fake embeddings the fixtures return the expected chunks; below-threshold grounding returns the fixed reply and the fake server sees no chat request; only ready documents are searchable; the config switches change behavior; no verifier call is made (I9); the synthetic `search_kb` rows are recorded. The eval datasets are drafted here and wait for approval (gate 2).
- **6e Integration.** Replace the stub with the real `run_turn`. Tests: the walkthrough scenario from the design discussion end to end on the fake server (turns, the card click, the knowledge question), asserting the stored rows, the events and the F11 transcript; a real-model smoke run only at gate 1.

## Phase 7 - Observability

Rules in scope: F7, H1 to H9.

- **7.1 Metrics.** Build metrics from the `Done` timings and events (H2 to H4). Tests: after a turn on the fake server, `/metrics` has the expected series and only fixed label sets; a cancelled turn counts as `cancelled`; the ingestion gauge moves.
- **7.2 Exposure.** Through the frontend nginx, `/metrics` is blocked while the internal scrape works (H6); SSE passes through token by token. Tests: the external request is refused; a streamed turn through nginx delivers tokens incrementally.
- **7.3 Prometheus and Grafana.** Provisioning, Postgres exporter, Qdrant scrape, 15-day retention, four dashboards (H1, H7 to H9). Tests: config validated with `promtool`; after startup all targets are up; Grafana lists the four dashboards through its API.
- **7.4 Langfuse.** One trace per turn with a span per stage, session id `chat-<id>` (F7). Tests: session id formatting; tracing is a no-op without keys; with the SDK's test mode or a local exporter, a turn produces the expected spans.

## Phase 8 - Hardening and demo

Rules in scope: every rule not yet covered.

- **8.1 End to end.** Playwright for the full scenario, both branches (specialty available, and not available).
- **8.2 Security pass.** The complete B8 matrix, cookie flags, markdown XSS, no id leakage in errors. Tests: one automated test per item.
- **8.3 Evals.** Run the ablation and write `docs/evals/v0.1.0.md` (gate 4: paid).
- **8.4 Docs and demo.** README, demo script. Branding and deployment are asked at this point.
- **8.5 Final check.** The rule coverage tool passes with no uncovered rule; a fresh clone runs `docker compose up` and `make check` green.

## Gates

| Gate | When | Needs from the user |
|---|---|---|
| 1 | before any real model call (phase 6e smoke, evals) | API key in `.env`, model names per role, embedding dimensions |
| 2 | end of 6d | approve the drafted eval datasets and fixtures |
| 3 | phase 8 | branding, instance size, domain, SSL |
| 4 | any paid eval run | go-ahead for the cost |
