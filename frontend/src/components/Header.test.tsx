import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { Header } from './Header';

const mockRefresh = vi.fn();
const mockUser: { username: string; role: string; has_profile: boolean; mode: string; name: string | null } = {
  username: 'admin1', role: 'admin', has_profile: true, mode: 'admin', name: 'Admin One',
};

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
    Object.assign(mockUser, { role: 'admin', mode: 'admin', name: 'Admin One' });
  });

  it('B5: admin sees mode toggle', () => {
    renderHeader();
    expect(screen.getByTestId('mode-toggle')).toBeTruthy();
    expect(screen.getByTestId('mode-toggle').textContent).toBe('User view');
  });

  it('B5: admin panel shows the section tabs with the current one marked', () => {
    renderHeader();
    expect(screen.getByTestId('admin-nav')).toBeInTheDocument();
    expect(screen.getByTestId('admin-nav-kb')).toHaveAttribute('aria-current', 'page');
  });

  it('shows the profile name next to the account controls', () => {
    renderHeader();
    expect(screen.getByTestId('display-name')).toHaveTextContent('Admin One');
  });

  it('falls back to the username without a profile name', () => {
    mockUser.name = null;
    renderHeader();
    expect(screen.getByTestId('display-name')).toHaveTextContent('admin1');
  });

  it('B5: admin in user view gets the Admin panel toggle but no section menu', () => {
    mockUser.mode = 'user';
    renderHeader();
    expect(screen.getByTestId('mode-toggle').textContent).toBe('Admin panel');
    expect(screen.queryByTestId('admin-nav')).toBeNull();
  });

  it('B5: a regular user sees neither the toggle nor the section menu', () => {
    Object.assign(mockUser, { role: 'user', mode: 'user' });
    renderHeader();
    expect(screen.queryByTestId('mode-toggle')).toBeNull();
    expect(screen.queryByTestId('admin-nav')).toBeNull();
  });

  it.each([['admin', 'admin'], ['admin', 'user'], ['user', 'user']])('shows the theme switch for a %s in %s mode', (role, mode) => {
    Object.assign(mockUser, { role, mode });
    renderHeader();
    expect(screen.getByRole('group', { name: 'Color theme' })).toBeInTheDocument();
  });
});
