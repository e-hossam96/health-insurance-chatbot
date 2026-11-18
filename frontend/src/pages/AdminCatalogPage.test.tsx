import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminCatalogPage } from './AdminCatalogPage';
import { createDoctor, deleteClinic, deleteLocation, getCascadePreview, setClinicSpecialties } from '../api/admin';

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

vi.mock('../api/admin', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/admin')>();
  return {
    describeCascade: actual.describeCascade,
    getLocations: () => Promise.resolve([{ id: 1, name: 'Cairo', clinic_count: 2 }, { id: 2, name: 'Giza', clinic_count: 0 }]),
    getSpecialties: () => Promise.resolve([{ id: 1, name: 'Cardiology' }, { id: 2, name: 'Dermatology' }]),
    getClinics: () => Promise.resolve([
      {
        id: 1, name: 'Nile Clinic', location_id: 1, location_name: 'Cairo',
        specialties: [{ id: 1, name: 'Cardiology', clinic_specialty_id: 11 }, { id: 2, name: 'Dermatology', clinic_specialty_id: 12 }],
      },
      { id: 2, name: 'Empty Clinic', location_id: 2, location_name: 'Giza', specialties: [] },
    ]),
    getDoctors: () => Promise.resolve([
      { id: 1, name: 'Dr. X', clinic_specialty_id: 11, clinic_id: 1, clinic_name: 'Nile Clinic', specialty_id: 1, specialty_name: 'Cardiology' },
    ]),
    getCascadePreview: vi.fn(),
    createLocation: vi.fn(),
    createSpecialty: vi.fn(),
    createClinic: vi.fn(),
    createDoctor: vi.fn(),
    deleteLocation: vi.fn(),
    deleteSpecialty: vi.fn(),
    deleteClinic: vi.fn(),
    deleteDoctor: vi.fn(),
    setClinicSpecialties: vi.fn(),
  };
});

