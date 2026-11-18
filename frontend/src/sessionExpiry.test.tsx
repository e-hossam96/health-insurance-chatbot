import type { ReactNode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { AuthProvider } from './api/AuthContext';
import { apiFetch, onUnauthorized, reportUnauthorized } from './api/client';
import { GuardedRoute, returnPathAfterLogin } from './components/GuardedRoute';

vi.mock('./api/auth', () => ({
  getMe: vi.fn().mockResolvedValue({ username: 'user1', role: 'user', has_profile: true, mode: 'user' }),
}));

function LoginProbe(): ReactNode {
  const location = useLocation();
  return <p data-testid="login-probe">{JSON.stringify(location.state)}</p>;
}

describe('session expiry', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a 401 from an API call is reported, but not from the auth routes', async () => {
    const heard: string[] = [];
    const stop = onUnauthorized(() => heard.push('401'));
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: { error: { code: 'not_authenticated', message: 'x' } } }), { status: 401 }))));

    await expect(apiFetch('/me/visits')).rejects.toMatchObject({ status: 401 });
    await expect(apiFetch('/auth/me')).rejects.toMatchObject({ status: 401 });
    reportUnauthorized(403, '/me/visits');
    stop();
    reportUnauthorized(401, '/me/visits');

    expect(heard).toEqual(['401']);
  });

  it('an expired session sends the user to /login, remembering the page they were on', async () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/chat/5?from=drawer']}>
          <Routes>
            <Route path="/chat/:sessionId" element={<GuardedRoute path="/chat/:sessionId"><p>chat page</p></GuardedRoute>} />
            <Route path="/login" element={<LoginProbe />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
    expect(await screen.findByText('chat page')).toBeTruthy();

    act(() => reportUnauthorized(401, '/me/sessions'));

    await waitFor(() => expect(screen.getByTestId('login-probe').textContent).toBe('{"from":"/chat/5?from=drawer"}'));
  });

  it('after login the user goes back to the remembered page only if their role may open it', () => {
    expect(returnPathAfterLogin({ from: '/chat/5?x=1' }, 'user', true, 'user')).toBe('/chat/5?x=1');
    expect(returnPathAfterLogin({ from: '/admin/visits' }, 'user', true, 'user')).toBeNull();
    expect(returnPathAfterLogin({ from: '/admin/visits?visit=2' }, 'admin', true, 'admin')).toBe('/admin/visits?visit=2');
    expect(returnPathAfterLogin({ from: '/chat' }, 'user', false, 'user')).toBeNull();
    expect(returnPathAfterLogin({ from: '//evil.test/chat' }, 'user', true, 'user')).toBeNull();
    expect(returnPathAfterLogin({ from: '/login' }, 'user', true, 'user')).toBeNull();
    expect(returnPathAfterLogin(null, 'user', true, 'user')).toBeNull();
  });
});
