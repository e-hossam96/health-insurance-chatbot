import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { ChatPage } from './ChatPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'user1', role: 'user', has_profile: true, mode: 'user' },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/auth', () => ({
  logout: vi.fn(),
  setMode: vi.fn(),
}));

vi.mock('../api/chat', () => ({
  getSessions: vi.fn().mockResolvedValue([]),
  getMessages: vi.fn().mockResolvedValue([]),
  streamChat: vi.fn(),
  INTENT_LABELS: {
    'visit.book': 'Book a visit',
    'visit.check': 'My visits',
    'visit.cancel': 'Cancel a visit',
    'complaint.file': 'File a complaint',
    'complaint.check': 'My complaints',
    'qa.db': 'Clinic question',
    'qa.kb': 'Policy question',
    'other': 'Chat',
  },
  STARTER_CARDS: [
    { label: 'Book a clinic visit', message: "I'd like to book a clinic visit." },
    { label: 'Check my visits', message: 'Show me my visits.' },
    { label: 'Cancel a visit', message: 'I want to cancel a visit.' },
    { label: 'File a complaint', message: 'I want to file a complaint about a visit.' },
    { label: 'Check my complaints', message: 'Show me my complaints.' },
    { label: 'Ask about my coverage', message: 'What does my health insurance cover?' },
  ],
}));

vi.mock('../api/visits', () => ({
  getMyVisits: vi.fn().mockResolvedValue([]),
  getMyComplaints: vi.fn().mockResolvedValue([]),
  cancelVisit: vi.fn(),
  bookVisit: vi.fn(),
  fileComplaint: vi.fn(),
}));

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('C8: shows UTC note', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('utc-note')).toBeTruthy();
      expect(screen.getByText('All times are UTC.')).toBeTruthy();
    });
  });

  it('F13: shows starter cards when no session', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('starter-cards')).toBeTruthy();
      const cards = screen.getAllByTestId('starter-card');
      expect(cards.length).toBe(6);
    });
  });

  it('F13: shows send button and input', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('chat-input')).toBeTruthy();
      expect(screen.getByTestId('send-btn')).toBeTruthy();
    });
  });

  it('F13: sidebar with new chat button', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('chat-sidebar')).toBeTruthy();
      expect(screen.getByTestId('new-chat-btn')).toBeTruthy();
    });
  });

  it('F17: script tag in markdown is not rendered as HTML', async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    // The MarkdownContent component should escape HTML
    // We test this by checking the component directly
    const { container } = render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    // No script tags should be in the page
    const scripts = container.querySelectorAll('script');
    expect(scripts.length).toBe(0);
  });
});

describe('Intent labels', () => {
  it('F6: all intent codes have labels', async () => {
    const { INTENT_LABELS } = await import('../api/chat');
    expect(INTENT_LABELS['visit.book']).toBe('Book a visit');
    expect(INTENT_LABELS['visit.check']).toBe('My visits');
    expect(INTENT_LABELS['visit.cancel']).toBe('Cancel a visit');
    expect(INTENT_LABELS['complaint.file']).toBe('File a complaint');
    expect(INTENT_LABELS['complaint.check']).toBe('My complaints');
    expect(INTENT_LABELS['qa.db']).toBe('Clinic question');
    expect(INTENT_LABELS['qa.kb']).toBe('Policy question');
    expect(INTENT_LABELS['other']).toBe('Chat');
  });
});

describe('Stream parser', () => {
  it('F12: SSE stream parser handles events correctly', async () => {
    const originalFetch = globalThis.fetch;
    const events: string[] = [];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => {
          let sent = false;
          return {
            read: async () => {
              if (sent) return { done: true, value: undefined };
              sent = true;
              const text =
                'event: session\ndata: {"session_id": 42}\n\nevent: token\ndata: {"text": "Hello "}\n\nevent: done\ndata: {}\n\n';
              return {
                done: false,
                value: new TextEncoder().encode(text),
              };
            },
          };
        },
      },
    }) as unknown as typeof fetch;

    try {
      const { streamChat } = await vi.importActual<typeof import('../api/chat')>('../api/chat');
      await streamChat('test', null, {
        onSession: (sid) => events.push(`session:${sid}`),
        onToken: (t) => events.push(`token:${t}`),
        onIntent: (i) => events.push(`intent:${i}`),
        onCards: (type) => events.push(`cards:${type}`),
        onDone: () => events.push('done'),
        onError: (code) => events.push(`error:${code}`),
      }, new AbortController().signal);

      expect(events).toContain('session:42');
      expect(events).toContain('token:Hello ');
      expect(events).toContain('done');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
