import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminVisitsPage } from './AdminVisitsPage';
import { completeVisit } from '../api/admin';

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
  getAdminVisits: vi.fn().mockResolvedValue({
    items: [
      { id: 1, profile_id: 1, slot_id: 10, status: 'scheduled' },
      { id: 2, profile_id: 1, slot_id: 11, status: 'completed' },
    ],
    total: 2,
  }),
  completeVisit: vi.fn().mockResolvedValue({ id: 1, status: 'completed' }),
}));

describe('AdminVisitsPage', () => {
  it('AP4: shows visits table with status badges', async () => {
    render(
      <MemoryRouter>
        <AdminVisitsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('admin-visits-table')).toBeTruthy();
      const badges = screen.getAllByTestId('visit-status-badge');
      expect(badges.length).toBe(2);
    });
  });

  it('D3: Mark completed asks for confirmation before completing', async () => {
    render(
      <MemoryRouter>
        <AdminVisitsPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId('complete-btn'));
    expect(screen.getByRole('dialog')).toHaveTextContent('Mark visit #1 as completed?');
    expect(completeVisit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(completeVisit).toHaveBeenCalledWith(1));
  });

  it('AP4: shows complete button for scheduled', async () => {
    render(
      <MemoryRouter>
        <AdminVisitsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('complete-btn')).toBeTruthy();
    });
  });
});
