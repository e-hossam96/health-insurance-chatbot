import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
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
  getDoctors: () => Promise.resolve([{ id: 1, name: 'Dr. Sara', clinic_specialty_id: 1 }]),
  getSlots: vi.fn().mockResolvedValue([
    { id: 10, doctor_id: 1, start_at: '2026-12-01T09:00:00Z', status: 'available' },
    { id: 11, doctor_id: 1, start_at: '2026-12-01T10:00:00Z', status: 'booked' },
  ]),
  createSlot: vi.fn(),
  deleteSlot: vi.fn(),
  autofillSlots: vi.fn().mockResolvedValue({ created: 120, message: 'Created 120 slot(s)' }),
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <AdminSlotsPage />
    </MemoryRouter>,
  );
}

describe('AdminSlotsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('AP3: shows doctor select', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('doctor-select')).toBeTruthy();
    });
    expect(screen.getByText('Dr. Sara')).toBeTruthy();
  });

  it('AP3: shows slot grid after selecting doctor', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
    await waitFor(() => {
      expect(screen.getByTestId('slot-grid')).toBeTruthy();
    });
  });

  it('C5: autofill shows result message', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
    await waitFor(() => expect(screen.getByTestId('autofill-btn')).toBeTruthy());
    fireEvent.click(screen.getByTestId('autofill-btn'));
    expect(screen.getByRole('dialog')).toHaveTextContent('Create all missing slots for Dr. Sara');
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => {
      expect(screen.getByTestId('autofill-message').textContent).toContain('Created 120');
    });
  });

  it('AP3: a free slot is removed straight away from its chip; a booked one has no remove', async () => {
    const { deleteSlot } = await import('../api/admin');
    renderPage();
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
    const removeButtons = await screen.findAllByRole('button', { name: 'Remove slot' });
    expect(removeButtons).toHaveLength(1);
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(deleteSlot).toHaveBeenCalledWith(10));
  });

  it('AP3: a slot that cannot be removed shows why above the grid', async () => {
    const { deleteSlot } = await import('../api/admin');
    (deleteSlot as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: 'Slot is booked.' } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove slot' }));
    expect((await screen.findByTestId('slot-grid-error')).textContent).toBe('Slot is booked.');
  });

  it('C5: cancelling the auto-fill confirmation creates nothing', async () => {
    const { autofillSlots } = await import('../api/admin');
    renderPage();
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
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
    await waitFor(() => expect(screen.getByTestId('doctor-select')).toBeTruthy());
    fireEvent.change(screen.getByTestId('doctor-select'), { target: { value: '1' } });
    await waitFor(() => expect(screen.getByText('Add slot')).toBeTruthy());
    fireEvent.click(screen.getByText('Add slot'));

    const dateInput = screen.getByTestId('slot-date-input');
    fireEvent.change(dateInput, { target: { value: '2026-12-01' } });
    fireEvent.submit(dateInput.closest('form')!);

    await waitFor(() => {
      expect(screen.getByTestId('slot-form-error').textContent).toContain('Duplicate');
    });
  });
});
