import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ChatSession } from '../../api/chat';
import { ChatSidebar } from './ChatSidebar';

const NOW = new Date('2026-11-17T12:00:00Z');

function session(id: number, firstMessage: string): ChatSession {
  return { id, intent: null, first_user_message: firstMessage, created_at: '2026-11-17T11:00:00Z', last_message_at: '2026-11-17T11:59:30Z' };
}

function renderSidebar(activeSessionId: number | null): { onSelect: ReturnType<typeof vi.fn>; onNewChat: ReturnType<typeof vi.fn> } {
  const onSelect = vi.fn();
  const onNewChat = vi.fn();
  render(
    <ChatSidebar
      sessions={[session(1, 'I need a dermatologist'), session(2, 'Is physiotherapy covered?')]}
      activeSessionId={activeSessionId}
      now={NOW}
      loadFailed={false}
      open={false}
      onClose={vi.fn()}
      onRetry={vi.fn()}
      onSelect={onSelect}
      onNewChat={onNewChat}
    />,
  );
  return { onSelect, onNewChat };
}

describe('ChatSidebar', () => {
  it('F1: marks only the open session as current', () => {
    renderSidebar(2);
    const [first, second] = screen.getAllByTestId('session-item');
    expect(second).toHaveAttribute('aria-current', 'true');
    expect(first).not.toHaveAttribute('aria-current');
  });

  it('F1: marks no session as current on a new chat', () => {
    renderSidebar(null);
    for (const item of screen.getAllByTestId('session-item')) expect(item).not.toHaveAttribute('aria-current');
  });

  it('F1: New chat and picking a session report back to the page', async () => {
    const user = userEvent.setup();
    const { onSelect, onNewChat } = renderSidebar(1);
    await user.click(screen.getByRole('button', { name: 'New chat' }));
    expect(onNewChat).toHaveBeenCalledTimes(1);
    await user.click(screen.getAllByTestId('session-item')[1]);
    expect(onSelect).toHaveBeenCalledWith(2);
  });
});
