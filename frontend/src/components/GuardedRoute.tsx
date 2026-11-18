import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useAuth } from '../api/AuthContext';

function getRedirect(
  status: 'unauthenticated' | 'authenticated',
  role: string,
  hasProfile: boolean,
  mode: string,
  path: string,
): string | null {
  if (status === 'unauthenticated') {
    if (path === '/signup' || path === '/login') return null;
    return '/login';
  }

  if (path === '/signup' || path === '/login') {
    if (role === 'admin') return '/admin/kb';
    if (!hasProfile) return '/onboarding';
    return '/chat';
  }

  if (path.startsWith('/admin/')) {
    if (role !== 'admin' || mode !== 'admin') return '/chat';
    return null;
  }

  if (path === '/onboarding') {
    if (hasProfile) return '/chat';
    return null;
  }

  if (path.startsWith('/chat')) {
    if (!hasProfile && role !== 'admin') return '/onboarding';
    return null;
  }

  return null;
}

export { getRedirect };

export type LoginRedirectState = { from: string };

export function returnPathAfterLogin(state: unknown, role: string, hasProfile: boolean, mode: string): string | null {
  const from = (state as Partial<LoginRedirectState> | null)?.from;
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return null;
  const pathname = from.split(/[?#]/)[0] ?? from;
  if (pathname === '/login' || pathname === '/signup') return null;
  return getRedirect('authenticated', role, hasProfile, mode, pathname) === null ? from : null;
}

export function GuardedRoute({
  children,
  path,
}: {
  children: ReactNode;
  path: string;
}): ReactNode {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === 'loading') {
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }

  const redirect = getRedirect(
    auth.status,
    auth.status === 'authenticated' ? auth.user.role : '',
    auth.status === 'authenticated' ? auth.user.has_profile : false,
    auth.status === 'authenticated' ? auth.user.mode : '',
    path,
  );

  if (redirect === '/login') {
    const state: LoginRedirectState = { from: `${location.pathname}${location.search}` };
    return <Navigate to={redirect} replace state={state} />;
  }
  if (redirect) return <Navigate to={redirect} replace />;
  return <>{children}</>;
}
