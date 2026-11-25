import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { VisitsDrawer } from './VisitsDrawer';

vi.mock('../api/visits', () => ({
  getMyVisits: vi.fn(),
  getMyComplaints: vi.fn(),
  cancelVisit: vi.fn(),
}));

const visitsApi = await import('../api/visits');
const getMyVisits = vi.mocked(visitsApi.getMyVisits);
const getMyComplaints = vi.mocked(visitsApi.getMyComplaints);

describe('VisitsDrawer load failures', () => {
  it('F14: a failed load shows an error with Retry, not an empty list', async () => {
    getMyVisits.mockRejectedValueOnce(new Error('offline'));
    getMyComplaints.mockRejectedValueOnce(new Error('offline'));
    render(
      <MemoryRouter>
        <VisitsDrawer open={true} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('drawer-load-error')).toHaveTextContent('Could not load your visits.');
    expect(screen.queryByText('No visits yet.')).toBeNull();

    const user = userEvent.setup();
    await user.click(screen.getByTestId('drawer-tab-complaints'));
    expect(screen.getByTestId('drawer-load-error')).toHaveTextContent('Could not load your complaints.');
    expect(screen.queryByText('No complaints yet.')).toBeNull();

    getMyVisits.mockResolvedValue([]);
    getMyComplaints.mockResolvedValue([]);
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('No complaints yet.')).toBeTruthy();
    expect(screen.queryByTestId('drawer-load-error')).toBeNull();
  });
});
