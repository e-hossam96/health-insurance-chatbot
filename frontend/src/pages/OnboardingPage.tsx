import { AuthLayout } from '../components/AuthLayout';
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
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
  const [locationsFailed, setLocationsFailed] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  const loadLocations = useCallback((): void => {
    getLocations()
      .then(items => {
        setLocations(items);
        setLocationsFailed(false);
      })
      .catch(() => setLocationsFailed(true));
  }, []);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

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
    <AuthLayout>
      <form onSubmit={handleSubmit} className="card w-full max-w-sm p-8">
        <h1 className="mb-6 text-xl font-bold">Complete your profile</h1>
        {error && <p className="alert error mb-4" role="alert">{error}</p>}
        <label className="field-label">Full name</label>
        <input
          className="input mb-4"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <label className="field-label">Location</label>
        {locationsFailed && (
          <p className="alert error mb-2" data-testid="locations-error">
            Could not load locations.
            <button type="button" onClick={loadLocations} className="link-btn ml-2 underline">
              Retry
            </button>
          </p>
        )}
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
    </AuthLayout>
  );
}
