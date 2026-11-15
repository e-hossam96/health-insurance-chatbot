import { type FormEvent, type ReactNode, useEffect, useState } from 'react';
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
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr.error?.message ?? 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded shadow-md w-full max-w-sm">
        <h2 className="text-lg font-semibold mb-6">Complete your profile</h2>
        {error && <p className="text-red-600 text-sm mb-4" role="alert">{error}</p>}
        <label className="block text-sm font-medium mb-1">Full name</label>
        <input
          className="w-full border rounded px-3 py-2 mb-3"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <label className="block text-sm font-medium mb-1">Location</label>
        <select
          className="w-full border rounded px-3 py-2 mb-3"
          value={locationId}
          onChange={(e) => setLocationId(e.target.value ? Number(e.target.value) : '')}
        >
          <option value="">Select a location</option>
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>{loc.name}</option>
          ))}
        </select>
        <p className="text-xs text-gray-500 mb-4">
          Name and location can&apos;t be changed after you submit.
        </p>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white rounded py-2 hover:bg-blue-700 disabled:opacity-50"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
