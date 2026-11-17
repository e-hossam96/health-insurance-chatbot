import { Logo } from '../components/Logo';
import { errorMessage } from '../api/client';
import { type FormEvent, type ReactNode, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { signup } from '../api/auth';
import { useAuth } from '../api/AuthContext';

export function SignupPage(): ReactNode {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !password || !confirm) {
      setError('All fields are required.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setLoading(true);
    try {
      await signup(username.trim(), password);
      await refresh();
      navigate('/onboarding');
    } catch (err: unknown) {
      setError(errorMessage(err, 'Something went wrong.'));
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
        <h2 className="mb-6 text-center text-base font-medium text-muted">Create your account</h2>
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
          className="input mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
        />
        <label className="field-label">Confirm</label>
        <input
          type="password"
          className="input mb-6"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
        />
        <button
          type="submit"
          disabled={loading}
          className="btn w-full"
        >
          Sign up
        </button>
        <p className="mt-5 text-center text-sm text-muted">
          Already have an account? <Link to="/login" className="font-semibold text-accent hover:underline hover:underline-offset-3">Log in</Link>
        </p>
      </form>
    </div>
  );
}
