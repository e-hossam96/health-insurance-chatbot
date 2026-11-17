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
  onSelect,
  onNewChat,
}: {
  sessions: ChatSession[];
  activeSessionId: number | null;
  now: Date;
  onSelect: (sessionId: number) => void;
  onNewChat: () => void;
}): ReactNode {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-card/60" data-testid="chat-sidebar">
      <button
        type="button"
        onClick={onNewChat}
        className="btn btn-sm m-3 py-2"
        data-testid="new-chat-btn"
      >
        <PlusIcon />
        New chat
      </button>
      <div className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {sessions.map(s => (
          <button
            type="button"
            key={s.id}
            onClick={() => onSelect(s.id)}
            aria-current={s.id === activeSessionId ? 'true' : undefined}
            className={`w-full rounded-control px-3 py-2.5 text-left transition-colors ${
              s.id === activeSessionId ? 'bg-accent-soft text-accent' : 'hover:bg-surface'
            }`}
            data-testid="session-item"
          >
            <div className="text-sm font-medium truncate" data-testid="session-label">
              {intentLabel(s.intent)}
            </div>
            {s.first_user_message && (
              <div className="truncate text-xs text-muted">{preview(s.first_user_message)}</div>
            )}
            <div className="text-xs text-muted">{relativeTime(s.last_message_at, now)}</div>
          </button>
        ))}
      </div>
    </aside>
  );
}
