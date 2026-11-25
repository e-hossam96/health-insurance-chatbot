import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Dialog } from '../components/Dialog';
import { useConfirm } from '../components/ConfirmDialog';
import { errorMessage } from '../api/client';
import { Header } from '../components/Header';
import * as api from '../api/admin';

const HOURS = [9, 10, 11, 12, 13, 14, 15, 16];

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function formatDay(year: number, month: number, day: number): string {
  return `${WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]} ${day}`;
}

function endOfCurrentMonthLabel(now: Date): string {
  const last = daysInMonth(now.getUTCFullYear(), now.getUTCMonth() + 1);
  return `${last} ${MONTH_NAMES[now.getUTCMonth()]?.slice(0, 3) ?? ''}`;
}

function uniqueById<T extends { id: number }>(items: T[]): T[] {
  return [...new Map(items.map((item) => [item.id, item])).values()];
}

export function AdminSlotsPage(): ReactNode {
  const [doctors, setDoctors] = useState<api.Doctor[]>([]);
  const [clinics, setClinics] = useState<api.Clinic[]>([]);
  const [locationFilter, setLocationFilter] = useState<number | ''>('');
  const [clinicFilter, setClinicFilter] = useState<number | ''>('');
  const [specialtyFilter, setSpecialtyFilter] = useState<number | ''>('');
  const [doctorId, setDoctorId] = useState<number | ''>('');
  const [year, setYear] = useState(() => new Date().getUTCFullYear());
  const [month, setMonth] = useState(() => new Date().getUTCMonth() + 1);
  const [slots, setSlots] = useState<api.Slot[]>([]);
  const [loadedAt, setLoadedAt] = useState(() => Date.now());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [gridError, setGridError] = useState('');
  const { confirm, confirmDialog } = useConfirm();

  const [showAdd, setShowAdd] = useState(false);
  const [addDate, setAddDate] = useState('');
  const [addHour, setAddHour] = useState(9);
  const [addError, setAddError] = useState('');

  useEffect(() => {
    api.getDoctors().then(setDoctors).catch(() => {});
    api.getClinics().then(setClinics).catch(() => {});
  }, []);

  const loadSlots = useCallback(() => {
    if (doctorId === '') return;
    setLoading(true);
    api.getSlots(doctorId, year, month)
      .then((data) => { setSlots(data); setLoadedAt(Date.now()); })
      .catch(() => setSlots([]))
      .finally(() => setLoading(false));
  }, [doctorId, year, month]);

  useEffect(loadSlots, [loadSlots]);

  function prevMonth(): void {
    if (month === 1) { setMonth(12); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  }
  function nextMonth(): void {
    if (month === 12) { setMonth(1); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  }

  const monthName = MONTH_NAMES[month - 1] ?? '';
  const numDays = daysInMonth(year, month);

  const slotMap = new Map<string, api.Slot>();
  for (const s of slots) {
    const d = new Date(s.start_at);
    if (d.getUTCFullYear() !== year || d.getUTCMonth() + 1 !== month) continue;
    slotMap.set(`${d.getUTCDate()}-${d.getUTCHours()}`, s);
  }

  const clinicLocation = new Map(clinics.map((c) => [c.id, c.location_id]));
  const locations = uniqueById(clinics.map((c) => ({ id: c.location_id, name: c.location_name })));
  const clinicOptions = clinics.filter((c) => locationFilter === '' || c.location_id === locationFilter);
  const doctorsInPlace = doctors.filter((d) =>
    (locationFilter === '' || clinicLocation.get(d.clinic_id) === locationFilter) &&
    (clinicFilter === '' || d.clinic_id === clinicFilter));
  const specialtyOptions = uniqueById(doctorsInPlace.map((d) => ({ id: d.specialty_id, name: d.specialty_name })));
  const doctorOptions = doctorsInPlace.filter((d) => specialtyFilter === '' || d.specialty_id === specialtyFilter);

  function narrow(apply: () => void): void {
    apply();
    setDoctorId('');
    setSlots([]);
  }

  async function handleAddSlot(e: FormEvent): Promise<void> {
    e.preventDefault();
    setAddError('');
    if (doctorId === '' || !addDate) return;
    const startAt = `${addDate}T${String(addHour).padStart(2, '0')}:00:00Z`;
    try {
      await api.createSlot(doctorId, startAt);
      setShowAdd(false);
      loadSlots();
    } catch (err: unknown) {
      setAddError(errorMessage(err, 'Failed to create slot'));
    }
  }

  async function handleDeleteSlot(slotId: number): Promise<void> {
    setGridError('');
    try {
      await api.deleteSlot(slotId);
      loadSlots();
    } catch (err: unknown) {
      setGridError(errorMessage(err, 'Cannot remove slot'));
    }
  }

  function askAutofill(): void {
    if (doctorId === '') return;
    const selectedDoctor = doctorId;
    const doctorName = doctors.find((d) => d.id === selectedDoctor)?.name ?? 'this doctor';
    confirm({
      title: 'Auto-fill to end of month?',
      message: `Create all missing slots for ${doctorName} from now to ${endOfCurrentMonthLabel(new Date())}? Existing slots are kept.`,
      confirmLabel: 'Create slots',
      tone: 'primary',
      failureText: 'Auto-fill failed',
      run: async () => {
        setMessage('');
        const result = await api.autofillSlots(selectedDoctor);
        setMessage(result.message);
        loadSlots();
      },
    });
  }

  return (
    <div>
      <Header />
      <div className="page">
        <h1 className="page-title">Slots</h1>

        <div className="card mb-4 flex flex-wrap items-end gap-4 p-4">
          <div>
            <label className="field-label" htmlFor="slots-location">Location</label>
            <select id="slots-location" className="input w-auto py-2 text-sm" value={locationFilter} data-testid="location-filter"
              onChange={(e) => narrow(() => { setLocationFilter(e.target.value === '' ? '' : Number(e.target.value)); setClinicFilter(''); setSpecialtyFilter(''); })}>
              <option value="">All locations</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="slots-clinic">Clinic</label>
            <select id="slots-clinic" className="input w-auto py-2 text-sm" value={clinicFilter} data-testid="clinic-filter"
              onChange={(e) => narrow(() => { setClinicFilter(e.target.value === '' ? '' : Number(e.target.value)); setSpecialtyFilter(''); })}>
              <option value="">All clinics</option>
              {clinicOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="slots-specialty">Specialty</label>
            <select id="slots-specialty" className="input w-auto py-2 text-sm" value={specialtyFilter} data-testid="specialty-filter"
              onChange={(e) => narrow(() => setSpecialtyFilter(e.target.value === '' ? '' : Number(e.target.value)))}>
              <option value="">All specialties</option>
              {specialtyOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="slots-doctor">Doctor</label>
            <select
              id="slots-doctor"
              className="input w-auto py-2 text-sm"
              value={doctorId}
              onChange={(e) => setDoctorId(e.target.value === '' ? '' : Number(e.target.value))}
              data-testid="doctor-select"
            >
              <option value="">Select doctor</option>
              {doctorOptions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={prevMonth} aria-label="Previous month">&lt;</button>
            <span className="min-w-32 text-center text-sm font-semibold" data-testid="month-label">{monthName} {year}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={nextMonth} aria-label="Next month">&gt;</button>
          </div>

          <button type="button" className="btn btn-sm" onClick={() => setShowAdd(true)} disabled={doctorId === ''}>Add slot</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={askAutofill} disabled={doctorId === ''} data-testid="autofill-btn">Auto-fill to end of month</button>
        </div>

        {message && <p className="alert success mb-4" data-testid="autofill-message">{message}</p>}

        {gridError && <p className="alert error mb-4" role="alert" data-testid="slot-grid-error">{gridError}</p>}

        {loading && <p className="text-sm text-muted">Loading slots...</p>}

        {doctorId !== '' && !loading && (
          <div className="table-wrap" data-testid="slot-grid">
            <table className="table compact text-xs">
              <thead>
                <tr>
                  <th>Day</th>
                  {HOURS.map((h) => <th key={h} className="text-center!">{String(h).padStart(2, '0')}:00</th>)}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: numDays }, (_, i) => i + 1).map((day) => (
                  <tr key={day}>
                    <td className="whitespace-nowrap font-medium">{formatDay(year, month, day)}</td>
                    {HOURS.map((h) => {
                      const slot = slotMap.get(`${day}-${h}`);
                      if (!slot) return <td key={h} className="text-center! text-line-strong">—</td>;
                      if (slot.status === 'booked') {
                        return (
                          <td key={h} className="text-center!">
                            {slot.visit_id === null
                              ? <span className="badge warn">booked</span>
                              : <Link to={`/admin/visits?visit=${slot.visit_id}`} className="badge warn" title="Open the visit" data-testid="booked-slot-link">booked</Link>}
                          </td>
                        );
                      }
                      if (new Date(slot.start_at).getTime() <= loadedAt) {
                        return <td key={h} className="text-center!"><span className="badge opacity-60" data-testid="past-slot">past</span></td>;
                      }
                      return (
                        <td key={h} className="text-center!">
                          <span className="badge success pr-1">
                            free
                            <button type="button" className="grid h-4 w-4 place-items-center rounded-full leading-none hover:bg-danger-soft hover:text-danger" onClick={() => void handleDeleteSlot(slot.id)} title="Remove" aria-label="Remove slot">×</button>
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Dialog open={showAdd} title="Add Slot" onClose={() => setShowAdd(false)}>
          <form onSubmit={(e) => void handleAddSlot(e)}>
            <input type="date" className="input mb-3" value={addDate} onChange={(e) => setAddDate(e.target.value)} data-testid="slot-date-input" required />
            <select className="input mb-3" value={addHour} onChange={(e) => setAddHour(Number(e.target.value))} data-testid="slot-hour-select">
              {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
            {addError && <p className="alert error mb-4" data-testid="slot-form-error">{addError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
              <button type="submit" className="btn btn-sm">Add</button>
            </div>
          </form>
        </Dialog>
        {confirmDialog}
      </div>
    </div>
  );
}
