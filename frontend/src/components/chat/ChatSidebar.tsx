import type { ReactNode } from 'react';
import { type ChatSession, intentLabel, relativeTime } from '../../api/chat';
import { PlusIcon } from '../icons';

const PREVIEW_LENGTH = 40;

function preview(text: string): string {
  return text.length > PREVIEW_LENGTH ? `${text.slice(0, PREVIEW_LENGTH).trimEnd()}…` : text;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  now,
  loadFailed,
  open,
  onClose,
  onRetry,
  onSelect,
  onNewChat,
}: {
  sessions: ChatSession[];
  activeSessionId: number | null;
  now: Date;
  loadFailed: boolean;
  open: boolean;
  onClose: () => void;
  onRetry: () => void;
  onSelect: (sessionId: number) => void;
  onNewChat: () => void;
}): ReactNode {
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-overlay md:hidden" onClick={onClose} data-testid="sidebar-backdrop" />}
      <aside
        className={`${open ? 'fixed inset-y-0 left-0 z-40 flex' : 'hidden'} w-64 shrink-0 flex-col border-r border-line bg-card md:static md:z-auto md:flex`}
        data-testid="chat-sidebar"
      >
        <button
          type="button"
          onClick={onNewChat}
          className="btn btn-sm m-3 py-2"
          data-testid="new-chat-btn"
        >
          <PlusIcon />
          New chat
        </button>
        {loadFailed && (
          <p className="alert error mx-3 mb-2 text-xs" data-testid="sessions-error">
            Could not load your chats.
            <button type="button" onClick={onRetry} className="link-btn ml-1 underline" data-testid="sessions-retry-btn">
              Retry
            </button>
          </p>
        )}
        <div className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
          {sessions.map(s => (
            <button
              type="button"
              key={s.id}
              onClick={() => onSelect(s.id)}
              aria-current={s.id === activeSessionId ? 'true' : undefined}
              className={`w-full rounded-control px-3 py-2.5 text-left transition-colors ${
                s.id === activeSessionId ? 'bg-surface shadow-[inset_3px_0_0_var(--accent)]' : 'hover:bg-surface'
              }`}
              data-testid="session-item"
            >
              <div
                dir="auto"
                className={`truncate text-sm font-medium ${s.id === activeSessionId ? 'font-semibold' : ''}`}
                data-testid="session-title"
              >
                {s.first_user_message ? preview(s.first_user_message) : intentLabel(s.intent)}
              </div>
              <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                <span className="badge px-2! py-0!" data-testid="session-label">{intentLabel(s.intent)}</span>
                <span>{relativeTime(s.last_message_at, now)}</span>
              </div>
            </button>
          ))}
        </div>
      </aside>
    </>
  );
}
