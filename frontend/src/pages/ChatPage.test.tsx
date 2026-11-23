import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ChatMessage, ChatSession, StreamEvent } from '../api/chat';
import { ChatPage } from './ChatPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'user1', role: 'user', has_profile: true, mode: 'user' },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/auth', () => ({ logout: vi.fn(), setMode: vi.fn() }));

vi.mock('../api/chat', async importOriginal => {
  const actual = await importOriginal<typeof import('../api/chat')>();
  return { ...actual, getSessions: vi.fn(), getMessages: vi.fn(), streamChat: vi.fn() };
});

vi.mock('../api/visits', () => ({
  getMyVisits: vi.fn().mockResolvedValue([]),
  getMyComplaints: vi.fn().mockResolvedValue([]),
  cancelVisit: vi.fn(),
  bookVisit: vi.fn(),
  fileComplaint: vi.fn(),
}));

const chatApi = await import('../api/chat');
const visitsApi = await import('../api/visits');
const streamChat = vi.mocked(chatApi.streamChat);
const getSessions = vi.mocked(chatApi.getSessions);
const getMessages = vi.mocked(chatApi.getMessages);
const bookVisit = vi.mocked(visitsApi.bookVisit);

const DOCTOR_CARDS: StreamEvent = {
  event: 'cards',
  cards: {
    type: 'doctors',
    items: [
      { slot_id: 1, doctor_name: 'Dr. Sara', specialty: 'Dermatology', clinic: 'Cairo Clinic', location: 'Cairo', start_at: '2026-12-15T10:00:00Z' },
      { slot_id: 2, doctor_name: 'Dr. Omar', specialty: 'Dermatology', clinic: 'Nile Medical', location: 'Cairo', start_at: '2026-12-16T14:00:00Z' },
    ],
  },
};

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

type Gate = { open: () => void };

function scriptStream(before: StreamEvent[], after: StreamEvent[] = [], gate?: { current: Gate | null }): void {
  streamChat.mockImplementationOnce(async (_message, _sessionId, onEvent, signal) => {
    for (const event of before) onEvent(event);
    if (gate) {
      await new Promise<void>((resolve, reject) => {
        gate.current = { open: resolve };
        signal.addEventListener('abort', () => reject(abortError()));
      });
    }
    for (const event of after) onEvent(event);
  });
}

function renderChat(path = '/chat'): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:sessionId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function input(): HTMLInputElement {
  return screen.getByTestId('chat-input') as HTMLInputElement;
}

