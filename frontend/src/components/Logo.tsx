import type { ReactNode } from 'react';
import { ChatPlusIcon } from './icons';

export const APP_NAME = 'Health Insurance Chatbot';

export function LogoMark({ size = 36 }: { size?: number }): ReactNode {
  return (
    <span
      className="grid flex-none place-items-center rounded-control bg-linear-135 from-accent to-accent-hover text-on-accent shadow-card"
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
        Health Insurance <span className="text-accent">Chatbot</span>
      </span>
    </span>
  );
}
