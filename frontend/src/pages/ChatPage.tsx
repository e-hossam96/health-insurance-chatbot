import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  type CardsPayload,
  type ChatSession,
  ChatRequestError,
  STARTER_CARDS,
  getMessages,
  getSessions,
  streamChat,
} from '../api/chat';
import type { ApiError } from '../api/client';
import { type StaticMessage, bookVisit, cancelVisit, fileComplaint } from '../api/visits';
import { Header } from '../components/Header';
import { LogoMark } from '../components/Logo';
import { SendIcon } from '../components/icons';
import { VisitsDrawer } from '../components/VisitsDrawer';
import { ChatCards } from '../components/chat/ChatCards';
import { type CardFailureKind, type CardSetState, INITIAL_CARD_STATE } from '../components/chat/cardState';
import { ChatSidebar } from '../components/chat/ChatSidebar';
import { MarkdownContent } from '../components/chat/MarkdownContent';

type ChatItem =
  | { kind: 'message'; key: string; role: 'user' | 'assistant'; content: string }
  | { kind: 'cards'; key: string; cards: CardsPayload; state: CardSetState };

type TurnError = { userKey: string; text: string; message: string };

const SHOW_OTHER_OPTIONS = 'Show me other options.';
const GENERIC_ERROR = 'Something went wrong.';

let keyCounter = 0;
function nextKey(prefix: string): string {
  keyCounter += 1;
  return `${prefix}-${keyCounter}`;
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === 'object' && value !== null && 'error' in value;
}

function failureKind(err: unknown): CardFailureKind {
  const code = isApiError(err) ? err.error.code : '';
  if (code === 'slot_taken') return 'slot_taken';
  if (code === 'visit_not_cancellable') return 'not_cancellable';
  return 'error';
}

function staticItems(messages: StaticMessage[] | null | undefined): ChatItem[] {
  return (messages ?? [])
    .filter(m => (m.role === 'user' || m.role === 'assistant') && m.content !== '')
    .map(m => ({ kind: 'message', key: `static-${m.id}`, role: m.role as 'user' | 'assistant', content: m.content }));
}

