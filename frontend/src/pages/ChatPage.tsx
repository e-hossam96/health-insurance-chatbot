import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  type ChatMessage,
  type ChatSession,
  INTENT_LABELS,
  STARTER_CARDS,
  getMessages,
  getSessions,
  streamChat,
} from '../api/chat';
import { bookVisit, cancelVisit, fileComplaint } from '../api/visits';
import { Header } from '../components/Header';
import { VisitsDrawer } from '../components/VisitsDrawer';

type CardItem = Record<string, unknown>;

type CardState = {
  type: string;
  items: CardItem[];
  bookedSlotId?: number;
  cancelledVisitId?: number;
  filedVisitId?: number;
  errorSlotId?: number;
  errorVisitId?: number;
  slotTakenId?: number;
};

type LocalMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

export function ChatPage(): ReactNode {
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(
    routeSessionId ? Number(routeSessionId) : null,
  );
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [cards, setCards] = useState<CardState | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const lastMessageRef = useRef('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await getSessions();
      setSessions(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  const loadMessages = useCallback(async (sid: number): Promise<void> => {
    try {
      const data = await getMessages(sid);
      setMessages(
        data.map((m: ChatMessage) => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
        })),
      );
      setCards(null);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (activeSessionId) {
      void loadMessages(activeSessionId);
    } else {
      setMessages([]);
      setCards(null);
    }
  }, [activeSessionId, loadMessages]);

  useEffect(() => {
    if (messagesEndRef.current && 'scrollIntoView' in messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingText]);

  async function sendMessage(text: string): Promise<void> {
    if (!text.trim() || isStreaming) return;

    const userMsg: LocalMessage = { id: `temp-${Date.now()}`, role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setStreamingText('');
    setCards(null);
    setError(null);
    setIsStreaming(true);
    setInput('');
    lastMessageRef.current = text;

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(text, activeSessionId, {
        onSession: (sid: number) => {
          if (!activeSessionId) {
            setActiveSessionId(sid);
            navigate(`/chat/${sid}`, { replace: true });
          }
        },
        onToken: (token: string) => {
          setStreamingText(prev => prev + token);
        },
        onIntent: () => {
          // intent tracked server-side; no client action needed
        },
        onCards: (type: string, items: CardItem[]) => {
          setCards({ type, items });
        },
        onDone: () => {
          setStreamingText(prev => {
            if (prev) {
              const assistantMsg: LocalMessage = {
                id: `assistant-${Date.now()}`,
                role: 'assistant',
                content: prev.trim(),
              };
              setMessages(msgs => [...msgs, assistantMsg]);
            }
            return '';
          });
          void refreshSessions();
        },
        onError: (_code: string, message: string) => {
          setError(message || 'Something went wrong.');
        },
      }, controller.signal);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // F16: user stopped - restore input
        setInput(text);
        setMessages(prev => prev.filter(m => m.id !== userMsg.id));
      } else {
        setError('Something went wrong.');
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  function handleStop(): void {
    abortRef.current?.abort();
  }

  function handleRetry(): void {
    setError(null);
    if (lastMessageRef.current) {
      void sendMessage(lastMessageRef.current);
    }
  }

  function handleNewChat(): void {
    setActiveSessionId(null);
    setMessages([]);
    setCards(null);
    setError(null);
    setStreamingText('');
    navigate('/chat', { replace: true });
  }

  function handleSelectSession(sid: number): void {
    setActiveSessionId(sid);
    navigate(`/chat/${sid}`, { replace: true });
  }

  async function handleBookSlot(slotId: number): Promise<void> {
    if (!activeSessionId) return;
    try {
      const resp = await bookVisit(activeSessionId, slotId);
      setCards(prev =>
        prev ? { ...prev, bookedSlotId: slotId } : prev,
      );
      // Append static messages
      if (resp.messages?.length) {
        const userMsg = resp.messages.find((m: { role: string }) => m.role === 'user');
        const assistantMsg = resp.messages.filter((m: { role: string; content: string }) => m.role === 'assistant' && m.content).pop();
        if (userMsg) setMessages(prev => [...prev, { id: `static-u-${Date.now()}`, role: 'user', content: userMsg.content }]);
        if (assistantMsg) setMessages(prev => [...prev, { id: `static-a-${Date.now()}`, role: 'assistant', content: assistantMsg.content }]);
      }
    } catch (err: unknown) {
      const e = err as { error?: { code?: string } };
      if (e.error?.code === 'slot_taken') {
        setCards(prev => prev ? { ...prev, slotTakenId: slotId } : prev);
      } else {
        setCards(prev => prev ? { ...prev, errorSlotId: slotId } : prev);
      }
    }
  }

  async function handleCancelVisit(visitId: number): Promise<void> {
    if (!activeSessionId) return;
    try {
      await cancelVisit(visitId, activeSessionId);
      setCards(prev => prev ? { ...prev, cancelledVisitId: visitId } : prev);
    } catch {
      setCards(prev => prev ? { ...prev, errorVisitId: visitId } : prev);
    }
  }

  async function handleFileComplaint(visitId: number, description: string): Promise<void> {
    if (!activeSessionId) return;
    try {
      await fileComplaint(activeSessionId, visitId, description);
      setCards(prev => prev ? { ...prev, filedVisitId: visitId } : prev);
    } catch {
      setCards(prev => prev ? { ...prev, errorVisitId: visitId } : prev);
    }
  }

  const showStarters = messages.length === 0 && !activeSessionId;

  return (
    <div className="min-h-screen flex flex-col">
      <Header onVisitsClick={() => setDrawerOpen(true)} />
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 border-r border-gray-200 bg-gray-50 flex flex-col" data-testid="chat-sidebar">
          <button
            onClick={handleNewChat}
            className="m-2 p-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            data-testid="new-chat-btn"
          >
            + New chat
          </button>
          <div className="flex-1 overflow-y-auto">
            {sessions.map(s => (
              <button
                key={s.id}
                onClick={() => handleSelectSession(s.id)}
                className={`w-full text-left p-3 border-b border-gray-200 hover:bg-gray-100 ${
                  s.id === activeSessionId ? 'bg-blue-50' : ''
                }`}
                data-testid="session-item"
              >
                <div className="text-sm font-medium truncate">
                  {s.intent ? (INTENT_LABELS[s.intent] ?? s.intent) : 'New chat'}
                </div>
                {s.first_user_message && (
                  <div className="text-xs text-gray-500 truncate">{s.first_user_message}</div>
                )}
              </button>
            ))}
          </div>
        </aside>

        {/* Chat area */}
        <main className="flex-1 flex flex-col" data-testid="chat-main">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {showStarters && (
              <div data-testid="starter-cards">
                <p className="text-gray-500 text-center mb-4">How can I help today?</p>
                <div className="grid grid-cols-2 gap-3 max-w-lg mx-auto">
                  {STARTER_CARDS.map(card => (
                    <button
                      key={card.label}
                      onClick={() => void sendMessage(card.message)}
                      className="p-3 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 text-left"
                      data-testid="starter-card"
                      disabled={isStreaming}
                    >
                      {card.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(m => (
              <div
                key={m.id}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-xl px-4 py-2 rounded-lg ${
                    m.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-900'
                  }`}
                  data-testid={`msg-${m.role}`}
                >
                  <MarkdownContent content={m.content} />
                </div>
              </div>
            ))}

            {streamingText && (
              <div className="flex justify-start">
                <div className="max-w-xl px-4 py-2 rounded-lg bg-gray-100 text-gray-900" data-testid="msg-streaming">
                  <MarkdownContent content={streamingText} />
                </div>
              </div>
            )}

            {cards && (
              <div className="flex flex-wrap gap-3" data-testid="chat-cards">
                {cards.type === 'doctors' && cards.items.map((item, i) => (
                  <DoctorCard
                    key={i}
                    item={item}
                    disabled={isStreaming || cards.bookedSlotId !== undefined}
                    booked={cards.bookedSlotId === (item.slot_id as number)}
                    slotTaken={cards.slotTakenId === (item.slot_id as number)}
                    error={cards.errorSlotId === (item.slot_id as number)}
                    onBook={() => void handleBookSlot(item.slot_id as number)}
                    onShowOther={() => void sendMessage('Show me other options.')}
                  />
                ))}
                {cards.type === 'cancel_confirm' && cards.items.map((item, i) => (
                  <CancelCard
                    key={i}
                    item={item}
                    disabled={isStreaming || cards.cancelledVisitId !== undefined}
                    cancelled={cards.cancelledVisitId === (item.visit_id as number)}
                    error={cards.errorVisitId === (item.visit_id as number)}
                    onCancel={() => void handleCancelVisit(item.visit_id as number)}
                  />
                ))}
                {cards.type === 'visits_for_complaint' && cards.items.map((item, i) => (
                  <ComplaintCard
                    key={i}
                    item={item}
                    disabled={isStreaming || cards.filedVisitId !== undefined}
                    filed={cards.filedVisitId === (item.visit_id as number)}
                    error={cards.errorVisitId === (item.visit_id as number)}
                    onFile={(desc: string) => void handleFileComplaint(item.visit_id as number, desc)}
                  />
                ))}
              </div>
            )}

            {error && (
              <div className="flex justify-start" data-testid="chat-error">
                <div className="px-4 py-2 bg-red-50 text-red-700 rounded-lg">
                  {error}
                  <button
                    onClick={handleRetry}
                    className="ml-2 underline"
                    data-testid="retry-btn"
                  >
                    Retry
                  </button>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="border-t border-gray-200 p-4">
            <form
              onSubmit={e => {
                e.preventDefault();
                void sendMessage(input);
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Type your message..."
                className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
                disabled={isStreaming}
                data-testid="chat-input"
              />
              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStop}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                  data-testid="stop-btn"
                >
                  Stop
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                  data-testid="send-btn"
                >
                  Send
                </button>
              )}
            </form>
            <p className="text-xs text-gray-400 mt-1" data-testid="utc-note">All times are UTC.</p>
          </div>
        </main>
      </div>
      <VisitsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}

// F17: render Markdown without raw HTML
function MarkdownContent({ content }: { content: string }): ReactNode {
  // Simple markdown: bold, italic, lists, code
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const html = escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-gray-200 px-1 rounded text-sm">$1</code>')
    .replace(/\n/g, '<br />');
  return <span dangerouslySetInnerHTML={{ __html: html }} data-testid="markdown-content" />;
}

function DoctorCard({
  item,
  disabled,
  booked,
  slotTaken,
  error,
  onBook,
  onShowOther,
}: {
  item: CardItem;
  disabled: boolean;
  booked: boolean;
  slotTaken: boolean;
  error: boolean;
  onBook: () => void;
  onShowOther: () => void;
}): ReactNode {
  return (
    <div className="border border-gray-200 rounded-lg p-3 w-56" data-testid="doctor-card">
      <div className="font-medium text-sm">{item.doctor_name as string}</div>
      <div className="text-xs text-gray-500">{item.specialty as string}</div>
      <div className="text-xs text-gray-500">{item.clinic as string}</div>
      <div className="text-xs text-gray-500">{item.location as string}</div>
      <div className="text-xs text-gray-600 mt-1">{item.start_at as string} UTC</div>
      {booked ? (
        <span className="inline-block mt-2 text-xs text-green-700 bg-green-100 px-2 py-1 rounded" data-testid="booked-badge">
          Booked
        </span>
      ) : slotTaken ? (
        <div className="mt-2">
          <span className="text-xs text-red-600">This slot was just taken</span>
          <button
            onClick={onShowOther}
            className="ml-1 text-xs text-blue-600 underline"
            data-testid="show-other-btn"
          >
            Show other options
          </button>
        </div>
      ) : error ? (
        <div className="mt-2">
          <span className="text-xs text-red-600">Could not book. Try again.</span>
          <button onClick={onBook} className="ml-1 text-xs text-blue-600 underline" data-testid="card-retry-btn">
            Retry
          </button>
        </div>
      ) : (
        <button
          onClick={onBook}
          disabled={disabled}
          className="mt-2 text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
          data-testid="book-btn"
        >
          Book
        </button>
      )}
    </div>
  );
}

function CancelCard({
  item,
  disabled,
  cancelled,
  error,
  onCancel,
}: {
  item: CardItem;
  disabled: boolean;
  cancelled: boolean;
  error: boolean;
  onCancel: () => void;
}): ReactNode {
  return (
    <div className="border border-gray-200 rounded-lg p-3 w-56" data-testid="cancel-card">
      <div className="font-medium text-sm">{item.doctor_name as string}</div>
      <div className="text-xs text-gray-500">{item.specialty as string}</div>
      <div className="text-xs text-gray-500">{item.clinic as string}</div>
      <div className="text-xs text-gray-600 mt-1">{item.start_at as string} UTC</div>
      {cancelled ? (
        <span className="inline-block mt-2 text-xs text-red-700 bg-red-100 px-2 py-1 rounded" data-testid="cancelled-badge">
          Cancelled
        </span>
      ) : error ? (
        <div className="mt-2">
          <span className="text-xs text-red-600">Could not cancel.</span>
          <button onClick={onCancel} className="ml-1 text-xs text-blue-600 underline">Retry</button>
        </div>
      ) : (
        <button
          onClick={onCancel}
          disabled={disabled}
          className="mt-2 text-xs bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50"
          data-testid="cancel-confirm-btn"
        >
          Yes, cancel visit
        </button>
      )}
    </div>
  );
}

function ComplaintCard({
  item,
  disabled,
  filed,
  error,
  onFile,
}: {
  item: CardItem;
  disabled: boolean;
  filed: boolean;
  error: boolean;
  onFile: (description: string) => void;
}): ReactNode {
  const [desc, setDesc] = useState('');
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg p-3 w-64" data-testid="complaint-card">
      <div className="font-medium text-sm">{item.doctor_name as string}</div>
      <div className="text-xs text-gray-500">{item.start_at as string} UTC</div>
      {filed ? (
        <span className="inline-block mt-2 text-xs text-green-700 bg-green-100 px-2 py-1 rounded" data-testid="filed-badge">
          Complaint filed
        </span>
      ) : error ? (
        <span className="text-xs text-red-600">Failed to file complaint.</span>
      ) : expanded ? (
        <div className="mt-2">
          <textarea
            value={desc}
            onChange={e => setDesc(e.target.value)}
            placeholder="What happened?"
            className="w-full border border-gray-300 rounded p-1 text-sm"
            rows={2}
            data-testid="complaint-desc"
          />
          <div className="flex gap-2 mt-1">
            <button
              onClick={() => onFile(desc)}
              disabled={disabled || !desc.trim()}
              className="text-xs bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
              data-testid="submit-complaint-btn"
            >
              Submit complaint
            </button>
            <button
              onClick={() => setExpanded(false)}
              className="text-xs text-gray-500"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setExpanded(true)}
          disabled={disabled}
          className="mt-2 text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
          data-testid="select-visit-btn"
        >
          Select
        </button>
      )}
    </div>
  );
}
