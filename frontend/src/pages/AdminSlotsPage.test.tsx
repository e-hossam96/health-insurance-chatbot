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
    window.confirm = vi.fn(() => true);
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
    await waitFor(() => {
      expect(screen.getByTestId('autofill-message').textContent).toContain('Created 120');
    });
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
