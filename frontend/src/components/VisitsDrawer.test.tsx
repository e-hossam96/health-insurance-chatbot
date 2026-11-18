import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { VisitsDrawer } from './VisitsDrawer';
import { cancelVisit } from '../api/visits';

vi.mock('../api/visits', () => ({
  getMyVisits: () => Promise.resolve([
    { id: 1, slot_id: 10, status: 'scheduled', doctor_name: 'Dr. Sara', specialty: 'Derm', clinic: 'Clinic A', location: 'Cairo', start_at: '2026-12-15T10:00:00Z' },
    { id: 2, slot_id: 11, status: 'completed', doctor_name: 'Dr. Omar', specialty: 'Cardio', clinic: 'Clinic B', location: 'Giza', start_at: '2026-12-10T09:00:00Z' },
  ]),
  getMyComplaints: () => Promise.resolve([
    {
      id: 1, visit_id: 2, description: 'Bad service', status: 'open',
      created_at: '2026-12-11T08:00:00Z', visit_start_at: '2026-12-10T09:00:00Z', doctor_name: 'Dr. Omar',
      replies: [{ id: 1, body: 'We apologize.', created_at: '2026-12-12T07:30:00Z' }],
    },
    {
      id: 2, visit_id: 3, description: 'Late start', status: 'closed',
      created_at: '2026-12-04T08:00:00Z', visit_start_at: '2026-12-03T14:00:00Z', doctor_name: 'Dr. Sara',
      replies: [],
    },
  ]),
  cancelVisit: vi.fn().mockResolvedValue({}),
}));

describe('VisitsDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('C8: visit times are shown in UTC, not the browser time zone', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('Tue 15 Dec, 10:00 UTC')).toBeTruthy();
    expect(screen.queryByText(/19:00/)).toBeNull();
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
    expect(screen.getByRole('dialog')).toHaveTextContent('Dr. Sara, Tue 15 Dec, 10:00 UTC');
    expect(cancelVisit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(cancelVisit).toHaveBeenCalledWith(1));
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
      expect(screen.getByText('Reply (Sat 12 Dec, 07:30 UTC, Support team):')).toBeTruthy();
      expect(screen.getByText('We apologize.')).toBeTruthy();
    });
  });

  it('F14: each complaint names its visit, its filed date, and says when no reply came yet', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId('drawer-tab-complaints'));
    const visits = await screen.findAllByTestId('complaint-visit');
    expect(visits.map((v) => v.textContent)).toEqual(['Visit 10 Dec - Dr. Omar', 'Visit 3 Dec - Dr. Sara']);
    expect(screen.getAllByTestId('complaint-filed').map((f) => f.textContent)).toEqual(['Filed 11 Dec', 'Filed 4 Dec']);
    expect(screen.getAllByTestId('complaint-no-reply')).toHaveLength(1);
    expect(screen.getByTestId('complaint-no-reply').textContent).toBe('No reply yet');
    expect(screen.queryByText(/admin1/)).toBeNull();
  });

  it('F14: the tabs show which list is open', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await screen.findByTestId('visits-list');
    expect(screen.getByTestId('drawer-tab-visits')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('drawer-tab-complaints')).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByTestId('drawer-tab-complaints'));
    expect(screen.getByTestId('drawer-tab-complaints')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('complaints-list')).toBeTruthy();
    expect(screen.queryByTestId('visits-list')).toBeNull();
  });

  it('F14: the close button and the backdrop close the drawer', async () => {
    const onClose = vi.fn();
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={onClose} />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('visits-drawer').previousElementSibling as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('F14: a refused cancel keeps the dialog open with the reason', async () => {
    (cancelVisit as ReturnType<typeof vi.fn>).mockRejectedValueOnce({});
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId('cancel-visit-btn'));
    fireEvent.click(screen.getByTestId('confirm-yes'));
    expect((await screen.findByTestId('confirm-error')).textContent).toBe('Cannot cancel this visit.');
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