function parseSessionId(param: string | undefined): number | null {
  if (param === undefined) return null;
  const id = Number(param);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function ChatPage(): ReactNode {
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [turnError, setTurnError] = useState<TurnError | null>(null);
  const [input, setInput] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const activeSessionRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async (): Promise<void> => {
    try {
      setSessions(await getSessions());
      setNow(new Date());
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  const activateSession = useCallback((sessionId: number | null): void => {
    abortRef.current?.abort();
    activeSessionRef.current = sessionId;
    setActiveSessionId(sessionId);
    setItems([]);
    setStreamingText('');
    setTurnError(null);
    setLoadFailed(false);
    if (sessionId === null) return;
    void getMessages(sessionId)
      .then(messages => {
        if (activeSessionRef.current !== sessionId) return;
        setItems(messages.map(m => ({ kind: 'message', key: `db-${m.id}`, role: m.role, content: m.content })));
      })
      .catch(() => {
        if (activeSessionRef.current === sessionId) setLoadFailed(true);
      });
  }, []);

  useEffect(() => {
    const sessionId = parseSessionId(routeSessionId);
    if (sessionId === activeSessionRef.current) return;
    activateSession(sessionId);
  }, [routeSessionId, activateSession]);

  useEffect(() => {
    const end = messagesEndRef.current;
    if (end && typeof end.scrollIntoView === 'function') end.scrollIntoView({ behavior: 'smooth' });
  }, [items, streamingText]);

  async function sendMessage(text: string, retryOf?: TurnError): Promise<void> {
    if (text.trim() === '' || isStreaming) return;

    const userKey = nextKey('user');
    setItems(prev => [
      ...(retryOf ? prev.filter(i => i.key !== retryOf.userKey) : prev),
      { kind: 'message', key: userKey, role: 'user', content: text },
    ]);
    setStreamingText('');
    setTurnError(null);
    setIsStreaming(true);
    setInput('');

    const controller = new AbortController();
    abortRef.current = controller;
    const startsNewSession = activeSessionRef.current === null;
    let assistantText = '';
    let pendingCards: CardsPayload | null = null;
    const forgetUnsavedSession = (): void => {
      if (!startsNewSession || activeSessionRef.current === null) return;
      activeSessionRef.current = null;
      setActiveSessionId(null);
      navigate('/chat', { replace: true });
      void refreshSessions();
    };

    try {
      await streamChat(text, activeSessionRef.current, event => {
        if (controller.signal.aborted) return;
        switch (event.event) {
          case 'session':
            if (activeSessionRef.current === null) {
              activeSessionRef.current = event.session_id;
              setActiveSessionId(event.session_id);
              navigate(`/chat/${event.session_id}`, { replace: true });
              void refreshSessions();
            }
            break;
          case 'token':
            assistantText += event.text;
            setStreamingText(assistantText);
            break;
          case 'intent':
            break;
          case 'cards':
            pendingCards = event.cards;
            break;
          case 'done': {
            const finished: ChatItem[] = [];
            if (assistantText.trim() !== '') {
              finished.push({ kind: 'message', key: nextKey('assistant'), role: 'assistant', content: assistantText.trim() });
            }
            if (pendingCards) {
              finished.push({ kind: 'cards', key: nextKey('cards'), cards: pendingCards, state: INITIAL_CARD_STATE });
            }
            setItems(prev => [...prev, ...finished]);
            setStreamingText('');
            void refreshSessions();
            break;
          }
          case 'error':
            setStreamingText('');
            setTurnError({ userKey, text, message: GENERIC_ERROR });
            forgetUnsavedSession();
            break;
        }
      }, controller.signal);
    } catch (err: unknown) {
      setStreamingText('');
      if (controller.signal.aborted) {
        setItems(prev => prev.filter(i => i.key !== userKey));
        if (abortRef.current === controller) {
          setInput(text);
          forgetUnsavedSession();
        }
      } else {
        const message = err instanceof ChatRequestError ? err.message : GENERIC_ERROR;
        setTurnError({ userKey, text, message });
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setIsStreaming(false);
    }
  }

  function updateCards(key: string, update: (state: CardSetState) => CardSetState): void {
    setItems(prev => prev.map(i => (i.kind === 'cards' && i.key === key ? { ...i, state: update(i.state) } : i)));
  }

  async function runCardAction(
    key: string,
    id: number,
    action: (sessionId: number) => Promise<{ messages?: StaticMessage[] | null }>,
  ): Promise<void> {
    const sessionId = activeSessionRef.current;
    if (sessionId === null) return;
    updateCards(key, s => ({ ...s, busyId: id, failure: null }));
    try {
      const response = await action(sessionId);
      updateCards(key, s => ({ ...s, busyId: null, doneId: id }));
      setItems(prev => [...prev, ...staticItems(response.messages)]);
      void refreshSessions();
    } catch (err: unknown) {
      updateCards(key, s => ({ ...s, busyId: null, failure: { id, kind: failureKind(err) } }));
    }
  }

  function handleStop(): void {
    abortRef.current?.abort();
  }

  function handleNewChat(): void {
    activateSession(null);
    setInput('');
    navigate('/chat', { replace: true });
  }

  function handleSelectSession(sessionId: number): void {
    if (sessionId === activeSessionRef.current) return;
    activateSession(sessionId);
    navigate(`/chat/${sessionId}`);
  }

  const showStarters = items.length === 0 && activeSessionId === null && !isStreaming;

  return (
    <div className="h-screen flex flex-col">
      <Header onVisitsClick={() => setDrawerOpen(true)} />
      <div className="flex-1 flex overflow-hidden">
        <ChatSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          now={now}
          onSelect={handleSelectSession}
          onNewChat={handleNewChat}
        />
        <main className="flex-1 flex flex-col min-w-0" data-testid="chat-main">
          <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
            {showStarters && (
              <div data-testid="starter-cards">
                <div className="mx-auto mt-[12vh] mb-6 flex max-w-lg flex-col items-center gap-3 text-center">
                  <LogoMark size={48} />
                  <p className="text-xl font-bold">How can I help today?</p>
                  <p className="text-sm text-muted">Book a visit, check a complaint, ask about clinics, or ask an insurance question such as refunds or spending limits.</p>
                </div>
                <div className="mx-auto grid max-w-lg grid-cols-1 gap-3 sm:grid-cols-2">
                  {STARTER_CARDS.map(card => (
                    <button
                      type="button"
                      key={card.label}
                      onClick={() => void sendMessage(card.message)}
                      className="card rise p-4 text-left text-sm font-medium transition-colors hover:border-accent hover:bg-accent-soft hover:text-accent"
                      data-testid="starter-card"
                    >
                      {card.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {items.map(item =>
              item.kind === 'message' ? (
                <div key={item.key} className={`rise flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-xl px-4 py-2.5 ${
                      item.role === 'user'
                        ? 'rounded-card rounded-br-md bg-accent text-on-accent'
                        : 'rounded-card rounded-bl-md border border-line bg-card shadow-card'
                    }`}
                    data-testid={`msg-${item.role}`}
                  >
                    {item.role === 'user' ? <p dir="auto" className="whitespace-pre-wrap break-words">{item.content}</p> : <MarkdownContent content={item.content} />}
                  </div>
                </div>
              ) : (
                <ChatCards
                  key={item.key}
                  cards={item.cards}
                  state={item.state}
                  locked={isStreaming}
                  onBook={slotId => void runCardAction(item.key, slotId, sid => bookVisit(sid, slotId))}
                  onCancelVisit={visitId => void runCardAction(item.key, visitId, sid => cancelVisit(visitId, sid))}
                  onFileComplaint={(visitId, description) =>
                    void runCardAction(item.key, visitId, sid => fileComplaint(sid, visitId, description))
                  }
                  onShowOther={() => void sendMessage(SHOW_OTHER_OPTIONS)}
                />
              ),
            )}

            {isStreaming && (
              <div className="flex justify-start">
                <div className="max-w-xl rounded-card rounded-bl-md border border-line bg-card px-4 py-2.5 shadow-card" data-testid="msg-streaming">
                  {streamingText === '' ? (
                    <span className="animate-pulse text-muted" data-testid="typing-indicator">…</span>
                  ) : (
                    <MarkdownContent content={streamingText} />
                  )}
                </div>
              </div>
            )}

            {loadFailed && (
              <p className="alert error" data-testid="load-error">Could not load this chat.</p>
            )}

            {turnError && (
              <div className="flex justify-start" data-testid="chat-error">
                <div className="alert error">
                  {turnError.message}
                  <button
                    type="button"
                    onClick={() => void sendMessage(turnError.text, turnError)}
                    className="link-btn ml-2 underline"
                    data-testid="retry-btn"
                  >
                    Retry
                  </button>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
          </div>

          <div className="border-t border-line bg-card/70 px-4 py-3 backdrop-blur">
            <div className="mx-auto w-full max-w-3xl">
            <form
              onSubmit={e => {
                e.preventDefault();
                void sendMessage(input);
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                dir="auto"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Type your message..."
                maxLength={1000}
                className="input flex-1 px-4"
                disabled={isStreaming}
                data-testid="chat-input"
              />
              {isStreaming ? (
                <button
                  key="stop"
                  type="button"
                  onClick={e => {
                    e.preventDefault();
                    handleStop();
                  }}
                  className="btn btn-danger"
                  data-testid="stop-btn"
                >
                  Stop
                </button>
              ) : (
                <button
                  key="send"
                  type="submit"
                  disabled={input.trim() === ''}
                  className="btn"
                  data-testid="send-btn"
                >
                  <SendIcon />
                  Send
                </button>
              )}
            </form>
            <p className="mt-1.5 text-xs text-muted" data-testid="utc-note">All times are UTC.</p>
            </div>
          </div>
        </main>
      </div>
      <VisitsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
