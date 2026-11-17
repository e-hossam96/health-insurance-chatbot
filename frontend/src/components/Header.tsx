import { Logo } from './Logo';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { logout, setMode } from '../api/auth';
import { useAuth } from '../api/AuthContext';
import { ThemeToggle } from './ThemeToggle';

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
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-card/80 px-5 py-3 backdrop-blur">
      <Logo />
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-2 text-sm text-muted">{user.username}</span>
        {user.mode === 'user' && onVisitsClick && (
          <button type="button" onClick={onVisitsClick} className="btn btn-ghost btn-sm" data-testid="visits-btn">
            My visits &amp; complaints
          </button>
        )}
        {user.role === 'admin' && (
          <button type="button" onClick={handleModeToggle} className="btn btn-secondary btn-sm" data-testid="mode-toggle">
            {user.mode === 'admin' ? 'User view' : 'Admin panel'}
          </button>
        )}
        <button type="button" onClick={handleLogout} className="btn btn-ghost btn-sm" data-testid="logout-btn">
          Log out
        </button>
        <ThemeToggle />
      </div>
    </header>
  );
}
