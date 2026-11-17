# frontend

The React app: login, onboarding, the chat with action cards, and the admin panel. Built with Vite, TypeScript, React Router, TanStack Query and Tailwind. nginx serves it in Docker and proxies `/api` to the backend. Screens: [`docs/spec/wireframes.md`](../docs/spec/wireframes.md).

## How the chat works

```mermaid
flowchart LR
    page["ChatPage"]
    stream["api/chat.ts<br/>streamChat()"]
    backend(["backend<br/>POST /me/chat"])
    text["MarkdownContent<br/>streamed answer"]
    cards["ChatCards<br/>doctors, visits"]
    write(["backend<br/>POST /me/visits ..."])

    page -- "message" --> stream
    stream -- "fetch + SSE parser" --> backend
    backend -. "token events" .-> text
    backend -. "cards event" .-> cards
    cards -- "click Book / Cancel / File" --> write

    classDef ui fill:#2563eb,stroke:#93c5fd,color:#ffffff
    classDef client fill:#7c3aed,stroke:#c4b5fd,color:#ffffff
    classDef server fill:#0f766e,stroke:#5eead4,color:#ffffff
    class page,text,cards ui
    class stream client
    class backend,write server
    linkStyle default stroke:#64748b,stroke-width:1.5px
```

- The chat stream is a POST, so it is read with `fetch` and a small SSE parser (`createSseParser`), not `EventSource`.
- Assistant text is rendered as Markdown without raw HTML.
- Cards are the only way to write: each button calls a backend endpoint, and the reply rows it returns are added to the chat.
- `GuardedRoute` sends each role to its home: admins to `/admin/kb`, users without a profile to `/onboarding`, everyone else to `/chat`.

## Layout

| Path | Contents |
|---|---|
| `src/api/` | typed fetch clients per area (`auth`, `chat`, `visits`, `admin`, `kb`) and `AuthContext` |
| `src/pages/` | one component per screen |
| `src/components/` | header with the admin section menu (`AdminNav`, sections in `adminSections.tsx`), theme switch, dialog, visits drawer, icons |
| `src/components/chat/` | sidebar, cards, Markdown renderer |
| `e2e/` | Playwright specs against mocked APIs |
| `e2e-stack/` | Playwright specs against the full Docker stack |
| `nginx*.conf*` | dev and production nginx configs |

## Sample

This sample streams one turn with the typed client the chat page uses:

```ts
import { streamChat, type StreamEvent } from './api/chat';

const controller = new AbortController();
let answer = '';

await streamChat('I need a dermatologist', null, (event: StreamEvent) => {
  switch (event.event) {
    case 'session':
      console.log('session', event.session_id);
      break;
    case 'token':
      answer += event.text;
      break;
    case 'cards':
      console.log(event.cards.type, event.cards.items.length);
      break;
    case 'error':
      console.error(event.code, event.message);
      break;
  }
}, controller.signal);

console.log(answer);
```

Call `controller.abort()` to stop a reply. The backend then cancels the model call and stores nothing.

## Commands

```bash
npm ci
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000
npm run lint         # oxlint
npm run typecheck    # tsc
npm test             # Vitest
npx playwright test e2e/chat.spec.ts e2e/kb.spec.ts
```
