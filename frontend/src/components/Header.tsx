import { Logo } from './Logo';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { logout, setMode } from '../api/auth';
import { useAuth } from '../api/AuthContext';

export function Header({ onVisitsClick }: { onVisitsClick?: () => void } = {}): ReactNode {
  const auth = useAuth();
  const navigate = useNavigate();

  if (auth.status !== 'authenticated') return null;
  const { user, refresh } = auth;

  const handleLogout = async (): Promise<void> => {
    await logout();
    await refresh();
    navigate('/login');
  };

  const handleModeToggle = async (): Promise<void> => {
    const newMode = user.mode === 'admin' ? 'user' : 'admin';
    await setMode(newMode);
    await refresh();
    navigate(newMode === 'admin' ? '/admin/kb' : '/chat');
  };

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-brand-800 bg-brand-900">
      <Logo tone="dark" />
      <div className="flex items-center gap-4">
        <span className="text-sm text-brand-100">{user.username}</span>
        {user.mode === 'user' && onVisitsClick && (
          <button
            onClick={onVisitsClick}
            className="text-sm text-brand-400 hover:underline"
            data-testid="visits-btn"
          >
            My visits &amp; complaints
          </button>
        )}
        {user.role === 'admin' && (
          <button
            onClick={handleModeToggle}
            className="text-sm text-brand-400 hover:underline"
            data-testid="mode-toggle"
          >
            {user.mode === 'admin' ? 'User view' : 'Admin panel'}
          </button>
        )}
        <button
          onClick={handleLogout}
          className="text-sm text-brand-100 hover:underline"
          data-testid="logout-btn"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
