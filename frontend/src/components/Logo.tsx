import type { ReactNode } from 'react';
import { ChatPlusIcon } from './icons';

export const APP_NAME = 'Health Insurance Chatbot';

export function LogoMark({ size = 36 }: { size?: number }): ReactNode {
  return (
    <span
      className="grid flex-none place-items-center rounded-control bg-accent text-on-accent"
      style={{ width: size, height: size }}
    >
      <ChatPlusIcon size={Math.round(size * 0.58)} />
    </span>
  );
}

export function Logo({ size = 36 }: { size?: number }): ReactNode {
  return (
    <span className="inline-flex items-center gap-3" data-testid="app-logo">
      <LogoMark size={size} />
      <span className="text-[1.05rem] font-bold tracking-tight text-fg">
        {APP_NAME}
      </span>
    </span>
  );
}
