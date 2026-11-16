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
      <div className="max-w-5xl mx-auto p-4">
        <h2 className="text-xl font-bold mb-4">Slots</h2>

        <div className="flex flex-wrap gap-4 items-end mb-4">
          <div>
            <label className="text-sm font-medium block mb-1">Doctor</label>
            <select
              className="border rounded p-2 text-sm"
              value={doctorId}
              onChange={(e) => setDoctorId(Number(e.target.value))}
              data-testid="doctor-select"
            >
              <option value="">Select doctor</option>
              {doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button className="border rounded px-2 py-1 text-sm" onClick={prevMonth}>&lt;</button>
            <span className="font-medium text-sm" data-testid="month-label">{monthName} {year}</span>
            <button className="border rounded px-2 py-1 text-sm" onClick={nextMonth}>&gt;</button>
          </div>

          <button className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm" onClick={() => setShowAdd(true)} disabled={doctorId === ''}>Add slot</button>
          <button className="bg-green-600 text-white px-3 py-1 rounded text-sm" onClick={() => void handleAutofill()} disabled={doctorId === ''} data-testid="autofill-btn">Auto-fill to end of month</button>
        </div>

        {message && <p className="mb-4 text-sm font-medium text-green-700" data-testid="autofill-message">{message}</p>}

        {loading && <p>Loading slots...</p>}

        {doctorId !== '' && !loading && (
          <div className="overflow-x-auto" data-testid="slot-grid">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-1 pr-2">Day</th>
                  {HOURS.map((h) => <th key={h} className="text-center py-1 px-1">{String(h).padStart(2, '0')}:00</th>)}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: numDays }, (_, i) => i + 1).map((day) => (
                  <tr key={day} className="border-b">
                    <td className="py-1 pr-2 font-medium whitespace-nowrap">{formatDay(year, month, day)}</td>
                    {HOURS.map((h) => {
                      const slot = slotMap.get(`${day}-${h}`);
                      if (!slot) return <td key={h} className="text-center py-1 px-1 text-gray-300">—</td>;
                      if (slot.status === 'booked') {
                        return <td key={h} className="text-center py-1 px-1"><span className="bg-yellow-200 text-yellow-800 px-1 rounded text-xs">booked</span></td>;
                      }
                      return (
                        <td key={h} className="text-center py-1 px-1">
                          <span className="bg-green-100 text-green-800 px-1 rounded text-xs">
                            free
                            <button className="ml-1 text-red-500" onClick={() => void handleDeleteSlot(slot.id)} title="Remove">×</button>
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
            <input type="date" className="border rounded w-full p-2 mb-2" value={addDate} onChange={(e) => setAddDate(e.target.value)} data-testid="slot-date-input" required />
            <select className="border rounded w-full p-2 mb-2" value={addHour} onChange={(e) => setAddHour(Number(e.target.value))} data-testid="slot-hour-select">
              {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
            {addError && <p className="text-red-600 text-sm mb-2" data-testid="slot-form-error">{addError}</p>}
            <div className="flex gap-2 justify-end">
              <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setShowAdd(false)}>Cancel</button>
              <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Add</button>
            </div>
          </form>
        </Dialog>
      </div>
    </div>
  );
}
