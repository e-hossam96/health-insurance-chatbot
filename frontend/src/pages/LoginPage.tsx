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
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <form onSubmit={handleSubmit} className="card rise w-full max-w-sm p-8">
        <h1 className="mb-3 flex justify-center">
          <Logo size={40} />
        </h1>
        <h2 className="mb-6 text-center text-base font-medium text-muted">Log in</h2>
        {error && <p className="alert error mb-4" role="alert">{error}</p>}
        <label className="field-label">Username</label>
        <input
          className="input mb-4"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <label className="field-label">Password</label>
        <input
          type="password"
          className="input mb-6"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button
          type="submit"
          disabled={loading}
          className="btn w-full"
        >
          Log in
        </button>
        <p className="mt-5 text-center text-sm text-muted">
          New here? <Link to="/signup" className="font-semibold text-accent hover:underline hover:underline-offset-3">Sign up</Link>
        </p>
      </form>
    </div>
  );
}
