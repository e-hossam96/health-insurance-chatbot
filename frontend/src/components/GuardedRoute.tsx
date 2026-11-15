import type { ReactNode } from 'react';
import { Navigate } from 'react-router';
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

export function GuardedRoute({
  children,
  path,
}: {
  children: ReactNode;
  path: string;
}): ReactNode {
  const auth = useAuth();

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

  if (redirect) return <Navigate to={redirect} replace />;
  return <>{children}</>;
}
