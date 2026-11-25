import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { OnboardingPage } from './OnboardingPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({ status: 'authenticated', user: { role: 'user', has_profile: false, mode: 'user', name: null }, refresh: vi.fn() }),
}));

vi.mock('../api/auth', () => ({ getLocations: vi.fn(), createProfile: vi.fn() }));

const authApi = await import('../api/auth');
const getLocations = vi.mocked(authApi.getLocations);

describe('OnboardingPage location load', () => {
  it('B3: a failed location load shows an error with Retry instead of an empty dropdown', async () => {
    getLocations.mockRejectedValueOnce(new Error('offline'));
    render(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('locations-error')).toHaveTextContent('Could not load locations.');

    getLocations.mockResolvedValue([{ id: 1, name: 'Cairo' }]);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('option', { name: 'Cairo' })).toBeTruthy();
    expect(screen.queryByTestId('locations-error')).toBeNull();
  });
});
