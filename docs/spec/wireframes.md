# Health Insurance Chatbot - Wireframes

Version: v0.1.0

Companion files: `schema.dbml` (tables; its A-items are migration notes), `rules.md` (behavior rules B to I, IDs like D6 and F12), `api.md` (API contracts) and `ai.md` (AI package design). ASCII only, so it survives copy/paste anywhere.

---

## 1. Context

- Product: demo of an AI chatbot for a health insurer, shown to insurers and employers. The AI side is specified in `ai.md`. The UI must look business-ready.
- Stack: React frontend, FastAPI backend, Postgres, Qdrant (KB retrieval), Langfuse (LLM tracing), Prometheus + Grafana (backend metrics, rules H1 to H9 in `rules.md`). AI design is in `ai.md`.
- Roles: `user` (self-registered), `admin` (inserted in the DB by the super admin). The super admin has DB access only, no UI.
- Admins use one account for both panels and can toggle between them (B5).
- Auth: server-side session in an HTTP-only cookie (B10, B11). Contracts in `api.md`.
- Time: everything is UTC and the UI says so (C8). No time zone conversion anywhere.
- Frontend stack: Vite, TypeScript, React Router, TanStack Query, Tailwind with shadcn/ui. The chat stream is read with fetch (it is a POST), not EventSource.
- Language: English only. Assistant text renders as Markdown with raw HTML disabled (F17). Branding: the product is "Health Insurance Chatbot" with a text logo (a chat-bubble mark); colors follow the system light or dark setting, and every page has a toggle to pin light, dark or system: in the header on signed-in pages, and in the top-right corner on login, signup and onboarding. The palette is an indigo accent (#2C4BD0 light, #8FA3FF dark) on cool neutrals (#F4F6FA / #0D1119 page, #FFFFFF / #151B27 cards), with soft 1px dividers, 10px control and 14px card radii, and soft shadows. Tokens live in `frontend/src/index.css`.
- The chatbot is the primary way to do everything (book, cancel, complain, ask). The drawer is a convenience.
- Out of scope for v1: password reset, profile editing, user replies in complaints, deleting chats, Excel upload, notifications.

---

## 2. Routes and access

| Route | Who | Purpose |
|---|---|---|
| /signup | anonymous | Create a user account |
| /login | anonymous | Log in (users and admins) |
| /onboarding | user without profile | Create profile (name, location) |
| /chat, /chat/:sessionId | user; admin in user view | Chat + visits/complaints drawer |
| /admin/kb | admin | KB documents |
| /admin/catalog | admin | Locations, specialties, clinics, doctors |
| /admin/slots | admin | Slots |
| /admin/visits | admin | Visits |
| /admin/complaints | admin | Complaints |

Redirect after login:
- admin -> /admin/kb
- user without profile -> /onboarding
- user with profile -> /chat

Guards (UX only; the backend checks the role on every call, B8):
- Not logged in -> /login.
- /signup or /login while logged in -> the role's home.
- User opening /admin/* -> /chat.
- User without profile opening /chat -> /onboarding. User with profile opening /onboarding -> /chat.
- Admin in user view acts as a normal member with their own profile (created in the DB, so no onboarding).
- API prefixes: /admin/... and /me/... Authorization follows the active mode (B5, B11): /admin/* needs role admin and mode admin, /me/* needs mode user.

---

## 3. Shared header

```
+-------------------------------------------------------------------------+
| Health Insurance Chatbot  Sara N.   [My visits & complaints] [Admin panel]  [Log out] |
+-------------------------------------------------------------------------+
```

- Left: app name.
- Display name: `profile.name`, or the username if there is no profile (admin in admin panel).
- `[My visits & complaints]`: user view only. Opens the drawer (section 6).
- Mode toggle: admins only. In the admin panel it reads `[User view]`, in user view it reads `[Admin panel]`. Calls POST /auth/mode, then goes to /chat or /admin/kb.
- Section menu: admin panel only, just before `[User view]`. See section 7.
- `[Log out]`, then the theme switch (system, light, dark).
- Desktop first. On narrow screens the chat sidebar collapses and the drawer goes full screen.

---

## 4. Public screens

### S1. Sign up (/signup)

```
+------------------------------------------+
|        Health Insurance Chatbot          |
|        Create your account               |
|                                          |
|  Username   [______________________]    |
|  Password   [______________________]    |
|  Confirm    [______________________]    |
|                                          |
|  [ Sign up ]                             |
|  Already have an account? Log in         |
+------------------------------------------+
```

- Users only. No role field; the backend hard-codes `role = 'user'` (B1).
- Success -> logged in -> /onboarding.
- Errors: username taken (usernames are unique across all accounts), passwords do not match, password shorter than 8 characters, empty fields.
- Calls: POST /auth/signup

### S2. Log in (/login)

```
+------------------------------------------+
|        Health Insurance Chatbot          |
|        Log in                            |
|                                          |
|  Username   [______________________]    |
|  Password   [______________________]    |
|                                          |
|  [ Log in ]                              |
|  New here? Sign up                       |
+------------------------------------------+
```

- Same screen for admins and users. Redirect per section 2.
- Error: "Wrong username or password" (same message for both cases).
- Calls: POST /auth/login, GET /auth/me (username, role, has_profile, mode); POST /auth/logout from the header

### S3. Onboarding (/onboarding)

```
+------------------------------------------+
|  Complete your profile                   |
|                                          |
|  Full name  [______________________]    |
|  Location   [ Select a location   v ]   |
|                                          |
|  (i) Name and location can't be changed  |
|      after you submit.                   |
|                                          |
|  [ Continue ]                            |
+------------------------------------------+
```

- Location dropdown = rows of `location`.
- Visible note only; no review or confirm step (B3).
- Success -> /chat.
- Calls: GET /locations, POST /me/profile

---

## 5. User panel: chat (/chat)

### Layout

```
+-------------------------------------------------------------------------+
| HEADER (section 3)                                                      |
+------------------+------------------------------------------------------+
| [+ New chat]     |                                                      |
|                  |        Hi Sara, how can I help today?                |
| Book a visit     |                                                      |
|  "I need a derm" |  +------------------+   +------------------+         |
|  2 min ago       |  | Book a clinic    |   | Check my         |         |
|                  |  | visit            |   | visits           |         |
| Policy question  |  +------------------+   +------------------+         |
|  "What does my.."|  +------------------+   +------------------+         |
|  Yesterday       |  | Cancel a         |   | File a           |         |
|                  |  | visit            |   | complaint        |         |
| ...              |  +------------------+   +------------------+         |
|                  |  +------------------+   +------------------+         |
|                  |  | Check my         |   | Ask about my     |         |
|                  |  | complaints       |   | coverage         |         |
|                  |  +------------------+   +------------------+         |
|                  |                                                      |
|                  | +-----------------------------------+ +----------+   |
|                  | | Type your message...              | |  Send    |   |
|                  | +-----------------------------------+ +----------+   |
|                  | All times are UTC.                                   |
+------------------+------------------------------------------------------+
```

### Sidebar

- Sessions of the logged-in profile, newest `last_message_at` first.
- Each item: line 1 = intent label (from `chat_session.intent`, code mapped to a display name in the frontend; null -> "New chat"). Line 2 = first user message truncated (about 40 chars). Line 3 = relative time.
- `[+ New chat]` only clears the UI. No session row is created until the first message is sent (F1).
- Clicking an item opens /chat/:sessionId and loads its transcript.
- No delete/archive in v1.

### Intent labels

`chat_session.intent` holds a flat dotted code (F6). The frontend maps it to the label:

| Code | Sidebar label |
|---|---|
| visit.book | Book a visit |
| visit.check | My visits |
| visit.cancel | Cancel a visit |
| complaint.file | File a complaint |
| complaint.check | My complaints |
| qa.db | Clinic question |
| qa.kb | Policy question |
| other | Chat |
| (null) | New chat |

qa.db is answered from the database (clinics, specialties, doctors, availability). qa.kb is answered from the knowledge base (policy, coverage, exclusions, procedures). Grouping or icons can use the prefix before the dot (visit, complaint, qa).

### Starter cards (empty chat only)

Clicking a card sends its text as the first user message. Fixed texts:

Six cards in a 2 by 3 grid, in this order:

| Card | Message sent | Expected intent |
|---|---|---|
| Book a clinic visit | "I'd like to book a clinic visit." | visit.book |
| Check my visits | "Show me my visits." | visit.check |
| Cancel a visit | "I want to cancel a visit." | visit.cancel |
| File a complaint | "I want to file a complaint about a visit." | complaint.file |
| Check my complaints | "Show me my complaints." | complaint.check |
| Ask about my coverage | "What does my health insurance cover?" | qa.kb |

The expected intent is what the classifier should return for that message. The routing eval checks it (`ai.md`).

### Conversation

```
                                   +----------------------------------+
                                   | I need a dermatologist           |  <- user, right
                                   +----------------------------------+

 +--------------------------------------------------------------------+
 | Here are the earliest options in Cairo:                            |  <- assistant, left
 | Dr. Sara Nabil (Sun 15 Nov 10:00), Dr. Omar Hassan (Mon 16 Nov     |     (text names the
 | 14:00), Dr. Lina Fares (Tue 17 Nov 09:00).                         |      options, F9)
 +--------------------------------------------------------------------+
 +------------------+ +------------------+ +------------------+
 | Dr. Sara Nabil   | | Dr. Omar Hassan  | | Dr. Lina Fares   |        <- recommendation
 | Dermatology      | | Dermatology      | | Dermatology      |           cards (after the
 | Cairo Clinic     | | Nile Medical     | | Cairo Clinic     |           last token)
 | Sun 15 Nov 10:00 | | Mon 16 Nov 14:00 | | Tue 17 Nov 09:00 |
 | [ Book ]         | | [ Book ]         | | [ Book ]         |
 +------------------+ +------------------+ +------------------+
```

### Streaming behavior (F12, F13)

- On send: user bubble appears, assistant bubble shows a typing indicator, then tokens stream in.
- Cards render only after the last token, from a final event carrying the card payload.
- Assistant text renders as Markdown (lists, bold, links) with raw HTML disabled (F17). It re-renders as tokens arrive.
- While a turn streams: the input is disabled, `[ Send ]` becomes `[ Stop ]`, and all older cards are disabled.
- `[ Stop ]`, closing the tab or losing the connection cancels the turn: the LLM call is aborted and nothing is stored, not even the user message (F16). The input gets the unsent text back so the user can resend.
- Reopening a session loads only `user` rows and final `assistant` rows (F11). Cards are gone; the assistant text still names the options.
- Stream error: inline "Something went wrong." + `[Retry]`, which resends the last message. A failed turn stores nothing (F3), so retry is clean.
- A new session is created by the first message. The stream response returns its `session_id`, and the sidebar item appears with the label "New chat" until `intent` is set.

### Recommendation card

Data: doctor name, specialty, clinic, date/time (UTC, with the suffix "UTC"), Book button. Up to 3 cards per recommendation (ranked per D5) or per slot lookup for a chosen doctor (earliest first). No slots found -> assistant text only, no cards.

| State | UI |
|---|---|
| default | `[ Book ]` enabled |
| locked | disabled while a turn streams (F13) |
| booking | spinner on the button, other cards disabled |
| booked | card shows "Booked" badge; sibling cards disabled; the static user message and the static assistant confirmation are appended to the chat (D6) |
| slot taken | card shows "This slot was just taken" + `[ Show other options ]`, which sends the user message "Show me other options." Nothing stored (D7) |
| error | "Could not book. Try again." + `[ Retry ]` |

- The button calls the booking endpoint directly (no LLM), with `session_id` and `slot_id` (D6).
- Calls: POST /me/visits {session_id, slot_id}

### Complaint flow (cards)

```
 Assistant: Which visit is this about?
 +------------------------+ +------------------------+
 | 12 Nov, 10:00          | | 03 Nov, 14:00          |
 | Dr. Sara Nabil         | | Dr. Omar Hassan        |
 | Cairo Clinic           | | Nile Medical           |
 | [ Select ]             | | [ Select ]             |
 +------------------------+ +------------------------+

 After [ Select ] the card expands:
 +--------------------------------------------+
 | 12 Nov, 10:00 - Dr. Sara Nabil             |
 | What happened?                             |
 | [________________________________________]|
 | [________________________________________]|
 | [ Submit complaint ]   [ Cancel ]          |
 +--------------------------------------------+
```

- Cards list only the user's completed visits that have no complaint yet (E1, E2). None -> assistant text says so, no cards.
- Description is required.
- Submit calls the endpoint with `session_id`, `visit_id`, `description`; the card becomes "Complaint filed" and the 4 static messages are stored (E6). The same locks and error states as the booking card apply.
- Calls: POST /me/complaints {session_id, visit_id, description}

### Cancel flow (cards)

```
 Assistant: Which visit do you want to cancel?
 +------------------------+ +------------------------+
 | Sun 15 Nov, 10:00      | | Tue 17 Nov, 09:00      |
 | Dr. Sara Nabil         | | Dr. Lina Fares         |
 | Dermatology            | | Dermatology            |
 | Cairo Clinic           | | Cairo Clinic           |
 | [ Yes, cancel visit ]  | | [ Yes, cancel visit ]  |
 +------------------------+ +------------------------+
```

- Cards list only the user's own Scheduled visits (D8). One matching visit -> one card. None -> assistant text says so, no cards.
- The card names the visit and the button says what it does, so the click is the confirmation (same as Book).
- States: default, locked while a turn streams (F13), cancelling (spinner), cancelled ("Cancelled" badge, sibling cards disabled), not cancellable ("This visit can no longer be cancelled", code visit_not_cancellable), error + `[ Retry ]`.
- On success the 4 static messages are stored (D8) and the slot becomes available again (D2).
- Calls: POST /me/visits/:id/cancel {session_id}

### Chat calls

- POST /me/chat {session_id?, message}: response is text/event-stream (events in `api.md`).
- GET /me/sessions
- GET /me/sessions/:id/messages

---

## 6. User panel: "My visits & complaints" drawer

Opens from the header over the chat (right side, close with [x]). Normal APIs, no LLM (F14). Refetch on open.

```
                              +--------------------------------------+
                              | My visits & complaints          [x]  |
                              | [ Visits ]  [ Complaints ]           |
                              +--------------------------------------+
                              | Sun 15 Nov, 10:00        [Scheduled] |
                              | Dr. Sara Nabil - Dermatology         |
                              | Cairo Clinic                [Cancel] |
                              |--------------------------------------|
                              | Thu 12 Nov, 10:00        [Completed] |
                              | Dr. Omar Hassan - Cardiology         |
                              | Nile Medical                         |
                              |--------------------------------------|
                              | Mon 02 Nov, 09:00        [Cancelled] |
                              | ...                                  |
                              +--------------------------------------+
```

Complaints tab:

```
                              +--------------------------------------+
                              | Visit 12 Nov - Dr. Omar Hassan       |
                              | Filed 13 Nov                  [Open] |
                              | "The wait was too long..."           |
                              |  Reply (14 Nov, Support team):       |
                              |  "We have contacted the clinic..."   |
                              |--------------------------------------|
                              | Visit 03 Nov - Dr. Sara Nabil        |
                              | Filed 04 Nov                [Closed] |
                              | "..."                                |
                              |  No reply yet                        |
                              +--------------------------------------+
```

- Visits: upcoming first. Status badges: Scheduled, Completed, Cancelled. `[Cancel]` only on Scheduled, with a confirm dialog. Convenience only: the chatbot can also cancel (D8). It calls the cancel endpoint without `session_id`, so no chat message is written (D8).
- Complaints: read-only. Shows description, date, status badge, and admin replies as a thread (label "Support team", date). Empty -> "No reply yet".
- Empty states: "No visits yet" / "No complaints yet".
- Calls: GET /me/visits, POST /me/visits/:id/cancel (no session_id), GET /me/complaints

---

## 7. Admin panel

Header as in section 3, with a section menu next to the `[User view]` toggle so admins never type a path:

```
+-------------------------------------------------------------------------+
| Health Insurance Chatbot   admin1  [KB documents v] [User view] [Log out] |
|                                    +-----------------------------------+ |
|                                    | KB documents                      | |
|                                    |   Upload and index policy files   | |
|                                    | Catalog                           | |
|                                    |   Locations, specialties, clinics,| |
|                                    |   doctors                         | |
|                                    | Slots                             | |
|                                    |   Open and remove appointment     | |
|                                    |   slots                           | |
|                                    | Visits                            | |
|                                    |   Review and complete booked      | |
|                                    |   visits                          | |
|                                    | Complaints                        | |
|                                    |   Reply to and close complaints   | |
|                                    +-----------------------------------+ |
+-------------------------------------------------------------------------+
```

- The trigger shows the current section's name and icon. The menu lists the five sections in this order, each with an icon and a one-line hint, and highlights the current one.
- Picking a section goes to its page and closes the menu. Escape or a click outside closes it; arrow keys move between sections.
- Shown only in admin mode. In user view an admin sees `[Admin panel]`, which lands on /admin/kb.

Row actions and confirmations (all admin screens, and the member's visits drawer):

- Actions that change data are buttons, never text links; links are only for going to another page. Row actions sit right-aligned in the last column.
- Main row action (`[Re-index]`, `[Retry]`, `[Mark completed]`, `[Reply]`): small outlined accent button.
- Destructive action (`[Delete]`, `[Close]`, the drawer's `[Cancel]`): small borderless red button that tints on hover, kept quieter than the main action.
- Dense grids (the x on a free slot chip): icon-only button with a tooltip and an accessible label. Removing a free slot is not confirmed (it is easy to re-add).
- Every delete, close, complete, cancel and auto-fill opens the same in-app confirm dialog, never the browser's `confirm()`: a title naming the item ("Delete Cairo?"), one line on what happens (including what cascades), `[Cancel]` (focused) and a confirm button labelled with the action (red for destructive, accent otherwise). Escape or a click outside cancels. While the request runs both buttons are disabled; on failure the dialog stays open and shows the server's message (for example A5's "Can't delete: it has visit history."); on success it closes and the list reloads.
- Errors that are not tied to a confirmation (a rejected reply, a slot that cannot be removed) show inline next to the control, never in `alert()`.

### AP1. KB documents (/admin/kb)

```
+-------------------------------------------------------------------------+
| +---------------------------------------------------------------------+ |
| |   Drag files here or [ Browse ]       pdf, txt, docx - max 10 MB    | |
| +---------------------------------------------------------------------+ |
| Filename       Type  Size    Status        Uploaded by  Date    Actions |
| handbook.pdf   pdf   2.1 MB  [Ready]       admin1       14 Nov  [Re-index] [Delete]
| faq.docx       docx  80 KB   [Processing]  admin1       14 Nov  [Delete]
| old.txt        txt   4 KB    [Failed] (i)  admin2       13 Nov  [Retry] [Delete]
+-------------------------------------------------------------------------+
```

- Statuses: Uploaded, Processing, Ready, Failed (G5). Failed shows `error_message` in a tooltip or expandable row.
- Upload returns immediately; the row appears as Uploaded. Poll the list every few seconds while any row is Uploaded or Processing.
- Multiple files allowed; each becomes its own row.
- Upload errors: too large (show the limit), unsupported type, already uploaded (same hash) (G2, G3).
- `[Retry]` / `[Re-index]` set the status back to Uploaded and re-run (G6). `[Delete]` asks for confirmation (G9).
- The size limit shown in the drop zone comes from config.
- Calls: GET /admin/kb-documents, POST /admin/kb-documents, POST /admin/kb-documents/:id/reindex, DELETE /admin/kb-documents/:id

### AP2. Catalog (/admin/catalog)

Tabs: Locations, Specialties, Clinics, Doctors. Each tab is a table with a `[+ Add ...]` button that opens a small form dialog.

```
| [ Locations ] [ Specialties ] [ Clinics ] [ Doctors ]                   |
+-------------------------------------------------------------------------+
| Clinics                                                [ + Add clinic ] |
| Name            Location   Specialties                    Actions       |
| Cairo Clinic    Cairo      [Dermatology] [Cardiology]     [Specialties] [Delete]
| Nile Medical    Giza       [Cardiology]                   [Specialties] [Delete]
+-------------------------------------------------------------------------+
```

| Tab | Columns | Add form |
|---|---|---|
| Locations | name, clinic count | name |
| Specialties | name | name |
| Clinics | name, location, specialties (chips) | name, location (select), specialties (multi-select) |
| Doctors | name, clinic, specialty | name, clinic (select), specialty (select, limited to the clinic's linked specialties) |

- Clinic specialties are `clinic_specialty` rows. `[Specialties]` opens a multi-select to add or remove links.
- Doctors need a clinic with at least one linked specialty; otherwise the form says "Add a specialty to this clinic first."
- Delete shows a confirm dialog listing what cascades ("Also deletes 2 clinics, 5 doctors, 320 slots") (A5).
- Delete fails if anything below has visit history: friendly message "Can't delete: it has visit history." (A5).
- Names are unique per table; duplicate -> inline error (A4).
- v1: add and delete only. Renames are done in the DB.
- Calls: GET/POST/DELETE /admin/locations, /admin/specialties, /admin/clinics, /admin/doctors; PUT /admin/clinics/:id/specialties

### AP3. Slots (/admin/slots)

```
+-------------------------------------------------------------------------+
| Location [Cairo v] Clinic [Cairo Clinic v] Specialty [Derm. v] Doctor [Dr. Sara v] |
| Month  < Nov 2026 >                      [ Add slot ] [ Auto-fill to end of month ] |
+-------------------------------------------------------------------------+
| Sun 15 Nov | [09 free] [10 BOOKED] [11 free] [12 free] [13 free] [14 free] [15 free] [16 free] |
| Mon 16 Nov | [09 free] [10 free]   [11 free] ...                                    |
| Tue 17 Nov | (no slots)                                                              |
| ...                                                                     |
+-------------------------------------------------------------------------+
```

- Pick a doctor via the cascading filters; the month view shows one row per day with hour chips (09 to 16, UTC).
- Chips: free (has an x to remove), booked (locked, links to the visit), past (greyed, read-only).
- `[ Add slot ]`: dialog with date and hour (09 to 16 only). Duplicate -> error (C3).
- Remove: only free slots (C4). Booked slot -> "Cancel the visit first."
- `[ Auto-fill to end of month ]`: confirm dialog ("Create all missing slots for Dr. Sara from now to 30 Nov?"), then a result message "Created 120 slots, skipped 16 existing." (C5). Safe to run twice. If nothing is missing it says "Nothing to create." Current month only, even on the last day; run it again on the 1st.
- Calls: GET /admin/doctors/:id/slots?month=, POST /admin/doctors/:id/slots, DELETE /admin/slots/:id, POST /admin/doctors/:id/slots/autofill

### AP4. Visits (/admin/visits)

```
+-------------------------------------------------------------------------+
| Status [Scheduled v]   Search patient [__________]                      |
+-------------------------------------------------------------------------+
| Patient   Location  Clinic        Specialty  Doctor      When          Status       Action |
| Sara N.   Cairo     Cairo Clinic  Derm.      Dr. Sara    15 Nov 10:00  [Scheduled]  [Mark completed] |
| Omar K.   Giza      Nile Medical  Cardio.    Dr. Omar    12 Nov 10:00  [Completed]  -                 |
+-------------------------------------------------------------------------+
```

- All visits of all patients. Default filter: Scheduled. Sort by date.
- `[Mark completed]` only on Scheduled, with a confirm dialog (D3). Cancelled and Completed are final; admins cannot cancel.
- Patient = `profile.name`. Other columns derived by joins (D4).
- Calls: GET /admin/visits, POST /admin/visits/:id/complete

### AP5. Complaints (/admin/complaints)

```
+------------------------------+------------------------------------------+
| Status [Open v]              | Complaint #14                    [Open]  |
|                              | Patient: Omar K.                         |
| #14 Omar K.        [Open]    | Visit: 12 Nov 10:00, Dr. Omar Hassan,    |
|     13 Nov - 1 reply         |        Nile Medical                      |
| #12 Sara N.        [Open]    |                                          |
|     11 Nov - no reply        | "The wait was too long..."   (13 Nov)    |
| #09 Lina F.        [Closed]  |                                          |
|     02 Nov - 2 replies       | Replies                                  |
|                              |  admin1 (14 Nov): "We have contacted..." |
|                              |                                          |
|                              | +--------------------------------------+ |
|                              | | Write a reply...                     | |
|                              | +--------------------------------------+ |
|                              | [x] Close complaint after sending        |
|                              | [ Send reply ]        [ Close complaint ]|
+------------------------------+------------------------------------------+
```

- Left: list with status filter (Open default), newest first. Right: detail of the selected complaint.
- A reply does not change status (E4). Closing is separate: the checkbox on send, or `[ Close complaint ]` on its own.
- Closed complaints: reply box disabled with "Closed complaints can't receive replies." (E5)
- Replies show the admin username and date. Users see them as "Support team".
- Calls: GET /admin/complaints, GET /admin/complaints/:id, POST /admin/complaints/:id/replies {body, close?}, POST /admin/complaints/:id/close

---

## 8. Shared UI states

- Loading: skeleton rows for tables, spinner on buttons that call the backend.
- Empty: every list has a one-line empty state with the next action ("No documents yet. Upload one above.").
- Errors: toast for failed actions; inline messages for forms.
- Session expired (401): redirect to /login, then back to the previous route.
- Destructive actions (delete, mark completed, cancel visit, auto-fill) use a confirm dialog.
- Times: always UTC (C8). Cards, drawer items and table cells carry the suffix "UTC", and a note under the chat input says "All times are UTC." Slot hours are always on the hour.

---

## 9. Decisions and open items

Decided:
1. Intents: flat dotted codes (section 5, F6). qa.db = answered from the database, qa.kb = answered from the knowledge base.
2. Time zone: UTC everywhere (C8).
3. Numbers: 3 recommendation cards, context = last 40 message rows (F4), upload limit 10 MB, abuse limits per F15.
4. Accepted defaults: sibling cards disabled after a booking; admins land on /admin/kb; catalog is add and delete only (renames in the DB); replies on closed complaints are rejected (E5).
5. Language and rendering: English only; assistant text is Markdown without raw HTML (F17).
6. UI stack: see section 1.
7. Storage: KB originals on a local Docker volume. S3 is not used (G11).
8. Auth: session cookie, argon2, 7-day sessions, create_admin script (B10 to B13).
9. Observability: Prometheus + Grafana, Grafana via SSH tunnel only, no alerts, Postgres exporter only, no Loki (H1 to H9).
10. Auto-fill: current month only, even at month end (C5).
11. Card-click confirmation for all writes (book, complaint, cancel). A disconnect or Stop cancels the turn and stores nothing (F16).
12. Case-insensitive uniqueness on usernames, location names and specialty names (A4). Login is case-insensitive.
13. AI design is in `ai.md`: router plus agents with per-turn routing (I1 to I4), OpenAI-style providers per role (I11), no semantic cache (I10), no runtime self-evaluation (I9), an eval module in the AI package.

Still open:
- Branding (later).
- Deployment specifics: instance size, domain or subdomain, SSL.
- Seed script design (later, with Claude Code).
- AI open items are listed in `ai.md` (reranker provider, model names, eval datasets and fixtures).

---

## 10. API

Contracts (conventions, errors, auth, chat stream, card actions) are in `api.md`. Per-screen endpoint paths are in the `Calls:` lines above.
