import type { ReactNode } from 'react';
import { ThemeToggle } from './ThemeToggle';

export function AuthLayout({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      {children}
    </div>
  );
}
