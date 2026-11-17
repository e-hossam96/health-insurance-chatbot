import { type FormEvent, type ReactNode, useState } from 'react';
import { Header } from '../components/Header';
import { Dialog } from '../components/Dialog';
import { useApiList } from '../hooks/useApiList';
import { errorMessage } from '../api/client';
import * as api from '../api/admin';

type Tab = 'locations' | 'specialties' | 'clinics' | 'doctors';

type CatalogRow = { id: number; cells: ReactNode[] };

function useCatalogActions(reload: () => void): {
  showAdd: boolean;
  setShowAdd: (open: boolean) => void;
  formError: string;
  submitAdd: (e: FormEvent, create: () => Promise<unknown> | null, resetForm: () => void) => Promise<void>;
  remove: (confirmText: string, del: () => Promise<unknown>) => Promise<void>;
} {
  const [showAdd, setShowAdd] = useState(false);
  const [formError, setFormError] = useState('');

  async function submitAdd(e: FormEvent, create: () => Promise<unknown> | null, resetForm: () => void): Promise<void> {
    e.preventDefault();
    setFormError('');
    const pending = create();
    if (pending === null) return;
    try {
      await pending;
      resetForm();
      setShowAdd(false);
      reload();
    } catch (err: unknown) {
      setFormError(errorMessage(err, 'Failed to create'));
    }
  }

  async function remove(confirmText: string, del: () => Promise<unknown>): Promise<void> {
    if (!confirm(confirmText)) return;
    try {
      await del();
      reload();
    } catch (err: unknown) {
      alert(errorMessage(err, 'Failed to delete'));
    }
  }

  return { showAdd, setShowAdd, formError, submitAdd, remove };
}

