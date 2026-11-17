import { type FormEvent, type ReactNode, useEffect, useState } from 'react';
import { errorMessage } from '../api/client';
import { useNavigate } from 'react-router';
import { createProfile, getLocations, type LocationItem } from '../api/auth';
import { useAuth } from '../api/AuthContext';

export function OnboardingPage(): ReactNode {
  const [name, setName] = useState('');
  const [locationId, setLocationId] = useState<number | ''>('');
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  useEffect(() => {
    void getLocations().then(setLocations);
  }, []);

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Name is required.');
      return;
    }
    if (!locationId) {
      setError('Please select a location.');
      return;
    }

    setLoading(true);
    try {
      await createProfile(name.trim(), locationId);
      await refresh();
      navigate('/chat');
    } catch (err: unknown) {
      setError(errorMessage(err, 'Something went wrong.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <form onSubmit={handleSubmit} className="card rise w-full max-w-sm p-8">
        <h2 className="mb-6 text-xl font-bold">Complete your profile</h2>
        {error && <p className="alert error mb-4" role="alert">{error}</p>}
        <label className="field-label">Full name</label>
        <input
          className="input mb-4"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <label className="field-label">Location</label>
        <select
          className="input mb-4"
          value={locationId}
          onChange={(e) => setLocationId(e.target.value ? Number(e.target.value) : '')}
        >
          <option value="">Select a location</option>
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>{loc.name}</option>
          ))}
        </select>
        <p className="mb-6 text-xs text-muted">
          Name and location can&apos;t be changed after you submit.
        </p>
        <button
          type="submit"
          disabled={loading}
          className="btn w-full"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
