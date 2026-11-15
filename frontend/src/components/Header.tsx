import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { logout, setMode } from '../api/auth';
import { useAuth } from '../api/AuthContext';

export function Header(): ReactNode {
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
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
      <span className="font-semibold text-lg">Health Assistant</span>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-600">{user.username}</span>
        {user.mode === 'user' && (
          <button
            onClick={() => navigate('/chat')}
            className="text-sm text-blue-600 hover:underline"
          >
            My visits &amp; complaints
          </button>
        )}
        {user.role === 'admin' && (
          <button
            onClick={handleModeToggle}
            className="text-sm text-blue-600 hover:underline"
            data-testid="mode-toggle"
          >
            {user.mode === 'admin' ? 'User view' : 'Admin panel'}
          </button>
        )}
        <button
          onClick={handleLogout}
          className="text-sm text-red-600 hover:underline"
          data-testid="logout-btn"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
