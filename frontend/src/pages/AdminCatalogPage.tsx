import { type FormEvent, type ReactNode, useState } from 'react';
import { Header } from '../components/Header';
import { Dialog } from '../components/Dialog';
import { useConfirm } from '../components/ConfirmDialog';
import { useApiList } from '../hooks/useApiList';
import { errorMessage } from '../api/client';
import * as api from '../api/admin';

type Tab = 'locations' | 'specialties' | 'clinics' | 'doctors';

type CatalogRow = { id: number; name: string; cells: ReactNode[] };

function useCatalogActions(reload: () => void): {
  showAdd: boolean;
  setShowAdd: (open: boolean) => void;
  formError: string;
  submitAdd: (e: FormEvent, create: () => Promise<unknown> | null, resetForm: () => void) => Promise<void>;
  remove: (kind: api.CascadeKind, row: CatalogRow, del: () => Promise<unknown>) => void;
  confirmDialog: ReactNode;
} {
  const [showAdd, setShowAdd] = useState(false);
  const [formError, setFormError] = useState('');
  const { confirm, confirmDialog } = useConfirm();

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

  function remove(kind: api.CascadeKind, row: CatalogRow, del: () => Promise<unknown>): void {
    const ask = (message: string, blocked?: string): void => {
      confirm({
        title: `Delete ${row.name}?`,
        message: `${message} This cannot be undone.`,
        confirmLabel: 'Delete',
        failureText: 'Failed to delete',
        ...(blocked === undefined ? {} : { blocked }),
        run: async () => {
          await del();
          reload();
        },
      });
    };
    api.getCascadePreview(kind, row.id)
      .then((preview) => ask(api.describeCascade(preview.cascade), preview.blocked ?? undefined))
      .catch(() => ask('Anything that belongs to it is deleted too.'));
  }

  return { showAdd, setShowAdd, formError, submitAdd, remove, confirmDialog };
}

