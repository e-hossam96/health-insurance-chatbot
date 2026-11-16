import type { ReactNode } from 'react';
import { type ChatSession, intentLabel, relativeTime } from '../../api/chat';

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
    <aside className="w-64 shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col" data-testid="chat-sidebar">
      <button
        type="button"
        onClick={onNewChat}
        className="m-2 p-2 text-sm bg-brand-400 text-brand-900 rounded hover:bg-brand-500"
        data-testid="new-chat-btn"
      >
        + New chat
      </button>
      <div className="flex-1 overflow-y-auto">
        {sessions.map(s => (
          <button
            type="button"
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`w-full text-left p-3 border-b border-gray-200 hover:bg-gray-100 ${
              s.id === activeSessionId ? 'bg-brand-50' : ''
            }`}
            data-testid="session-item"
          >
            <div className="text-sm font-medium truncate" data-testid="session-label">
              {intentLabel(s.intent)}
            </div>
            {s.first_user_message && (
              <div className="text-xs text-gray-500 truncate">{preview(s.first_user_message)}</div>
            )}
            <div className="text-xs text-gray-400">{relativeTime(s.last_message_at, now)}</div>
          </button>
        ))}
      </div>
    </aside>
  );
}
