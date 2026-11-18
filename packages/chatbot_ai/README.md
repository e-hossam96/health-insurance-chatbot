# chatbot_ai

The AI package. It contains the router, the agents, the RAG pipeline, KB ingestion and the evals.

It runs inside the backend process, and it is kept deliberately small in what it touches:

- **It has no** Postgres access, web-framework code or Prometheus code.
- **It does** call the model providers and Qdrant.
- **The backend gives it data** through **Ports**: small interfaces (Protocols) that this package defines and the backend implements.
- **The backend reads back** plain events and timings.

The full design is in [`docs/spec/ai.md`](../../docs/spec/ai.md). For setup and the model settings, see the [root README](../../README.md#2-models-one-config-per-role).

## How a turn works

```mermaid
flowchart LR
    request(["TurnRequest<br/>history, message, profile"])
    router{{"router model<br/>picks one intent"}}
    tools["scheduling / complaints<br/>tool loop over Ports"]
    rag["knowledge<br/>rewrite, hybrid search, rerank, answer"]
    plain["responder<br/>no tools"]
    events(["events<br/>Intent, Token, Cards, Done"])

    request --> router
    router --> tools --> events
    router --> rag --> events
    router --> plain --> events

    classDef io fill:#475569,stroke:#94a3b8,color:#ffffff
    classDef step fill:#7c3aed,stroke:#c4b5fd,color:#ffffff
    classDef agent fill:#2563eb,stroke:#93c5fd,color:#ffffff
    class request,events io
    class router step
    class tools,rag,plain agent
    linkStyle default stroke:#64748b,stroke-width:1.5px
```

The same flow in words:

1. A `TurnRequest` comes in, with the history, the new message and the member's profile.
2. The router model picks one intent for the turn.
3. Exactly one agent answers:
   - **scheduling** or **complaints**: a tool loop that reads data through the Ports,
   - **knowledge**: rewrites the question, runs hybrid search, reranks, then answers,
   - **responder**: a plain answer with no tools.
4. The agent's output comes back as events.

## The public interface

### `run_turn(request, ports, settings)`

An async generator. It yields these events, in this order:

| Event | When |
|---|---|
| `Intent` | only when `needs_label` is set on the request |
| `Token` | repeatedly, while the answer streams |
| `Cards` | when a tool found slots or visits |
| `Done` | last; carries the rows to store, the timings and the token usage |

### The Ports (read only)

The model only reads. Its tools call three Ports that the backend implements:

- `SchedulingPort`
- `ComplaintsPort`
- `KnowledgePort`

Bookings and complaints are never written here. Endpoints in the backend write them when the user clicks a card.

### `ingest(document_id, file_path, file_type, settings)`

Parses a PDF, DOCX or TXT file with Docling, chunks it, and writes dense and BM25 vectors to Qdrant. `delete_document` removes a document's vectors again.

### Settings

Each model role (chat, router, rewrite, embedding, judge) has its own `AI_<ROLE>_*` settings in `AISettings`.

## Layout

| Path | Contents |
|---|---|
| `interface.py` | `TurnRequest`, the event types, `Ports` |
| `orchestrator.py`, `router.py` | classify the turn and pick one agent |
| `agents/` | the tool loop, the knowledge pipeline, the responder |
| `tools/` | tool schemas, Port Protocols, return models |
| `rag/`, `rerank/` | query rewrite, hybrid search, the reranker Protocol |
| `ingest/` | parse, chunk, index |
| `prompts/` | one Markdown prompt per agent, plus shared blocks |
| `evals/` | offline suites that call real models |
| `stub.py` | canned turns for tests and demos; needs no models |

## Sample: stream one turn without any services

This sample uses the **stub runner**. It takes the same `TurnRequest` and yields the same events as `run_turn`, but needs no API key, no Postgres and no Qdrant.

```python
import asyncio

from chatbot_ai import Cards, Done, Intent, ProfileInfo, Token, TurnRequest, run_stub_turn


async def main() -> None:
    request = TurnRequest(
        history=[],
        message="I want to book a dermatologist",
        profile=ProfileInfo(display_name="Sara", location_name="Cairo", location_id=1),
        needs_label=True,
        session_id=1,
    )
    async for event in run_stub_turn(request):
        match event:
            case Intent(code=code):
                print(f"[intent] {code}")
            case Token(text=text):
                print(text, end="", flush=True)
            case Cards(type=card_type, items=items):
                print(f"\n[cards] {card_type}: {len(items)} item(s)")
            case Done(new_rows=rows, timings=timings):
                print(f"[done] {len(rows)} new row(s), total {timings.total:.3f}s")


asyncio.run(main())
```

Output:

```text
[intent] visit.book
Here are the available options for you.
[cards] doctors: 1 item(s)
[done] 4 new row(s), total 0.000s
```

### Using the real models instead

1. Set the `AI_*` variables in `.env`.
2. Replace `run_stub_turn(request)` with `run_turn(request, ports, AISettings())`.
3. Build `ports` as `Ports(scheduling=..., complaints=..., knowledge=...)`. Each member must implement its Protocol in `tools/ports.py`. The backend's versions are in `backend/ai_ports.py`.

## Commands

Run these from the repo root.

```bash
uv run pytest packages/chatbot_ai/tests                 # unit and integration tests (fake models, real Qdrant)
uv run python -m chatbot_ai.evals routing --smoke       # real models, costs money
```
