import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { OnboardingPage } from './OnboardingPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({ status: 'authenticated', user: { role: 'user', has_profile: false, mode: 'user' }, refresh: vi.fn() }),
}));

vi.mock('../api/auth', () => ({
  getLocations: () => Promise.resolve([]),
  createProfile: vi.fn(),
}));

describe('OnboardingPage', () => {
  it('B3: shows immutability notice', () => {
    render(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/can't be changed/i)).toBeTruthy();
  });
});
