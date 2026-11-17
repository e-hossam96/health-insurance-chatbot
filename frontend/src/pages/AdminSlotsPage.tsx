import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
import { Dialog } from '../components/Dialog';
import { errorMessage } from '../api/client';
import { Header } from '../components/Header';
import * as api from '../api/admin';

const HOURS = [9, 10, 11, 12, 13, 14, 15, 16];

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function formatDay(year: number, month: number, day: number): string {
  const d = new Date(year, month - 1, day);
  const weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
  return `${weekday} ${day}`;
}

export function AdminSlotsPage(): ReactNode {
  const [doctors, setDoctors] = useState<api.Doctor[]>([]);
  const [doctorId, setDoctorId] = useState<number | ''>('');
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [month, setMonth] = useState(() => new Date().getMonth() + 1);
  const [slots, setSlots] = useState<api.Slot[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const [showAdd, setShowAdd] = useState(false);
  const [addDate, setAddDate] = useState('');
  const [addHour, setAddHour] = useState(9);
  const [addError, setAddError] = useState('');

  useEffect(() => {
    api.getDoctors().then(setDoctors).catch(() => {});
  }, []);

  const loadSlots = useCallback(() => {
    if (doctorId === '') return;
    setLoading(true);
    api.getSlots(doctorId, year, month)
      .then(setSlots)
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

  const monthName = new Date(year, month - 1).toLocaleString('en', { month: 'long' });
  const numDays = daysInMonth(year, month);

  const slotMap = new Map<string, api.Slot>();
  for (const s of slots) {
    const d = new Date(s.start_at);
    const key = `${d.getUTCDate()}-${d.getUTCHours()}`;
    slotMap.set(key, s);
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
    try {
      await api.deleteSlot(slotId);
      loadSlots();
    } catch (err: unknown) {
      alert(errorMessage(err, 'Cannot remove slot'));
    }
  }

  async function handleAutofill(): Promise<void> {
    if (doctorId === '') return;
    if (!confirm('Create all missing slots for this doctor until end of month?')) return;
    setMessage('');
    try {
      const result = await api.autofillSlots(doctorId);
      setMessage(result.message);
      loadSlots();
    } catch {
      setMessage('Auto-fill failed');
    }
  }

  return (
    <div>
      <Header />
      <div className="page">
        <h2 className="page-title">Slots</h2>

        <div className="card mb-4 flex flex-wrap items-end gap-4 p-4">
          <div>
            <label className="field-label">Doctor</label>
            <select
              className="input w-auto py-2 text-sm"
              value={doctorId}
              onChange={(e) => setDoctorId(Number(e.target.value))}
              data-testid="doctor-select"
            >
              <option value="">Select doctor</option>
              {doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={prevMonth} aria-label="Previous month">&lt;</button>
            <span className="min-w-32 text-center text-sm font-semibold" data-testid="month-label">{monthName} {year}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={nextMonth} aria-label="Next month">&gt;</button>
          </div>

          <button type="button" className="btn btn-sm" onClick={() => setShowAdd(true)} disabled={doctorId === ''}>Add slot</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleAutofill()} disabled={doctorId === ''} data-testid="autofill-btn">Auto-fill to end of month</button>
        </div>

        {message && <p className="alert success mb-4" data-testid="autofill-message">{message}</p>}

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
                        return <td key={h} className="text-center!"><span className="badge warn">booked</span></td>;
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
      </div>
    </div>
  );
}
