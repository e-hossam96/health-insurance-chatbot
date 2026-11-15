import { describe, expect, it } from 'vitest';
import { getRedirect } from './components/GuardedRoute';

describe('getRedirect', () => {
  const cases: Array<{
    label: string;
    status: 'unauthenticated' | 'authenticated';
    role: string;
    hasProfile: boolean;
    mode: string;
    path: string;
    expected: string | null;
  }> = [
    // Unauthenticated
    { label: 'anon on /login stays', status: 'unauthenticated', role: '', hasProfile: false, mode: '', path: '/login', expected: null },
    { label: 'anon on /signup stays', status: 'unauthenticated', role: '', hasProfile: false, mode: '', path: '/signup', expected: null },
    { label: 'anon on /chat -> /login', status: 'unauthenticated', role: '', hasProfile: false, mode: '', path: '/chat', expected: '/login' },
    { label: 'anon on /admin/kb -> /login', status: 'unauthenticated', role: '', hasProfile: false, mode: '', path: '/admin/kb', expected: '/login' },
    { label: 'anon on /onboarding -> /login', status: 'unauthenticated', role: '', hasProfile: false, mode: '', path: '/onboarding', expected: '/login' },

    // Logged-in user without profile
    { label: 'user no profile on /login -> /onboarding', status: 'authenticated', role: 'user', hasProfile: false, mode: 'user', path: '/login', expected: '/onboarding' },
    { label: 'user no profile on /signup -> /onboarding', status: 'authenticated', role: 'user', hasProfile: false, mode: 'user', path: '/signup', expected: '/onboarding' },
    { label: 'user no profile on /onboarding stays', status: 'authenticated', role: 'user', hasProfile: false, mode: 'user', path: '/onboarding', expected: null },
    { label: 'user no profile on /chat -> /onboarding', status: 'authenticated', role: 'user', hasProfile: false, mode: 'user', path: '/chat', expected: '/onboarding' },

    // Logged-in user with profile
    { label: 'user with profile on /login -> /chat', status: 'authenticated', role: 'user', hasProfile: true, mode: 'user', path: '/login', expected: '/chat' },
    { label: 'user with profile on /onboarding -> /chat', status: 'authenticated', role: 'user', hasProfile: true, mode: 'user', path: '/onboarding', expected: '/chat' },
    { label: 'user with profile on /chat stays', status: 'authenticated', role: 'user', hasProfile: true, mode: 'user', path: '/chat', expected: null },
    { label: 'user on /admin/kb -> /chat', status: 'authenticated', role: 'user', hasProfile: true, mode: 'user', path: '/admin/kb', expected: '/chat' },

    // Admin in admin mode
    { label: 'admin mode on /login -> /admin/kb', status: 'authenticated', role: 'admin', hasProfile: true, mode: 'admin', path: '/login', expected: '/admin/kb' },
    { label: 'admin mode on /admin/kb stays', status: 'authenticated', role: 'admin', hasProfile: true, mode: 'admin', path: '/admin/kb', expected: null },

    // Admin in user mode
    { label: 'admin user mode on /admin/kb -> /chat', status: 'authenticated', role: 'admin', hasProfile: true, mode: 'user', path: '/admin/kb', expected: '/chat' },
    { label: 'admin user mode on /chat stays', status: 'authenticated', role: 'admin', hasProfile: true, mode: 'user', path: '/chat', expected: null },
  ];

  for (const c of cases) {
    it(c.label, () => {
      const result = getRedirect(c.status, c.role, c.hasProfile, c.mode, c.path);
      expect(result).toBe(c.expected);
    });
  }
});