const preview = getCascadePreview as ReturnType<typeof vi.fn>;

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
    preview.mockResolvedValue({ cascade: {}, blocked: null });
  });

  it('A5: delete is a button that asks for confirmation before deleting', async () => {
    renderPage();
    const [deleteCairo] = await screen.findAllByTestId('catalog-delete');
    expect(deleteCairo.tagName).toBe('BUTTON');
    fireEvent.click(deleteCairo);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Delete Cairo?');
    expect(preview).toHaveBeenCalledWith('locations', 1);
    expect(deleteLocation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(deleteLocation).toHaveBeenCalledWith(1));
  });

  it('A5: the confirm dialog lists what the delete cascades to', async () => {
    preview.mockResolvedValueOnce({ cascade: { clinics: 2, doctors: 5, slots: 320 }, blocked: null });
    renderPage();
    fireEvent.click((await screen.findAllByTestId('catalog-delete'))[0]);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Also deletes 2 clinics, 5 doctors, 320 slots.');
  });

  it('A5: a delete blocked by visit history says so before anything is sent', async () => {
    preview.mockResolvedValueOnce({ cascade: { specialties: 2, doctors: 1, slots: 4 }, blocked: "Can't delete: it has visit history." });
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-clinics'));
    fireEvent.click((await screen.findAllByTestId('catalog-delete'))[0]);
    expect((await screen.findByTestId('confirm-blocked')).textContent).toBe("Can't delete: it has visit history.");
    expect(screen.getByTestId('confirm-yes')).toBeDisabled();
    expect(preview).toHaveBeenCalledWith('clinics', 1);
    expect(deleteClinic).not.toHaveBeenCalled();
  });

  it('A5: a delete refused by the server still shows the reason in the dialog', async () => {
    (deleteClinic as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: "Can't delete: it has visit history." } });
    preview.mockResolvedValueOnce({ cascade: { specialties: 1, doctors: 2, slots: 0 }, blocked: null });
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-clinics'));
    fireEvent.click((await screen.findAllByTestId('catalog-delete'))[0]);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Also deletes 1 specialty link, 2 doctors.');
    fireEvent.click(screen.getByTestId('confirm-yes'));
    expect((await screen.findByTestId('confirm-error')).textContent).toBe("Can't delete: it has visit history.");
  });

  it('A5: when the preview fails the dialog still opens with a general warning', async () => {
    preview.mockRejectedValueOnce(new Error('offline'));
    renderPage();
    fireEvent.click((await screen.findAllByTestId('catalog-delete'))[1]);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Anything that belongs to it is deleted too.');
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
    expect(await screen.findByRole('dialog')).toHaveTextContent('Delete Giza?');
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

  it('AP2: the locations table shows each location with its clinic count', async () => {
    renderPage();
    const table = await screen.findByTestId('locations-table');
    const rows = within(table).getAllByRole('row').slice(1).map((row) => row.textContent);
    expect(rows[0]).toContain('Cairo');
    expect(rows[0]).toContain('2');
    expect(rows[1]).toContain('Giza');
    expect(rows[1]).toContain('0');
  });

  it('AP2: switches to specialties tab', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('tab-specialties')).toBeTruthy());
    fireEvent.click(screen.getByTestId('tab-specialties'));
    await waitFor(() => {
      expect(screen.getByText('Cardiology')).toBeTruthy();
    });
  });

  it('AP2: clinics show their location and specialty chips, and [Specialties] saves new links', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-clinics'));
    const [nileChips, emptyChips] = await screen.findAllByTestId('clinic-specialty-chips');
    expect(nileChips?.textContent).toBe('CardiologyDermatology');
    expect(emptyChips?.textContent).toBe('None');
    expect(screen.getByTestId('clinics-table')).toHaveTextContent('Cairo');

    fireEvent.click(screen.getAllByTestId('clinic-specialties-btn')[1] as HTMLElement);
    const editor = await screen.findByTestId('clinic-specialties-edit');
    fireEvent.click(within(editor).getByLabelText('Dermatology'));
    fireEvent.click(screen.getByTestId('clinic-specialties-save'));
    await waitFor(() => expect(setClinicSpecialties).toHaveBeenCalledWith(2, [2]));
  });

  it('AP2: removing a link that has doctors shows the refusal in the specialties dialog', async () => {
    (setClinicSpecialties as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: 'Cannot remove specialty 1: has doctors.' } });
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-clinics'));
    fireEvent.click((await screen.findAllByTestId('clinic-specialties-btn'))[0] as HTMLElement);
    const editor = await screen.findByTestId('clinic-specialties-edit');
    fireEvent.click(within(editor).getByLabelText('Cardiology'));
    fireEvent.click(screen.getByTestId('clinic-specialties-save'));
    expect((await screen.findByTestId('clinic-specialties-error')).textContent).toBe('Cannot remove specialty 1: has doctors.');
  });

  it('AP2: doctors show their clinic and specialty names', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-doctors'));
    const table = await screen.findByTestId('doctors-table');
    expect(table).toHaveTextContent('Nile Clinic');
    expect(table).toHaveTextContent('Cardiology');
    expect(table.textContent).not.toContain('11');
  });

  it('AP2: the doctor form offers only the chosen clinic specialties', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-doctors'));
    fireEvent.click(await screen.findByText('+ Add doctor'));
    fireEvent.change(screen.getByTestId('doctor-name-input'), { target: { value: 'Dr. New' } });
    fireEvent.change(screen.getByTestId('doctor-clinic-select'), { target: { value: '1' } });
    const specialty = screen.getByTestId('doctor-specialty-select');
    expect(within(specialty).getAllByRole('option').map((o) => o.textContent)).toEqual(['Select specialty', 'Cardiology', 'Dermatology']);
    fireEvent.change(specialty, { target: { value: '12' } });
    fireEvent.submit(specialty.closest('form') as HTMLFormElement);
    await waitFor(() => expect(createDoctor).toHaveBeenCalledWith('Dr. New', 12));
  });

  it('AP2: a clinic without specialties asks for one before a doctor can be added', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('tab-doctors'));
    fireEvent.click(await screen.findByText('+ Add doctor'));
    fireEvent.change(screen.getByTestId('doctor-clinic-select'), { target: { value: '2' } });
    expect(screen.getByTestId('doctor-no-specialty').textContent).toBe('Add a specialty to this clinic first.');
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
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
    fireEvent.submit(input.closest('form') as HTMLFormElement);

    await waitFor(() => {
      expect(screen.getByTestId('form-error').textContent).toContain('already exists');
    });
  });
});
