import { apiFetch } from './client';

// --- Types ---

export type Location = { id: number; name: string };
export type Specialty = { id: number; name: string };
export type Clinic = { id: number; name: string; location_id: number };
export type ClinicSpecialty = { id: number; clinic_id: number; specialty_id: number };
export type Doctor = { id: number; name: string; clinic_specialty_id: number };
export type Slot = { id: number; doctor_id: number; start_at: string; status: string };
export type AutofillResult = { created: number; message: string };

// --- Locations ---

export function getLocations(): Promise<Location[]> {
  return apiFetch('/admin/locations');
}

export function createLocation(name: string): Promise<Location> {
  return apiFetch('/admin/locations', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteLocation(id: number): Promise<{ deleted: boolean; cascade: { clinics: number } }> {
  return apiFetch(`/admin/locations/${id}`, { method: 'DELETE' });
}

// --- Specialties ---

export function getSpecialties(): Promise<Specialty[]> {
  return apiFetch('/admin/specialties');
}

export function createSpecialty(name: string): Promise<Specialty> {
  return apiFetch('/admin/specialties', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteSpecialty(id: number): Promise<{ deleted: boolean }> {
  return apiFetch(`/admin/specialties/${id}`, { method: 'DELETE' });
}

// --- Clinics ---

export function getClinics(): Promise<Clinic[]> {
  return apiFetch('/admin/clinics');
}

export function createClinic(name: string, location_id: number): Promise<Clinic> {
  return apiFetch('/admin/clinics', {
    method: 'POST',
    body: JSON.stringify({ name, location_id }),
  });
}

export function deleteClinic(id: number): Promise<{ deleted: boolean; cascade: { specialties: number; doctors: number } }> {
  return apiFetch(`/admin/clinics/${id}`, { method: 'DELETE' });
}

export function setClinicSpecialties(
  clinicId: number,
  specialtyIds: number[],
): Promise<ClinicSpecialty[]> {
  return apiFetch(`/admin/clinics/${clinicId}/specialties`, {
    method: 'PUT',
    body: JSON.stringify(specialtyIds.map((id) => ({ specialty_id: id }))),
  });
}

// --- Doctors ---

export function getDoctors(): Promise<Doctor[]> {
  return apiFetch('/admin/doctors');
}

export function createDoctor(name: string, clinic_specialty_id: number): Promise<Doctor> {
  return apiFetch('/admin/doctors', {
    method: 'POST',
    body: JSON.stringify({ name, clinic_specialty_id }),
  });
}

export function deleteDoctor(id: number): Promise<{ deleted: boolean; cascade: { slots: number } }> {
  return apiFetch(`/admin/doctors/${id}`, { method: 'DELETE' });
}

// --- Slots ---

export function getSlots(doctorId: number, year: number, month: number): Promise<Slot[]> {
  return apiFetch(`/admin/slots?doctor_id=${doctorId}&year=${year}&month=${month}`);
}

export function createSlot(doctorId: number, startAt: string): Promise<Slot> {
  return apiFetch('/admin/slots', {
    method: 'POST',
    body: JSON.stringify({ doctor_id: doctorId, start_at: startAt }),
  });
}

export function deleteSlot(slotId: number): Promise<{ deleted: boolean }> {
  return apiFetch(`/admin/slots/${slotId}`, { method: 'DELETE' });
}

export function autofillSlots(doctorId: number): Promise<AutofillResult> {
  return apiFetch('/admin/slots/autofill', {
    method: 'POST',
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}
