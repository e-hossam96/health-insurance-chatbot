import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminCatalogPage } from './AdminCatalogPage';

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
  getLocations: () => Promise.resolve([{ id: 1, name: 'Cairo' }, { id: 2, name: 'Giza' }]),
  getSpecialties: () => Promise.resolve([{ id: 1, name: 'Cardiology' }]),
  getClinics: () => Promise.resolve([{ id: 1, name: 'Nile Clinic', location_id: 1 }]),
  getDoctors: () => Promise.resolve([{ id: 1, name: 'Dr. X', clinic_specialty_id: 1 }]),
  createLocation: vi.fn(),
  createSpecialty: vi.fn(),
  createClinic: vi.fn(),
  createDoctor: vi.fn(),
  deleteLocation: vi.fn(),
  deleteSpecialty: vi.fn(),
  deleteClinic: vi.fn(),
  deleteDoctor: vi.fn(),
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <AdminCatalogPage />
    </MemoryRouter>,
  );
}

describe('AdminCatalogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('AP2: shows catalog tabs', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('tab-locations')).toBeTruthy();
      expect(screen.getByTestId('tab-specialties')).toBeTruthy();
      expect(screen.getByTestId('tab-clinics')).toBeTruthy();
      expect(screen.getByTestId('tab-doctors')).toBeTruthy();
    });
  });

  it('AP2: shows locations table', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Cairo')).toBeTruthy();
      expect(screen.getByText('Giza')).toBeTruthy();
    });
  });

  it('AP2: switches to specialties tab', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('tab-specialties')).toBeTruthy());
    fireEvent.click(screen.getByTestId('tab-specialties'));
    await waitFor(() => {
      expect(screen.getByText('Cardiology')).toBeTruthy();
    });
  });

  it('A4: shows duplicate error on location create', async () => {
    const { createLocation } = await import('../api/admin');
    const mockCreate = createLocation as ReturnType<typeof vi.fn>;
    mockCreate.mockRejectedValueOnce({ error: { message: "Location 'Cairo' already exists." } });

    renderPage();
    await waitFor(() => expect(screen.getByText('Cairo')).toBeTruthy());
    fireEvent.click(screen.getByText('+ Add location'));
    const input = screen.getByTestId('location-name-input');
    fireEvent.change(input, { target: { value: 'Cairo' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByTestId('form-error').textContent).toContain('already exists');
    });
  });
});
