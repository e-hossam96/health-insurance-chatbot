import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { VisitsDrawer } from './VisitsDrawer';

vi.mock('../api/visits', () => ({
  getMyVisits: () => Promise.resolve([
    { id: 2, slot_id: 11, status: 'completed', doctor_name: 'Dr. Omar', specialty: 'Cardio', clinic: 'Clinic B', location: 'Giza', start_at: '2026-12-10T09:00:00Z' },
  ]),
  getMyComplaints: () => Promise.resolve([
    {
      id: 1,
      visit_id: 2,
      description: 'Waited long <img src=x onerror="window.hacked=1">',
      status: 'open',
      created_at: '2026-12-11T08:00:00Z',
      visit_start_at: '2026-12-10T09:00:00Z',
      doctor_name: 'Dr. Omar',
      replies: [{ id: 1, body: 'Thanks for telling us <script>window.hacked=1</script><iframe src="https://evil.test"></iframe>', created_at: '2026-12-12T07:30:00Z' }],
    },
  ]),
  cancelVisit: vi.fn(),
}));

describe('VisitsDrawer and user or admin written text', () => {
  it('F17: complaint descriptions and admin replies render as text, never as HTML', async () => {
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('drawer-tab-complaints')).toBeTruthy());
    fireEvent.click(screen.getByTestId('drawer-tab-complaints'));
    await waitFor(() => expect(screen.getByText(/Thanks for telling us/)).toBeTruthy());
    const drawer = screen.getByTestId('visits-drawer');
    expect(drawer.querySelector('img, script, iframe')).toBeNull();
    expect(drawer.textContent).toContain('Waited long');
  });
});
