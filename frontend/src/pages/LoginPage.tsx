import { Logo } from '../components/Logo';
import { errorMessage } from '../api/client';
import { type FormEvent, type ReactNode, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { login } from '../api/auth';
import { useAuth } from '../api/AuthContext';

export function LoginPage(): ReactNode {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !password) {
      setError('All fields are required.');
      return;
    }

    setLoading(true);
    try {
      await login(username.trim(), password);
      await refresh();
      const me = await import('../api/auth').then((m) => m.getMe());
      if (me.role === 'admin') {
        navigate('/admin/kb');
      } else if (!me.has_profile) {
        navigate('/onboarding');
      } else {
        navigate('/chat');
      }
    } catch (err: unknown) {
      setError(errorMessage(err, 'Wrong username or password.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-brand-50">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded shadow-md w-full max-w-sm">
        <h1 className="text-xl mb-2 flex justify-center">
          <Logo size={32} />
        </h1>
        <h2 className="text-lg text-gray-600 mb-6 text-center">Log in</h2>
        {error && <p className="text-red-600 text-sm mb-4" role="alert">{error}</p>}
        <label className="block text-sm font-medium mb-1">Username</label>
        <input
          className="w-full border rounded px-3 py-2 mb-3"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <label className="block text-sm font-medium mb-1">Password</label>
        <input
          type="password"
          className="w-full border rounded px-3 py-2 mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-400 text-brand-900 rounded py-2 hover:bg-brand-500 disabled:opacity-50"
        >
          Log in
        </button>
        <p className="text-sm text-center mt-4 text-gray-600">
          New here? <Link to="/signup" className="text-brand-700 hover:underline">Sign up</Link>
        </p>
      </form>
    </div>
  );
}
