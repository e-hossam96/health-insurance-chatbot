# Health Insurance Chatbot - Behavior Rules

Version: v0.1.0

Companion to `schema.dbml`, `wireframes.md`, `api.md` and `ai.md`. Each rule has a stable ID (D6, F12, H2, ...). Other files cite IDs and never restate rules, so each rule has exactly one home: this file. Section A (database-level items such as CHECK constraints and the partial unique index) lives in `schema.dbml` as migration notes.

## B. Accounts and access

- **B1.** Sign-up is users only and hard-codes role = 'user'. Admins are inserted in the DB by the super admin.
- **B2.** Admin profiles are created in the DB; admins skip onboarding.
- **B3.** Users sign up, then complete the profile at first login. Form shows: "Name and location can't be changed after you submit." No review step.
- **B4.** Profiles are immutable except by the super admin (DB). No update endpoints, no test profile.
- **B5.** One login for all. Routing: admin -> admin panel; user without profile -> onboarding; otherwise -> chat. Admins get a toggle between admin panel and user view. Authorization follows the ACTIVE MODE.
- **B6.** The acting profile comes from the login session, never from the request body or the model.
- **B7.** complaint_reply.admin_account_id and kb_document.uploaded_by must reference role = 'admin' (not expressible as an FK).
- **B8.** Route guards in React are UX only. The backend checks the role on every endpoint. Prefixes: /admin/... and /me/...
- **B9.** No password reset flow. Reset in the DB.
- **B10.** Auth = opaque session token in an HTTP-only, Secure, SameSite=Lax cookie. Only its hash is stored (auth_session). Logout deletes the row. Expired rows are purged on login or startup. State-changing routes accept JSON only. One exception: the KB upload (POST /admin/kb-documents, admin only) takes the raw file body so its size limit is checked while streaming (G2).
- **B11.** /admin/* requires role = 'admin' AND active_mode = 'admin'. /me/* requires active_mode = 'user'. Only admins may set active_mode to 'admin' (POST /auth/mode).
- **B12.** Passwords are hashed with argon2, minimum length 8. Session lifetime 7 days (expires_at = created_at + 7 days).
- **B13.** Admins are created with a create_admin script (hashes the password, inserts the account with role = 'admin' and its profile).

## C. Slots

- **C1.** One hour, on the hour. End implied (start_at + 1 hour).
- **C2.** Working day 9:00-17:00 UTC (8 slots, starts 9..16). One constant.
- **C3.** Manual add: doctor + date + hour.
- **C4.** Manual remove: only while 'available'.
- **C5.** Auto-fill (per doctor): now until the last day of the current month, every day, 8 slots/day. Skips past hours. INSERT ... ON CONFLICT DO NOTHING (re-run safe). Returns counts. Current month only, even on the last day; admins run it again on the 1st. If nothing is missing it returns 0 created and the UI says "Nothing to create".
- **C6.** No Excel upload.
- **C7.** Users are offered only 'available' slots with start_at > now.
- **C8.** Everything is UTC: storage, API, UI, tool results, prompts and static messages. The UI says so ("All times are UTC"). No per-user or per-clinic time zone, no time zone headers, no conversion.

## D. Visits and booking

- **D1.** Booking, one transaction: UPDATE slot SET status = 'booked' WHERE status = 'available' AND start_at > now() (0 rows = taken), then insert the visit as 'scheduled'.
- **D2.** Cancel (user, own visit, 'scheduled' only), one transaction: visit -> 'cancelled', slot -> 'available'.
- **D3.** Complete (admin only). Transitions: scheduled -> completed, scheduled -> cancelled. Both final.
- **D4.** Doctor, clinic, specialty, location are derived by joins.
- **D5.** Recommendations ranked deterministically: specialty, profile's location, earliest available slot. The LLM only presents them.
- **D6.** Booking card: the button calls the booking endpoint directly with session_id + slot_id (no LLM). In the same transaction, insert 4 static messages: user ("Book ..."), assistant with a synthetic book_visit tool call, tool result, assistant confirmation.
- **D7.** Slot taken: endpoint returns a conflict, the card shows "slot just taken" + "Show other options" (normal user message). Nothing stored.
- **D8.** Cancel from chat: a tool proposes a cancel_confirm card (own visit, 'scheduled' only). The click calls POST /me/visits/:id/cancel with session_id; in one transaction do D2 and insert the 4 static messages (synthetic cancel_visit call). The drawer's cancel button omits session_id and writes no chat message (a convenience; chat is the primary path).
- **D9.** The model never writes data. Its tools are read tools plus tools that propose an action as a card. Every write runs through an endpoint on a click.

## E. Complaints

- **E1.** Only on a visit that belongs to the requester and is 'completed'.
- **E2.** One complaint per visit.
- **E3.** Only admins reply or close. Users read replies.
- **E4.** A reply doesn't change status. Closing is a separate admin action.
- **E5.** Replies on a closed complaint are rejected.
- **E6.** Filing from a card uses the D6 pattern (4 static messages with a synthetic file_complaint call, same transaction as the insert).

## F. Chat

- **F1.** Create a session on the first message or "New chat", never on page load.
- **F2.** Every request carries session_id. Check it belongs to the profile.
- **F3.** A turn stores all its messages (user, assistant tool calls, tool results, final assistant) in one transaction, then updates chat_session.last_message_at.
- **F4.** Context = last 40 message rows (tool calls and results included), then drop leading rows until the first 'user' row (never cut between a tool call and its result). Old tool results are truncated or replaced by placeholders (KB chunks are replayed in full only in the turn that retrieved them). Cap stored/replayed result size.
- **F5.** Time-varying data (slots, visit status, complaint status) is always re-fetched by a tool. Prompt note. Mid-chat slot changes accepted as rare.
- **F6.** Sidebar label = chat_session.intent, detected from the first message (one label per session: the primary intent). If detection fails, the first later turn that classifies successfully sets it. Once set it never changes. Stored as a flat dotted code in the varchar column; the frontend maps it to a display name. Codes: visit.book, visit.check, visit.cancel, complaint.file, complaint.check, qa.db (questions answered from the database: clinics, specialties, doctors, availability), qa.kb (general insurance questions answered from the knowledge base: refunds, spending limits, co-pays, coverage, exclusions, claims, approvals, procedures), other (greetings, off-topic). The classifier outputs one enum of these codes. Every turn is classified again for routing, which never changes the label (I1). Null -> "New chat". Detection failure never blocks the reply. Subtitle = first user message truncated (derived at query time).
- **F7.** Langfuse session ID = 'chat-' + chat_session.id.
- **F8.** No medical advice. Escape hatch to the complaint flow.
- **F9.** Assistant text names the options it presents (cards aren't stored).
- **F10.** chat_message is the history source of truth. No framework checkpointer. The context builder converts rows to the OpenAI message format (`ai.md`).
- **F11.** Transcript and sidebar show only 'user' rows and final 'assistant' rows (content non-empty, no tool_calls).
- **F12.** Streaming: tokens first, then a final event with the card payload. Cards render only after the last token. Cards aren't stored and disappear when a session is reopened.
- **F13.** While a turn streams, disable the input and older cards.
- **F14.** User panel includes a "My visits & complaints" drawer (visit statuses, admin replies), served by normal APIs.
- **F15.** Abuse limits (config values): 6 messages/min per user, 100 user messages/day per user (admins exempt), 1000 characters per message, ~800 output tokens per answer, sign-up 5/hour per IP, failed logins 10 per 15 min per IP + username. All counters are in memory, including the daily cap (keyed by user + UTC date). A turn is counted when it starts, so cancelled and failed turns count too. Counters reset on restart (accepted). No extra table. Client IP comes from the reverse proxy header.
- **F16.** Client disconnect mid-stream (closed tab or Stop button): cancel the LLM call and store nothing for the turn (same as a failed turn, F3). Safe because the model only reads (D9). The user's message is not stored either. If it was the first turn of a new chat, the session row created for it is removed too (also for a failed first turn). Card-action endpoints are plain requests and always run to completion in one transaction.
- **F17.** Reply language follows the member, per turn: the classifier labels the latest message ar (Arabic, any dialect or Arabizi), en or other (I1). ar -> the agent replies in Modern Standard Arabic; en and other -> American English. The system prompt carries that one instruction; the fixed I8 reply has an Arabic and an English text. If the language label is unusable, Arabic letters in the message mean ar, else en. Cards follow the turn too: the `cards` event carries `ar` or `en`, an Arabic card shows Arabic labels and dates right to left, and its click writes the D6, D8 and E6 static messages in Arabic. Doctor, clinic, location and specialty names always stay as stored in the database. The rest of the UI stays English; message text and inputs take their direction from the text (`dir="auto"`). Assistant text is Markdown, rendered without raw HTML (model output is untrusted).

## G. Knowledge base

- **G1.** Types: pdf, txt, docx.
- **G2.** Size limit in config (KB_MAX_UPLOAD_BYTES, 10 MB). Enforce in nginx client_max_body_size and the upload endpoint (count bytes while streaming, abort, delete the partial file). Store the real size.
- **G3.** Duplicates rejected via the unique content_hash.
- **G4.** Chunks live in Qdrant only (dense + BM25), payload: document_id, chunk_index, content, headings, kind (text | table), content_hash (details in `ai.md`).
- **G5.** Background job run in a child process inside the backend container, one job at a time (I12): uploaded -> processing -> ready | failed (+ error_message). Upload returns immediately; the admin panel polls.
- **G6.** Job is idempotent: delete the document's Qdrant points (filter on document_id), then extract, chunk, upsert. Retry/re-index: set 'uploaded' and re-run.
- **G7.** On startup, reset 'processing' rows to 'uploaded' and re-run.
- **G8.** Only 'ready' documents are searchable.
- **G9.** Delete order: Qdrant points, file, row. If Qdrant fails, keep the row.
- **G10.** Replace a document = delete + re-upload.
- **G11.** KB originals live on a local Docker volume; storage_path is a path on it. No S3.

## H. Observability (Prometheus + Grafana)

- **H1.** Prometheus and Grafana run as containers next to the backend (Docker). Prometheus scrapes the backend /metrics every 15 s, plus Qdrant's built-in /metrics, plus a Postgres exporter. No node exporter, cAdvisor or Loki.
- **H2.** The backend owns ALL Prometheus code. The ai package has no Prometheus dependency: it returns timings as plain values in its events (per-chunk elapsed time, time to first token, total duration, token usage, and durations of each stage (classify, rewrite, embed, search, rerank, generate), of tool calls and of ingestion). The backend turns them into metrics.
- **H3.** Metrics v1: HTTP rate, latency and errors by route template (not the raw path); chat turns by outcome (ok | error | cancelled), time to first token, LLM duration, chunk gap, tokens (prompt | completion), per-stage durations (classify | rewrite | embed | search | rerank | generate), turns by agent; ingestion outcomes and duration, plus a gauge of documents in 'processing'; rate-limit rejections by limit type; business counters incremented at the endpoint (signups, card actions by action and outcome). Tool, retrieval and per-trace detail stay in Langfuse; the ai events already carry those timings, so adding them later is a backend-only change.
- **H4.** Labels are small fixed sets only (route template, outcome, status, intent code, agent, stage, tool name, model name). Never user, session or document ids.
- **H5.** One uvicorn worker (prometheus_client default mode). F15 counters in memory need this too.
- **H6.** /metrics is not public: nginx blocks it externally, and Prometheus scrapes it over the internal Docker network. Grafana needs a real admin password from an environment variable and stays private: SSH tunnel only.
- **H7.** Config as code in a top-level observability/ folder: prometheus.yml, Grafana datasource provisioning, dashboard JSON. Retention 15 days on a persistent volume.
- **H8.** Dashboards v1: API health, chat and LLM, KB ingestion, demo overview (signups, bookings, complaints).
- **H9.** No alert rules in v1.

## I. AI pipeline (design in `ai.md`)

- **I1.** Routing is per turn. Every turn is classified (small model, one structured output with two labels: one enum of the F6 codes and one language code for F17) using the last 6 history rows (trimmed to start at a user row, as in F4), so a short follow-up continues the current task. The result picks the agent. Classifier failure never blocks the reply (F6): fall back to the responder agent.
- **I2.** Intent -> agent: visit.book, visit.check, visit.cancel and qa.db -> scheduling; complaint.file and complaint.check -> complaints; qa.kb -> knowledge; other -> responder (no tools). Scheduling and complaints are tool loops (max `AI_MAX_TOOL_ROUNDS` rounds). Knowledge is a fixed pipeline (I6).
- **I3.** The router is invisible. Classifier calls are never stored or shown; only the chosen agent's rows are stored (F3, F11), so history looks like a single-agent history.
- **I4.** All agents see the same history (F4) and the same shared prompt blocks (F5, F8, F17, C8, profile name and location, and a note that the history may contain tool calls the agent cannot make). No agent writes data (D9). Tools get the acting profile from the request context, never from model arguments (B6).
- **I5.** Database questions (qa.db) use typed, read-only, parameterized tools. No model-written SQL. Specialty and location arguments are validated against the catalog.
- **I6.** Knowledge order: rewrite, hybrid search per query, merge, dedupe (I7), rerank, top K, grounding check (I8), answer. Retrieval is recorded as a synthetic search_kb tool call and result so history keeps one shape (F3, F4).
- **I7.** Duplicate chunks are removed at query time only, after merging: by chunk id, then by normalized text hash. No cross-document dedupe at ingest (G3 blocks identical files), so deleting a document (G9) never removes chunks another document needs.
- **I8.** Grounding: no candidates, or a best rerank score below `AI_RERANK_MIN_SCORE` (when set), returns the fixed reply "I couldn't find that in the documents." (in Arabic for an ar turn, F17) with no generation call. Answers use only the retrieved excerpts.
- **I9.** No runtime self-evaluation of answers in v1 (no critic or verifier call before replying). Quality is measured offline by the eval module.
- **I10.** No semantic cache in v1.
- **I11.** Every model call goes through per-role provider config (base URL, key, model) in the OpenAI API shape. No provider or model names in code.
- **I12.** Ingestion runs in a child process, one job at a time (G5). The parent kills it on timeout. It returns its timings as values (H2) and the API process records the metrics.
- **I13.** Each optional retrieval stage has a config switch (retrieval mode, rerank provider, query count) so evals can ablate it.
- **I14.** One agent per turn. A message that mixes domains (for example an insurance question plus a clinic question) is answered by the chosen agent, which says what it cannot answer.
