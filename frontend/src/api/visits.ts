import { apiFetch } from './client';

export type VisitItem = {
  id: number;
  slot_id: number;
  status: string;
  doctor_name: string;
  specialty: string;
  clinic: string;
  location: string;
  start_at: string;
};

export type ReplyItem = {
  id: number;
  body: string;
};

export type ComplaintItem = {
  id: number;
  visit_id: number;
  description: string;
  status: string;
  replies: ReplyItem[];
};

export function getMyVisits(): Promise<VisitItem[]> {
  return apiFetch('/me/visits');
}

export function cancelVisit(visitId: number, sessionId?: number): Promise<unknown> {
  return apiFetch(`/me/visits/${visitId}/cancel`, {
    method: 'POST',
    body: JSON.stringify(sessionId ? { session_id: sessionId } : {}),
  });
}

export function getMyComplaints(): Promise<ComplaintItem[]> {
  return apiFetch('/me/complaints');
}

export function fileComplaint(sessionId: number, visitId: number, description: string): Promise<unknown> {
  return apiFetch('/me/complaints', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, visit_id: visitId, description }),
  });
}
