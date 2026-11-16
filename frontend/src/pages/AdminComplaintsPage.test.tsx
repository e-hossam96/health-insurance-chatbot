import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminComplaintsPage } from './AdminComplaintsPage';

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
  getAdminComplaints: vi.fn().mockResolvedValue({
    items: [
      { id: 1, visit_id: 2, description: 'Bad service', status: 'open' },
      { id: 2, visit_id: 3, description: 'Rude doctor', status: 'closed' },
      { id: 3, visit_id: 4, description: '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>', status: 'closed' },
    ],
    total: 3,
  }),
  replyToComplaint: vi.fn(),
  closeComplaint: vi.fn(),
}));

describe('AdminComplaintsPage', () => {
  it('AP5: shows complaints table with status badges', async () => {
    render(
      <MemoryRouter>
        <AdminComplaintsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('admin-complaints-table')).toBeTruthy();
      const badges = screen.getAllByTestId('complaint-status-badge');
      expect(badges.length).toBe(3);
    });
  });

  it('AP5: shows reply button for open complaints', async () => {
    render(
      <MemoryRouter>
        <AdminComplaintsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('reply-btn')).toBeTruthy();
    });
  });

  it('F17: a complaint written by a user is shown as text, never as HTML', async () => {
    const { container } = render(
      <MemoryRouter>
        <AdminComplaintsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/onerror/)).toBeTruthy());
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });
});
