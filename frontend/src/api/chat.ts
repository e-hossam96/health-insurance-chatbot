import { type ApiError, reportUnauthorized } from './client';

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

export type DoctorCardItem = {
  slot_id: number;
  doctor_name: string;
  specialty: string;
  clinic: string;
  location: string;
  start_at: string;
};

export type VisitCardItem = {
  visit_id: number;
  start_at: string;
  doctor_name: string;
  specialty: string;
  clinic: string;
};

export type CardLanguage = 'en' | 'ar';

export type CardsPayload = { language: CardLanguage } & (
  | { type: 'doctors'; items: DoctorCardItem[] }
  | { type: 'visits_for_complaint'; items: VisitCardItem[] }
  | { type: 'cancel_confirm'; items: VisitCardItem[] }
);

export type StreamEvent =
  | { event: 'session'; session_id: number }
  | { event: 'token'; text: string }
  | { event: 'intent'; intent: string }
  | { event: 'cards'; cards: CardsPayload }
  | { event: 'done' }
  | { event: 'error'; code: string; message: string };

export class ChatRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function getSessions(): Promise<ChatSession[]> {
  const res = await fetch(`${BASE}/me/sessions`, { credentials: 'include' });
  if (!res.ok) {
    reportUnauthorized(res.status, '/me/sessions');
    throw new Error('Failed to load sessions');
  }
  return res.json() as Promise<ChatSession[]>;
}

export async function getMessages(sessionId: number): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE}/me/sessions/${sessionId}/messages`, {
    credentials: 'include',
  });
  if (!res.ok) {
    reportUnauthorized(res.status, '/me/sessions');
    throw new Error('Failed to load messages');
  }
  return res.json() as Promise<ChatMessage[]>;
}

function toStreamEvent(name: string, data: string): StreamEvent | null {
  const parsed = JSON.parse(data) as Record<string, unknown>;
  switch (name) {
    case 'session':
      return { event: 'session', session_id: parsed.session_id as number };
    case 'token':
      return { event: 'token', text: parsed.text as string };
    case 'intent':
      return { event: 'intent', intent: parsed.intent as string };
    case 'cards':
      return { event: 'cards', cards: { ...(parsed as CardsPayload), language: parsed.language === 'ar' ? 'ar' : 'en' } };
    case 'done':
      return { event: 'done' };
    case 'error':
      return { event: 'error', code: parsed.code as string, message: parsed.message as string };
    default:
      return null;
  }
}

export type SseParser = { push: (chunk: string) => void; end: () => void };

export function createSseParser(onEvent: (event: StreamEvent) => void): SseParser {
  let buffer = '';
  let eventName = 'message';
  let dataLines: string[] = [];

  function dispatch(): void {
    if (dataLines.length > 0) {
      const event = toStreamEvent(eventName, dataLines.join('\n'));
      if (event) onEvent(event);
    }
    eventName = 'message';
    dataLines = [];
  }

  function handleLine(line: string): void {
    if (line === '') {
      dispatch();
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  }

  return {
    push(chunk: string): void {
      buffer += chunk;
      const lines = buffer.split(/\r\n|\r|\n/);
      buffer = lines.pop() ?? '';
      for (const line of lines) handleLine(line);
    },
    end(): void {
      if (buffer !== '') handleLine(buffer);
      buffer = '';
      dispatch();
    },
  };
}

export async function streamChat(
  message: string,
  sessionId: number | null,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const body: { message: string; session_id?: number } = { message };
  if (sessionId !== null) body.session_id = sessionId;

  const res = await fetch(`${BASE}/me/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    reportUnauthorized(res.status, '/me/chat');
    const err = (await res.json().catch(() => null)) as { detail?: ApiError } | null;
    const detail = err?.detail?.error;
    throw new ChatRequestError(
      res.status,
      detail?.code ?? 'request_failed',
      detail?.message ?? 'Something went wrong.',
    );
  }

  const reader = res.body?.getReader();
  if (!reader) throw new ChatRequestError(res.status, 'no_body', 'Something went wrong.');

  const decoder = new TextDecoder();
  const parser = createSseParser(onEvent);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode());
  parser.end();
}

export const INTENT_LABELS: Record<string, string> = {
  'visit.book': 'Book a visit',
  'visit.check': 'My visits',
  'visit.cancel': 'Cancel a visit',
  'complaint.file': 'File a complaint',
  'complaint.check': 'My complaints',
  'qa.db': 'Clinic question',
  'qa.kb': 'Insurance question',
  other: 'Chat',
};

export function intentLabel(intent: string | null): string {
  if (intent === null) return 'New chat';
  return INTENT_LABELS[intent] ?? 'Chat';
}

export const STARTER_CARDS: readonly { label: string; message: string }[] = [
  { label: 'Book a clinic visit', message: "I'd like to book a clinic visit." },
  { label: 'Check my visits', message: 'Show me my visits.' },
  { label: 'Cancel a visit', message: 'I want to cancel a visit.' },
  { label: 'File a complaint', message: 'I want to file a complaint about a visit.' },
  { label: 'Check my complaints', message: 'Show me my complaints.' },
  { label: 'Ask an insurance question', message: 'What does my health insurance cover?' },
];

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ARABIC_WEEKDAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
const ARABIC_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];

export function formatUtc(iso: string, language: CardLanguage = 'en'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return `${iso} UTC`;
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  if (language === 'ar') {
    return `${ARABIC_WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${ARABIC_MONTHS[date.getUTCMonth()]}، ${hours}:${minutes} UTC`;
  }
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}, ${hours}:${minutes} UTC`;
}

export function relativeTime(iso: string, now: Date): string {
  const seconds = Math.floor((now.getTime() - new Date(iso).getTime()) / 1000);
  if (Number.isNaN(seconds)) return '';
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  return `${days} days ago`;
}
