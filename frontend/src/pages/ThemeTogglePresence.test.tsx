import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';
import { OnboardingPage } from './OnboardingPage';
import { SignupPage } from './SignupPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({ status: 'unauthenticated', refresh: vi.fn() }),
}));

vi.mock('../api/auth', () => ({
  login: vi.fn(),
  signup: vi.fn(),
  getLocations: () => Promise.resolve([]),
  createProfile: vi.fn(),
}));

const PAGES: [string, () => ReactNode][] = [
  ['login', () => <LoginPage />],
  ['signup', () => <SignupPage />],
  ['onboarding', () => <OnboardingPage />],
];

describe.each(PAGES)('%s page', (_name, renderPage) => {
  it('offers the system, light and dark theme switch', () => {
    render(<MemoryRouter>{renderPage()}</MemoryRouter>);
    expect(screen.getByRole('group', { name: 'Color theme' })).toBeInTheDocument();
    for (const label of ['Match system theme', 'Light theme', 'Dark theme']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });
});
