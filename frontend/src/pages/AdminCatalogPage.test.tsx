import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminCatalogPage } from './AdminCatalogPage';
import { deleteClinic, deleteLocation } from '../api/admin';

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

  it('A5: delete is a button that asks for confirmation before deleting', async () => {
    renderPage();
    const [deleteCairo] = await screen.findAllByTestId('catalog-delete');
    expect(deleteCairo.tagName).toBe('BUTTON');
    fireEvent.click(deleteCairo);
    expect(screen.getByRole('dialog')).toHaveTextContent('Delete Cairo?');
    expect(deleteLocation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(deleteLocation).toHaveBeenCalledWith(1));
  });

  it('A5: a delete blocked by visit history shows the reason in the dialog', async () => {
    (deleteClinic as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: "Can't delete: it has visit history." } });
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-clinics'));
    fireEvent.click(await screen.findByTestId('catalog-delete'));
    expect(screen.getByRole('dialog')).toHaveTextContent('also deletes its linked specialties and doctors');
    fireEvent.click(screen.getByTestId('confirm-yes'));
    expect((await screen.findByTestId('confirm-error')).textContent).toBe("Can't delete: it has visit history.");
  });

  it('AP2: the tabs show which catalog list is open', async () => {
    renderPage();
    await screen.findByTestId('locations-table');
    expect(screen.getByTestId('tab-locations')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByTestId('tab-doctors'));
    expect(screen.getByTestId('tab-doctors')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('tab-locations')).toHaveAttribute('aria-pressed', 'false');
    expect(await screen.findByTestId('doctors-table')).toBeTruthy();
  });

  it('A5: cancelling the confirmation deletes nothing', async () => {
    renderPage();
    fireEvent.click((await screen.findAllByTestId('catalog-delete'))[1]);
    expect(screen.getByRole('dialog')).toHaveTextContent('Delete Giza?');
    fireEvent.click(screen.getByTestId('confirm-cancel'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(deleteLocation).not.toHaveBeenCalled();
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
