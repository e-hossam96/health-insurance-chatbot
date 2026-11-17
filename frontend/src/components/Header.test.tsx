import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { Header } from './Header';

const mockRefresh = vi.fn();
const mockUser = { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' };

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: mockUser,
    refresh: mockRefresh,
  }),
}));

vi.mock('../api/auth', () => ({
  logout: vi.fn(),
  setMode: vi.fn(),
}));

function renderHeader(): void {
  render(
    <MemoryRouter initialEntries={['/admin/kb']}>
      <Header />
    </MemoryRouter>,
  );
}

describe('Header', () => {
  beforeEach(() => {
    Object.assign(mockUser, { role: 'admin', mode: 'admin' });
  });

  it('B5: admin sees mode toggle', () => {
    renderHeader();
    expect(screen.getByTestId('mode-toggle')).toBeTruthy();
    expect(screen.getByTestId('mode-toggle').textContent).toBe('User view');
  });

  it('B5: admin panel shows the section menu next to the user view toggle', () => {
    renderHeader();
    expect(screen.getByTestId('admin-nav-btn')).toHaveTextContent('KB documents');
  });

  it('B5: admin in user view gets the Admin panel toggle but no section menu', () => {
    mockUser.mode = 'user';
    renderHeader();
    expect(screen.getByTestId('mode-toggle').textContent).toBe('Admin panel');
    expect(screen.queryByTestId('admin-nav-btn')).toBeNull();
  });

  it('B5: a regular user sees neither the toggle nor the section menu', () => {
    Object.assign(mockUser, { role: 'user', mode: 'user' });
    renderHeader();
    expect(screen.queryByTestId('mode-toggle')).toBeNull();
    expect(screen.queryByTestId('admin-nav-btn')).toBeNull();
  });
});
