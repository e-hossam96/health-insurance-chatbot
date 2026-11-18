# Health Insurance Chatbot - API Conventions and Contracts

Version: v0.1.0

Per-screen endpoint paths are in the `Calls:` lines of `wireframes.md` (sections 4 to 7). Rule IDs (B10, D6, F16, ...) refer to `rules.md`; A-rules are in `schema.dbml`. The AI package behind the chat stream is described in `ai.md`. Admin payloads are in the Admin sections below.

## Conventions

- JSON, snake_case. Ids are integers. Timestamps are ISO-8601 UTC strings. The frontend shows them as UTC; no time zone header or conversion (C8).
- Small lists are plain arrays. Admin visits, complaints and KB documents return `{items, total}` and accept `limit` and `offset` (default limit 50).
- Errors always look like this (FastAPI's `detail` wrapper is kept), including request validation errors, which name the invalid fields but never echo the submitted values:

```
{"detail": {"error": {"code": "slot_taken", "message": "This slot was just taken."}}}
```

| HTTP | Meaning | Codes |
|---|---|---|
| 401 | not logged in | invalid_credentials, not_authenticated |
| 403 | wrong role or mode | forbidden |
| 404 | not found, or not yours (no leaking) | not_found |
| 409 | conflict | slot_taken, slot_past, username_taken, profile_exists, duplicate_document, duplicate, has_history, slot_booked, invalid_transition, visit_not_cancellable, visit_not_completed, complaint_exists, complaint_closed |
| 413 | file too large | file_too_large |
| 415 | unsupported file type | unsupported_type |
| 422 | validation, including a chat message over the F15 length cap; a slot off the hour or outside 9 to 16 UTC (C1, C2) | validation_error, invalid_time |
| 429 | rate limit (F15), with Retry-After | rate_limited |
| 503 | a dependency is down; nothing was changed | kb_index_unavailable |

## Auth

- POST /auth/signup {username, password} -> 201, logged in
- POST /auth/login {username, password}
- POST /auth/logout
- GET /auth/me -> {username, role, has_profile, mode}
- POST /auth/mode {mode: "admin" | "user"} (admins only)
- Cookie: HTTP-only, Secure, SameSite=Lax (B10). Mode rules in B11. Passwords: argon2, minimum 8 characters. Sessions last 7 days (B12).

## Chat stream

`POST /me/chat {session_id?, message}` responds with text/event-stream:

| Event | Data | When |
|---|---|---|
| session | {session_id} | first, always |
| token | {text} | repeated while the answer streams |
| intent | {intent} | once, when the sidebar label is first set (usually the first turn, F6) |
| cards | {type, items} | after the last token, only if the turn produced cards |
| done | {} | end of turn |
| error | {code, message} | turn failed; nothing is stored (F3). The code is always `turn_error` and the message "Something went wrong." |

Card payloads (not stored, F12):

| type | item fields |
|---|---|
| doctors | slot_id, doctor_name, specialty, clinic, location, start_at |
| visits_for_complaint | visit_id, start_at, doctor_name, specialty, clinic |
| cancel_confirm | visit_id, start_at, doctor_name, specialty, clinic |

If the client disconnects (Stop, closed tab), the LLM call is cancelled and nothing is stored (F16). The turn still counts toward the rate limits (F15).

## Card actions

All three write the 4 static messages in the same transaction as the change (D6, E6, D8) and return the two displayable ones (static user message, static assistant confirmation).

- POST /me/visits {session_id, slot_id} -> 201 {visit, messages}. 409 slot_taken.
- POST /me/visits/:id/cancel {session_id?} -> {visit, messages?}. `messages` only when session_id is given. 409 visit_not_cancellable.
- POST /me/complaints {session_id, visit_id, description} -> 201 {complaint, messages}. 409 visit_not_completed, complaint_exists.

## Admin KB documents

Admin only (B11). Statuses and jobs follow G1 to G11.

- GET /admin/kb-documents?limit&offset -> {items, total, max_upload_bytes}. Item: {id, filename, file_type, file_size_bytes, status, error_message, uploaded_by (username), created_at}. Newest first. `max_upload_bytes` is KB_MAX_UPLOAD_BYTES, shown in the drop zone.
- POST /admin/kb-documents?filename=<name> with the raw file bytes as the body (one request per file, any Content-Type) -> 201 item with status 'uploaded'. The type comes from the filename extension (G1, else 415 unsupported_type). The body is streamed to disk while bytes are counted and hashed: over the limit gives 413 file_too_large and the partial file is deleted (G2); an empty body gives 422 validation_error; a known hash gives 409 duplicate_document (G3). The job starts in the background (G5).
- POST /admin/kb-documents/:id/reindex -> item. From 'ready' or 'failed' it sets 'uploaded', clears error_message and re-runs the job (G6); from 'uploaded' or 'processing' it changes nothing.
- DELETE /admin/kb-documents/:id -> 204. Deletes the Qdrant points, then the file, then the row (G9). If Qdrant fails: 503 kb_index_unavailable and the row and file are kept.

The upload is a raw body instead of multipart because the multipart parser reads the whole file before the handler runs, which would defeat the streaming size check in G2.

## Admin catalog, slots, visits and complaints

Admin only (B11). Delete responses report what cascaded (A5); a delete blocked by history returns 409 has_history.

- GET /admin/locations, GET /admin/specialties -> [{id, name}], by name. POST {name} -> 201 {id, name}; a case-insensitive duplicate gives 409 (A4). DELETE /admin/locations/:id -> {deleted, cascade: {clinics}}; 409 has_history while a profile uses it. DELETE /admin/specialties/:id -> {deleted}; 409 has_history while a clinic links it.
- GET /admin/clinics -> [{id, name, location_id}]. POST {name, location_id} -> 201 {id, name, location_id}. DELETE /admin/clinics/:id -> {deleted, cascade: {specialties, doctors}}; 409 has_history when its doctors have visits.
- PUT /admin/clinics/:id/specialties [{specialty_id}, ...] replaces the clinic's links -> [{id, clinic_id, specialty_id}]. Removing a link that has doctors gives 409 has_history.
- GET /admin/doctors -> [{id, name, clinic_specialty_id}]. POST {name, clinic_specialty_id} -> 201 {id, name, clinic_specialty_id}. DELETE /admin/doctors/:id -> {deleted, cascade: {slots}}; 409 has_history when it has visits.
- GET /admin/slots?doctor_id&year&month -> [{id, doctor_id, start_at, status}], by start_at. POST /admin/slots {doctor_id, start_at} -> 201 slot; 422 invalid_time (C1, C2), 409 duplicate (C3). DELETE /admin/slots/:id -> {deleted}; 409 slot_booked unless 'available' (C4). POST /admin/slots/autofill {doctor_id} -> {created, message} (C5; message "Nothing to create" when created is 0).
- GET /admin/visits?status&limit&offset -> {items: [{id, profile_id, slot_id, status}], total}, newest slot first (limit default 20, max 100). POST /admin/visits/:id/complete -> {id, status}; 409 invalid_transition unless 'scheduled' (D3).
- GET /admin/complaints?status&limit&offset -> {items: [{id, visit_id, description, status}], total}, newest first (limit default 20, max 100). POST /admin/complaints/:id/reply {body} -> 201 {id, complaint_id, admin_account_id, body} (E3, E4). POST /admin/complaints/:id/close -> {id, status}. Both give 409 complaint_closed on a closed complaint (E5).

## Other

- POST /me/profile {name, location_id} -> 201 {id, name, location_id, location_name}; 409 profile_exists (B2 to B4). GET /locations -> [{id, name}].
- GET /me/sessions -> [{id, intent, created_at, last_message_at, first_user_message}], newest `last_message_at` first. GET /me/sessions/:id/messages -> [{id, session_id, role, content}], only user rows and final assistant rows (F11).
- GET /me/visits -> [{id, slot_id, status, doctor_name, specialty, clinic, location, start_at}]. GET /me/complaints -> [{id, visit_id, description, status, replies: [{id, body}]}].
- POST /me/visits also returns 409 slot_past for a slot that has started (C7).
- GET /health -> {status: "ok"}, public. GET /metrics is Prometheus text, reached only on the internal network (H6); nginx answers /api/metrics with 404.
