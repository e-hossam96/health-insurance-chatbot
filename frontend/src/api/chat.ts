const BASE = '/api';

export type ChatSession = {
  id: number;
  intent: string | null;
  created_at: string;
  last_message_at: string;
  first_user_message: string | null;
};

export type ChatMessage = {
  id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content: string;
};

export type SSEEvent = {
  event: string;
  data: string;
};

export async function getSessions(): Promise<ChatSession[]> {
  const res = await fetch(`${BASE}/me/sessions`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to load sessions');
  return res.json() as Promise<ChatSession[]>;
}

export async function getMessages(sessionId: number): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE}/me/sessions/${sessionId}/messages`, {
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json() as Promise<ChatMessage[]>;
}

export type StreamCallbacks = {
  onSession: (sessionId: number) => void;
  onToken: (text: string) => void;
  onIntent: (intent: string) => void;
  onCards: (type: string, items: Record<string, unknown>[]) => void;
  onDone: () => void;
  onError: (code: string, message: string) => void;
};

export async function streamChat(
  message: string,
  sessionId: number | null,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  const body: Record<string, unknown> = { message };
  if (sessionId !== null) body.session_id = sessionId;

  const res = await fetch(`${BASE}/me/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const err = (await res.json()) as { detail: { error: { code: string; message: string } } };
    callbacks.onError(err.detail.error.code, err.detail.error.message);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6);
        const parsed = JSON.parse(data) as Record<string, unknown>;

        switch (currentEvent) {
          case 'session':
            callbacks.onSession(parsed.session_id as number);
            break;
          case 'token':
            callbacks.onToken(parsed.text as string);
            break;
          case 'intent':
            callbacks.onIntent(parsed.intent as string);
            break;
          case 'cards':
            callbacks.onCards(
              parsed.type as string,
              parsed.items as Record<string, unknown>[],
            );
            break;
          case 'done':
            callbacks.onDone();
            break;
          case 'error':
            callbacks.onError(
              parsed.code as string,
              parsed.message as string,
            );
            break;
        }
        currentEvent = '';
      }
    }
  }
}

export const INTENT_LABELS: Record<string, string> = {
  'visit.book': 'Book a visit',
  'visit.check': 'My visits',
  'visit.cancel': 'Cancel a visit',
  'complaint.file': 'File a complaint',
  'complaint.check': 'My complaints',
  'qa.db': 'Clinic question',
  'qa.kb': 'Policy question',
  'other': 'Chat',
};

export const STARTER_CARDS = [
  { label: 'Book a clinic visit', message: "I'd like to book a clinic visit." },
  { label: 'Check my visits', message: 'Show me my visits.' },
  { label: 'Cancel a visit', message: 'I want to cancel a visit.' },
  { label: 'File a complaint', message: 'I want to file a complaint about a visit.' },
  { label: 'Check my complaints', message: 'Show me my complaints.' },
  { label: 'Ask about my coverage', message: 'What does my health insurance cover?' },
];
