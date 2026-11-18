import { apiFetch } from './client';

// --- Types ---

export type Location = { id: number; name: string; clinic_count: number };
export type Specialty = { id: number; name: string };
export type NamedItem = { id: number; name: string };
export type ClinicSpecialtyName = { id: number; name: string; clinic_specialty_id: number };
export type Clinic = { id: number; name: string; location_id: number; location_name: string; specialties: ClinicSpecialtyName[] };
export type ClinicSpecialty = { id: number; clinic_id: number; specialty_id: number };
export type Doctor = {
  id: number;
  name: string;
  clinic_specialty_id: number;
  clinic_id: number;
  clinic_name: string;
  specialty_id: number;
  specialty_name: string;
};
export type Slot = { id: number; doctor_id: number; start_at: string; status: string; visit_id: number | null };
export type AutofillResult = { created: number; skipped: number; message: string };
export type CascadeKind = 'locations' | 'specialties' | 'clinics' | 'doctors';
export type CascadePreview = { cascade: Record<string, number>; blocked: string | null };
export type DeleteResult = { deleted: boolean; cascade?: Record<string, number> };

const CASCADE_ORDER = ['clinics', 'specialties', 'doctors', 'slots'] as const;
const CASCADE_LABELS: Record<string, [string, string]> = {
  clinics: ['clinic', 'clinics'],
  specialties: ['specialty link', 'specialty links'],
  doctors: ['doctor', 'doctors'],
  slots: ['slot', 'slots'],
};

export function describeCascade(cascade: Record<string, number>): string {
  const parts = CASCADE_ORDER.filter((key) => (cascade[key] ?? 0) > 0).map((key) => {
    const count = cascade[key] ?? 0;
    const [one, many] = CASCADE_LABELS[key] ?? [key, key];
    return `${count} ${count === 1 ? one : many}`;
  });
  return parts.length === 0 ? 'Nothing else is deleted.' : `Also deletes ${parts.join(', ')}.`;
}

export function getCascadePreview(kind: CascadeKind, id: number): Promise<CascadePreview> {
  return apiFetch(`/admin/${kind}/${id}/cascade`);
}

// --- Locations ---

export function getLocations(): Promise<Location[]> {
  return apiFetch('/admin/locations');
}

export function createLocation(name: string): Promise<NamedItem> {
  return apiFetch('/admin/locations', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteLocation(id: number): Promise<DeleteResult> {
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

export function deleteSpecialty(id: number): Promise<DeleteResult> {
  return apiFetch(`/admin/specialties/${id}`, { method: 'DELETE' });
}

// --- Clinics ---

export function getClinics(): Promise<Clinic[]> {
  return apiFetch('/admin/clinics');
}

export function createClinic(name: string, location_id: number): Promise<{ id: number; name: string; location_id: number }> {
  return apiFetch('/admin/clinics', {
    method: 'POST',
    body: JSON.stringify({ name, location_id }),
  });
}

export function deleteClinic(id: number): Promise<DeleteResult> {
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

export function createDoctor(name: string, clinic_specialty_id: number): Promise<{ id: number; name: string; clinic_specialty_id: number }> {
  return apiFetch('/admin/doctors', {
    method: 'POST',
    body: JSON.stringify({ name, clinic_specialty_id }),
  });
}

export function deleteDoctor(id: number): Promise<DeleteResult> {
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

// --- Admin Visits ---

export type AdminVisit = {
  id: number;
  profile_id: number;
  slot_id: number;
  status: string;
  patient_name: string;
  location: string;
  clinic: string;
  specialty: string;
  doctor_name: string;
  start_at: string;
};
export type AdminVisitList = { items: AdminVisit[]; total: number };
export type AdminVisitQuery = { limit?: number; offset?: number; status?: string; patient?: string; visitId?: number };

export function getAdminVisits(params: AdminVisitQuery = {}): Promise<AdminVisitList> {
  const search = new URLSearchParams();
  if (params.limit) search.set('limit', String(params.limit));
  if (params.offset) search.set('offset', String(params.offset));
  if (params.status) search.set('status', params.status);
  if (params.patient) search.set('patient', params.patient);
  if (params.visitId !== undefined) search.set('visit_id', String(params.visitId));
  return apiFetch(`/admin/visits?${search.toString()}`);
}

export function completeVisit(visitId: number): Promise<{ id: number; status: string }> {
  return apiFetch(`/admin/visits/${visitId}/complete`, { method: 'POST' });
}

// --- Admin Complaints ---

export type AdminComplaint = {
  id: number;
  visit_id: number;
  description: string;
  status: string;
  created_at: string;
  patient_name: string;
  reply_count: number;
};
export type AdminComplaintList = { items: AdminComplaint[]; total: number };
export type AdminComplaintReply = { id: number; body: string; created_at: string; admin_username: string };
export type AdminComplaintDetail = {
  id: number;
  description: string;
  status: string;
  created_at: string;
  patient_name: string;
  visit: { id: number; start_at: string; doctor_name: string; specialty: string; clinic: string; location: string };
  replies: AdminComplaintReply[];
};

export function getAdminComplaint(complaintId: number): Promise<AdminComplaintDetail> {
  return apiFetch(`/admin/complaints/${complaintId}`);
}

export function getAdminComplaints(params: { limit?: number; offset?: number; status?: string } = {}): Promise<AdminComplaintList> {
  const search = new URLSearchParams();
  if (params.limit) search.set('limit', String(params.limit));
  if (params.offset) search.set('offset', String(params.offset));
  if (params.status) search.set('status', params.status);
  return apiFetch(`/admin/complaints?${search.toString()}`);
}

export function replyToComplaint(
  complaintId: number,
  body: string,
  close = false,
): Promise<{ id: number; body: string; complaint_status: string }> {
  return apiFetch(`/admin/complaints/${complaintId}/reply`, {
    method: 'POST',
    body: JSON.stringify({ body, close }),
  });
}

export function closeComplaint(complaintId: number): Promise<{ id: number; status: string }> {
  return apiFetch(`/admin/complaints/${complaintId}/close`, { method: 'POST' });
}
