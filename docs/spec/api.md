# Health Insurance Chatbot - API Conventions and Contracts

Version: v0.1.0

Per-screen endpoint paths are in the `Calls:` lines of `wireframes.md` (sections 4 to 7). Rule IDs (B10, D6, F16, ...) refer to `rules.md`; A-rules are in `schema.dbml`. The AI package behind the chat stream is described in `ai.md`. Admin endpoint payloads are still to be specified.

## Conventions

- JSON, snake_case. Ids are integers. Timestamps are ISO-8601 UTC strings. The frontend shows them as UTC; no time zone header or conversion (C8).
- Small lists are plain arrays. Admin visits, complaints and KB documents return `{items, total}` and accept `limit` and `offset` (default limit 50).
- Errors always look like:

```
{"error": {"code": "slot_taken", "message": "This slot was just taken."}}
```

| HTTP | Meaning | Codes |
|---|---|---|
| 401 | not logged in | invalid_credentials, not_authenticated |
| 403 | wrong role or mode | forbidden |
| 404 | not found, or not yours (no leaking) | not_found |
| 409 | conflict | slot_taken, username_taken, duplicate_document, has_history, visit_not_cancellable, visit_not_completed, complaint_exists, complaint_closed |
| 413 | file too large | file_too_large |
| 415 | unsupported file type | unsupported_type |
| 422 | validation, including a chat message over the F15 length cap | validation_error |
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
| error | {code, message} | turn failed; nothing is stored (F3) |

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

## Other

- GET /me/sessions, GET /me/sessions/:id/messages (only user rows and final assistant rows, F11), GET /me/visits, GET /me/complaints, POST /me/profile, GET /locations.
- Admin endpoints are listed per screen in section 7.
