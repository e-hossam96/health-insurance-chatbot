import type { ReactNode } from 'react';

export const APP_NAME = 'Health Insurance Chatbot';

export function LogoMark({ size = 28 }: { size?: number }): ReactNode {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#6A9BD1" />
      <path d="M8 9h16a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-9l-5 4v-4H8a3 3 0 0 1-3-3v-8a3 3 0 0 1 3-3z" fill="#001F3F" />
      <path d="M15 12h2v3h3v2h-3v3h-2v-3h-3v-2h3z" fill="#F0F4F8" />
    </svg>
  );
}

export function Logo({ tone = 'light', size = 28 }: { tone?: 'light' | 'dark'; size?: number }): ReactNode {
  return (
    <span className="inline-flex items-center gap-2" data-testid="app-logo">
      <LogoMark size={size} />
      <span className={`font-semibold tracking-tight ${tone === 'dark' ? 'text-brand-50' : 'text-brand-900'}`}>
        Health Insurance <span className="text-brand-400">Chatbot</span>
      </span>
    </span>
  );
}
