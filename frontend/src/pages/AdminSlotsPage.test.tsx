import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminSlotsPage } from './AdminSlotsPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/auth', () => ({
  logout: vi.fn(),
  setMode: vi.fn(),
}));

vi.mock('../api/admin', () => ({
  getDoctors: () => Promise.resolve([
    { id: 1, name: 'Dr. Sara', clinic_specialty_id: 1, clinic_id: 1, clinic_name: 'Cairo Clinic', specialty_id: 1, specialty_name: 'Dermatology' },
    { id: 2, name: 'Dr. Omar', clinic_specialty_id: 2, clinic_id: 2, clinic_name: 'Nile Medical', specialty_id: 2, specialty_name: 'Cardiology' },
  ]),
  getClinics: () => Promise.resolve([
    { id: 1, name: 'Cairo Clinic', location_id: 1, location_name: 'Cairo', specialties: [] },
    { id: 2, name: 'Nile Medical', location_id: 2, location_name: 'Giza', specialties: [] },
  ]),
  getSlots: vi.fn().mockResolvedValue([
    { id: 9, doctor_id: 1, start_at: '2026-11-18T09:00:00Z', status: 'available', visit_id: null },
    { id: 10, doctor_id: 1, start_at: '2026-11-20T09:00:00Z', status: 'available', visit_id: null },
    { id: 11, doctor_id: 1, start_at: '2026-11-20T10:00:00Z', status: 'booked', visit_id: 77 },
  ]),
  createSlot: vi.fn(),
  deleteSlot: vi.fn(),
  autofillSlots: vi.fn().mockResolvedValue({ created: 120, skipped: 16, message: 'Created 120 slots, skipped 16 existing.' }),
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <AdminSlotsPage />
    </MemoryRouter>,
  );
}

async function pickDoctor(id = '1'): Promise<void> {
  await waitFor(() => expect(screen.getByText('Dr. Sara')).toBeTruthy());
  fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: id } });
}

describe('AdminSlotsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-18T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('AP3: shows doctor select', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('doctor-select')).toBeTruthy();
    });
    expect(screen.getByText('Dr. Sara')).toBeTruthy();
  });

  it('AP3: the location, clinic and specialty filters narrow the doctor list', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Dr. Omar')).toBeTruthy());
    fireEvent.change(screen.getByTestId('location-filter'), { target: { value: '2' } });
    const doctorOptions = within(screen.getByTestId('doctor-select')).getAllByRole('option').map((o) => o.textContent);
    expect(doctorOptions).toEqual(['Select doctor', 'Dr. Omar']);
    expect(within(screen.getByTestId('clinic-filter')).getAllByRole('option').map((o) => o.textContent)).toEqual(['All clinics', 'Nile Medical']);
    expect(within(screen.getByTestId('specialty-filter')).getAllByRole('option').map((o) => o.textContent)).toEqual(['All specialties', 'Cardiology']);
  });

  it('AP3: shows slot grid after selecting doctor', async () => {
    renderPage();
    await pickDoctor();
    await waitFor(() => {
      expect(screen.getByTestId('slot-grid')).toBeTruthy();
    });
  });

  it('C8: day labels and the month come from UTC, not the browser time zone', async () => {
    renderPage();
    await pickDoctor();
    await screen.findByTestId('slot-grid');
    expect(screen.getByTestId('month-label').textContent).toBe('November 2026');
    expect(screen.getByText('Sun 1')).toBeTruthy();
    expect(screen.getByText('Fri 20')).toBeTruthy();
  });

  it('C5: autofill names the end date and shows the created and skipped counts', async () => {
    renderPage();
    await pickDoctor();
    fireEvent.click(await screen.findByTestId('autofill-btn'));
    expect(screen.getByRole('dialog')).toHaveTextContent('Create all missing slots for Dr. Sara from now to 30 Nov?');
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => {
      expect(screen.getByTestId('autofill-message').textContent).toBe('Created 120 slots, skipped 16 existing.');
    });
  });

  it('AP3: a free slot is removed straight away from its chip; a booked one has no remove', async () => {
    const { deleteSlot } = await import('../api/admin');
    renderPage();
    await pickDoctor();
    const removeButtons = await screen.findAllByRole('button', { name: 'Remove slot' });
    expect(removeButtons).toHaveLength(1);
    fireEvent.click(removeButtons[0] as HTMLElement);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(deleteSlot).toHaveBeenCalledWith(10));
  });

  it('AP3: a past slot is greyed and read-only', async () => {
    renderPage();
    await pickDoctor();
    const past = await screen.findByTestId('past-slot');
    expect(past.textContent).toBe('past');
    expect(past.closest('td')?.querySelector('button')).toBeNull();
  });

  it('AP3: a booked slot links to its visit', async () => {
    renderPage();
    await pickDoctor();
    expect(await screen.findByTestId('booked-slot-link')).toHaveAttribute('href', '/admin/visits?visit=77');
  });

  it('AP3: a slot that cannot be removed shows why above the grid', async () => {
    const { deleteSlot } = await import('../api/admin');
    (deleteSlot as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: 'This slot is booked. Cancel the visit first.' } });
    renderPage();
    await pickDoctor();
    fireEvent.click(await screen.findByRole('button', { name: 'Remove slot' }));
    expect((await screen.findByTestId('slot-grid-error')).textContent).toBe('This slot is booked. Cancel the visit first.');
  });

  it('C5: cancelling the auto-fill confirmation creates nothing', async () => {
    const { autofillSlots } = await import('../api/admin');
    renderPage();
    await pickDoctor();
    fireEvent.click(await screen.findByTestId('autofill-btn'));
    fireEvent.click(screen.getByTestId('confirm-cancel'));
    expect(autofillSlots).not.toHaveBeenCalled();
    expect(screen.queryByTestId('autofill-message')).toBeNull();
  });

  it('C3: shows add slot dialog error on duplicate', async () => {
    const { createSlot } = await import('../api/admin');
    const mockCreate = createSlot as ReturnType<typeof vi.fn>;
    mockCreate.mockRejectedValueOnce({ error: { message: 'Duplicate slot for this doctor and time.' } });

    renderPage();
    await pickDoctor();
    await waitFor(() => expect(screen.getByText('Add slot')).toBeTruthy());
    fireEvent.click(screen.getByText('Add slot'));

    const dateInput = screen.getByTestId('slot-date-input');
    fireEvent.change(dateInput, { target: { value: '2026-12-01' } });
    fireEvent.submit(dateInput.closest('form') as HTMLFormElement);

    await waitFor(() => {
      expect(screen.getByTestId('slot-form-error').textContent).toContain('Duplicate');
    });
  });
});