function CatalogSection({
  title,
  addLabel,
  tableTestId,
  headers,
  rows,
  onAdd,
  onDelete,
  rowActions,
  dialogTitle,
  dialogOpen,
  onCloseDialog,
  onSubmit,
  submitDisabled,
  formError,
  confirmDialog,
  children,
}: {
  title: string;
  addLabel: string;
  tableTestId: string;
  headers: string[];
  rows: CatalogRow[];
  onAdd: () => void;
  onDelete: (row: CatalogRow) => void;
  rowActions?: (row: CatalogRow) => ReactNode;
  dialogTitle: string;
  dialogOpen: boolean;
  onCloseDialog: () => void;
  onSubmit: (e: FormEvent) => void;
  submitDisabled?: boolean;
  formError: string;
  confirmDialog: ReactNode;
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
          {rows.length === 0 && (
            <tr><td colSpan={headers.length + 1} className="text-muted">Nothing here yet. Add one above.</td></tr>
          )}
          {rows.map((row) => (
            <tr key={row.id}>
              {row.cells.map((cell, index) => <td key={index}>{cell}</td>)}
              <td>
                <div className="row-actions">
                  {rowActions?.(row)}
                  <button type="button" className="btn btn-danger-ghost btn-sm" onClick={() => onDelete(row)} data-testid="catalog-delete">Delete</button>
                </div>
              </td>
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
            <button type="submit" className="btn btn-sm" disabled={submitDisabled}>Add</button>
          </div>
        </form>
      </Dialog>
      {confirmDialog}
    </div>
  );
}

function NameInput({ value, onChange, testId }: { value: string; onChange: (v: string) => void; testId: string }): ReactNode {
  return (
    <input className="input mb-3" placeholder="Name" aria-label="Name" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId} required />
  );
}

function SpecialtyChecklist({
  specialties,
  selected,
  onToggle,
  testId,
}: {
  specialties: api.Specialty[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  testId: string;
}): ReactNode {
  if (specialties.length === 0) return <p className="mb-3 text-sm text-muted">No specialties yet. Add them in the Specialties tab.</p>;
  return (
    <fieldset className="mb-3" data-testid={testId}>
      <legend className="mb-1 text-sm text-muted">Specialties</legend>
      {specialties.map((s) => (
        <label key={s.id} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={selected.has(s.id)} onChange={() => onToggle(s.id)} />
          {s.name}
        </label>
      ))}
    </fieldset>
  );
}

function toggled(set: Set<number>, id: number): Set<number> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function LocationsTab(): ReactNode {
  const { items, loading, reload } = useApiList(api.getLocations);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');

  if (loading) return <p>Loading...</p>;

  return (
    <CatalogSection
      title="Locations"
      addLabel="+ Add location"
      tableTestId="locations-table"
      headers={['Name', 'Clinics']}
      rows={items.map((item) => ({ id: item.id, name: item.name, cells: [item.name, item.clinic_count] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(row) => actions.remove('locations', row, () => api.deleteLocation(row.id))}
      dialogTitle="Add Location"
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      onSubmit={(e) => void actions.submitAdd(e, () => api.createLocation(name), () => setName(''))}
      formError={actions.formError}
      confirmDialog={actions.confirmDialog}
    >
      <NameInput value={name} onChange={setName} testId="location-name-input" />
    </CatalogSection>
  );
}

function SpecialtiesTab(): ReactNode {
  const { items, loading, reload } = useApiList(api.getSpecialties);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');

  if (loading) return <p>Loading...</p>;

  return (
    <CatalogSection
      title="Specialties"
      addLabel="+ Add specialty"
      tableTestId="specialties-table"
      headers={['Name']}
      rows={items.map((item) => ({ id: item.id, name: item.name, cells: [item.name] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(row) => actions.remove('specialties', row, () => api.deleteSpecialty(row.id))}
      dialogTitle="Add Specialty"
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      onSubmit={(e) => void actions.submitAdd(e, () => api.createSpecialty(name), () => setName(''))}
      formError={actions.formError}
      confirmDialog={actions.confirmDialog}
    >
      <NameInput value={name} onChange={setName} testId="specialty-name-input" />
    </CatalogSection>
  );
}

function ClinicSpecialtiesDialog({
  clinic,
  specialties,
  onClose,
  onSaved,
}: {
  clinic: api.Clinic | null;
  specialties: api.Specialty[];
  onClose: () => void;
  onSaved: () => void;
}): ReactNode {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [openFor, setOpenFor] = useState<number | null>(null);

  if (clinic !== null && openFor !== clinic.id) {
    setOpenFor(clinic.id);
    setSelected(new Set(clinic.specialties.map((s) => s.id)));
    setError('');
  }

  async function save(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (clinic === null) return;
    setError('');
    try {
      await api.setClinicSpecialties(clinic.id, [...selected]);
      setOpenFor(null);
      onSaved();
    } catch (err: unknown) {
      setError(errorMessage(err, 'Could not save the specialties.'));
    }
  }

  function close(): void {
    setOpenFor(null);
    onClose();
  }

  return (
    <Dialog open={clinic !== null} title={`Specialties of ${clinic?.name ?? ''}`} onClose={close} panelClassName="min-w-80 max-w-md">
      <form onSubmit={(e) => void save(e)}>
        <SpecialtyChecklist specialties={specialties} selected={selected} onToggle={(id) => setSelected((s) => toggled(s, id))} testId="clinic-specialties-edit" />
        {error && <p className="alert error mb-4" role="alert" data-testid="clinic-specialties-error">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secondary btn-sm" onClick={close}>Cancel</button>
          <button type="submit" className="btn btn-sm" data-testid="clinic-specialties-save">Save</button>
        </div>
      </form>
    </Dialog>
  );
}

function ClinicsTab(): ReactNode {
  const { items: clinics, loading, reload } = useApiList(api.getClinics);
  const { items: locations } = useApiList(api.getLocations);
  const { items: specialties } = useApiList(api.getSpecialties);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');
  const [locationId, setLocationId] = useState<number | ''>('');
  const [newSpecialties, setNewSpecialties] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<api.Clinic | null>(null);

  if (loading) return <p>Loading...</p>;

  async function createWithSpecialties(clinicName: string, location: number): Promise<void> {
    const clinic = await api.createClinic(clinicName, location);
    if (newSpecialties.size > 0) await api.setClinicSpecialties(clinic.id, [...newSpecialties]);
  }

  const clinicsById = new Map(clinics.map((c) => [c.id, c]));

  return (
    <>
      <CatalogSection
        title="Clinics"
        addLabel="+ Add clinic"
        tableTestId="clinics-table"
        headers={['Name', 'Location', 'Specialties']}
        rows={clinics.map((c) => ({
          id: c.id,
          name: c.name,
          cells: [
            c.name,
            c.location_name,
            <span key="chips" className="flex flex-wrap gap-1" data-testid="clinic-specialty-chips">
              {c.specialties.length === 0
                ? <span className="text-sm text-muted">None</span>
                : c.specialties.map((s) => <span key={s.id} className="badge">{s.name}</span>)}
            </span>,
          ],
        }))}
        onAdd={() => actions.setShowAdd(true)}
        onDelete={(row) => actions.remove('clinics', row, () => api.deleteClinic(row.id))}
        rowActions={(row) => (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(clinicsById.get(row.id) ?? null)} data-testid="clinic-specialties-btn">
            Specialties
          </button>
        )}
        dialogTitle="Add Clinic"
        dialogOpen={actions.showAdd}
        onCloseDialog={() => actions.setShowAdd(false)}
        onSubmit={(e) =>
          void actions.submitAdd(
            e,
            () => (locationId === '' ? null : createWithSpecialties(name, locationId)),
            () => {
              setName('');
              setLocationId('');
              setNewSpecialties(new Set());
            },
          )
        }
        formError={actions.formError}
        confirmDialog={actions.confirmDialog}
      >
        <NameInput value={name} onChange={setName} testId="clinic-name-input" />
        <select className="input mb-3" aria-label="Location" value={locationId} onChange={(e) => setLocationId(e.target.value === '' ? '' : Number(e.target.value))} data-testid="clinic-location-select" required>
          <option value="">Select location</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <SpecialtyChecklist specialties={specialties} selected={newSpecialties} onToggle={(id) => setNewSpecialties((s) => toggled(s, id))} testId="clinic-specialties-new" />
      </CatalogSection>
      <ClinicSpecialtiesDialog clinic={editing} specialties={specialties} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />
    </>
  );
}

function DoctorsTab(): ReactNode {
  const { items: doctors, loading, reload } = useApiList(api.getDoctors);
  const { items: clinics } = useApiList(api.getClinics);
  const actions = useCatalogActions(reload);
  const [name, setName] = useState('');
  const [clinicId, setClinicId] = useState<number | ''>('');
  const [clinicSpecialtyId, setClinicSpecialtyId] = useState<number | ''>('');

  if (loading) return <p>Loading...</p>;

  const clinic = clinics.find((c) => c.id === clinicId);
  const clinicHasNoSpecialty = clinic !== undefined && clinic.specialties.length === 0;

  return (
    <CatalogSection
      title="Doctors"
      addLabel="+ Add doctor"
      tableTestId="doctors-table"
      headers={['Name', 'Clinic', 'Specialty']}
      rows={doctors.map((d) => ({ id: d.id, name: d.name, cells: [d.name, d.clinic_name, d.specialty_name] }))}
      onAdd={() => actions.setShowAdd(true)}
      onDelete={(row) => actions.remove('doctors', row, () => api.deleteDoctor(row.id))}
      dialogTitle="Add Doctor"
      dialogOpen={actions.showAdd}
      onCloseDialog={() => actions.setShowAdd(false)}
      submitDisabled={clinicHasNoSpecialty}
      onSubmit={(e) =>
        void actions.submitAdd(
          e,
          () => (clinicSpecialtyId === '' ? null : api.createDoctor(name, clinicSpecialtyId)),
          () => {
            setName('');
            setClinicId('');
            setClinicSpecialtyId('');
          },
        )
      }
      formError={actions.formError}
      confirmDialog={actions.confirmDialog}
    >
      <NameInput value={name} onChange={setName} testId="doctor-name-input" />
      <select
        className="input mb-3"
        aria-label="Clinic"
        value={clinicId}
        onChange={(e) => { setClinicId(e.target.value === '' ? '' : Number(e.target.value)); setClinicSpecialtyId(''); }}
        data-testid="doctor-clinic-select"
        required
      >
        <option value="">Select clinic</option>
        {clinics.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.location_name})</option>)}
      </select>
      {clinicHasNoSpecialty ? (
        <p className="alert error mb-3" data-testid="doctor-no-specialty">Add a specialty to this clinic first.</p>
      ) : (
        <select
          className="input mb-3"
          aria-label="Specialty"
          value={clinicSpecialtyId}
          onChange={(e) => setClinicSpecialtyId(e.target.value === '' ? '' : Number(e.target.value))}
          disabled={clinic === undefined}
          data-testid="doctor-specialty-select"
          required
        >
          <option value="">Select specialty</option>
          {(clinic?.specialties ?? []).map((s) => <option key={s.clinic_specialty_id} value={s.clinic_specialty_id}>{s.name}</option>)}
        </select>
      )}
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
        {tab === 'locations' && <LocationsTab />}
        {tab === 'specialties' && <SpecialtiesTab />}
        {tab === 'clinics' && <ClinicsTab />}
        {tab === 'doctors' && <DoctorsTab />}
      </div>
    </div>
  );
}
