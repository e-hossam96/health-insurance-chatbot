import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminVisitsPage } from './AdminVisitsPage';
import { completeVisit, getAdminVisits } from '../api/admin';

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
  getAdminVisits: vi.fn(),
  completeVisit: vi.fn().mockResolvedValue({ id: 1, status: 'completed' }),
}));

const VISITS = [
  {
    id: 1, profile_id: 1, slot_id: 10, status: 'scheduled', patient_name: 'Sara N.', location: 'Cairo',
    clinic: 'Cairo Clinic', specialty: 'Dermatology', doctor_name: 'Dr. Sara Nabil', start_at: '2026-11-15T10:00:00Z',
  },
  {
    id: 2, profile_id: 2, slot_id: 11, status: 'completed', patient_name: 'Omar K.', location: 'Giza',
    clinic: 'Nile Medical', specialty: 'Cardiology', doctor_name: 'Dr. Omar Hassan', start_at: '2026-11-12T10:00:00Z',
  },
];

function renderPage(path = '/admin/visits'): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AdminVisitsPage />
    </MemoryRouter>,
  );
}

describe('AdminVisitsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getAdminVisits as ReturnType<typeof vi.fn>).mockResolvedValue({ items: VISITS, total: 2 });
  });

  it('AP4: shows visits table with status badges', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('admin-visits-table')).toBeTruthy();
      const badges = screen.getAllByTestId('visit-status-badge');
      expect(badges.length).toBe(2);
    });
  });

  it('D4: each row names the patient, location, clinic, specialty, doctor and UTC time', async () => {
    renderPage();
    const [first] = await screen.findAllByTestId('visit-row');
    const cells = within(first as HTMLElement).getAllByRole('cell').map((c) => c.textContent);
    expect(cells.slice(0, 6)).toEqual(['Sara N.', 'Cairo', 'Cairo Clinic', 'Dermatology', 'Dr. Sara Nabil', 'Sun 15 Nov, 10:00 UTC']);
  });

  it('AP4: the list opens on Scheduled visits', async () => {
    renderPage();
    await screen.findAllByTestId('visit-row');
    expect(screen.getByTestId('status-filter')).toHaveValue('scheduled');
    expect(getAdminVisits).toHaveBeenCalledWith({ limit: 50, offset: 0, status: 'scheduled' });
  });

  it('AP4: searching by patient name asks the server for matching visits', async () => {
    renderPage();
    await screen.findAllByTestId('visit-row');
    fireEvent.change(screen.getByTestId('patient-search'), { target: { value: ' sara ' } });
    await waitFor(() => expect(getAdminVisits).toHaveBeenLastCalledWith({ limit: 50, offset: 0, status: 'scheduled', patient: 'sara' }), { timeout: 2000 });
  });

  it('AP3: a link from a booked slot opens just that visit, whatever its status', async () => {
    renderPage('/admin/visits?visit=2');
    await screen.findAllByTestId('visit-row');
    expect(getAdminVisits).toHaveBeenCalledWith({ limit: 50, offset: 0, visitId: 2 });
    expect(screen.getByTestId('clear-visit-filter')).toHaveTextContent('Showing visit #2');
  });

  it('D3: Mark completed asks for confirmation before completing', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('complete-btn'));
    expect(screen.getByRole('dialog')).toHaveTextContent("Mark Sara N.'s visit as completed?");
    expect(screen.getByRole('dialog')).toHaveTextContent('Dr. Sara Nabil, Sun 15 Nov, 10:00 UTC');
    expect(completeVisit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(completeVisit).toHaveBeenCalledWith(1));
  });

  it('AP4: shows complete button for scheduled', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByTestId('complete-btn')).toHaveLength(1);
    });
  });
});
