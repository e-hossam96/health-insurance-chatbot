import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
import { Header } from '../components/Header';
import * as api from '../api/admin';

type Tab = 'locations' | 'specialties' | 'clinics' | 'doctors';

function useApiList<T>(fetcher: () => Promise<T[]>): {
  items: T[];
  loading: boolean;
  reload: () => void;
} {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    fetcher()
      .then(setItems)
      .finally(() => setLoading(false));
  }, [fetcher]);
  useEffect(load, [load]);
  return { items, loading, reload: load };
}

// --- Dialog ---

function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}): ReactNode {
  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-lg p-6 min-w-80 max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}

// --- Locations Tab ---

function LocationsTab(): ReactNode {
  const { items, loading, reload } = useApiList(api.getLocations);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  async function handleAdd(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError('');
    try {
      await api.createLocation(name);
      setName('');
      setShowAdd(false);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr.error?.message ?? 'Failed to create');
    }
  }

  async function handleDelete(id: number): Promise<void> {
    if (!confirm('Delete this location?')) return;
    try {
      await api.deleteLocation(id);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      alert(apiErr.error?.message ?? 'Failed to delete');
    }
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold">Locations</h3>
        <button className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm" onClick={() => setShowAdd(true)}>+ Add location</button>
      </div>
      <table className="w-full text-sm" data-testid="locations-table">
        <thead><tr className="border-b"><th className="text-left py-1">Name</th><th className="text-right py-1">Actions</th></tr></thead>
        <tbody>
          {items.map((loc) => (
            <tr key={loc.id} className="border-b">
              <td className="py-1">{loc.name}</td>
              <td className="py-1 text-right"><button className="text-red-600 text-sm" onClick={() => handleDelete(loc.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Dialog open={showAdd} title="Add Location" onClose={() => setShowAdd(false)}>
        <form onSubmit={(e) => void handleAdd(e)}>
          <input className="border rounded w-full p-2 mb-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} data-testid="location-name-input" required />
          {error && <p className="text-red-600 text-sm mb-2" data-testid="form-error">{error}</p>}
          <div className="flex gap-2 justify-end">
            <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Add</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// --- Specialties Tab ---

function SpecialtiesTab(): ReactNode {
  const { items, loading, reload } = useApiList(api.getSpecialties);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  async function handleAdd(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError('');
    try {
      await api.createSpecialty(name);
      setName('');
      setShowAdd(false);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr.error?.message ?? 'Failed to create');
    }
  }

  async function handleDelete(id: number): Promise<void> {
    if (!confirm('Delete this specialty?')) return;
    try {
      await api.deleteSpecialty(id);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      alert(apiErr.error?.message ?? 'Failed to delete');
    }
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold">Specialties</h3>
        <button className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm" onClick={() => setShowAdd(true)}>+ Add specialty</button>
      </div>
      <table className="w-full text-sm" data-testid="specialties-table">
        <thead><tr className="border-b"><th className="text-left py-1">Name</th><th className="text-right py-1">Actions</th></tr></thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-b">
              <td className="py-1">{s.name}</td>
              <td className="py-1 text-right"><button className="text-red-600 text-sm" onClick={() => handleDelete(s.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Dialog open={showAdd} title="Add Specialty" onClose={() => setShowAdd(false)}>
        <form onSubmit={(e) => void handleAdd(e)}>
          <input className="border rounded w-full p-2 mb-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} data-testid="specialty-name-input" required />
          {error && <p className="text-red-600 text-sm mb-2" data-testid="form-error">{error}</p>}
          <div className="flex gap-2 justify-end">
            <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Add</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// --- Clinics Tab ---

function ClinicsTab(): ReactNode {
  const { items: clinics, loading: loadingClinics, reload } = useApiList(api.getClinics);
  const { items: locations } = useApiList(api.getLocations);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [locationId, setLocationId] = useState<number | ''>('');
  const [error, setError] = useState('');

  async function handleAdd(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError('');
    if (locationId === '') return;
    try {
      await api.createClinic(name, locationId);
      setName('');
      setLocationId('');
      setShowAdd(false);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr.error?.message ?? 'Failed to create');
    }
  }

  async function handleDelete(id: number): Promise<void> {
    if (!confirm('Delete this clinic and its linked specialties and doctors?')) return;
    try {
      await api.deleteClinic(id);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      alert(apiErr.error?.message ?? 'Failed to delete');
    }
  }

  if (loadingClinics) return <p>Loading...</p>;

  const locationMap = new Map(locations.map((l) => [l.id, l.name]));

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold">Clinics</h3>
        <button className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm" onClick={() => setShowAdd(true)}>+ Add clinic</button>
      </div>
      <table className="w-full text-sm" data-testid="clinics-table">
        <thead><tr className="border-b"><th className="text-left py-1">Name</th><th className="text-left py-1">Location</th><th className="text-right py-1">Actions</th></tr></thead>
        <tbody>
          {clinics.map((c) => (
            <tr key={c.id} className="border-b">
              <td className="py-1">{c.name}</td>
              <td className="py-1">{locationMap.get(c.location_id) ?? '—'}</td>
              <td className="py-1 text-right"><button className="text-red-600 text-sm" onClick={() => handleDelete(c.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Dialog open={showAdd} title="Add Clinic" onClose={() => setShowAdd(false)}>
        <form onSubmit={(e) => void handleAdd(e)}>
          <input className="border rounded w-full p-2 mb-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} data-testid="clinic-name-input" required />
          <select className="border rounded w-full p-2 mb-2" value={locationId} onChange={(e) => setLocationId(Number(e.target.value))} data-testid="clinic-location-select" required>
            <option value="">Select location</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          {error && <p className="text-red-600 text-sm mb-2" data-testid="form-error">{error}</p>}
          <div className="flex gap-2 justify-end">
            <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Add</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// --- Doctors Tab ---

function DoctorsTab(): ReactNode {
  const { items: doctors, loading, reload } = useApiList(api.getDoctors);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [csId, setCsId] = useState<number | ''>('');
  const [error, setError] = useState('');

  async function handleAdd(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError('');
    if (csId === '') return;
    try {
      await api.createDoctor(name, csId);
      setName('');
      setCsId('');
      setShowAdd(false);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr.error?.message ?? 'Failed to create');
    }
  }

  async function handleDelete(id: number): Promise<void> {
    if (!confirm('Delete this doctor and their slots?')) return;
    try {
      await api.deleteDoctor(id);
      reload();
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      alert(apiErr.error?.message ?? 'Failed to delete');
    }
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold">Doctors</h3>
        <button className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm" onClick={() => setShowAdd(true)}>+ Add doctor</button>
      </div>
      <table className="w-full text-sm" data-testid="doctors-table">
        <thead><tr className="border-b"><th className="text-left py-1">Name</th><th className="text-left py-1">Clinic-Specialty ID</th><th className="text-right py-1">Actions</th></tr></thead>
        <tbody>
          {doctors.map((d) => (
            <tr key={d.id} className="border-b">
              <td className="py-1">{d.name}</td>
              <td className="py-1">{d.clinic_specialty_id}</td>
              <td className="py-1 text-right"><button className="text-red-600 text-sm" onClick={() => handleDelete(d.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Dialog open={showAdd} title="Add Doctor" onClose={() => setShowAdd(false)}>
        <form onSubmit={(e) => void handleAdd(e)}>
          <input className="border rounded w-full p-2 mb-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} data-testid="doctor-name-input" required />
          <input className="border rounded w-full p-2 mb-2" placeholder="Clinic-Specialty ID" type="number" value={csId} onChange={(e) => setCsId(Number(e.target.value))} data-testid="doctor-cs-input" required />
          {error && <p className="text-red-600 text-sm mb-2" data-testid="form-error">{error}</p>}
          <div className="flex gap-2 justify-end">
            <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Add</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// --- Main Page ---

export function AdminCatalogPage(): ReactNode {
  const [tab, setTab] = useState<Tab>('locations');

  const tabs: { key: Tab; label: string }[] = [
    { key: 'locations', label: 'Locations' },
    { key: 'specialties', label: 'Specialties' },
    { key: 'clinics', label: 'Clinics' },
    { key: 'doctors', label: 'Doctors' },
  ];

  return (
    <div>
      <Header />
      <div className="max-w-4xl mx-auto p-4">
        <h2 className="text-xl font-bold mb-4">Catalog</h2>
        <div className="flex gap-1 border-b mb-4" data-testid="catalog-tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              className={`px-4 py-2 text-sm font-medium ${tab === t.key ? 'border-b-2 border-brand-400 text-brand-700' : 'text-gray-500'}`}
              onClick={() => setTab(t.key)}
              data-testid={`tab-${t.key}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'locations' && <LocationsTab />}
        {tab === 'specialties' && <SpecialtiesTab />}
        {tab === 'clinics' && <ClinicsTab />}
        {tab === 'doctors' && <DoctorsTab />}
      </div>
    </div>
  );
}