function CatalogSection({
  title,
  addLabel,
  tableTestId,
  headers,
  rows,
  onAdd,
  onDelete,
  dialogTitle,
  dialogOpen,
  onCloseDialog,
  onSubmit,
  formError,
  children,
}: {
  title: string;
  addLabel: string;
  tableTestId: string;
  headers: string[];
  rows: CatalogRow[];
  onAdd: () => void;
  onDelete: (id: number) => void;
  dialogTitle: string;
  dialogOpen: boolean;
  onCloseDialog: () => void;
  onSubmit: (e: FormEvent) => void;
  formError: string;
  children: ReactNode;
}): ReactNode {
  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        <button type="button" className="btn btn-sm" onClick={onAdd}>{addLabel}</button>
      </div>
      <div className="table-wrap">
      <table className="table" data-testid={tableTestId}>
        <thead>
          <tr>
            {headers.map((h) => <th key={h}>{h}</th>)}
            <th className="text-right!">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {row.cells.map((cell, index) => <td key={index}>{cell}</td>)}
              <td className="text-right!"><button type="button" className="link-btn danger" onClick={() => onDelete(row.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <Dialog open={dialogOpen} title={dialogTitle} onClose={onCloseDialog} panelClassName="min-w-80 max-w-md">
        <form onSubmit={onSubmit}>
          {children}
          {formError && <p className="alert error mb-4" data-testid="form-error">{formError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={onCloseDialog}>Cancel</button>
            <button type="submit" className="btn btn-sm">Add</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

function NameInput({ value, onChange, testId }: { value: string; onChange: (v: string) => void; testId: string }): ReactNode {
  return (
    <input className="input mb-3" placeholder="Name" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId} required />
  );
}

function NamedTab({
  kind,
  fetcher,
  create,
  del,
}: {
  kind: 'location' | 'specialty';
  fetcher: () => Promise<{ id: number; name: string }[]>;
  create: (name: string) => Promise<unknown>;
  del: (id: number) => Promise<unknown>;
}): ReactNode {
  const { items, loading, reload } = useApiList(fetcher);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');
  const title = kind === 'location' ? 'Locations' : 'Specialties';
  const label = kind === 'location' ? 'Location' : 'Specialty';

  if (loading) return <p>Loading...</p>;

  return (
    <CatalogSection
      title={title}
      addLabel={`+ Add ${kind}`}
      tableTestId={`${title.toLowerCase()}-table`}
      headers={['Name']}
      rows={items.map((item) => ({ id: item.id, cells: [item.name] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(id) => void actions.remove(`Delete this ${kind}?`, () => del(id))}
      dialogTitle={`Add ${label}`}
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      onSubmit={(e) => void actions.submitAdd(e, () => create(name), () => setName(''))}
      formError={actions.formError}
    >
      <NameInput value={name} onChange={setName} testId={`${kind}-name-input`} />
    </CatalogSection>
  );
}

function ClinicsTab(): ReactNode {
  const { items: clinics, loading, reload } = useApiList(api.getClinics);
  const { items: locations } = useApiList(api.getLocations);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');
  const [locationId, setLocationId] = useState<number | ''>('');

  if (loading) return <p>Loading...</p>;

  const locationNames = new Map(locations.map((l) => [l.id, l.name]));

  return (
    <CatalogSection
      title="Clinics"
      addLabel="+ Add clinic"
      tableTestId="clinics-table"
      headers={['Name', 'Location']}
      rows={clinics.map((c) => ({ id: c.id, cells: [c.name, locationNames.get(c.location_id) ?? '—'] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(id) => void actions.remove('Delete this clinic and its linked specialties and doctors?', () => api.deleteClinic(id))}
      dialogTitle="Add Clinic"
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      onSubmit={(e) =>
        void actions.submitAdd(
          e,
          () => (locationId === '' ? null : api.createClinic(name, locationId)),
          () => {
            setName('');
            setLocationId('');
          },
        )
      }
      formError={actions.formError}
    >
      <NameInput value={name} onChange={setName} testId="clinic-name-input" />
      <select className="input mb-3" value={locationId} onChange={(e) => setLocationId(Number(e.target.value))} data-testid="clinic-location-select" required>
        <option value="">Select location</option>
        {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </select>
    </CatalogSection>
  );
}

function DoctorsTab(): ReactNode {
  const { items: doctors, loading, reload } = useApiList(api.getDoctors);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');
  const [clinicSpecialtyId, setClinicSpecialtyId] = useState<number | ''>('');

  if (loading) return <p>Loading...</p>;

  return (
    <CatalogSection
      title="Doctors"
      addLabel="+ Add doctor"
      tableTestId="doctors-table"
      headers={['Name', 'Clinic-Specialty ID']}
      rows={doctors.map((d) => ({ id: d.id, cells: [d.name, d.clinic_specialty_id] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(id) => void actions.remove('Delete this doctor and their slots?', () => api.deleteDoctor(id))}
      dialogTitle="Add Doctor"
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      onSubmit={(e) =>
        void actions.submitAdd(
          e,
          () => (clinicSpecialtyId === '' ? null : api.createDoctor(name, clinicSpecialtyId)),
          () => {
            setName('');
            setClinicSpecialtyId('');
          },
        )
      }
      formError={actions.formError}
    >
      <NameInput value={name} onChange={setName} testId="doctor-name-input" />
      <input className="input mb-3" placeholder="Clinic-Specialty ID" type="number" value={clinicSpecialtyId} onChange={(e) => setClinicSpecialtyId(Number(e.target.value))} data-testid="doctor-cs-input" required />
    </CatalogSection>
  );
}

const TABS: { key: Tab; label: string }[] = [
  { key: 'locations', label: 'Locations' },
  { key: 'specialties', label: 'Specialties' },
  { key: 'clinics', label: 'Clinics' },
  { key: 'doctors', label: 'Doctors' },
];

export function AdminCatalogPage(): ReactNode {
  const [tab, setTab] = useState<Tab>('locations');

  return (
    <div>
      <Header />
      <div className="page">
        <h2 className="page-title">Catalog</h2>
        <div className="segmented mb-6" data-testid="catalog-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-pressed={tab === t.key}
              onClick={() => setTab(t.key)}
              data-testid={`tab-${t.key}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'locations' && <NamedTab kind="location" fetcher={api.getLocations} create={api.createLocation} del={api.deleteLocation} />}
        {tab === 'specialties' && <NamedTab kind="specialty" fetcher={api.getSpecialties} create={api.createSpecialty} del={api.deleteSpecialty} />}
        {tab === 'clinics' && <ClinicsTab />}
        {tab === 'doctors' && <DoctorsTab />}
      </div>
    </div>
  );
}
