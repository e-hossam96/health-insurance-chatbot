import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { Header } from './Header';

const mockRefresh = vi.fn();

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' },
    refresh: mockRefresh,
  }),
}));

vi.mock('../api/auth', () => ({
  logout: vi.fn(),
  setMode: vi.fn(),
}));

describe('Header', () => {
  it('B5: admin sees mode toggle', () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mode-toggle')).toBeTruthy();
    expect(screen.getByTestId('mode-toggle').textContent).toBe('User view');
  });
});
