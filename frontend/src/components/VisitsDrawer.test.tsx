import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { VisitsDrawer } from './VisitsDrawer';

vi.mock('../api/visits', () => ({
  getMyVisits: () => Promise.resolve([
    { id: 1, slot_id: 10, status: 'scheduled', doctor_name: 'Dr. Sara', specialty: 'Derm', clinic: 'Clinic A', location: 'Cairo', start_at: '2026-12-15T10:00:00Z' },
    { id: 2, slot_id: 11, status: 'completed', doctor_name: 'Dr. Omar', specialty: 'Cardio', clinic: 'Clinic B', location: 'Giza', start_at: '2026-12-10T09:00:00Z' },
  ]),
  getMyComplaints: () => Promise.resolve([
    { id: 1, visit_id: 2, description: 'Bad service', status: 'open', replies: [{ id: 1, body: 'We apologize.' }] },
  ]),
  cancelVisit: vi.fn().mockResolvedValue({}),
}));

describe('VisitsDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.confirm = vi.fn(() => true);
  });

  it('F14: shows visits list when open', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('visits-drawer')).toBeTruthy();
      expect(screen.getByText('Dr. Sara')).toBeTruthy();
    });
  });

  it('F14: shows status badges', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      const badges = screen.getAllByTestId('status-badge');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it('F14: cancel button on scheduled visit', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('cancel-visit-btn')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('cancel-visit-btn'));
    expect(window.confirm).toHaveBeenCalled();
  });

  it('F14: complaints tab shows replies with Support team label', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('drawer-tab-complaints')).toBeTruthy());
    fireEvent.click(screen.getByTestId('drawer-tab-complaints'));
    await waitFor(() => {
      expect(screen.getByText('Support team:')).toBeTruthy();
      expect(screen.getByText('We apologize.')).toBeTruthy();
    });
  });

  it('F14: hidden when not open', () => {
    const { container } = render(
      <MemoryRouter>
        <VisitsDrawer open={false} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(container.innerHTML).toBe('');
  });
});