async function send(text: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(input(), text);
  await user.click(screen.getByTestId('send-btn'));
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSessions.mockResolvedValue([]);
    getMessages.mockResolvedValue([]);
  });

  it('C8: shows the UTC note', async () => {
    renderChat();
    expect(await screen.findByText('All times are UTC.')).toBeTruthy();
  });

  it('F17: the message box takes its direction from the text, so Arabic types right to left', async () => {
    renderChat();
    expect((await screen.findByTestId('chat-input')).getAttribute('dir')).toBe('auto');
  });

  it('F1: shows the six starter cards in order on an empty chat', async () => {
    renderChat();
    const cards = await screen.findAllByTestId('starter-card');
    expect(cards.map(c => c.textContent)).toEqual([
      'Book a clinic visit',
      'Check my visits',
      'Cancel a visit',
      'File a complaint',
      'Check my complaints',
      'Ask a policy question',
    ]);
  });

  it('F1: a starter card sends its fixed text as the first message', async () => {
    scriptStream([{ event: 'session', session_id: 3 }, { event: 'token', text: 'Sure.' }, { event: 'done' }]);
    renderChat();
    await userEvent.setup().click((await screen.findAllByTestId('starter-card'))[0]);
    await waitFor(() => expect(streamChat).toHaveBeenCalledOnce());
    expect(streamChat.mock.calls[0][0]).toBe("I'd like to book a clinic visit.");
    expect(streamChat.mock.calls[0][1]).toBeNull();
    expect(await screen.findByText('Sure.')).toBeTruthy();
  });

  it('F1: the session id from the stream is used for the next turn', async () => {
    scriptStream([{ event: 'session', session_id: 9 }, { event: 'token', text: 'One.' }, { event: 'done' }]);
    scriptStream([{ event: 'session', session_id: 9 }, { event: 'token', text: 'Two.' }, { event: 'done' }]);
    renderChat();
    await send('first');
    await screen.findByText('One.');
    await send('second');
    await screen.findByText('Two.');
    expect(streamChat.mock.calls[1][1]).toBe(9);
    expect(screen.getAllByTestId('msg-user').map(m => m.textContent)).toEqual(['first', 'second']);
  });

  it('F6: the sidebar shows the mapped intent label, New chat for null', async () => {
    const sessions: ChatSession[] = [
      { id: 1, intent: 'qa.kb', created_at: '2026-11-15T10:00:00Z', last_message_at: '2026-11-15T10:00:00Z', first_user_message: 'What does my insurance cover?' },
      { id: 2, intent: null, created_at: '2026-11-15T09:00:00Z', last_message_at: '2026-11-15T09:00:00Z', first_user_message: 'hi' },
    ];
    getSessions.mockResolvedValue(sessions);
    renderChat();
    await waitFor(() => {
      expect(screen.getAllByTestId('session-label').map(l => l.textContent)).toEqual(['Policy question', 'New chat']);
    });
  });

  it('F17: a script tag in streamed text is not rendered', async () => {
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: '<script>alert("xss")</script>\n\n**safe**' }, { event: 'done' }]);
    renderChat();
    await send('hello');
    const reply = await screen.findByTestId('msg-assistant');
    expect(document.querySelector('script')).toBeNull();
    expect(reply.querySelector('strong')?.textContent).toBe('safe');
  });

  it('F13: input is disabled and Send becomes Stop while streaming', async () => {
    const gate: { current: Gate | null } = { current: null };
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'streaming' }], [{ event: 'done' }], gate);
    renderChat();
    await send('hello');
    await waitFor(() => expect(input().disabled).toBe(true));
    expect(screen.getByTestId('stop-btn')).toBeTruthy();
    expect(screen.queryByTestId('send-btn')).toBeNull();
    await act(async () => gate.current?.open());
    await waitFor(() => expect(input().disabled).toBe(false));
    expect(screen.getByTestId('send-btn')).toBeTruthy();
  });

  it('F12: cards render only after the turn finishes streaming', async () => {
    const gate: { current: Gate | null } = { current: null };
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'Here are options.' }, DOCTOR_CARDS], [{ event: 'done' }], gate);
    renderChat();
    await send('book');
    await screen.findByText('Here are options.');
    expect(screen.queryByTestId('doctor-card')).toBeNull();
    await act(async () => gate.current?.open());
    expect(await screen.findAllByTestId('doctor-card')).toHaveLength(2);
  });

  it('F13: older cards stay visible but disabled while the next turn streams', async () => {
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'Options.' }, DOCTOR_CARDS, { event: 'done' }]);
    const gate: { current: Gate | null } = { current: null };
    scriptStream([{ event: 'token', text: 'Thinking' }], [{ event: 'done' }], gate);
    renderChat();
    await send('book');
    const bookButtons = (await screen.findAllByTestId('book-btn')) as HTMLButtonElement[];
    expect(bookButtons.every(b => !b.disabled)).toBe(true);
    await send('more');
    await waitFor(() => expect(bookButtons.every(b => b.disabled)).toBe(true));
    await act(async () => gate.current?.open());
    await waitFor(() => expect(bookButtons.every(b => !b.disabled)).toBe(true));
  });

  it('F16: Stop removes the unsent turn and puts the text back in the input', async () => {
    const gate: { current: Gate | null } = { current: null };
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'partial' }], [{ event: 'done' }], gate);
    renderChat();
    await send('please stop');
    await screen.findByText('partial');
    await userEvent.setup().click(screen.getByTestId('stop-btn'));
    await waitFor(() => expect(input().value).toBe('please stop'));
    expect(input().disabled).toBe(false);
    expect(screen.queryByText('partial')).toBeNull();
    expect(screen.queryByTestId('msg-user')).toBeNull();
    expect(screen.queryByTestId('chat-error')).toBeNull();
    const signal = streamChat.mock.calls[0][3];
    expect(signal.aborted).toBe(true);
  });

  it('F3: a failed first turn drops its session and Retry resends the message once in a new one', async () => {
    scriptStream([{ event: 'session', session_id: 4 }, { event: 'error', code: 'turn_error', message: 'Something went wrong.' }]);
    scriptStream([{ event: 'session', session_id: 4 }, { event: 'token', text: 'Recovered.' }, { event: 'done' }]);
    renderChat();
    await send('trigger error');
    expect(await screen.findByText('Something went wrong.')).toBeTruthy();
    await userEvent.setup().click(screen.getByTestId('retry-btn'));
    await screen.findByText('Recovered.');
    expect(streamChat.mock.calls[1][0]).toBe('trigger error');
    expect(streamChat.mock.calls[1][1]).toBeNull();
    expect(screen.getAllByTestId('msg-user')).toHaveLength(1);
    expect(screen.queryByTestId('chat-error')).toBeNull();
  });

  it('F15: a rejected request shows the server message', async () => {
    streamChat.mockRejectedValueOnce(new chatApi.ChatRequestError(429, 'rate_limited', 'Too many messages.'));
    renderChat();
    await send('hello');
    expect(await screen.findByText('Too many messages.')).toBeTruthy();
    expect(screen.getByTestId('retry-btn')).toBeTruthy();
  });

  it('D6: booking appends the static messages and marks the card booked', async () => {
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'Options.' }, DOCTOR_CARDS, { event: 'done' }]);
    bookVisit.mockResolvedValueOnce({
      visit: { id: 10, status: 'scheduled' },
      messages: [
        { id: 50, session_id: 1, role: 'user', content: 'Book Dr. Sara on Tue 15 Dec, 10:00 UTC.' },
        { id: 53, session_id: 1, role: 'assistant', content: 'Your visit is booked.' },
      ],
    });
    renderChat();
    await send('book');
    await userEvent.setup().click((await screen.findAllByTestId('book-btn'))[0]);
    expect(bookVisit).toHaveBeenCalledWith(1, 1);
    expect(await screen.findByTestId('booked-badge')).toBeTruthy();
    expect(screen.getByText('Book Dr. Sara on Tue 15 Dec, 10:00 UTC.')).toBeTruthy();
    expect(screen.getByText('Your visit is booked.')).toBeTruthy();
  });

  it('D7: a taken slot sends "Show me other options." when asked', async () => {
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'Options.' }, DOCTOR_CARDS, { event: 'done' }]);
    scriptStream([{ event: 'token', text: 'Here are others.' }, { event: 'done' }]);
    bookVisit.mockRejectedValueOnce({ status: 409, error: { code: 'slot_taken', message: 'This slot was just taken.' } });
    renderChat();
    await send('book');
    const user = userEvent.setup();
    await user.click((await screen.findAllByTestId('book-btn'))[0]);
    await user.click(await screen.findByTestId('show-other-btn'));
    await screen.findByText('Here are others.');
    expect(streamChat.mock.calls[1][0]).toBe('Show me other options.');
  });

  it('F17: a replayed transcript and the sidebar subtitle never render HTML', async () => {
    getSessions.mockResolvedValue([
      { id: 5, intent: 'qa.kb', created_at: '2026-11-15T10:00:00Z', last_message_at: '2026-11-15T10:00:00Z', first_user_message: '<img src=x onerror="window.hacked=1">hello' },
    ]);
    getMessages.mockResolvedValue([
      { id: 1, session_id: 5, role: 'user', content: '<script>window.hacked=1</script>my question' },
      { id: 4, session_id: 5, role: 'assistant', content: 'Answer <iframe src="https://evil.test"></iframe><img src=x onerror="window.hacked=1"> **bold**' },
    ]);
    renderChat('/chat/5');
    const reply = await screen.findByTestId('msg-assistant');
    await waitFor(() => expect(screen.getAllByTestId('session-label').length).toBe(1));
    expect(document.querySelector('script, iframe, img')).toBeNull();
    expect(reply.querySelector('strong')?.textContent).toBe('bold');
    expect(screen.getByTestId('msg-user').textContent).toBe('<script>window.hacked=1</script>my question');
  });

  it('F12: reopening a session loads the transcript without cards', async () => {
    const transcript: ChatMessage[] = [
      { id: 1, session_id: 5, role: 'user', content: 'I need a dermatologist' },
      { id: 4, session_id: 5, role: 'assistant', content: 'Dr. Sara is free on Tuesday.' },
    ];
    getMessages.mockResolvedValue(transcript);
    renderChat('/chat/5');
    expect(await screen.findByText('Dr. Sara is free on Tuesday.')).toBeTruthy();
    expect(getMessages).toHaveBeenCalledWith(5);
    expect(screen.queryByTestId('chat-cards')).toBeNull();
    expect(screen.queryByTestId('starter-cards')).toBeNull();
  });

  it('F1: a new session does not reload its transcript and wipe the live turn', async () => {
    scriptStream([{ event: 'session', session_id: 12 }, { event: 'token', text: 'Hello there.' }, { event: 'done' }]);
    renderChat();
    await send('hi');
    await screen.findByText('Hello there.');
    expect(getMessages).not.toHaveBeenCalled();
    expect(screen.getByText('hi')).toBeTruthy();
  });

  it('F1: loading the chat page creates no session and sends nothing', async () => {
    renderChat();
    await screen.findAllByTestId('starter-card');
    expect(getSessions).toHaveBeenCalled();
    expect(streamChat).not.toHaveBeenCalled();
    expect(getMessages).not.toHaveBeenCalled();
  });

  it('F1: New chat clears the view without a request and the next send starts a session', async () => {
    getMessages.mockResolvedValue([
      { id: 1, session_id: 5, role: 'user', content: 'old question' },
      { id: 2, session_id: 5, role: 'assistant', content: 'old answer' },
    ]);
    scriptStream([{ event: 'session', session_id: 6 }, { event: 'token', text: 'Fresh.' }, { event: 'done' }]);
    renderChat('/chat/5');
    await screen.findByText('old answer');
    const sessionsCallsBefore = getSessions.mock.calls.length;

    await userEvent.setup().click(screen.getByTestId('new-chat-btn'));

    expect(await screen.findAllByTestId('starter-card')).toHaveLength(6);
    expect(screen.queryByText('old answer')).toBeNull();
    expect(getMessages).toHaveBeenCalledTimes(1);
    expect(getSessions.mock.calls.length).toBe(sessionsCallsBefore);
    expect(streamChat).not.toHaveBeenCalled();

    await send('a new topic');
    await screen.findByText('Fresh.');
    expect(streamChat.mock.calls[0][1]).toBeNull();
  });

  it('F12: cards from a live turn are gone after leaving the session and coming back', async () => {
    getSessions.mockResolvedValue([
      { id: 1, intent: 'visit.book', created_at: '2026-11-15T10:00:00Z', last_message_at: '2026-11-15T10:00:00Z', first_user_message: 'book' },
      { id: 2, intent: 'other', created_at: '2026-11-15T09:00:00Z', last_message_at: '2026-11-15T09:00:00Z', first_user_message: 'hi' },
    ]);
    getMessages.mockImplementation(async sessionId =>
      sessionId === 1
        ? [
            { id: 1, session_id: 1, role: 'user', content: 'book' },
            { id: 4, session_id: 1, role: 'assistant', content: 'Options.' },
          ]
        : [{ id: 9, session_id: 2, role: 'user', content: 'hi' }],
    );
    scriptStream([{ event: 'session', session_id: 1 }, { event: 'token', text: 'Options.' }, DOCTOR_CARDS, { event: 'done' }]);
    renderChat();
    await send('book');
    expect(await screen.findAllByTestId('doctor-card')).toHaveLength(2);

    const user = userEvent.setup();
    await user.click(screen.getAllByTestId('session-item')[1]);
    await screen.findByText('hi', { selector: '[data-testid="msg-user"] *' });
    await user.click(screen.getAllByTestId('session-item')[0]);

    await waitFor(() => expect(getMessages).toHaveBeenLastCalledWith(1));
    expect(await screen.findByText('Options.')).toBeTruthy();
    expect(screen.queryByTestId('doctor-card')).toBeNull();
  });

  it('F3: a failed turn in an existing session keeps the session for Retry', async () => {
    getMessages.mockResolvedValue([
      { id: 1, session_id: 8, role: 'user', content: 'earlier' },
      { id: 2, session_id: 8, role: 'assistant', content: 'earlier answer' },
    ]);
    scriptStream([{ event: 'session', session_id: 8 }, { event: 'error', code: 'turn_error', message: 'Something went wrong.' }]);
    scriptStream([{ event: 'session', session_id: 8 }, { event: 'token', text: 'Second try.' }, { event: 'done' }]);
    renderChat('/chat/8');
    await screen.findByText('earlier answer');
    await send('again');
    await userEvent.setup().click(await screen.findByTestId('retry-btn'));
    await screen.findByText('Second try.');
    expect(streamChat.mock.calls.map(c => c[1])).toEqual([8, 8]);
  });

  it('F16: stopping a new chat forgets its session so the resend starts a new one', async () => {
    const gate: { current: Gate | null } = { current: null };
    scriptStream([{ event: 'session', session_id: 30 }, { event: 'token', text: 'partial' }], [{ event: 'done' }], gate);
    scriptStream([{ event: 'session', session_id: 31 }, { event: 'token', text: 'Fresh answer.' }, { event: 'done' }]);
    renderChat();
    await send('first try');
    await screen.findByText('partial');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('stop-btn'));
    await waitFor(() => expect(input().value).toBe('first try'));
    await user.click(screen.getByTestId('send-btn'));
    await screen.findByText('Fresh answer.');
    expect(streamChat.mock.calls[1][1]).toBeNull();
  });
});
