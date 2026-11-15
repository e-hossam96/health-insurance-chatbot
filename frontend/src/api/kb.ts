import { apiFetch } from './client';

const BASE = '/api';

export type KbStatus = 'uploaded' | 'processing' | 'ready' | 'failed';

export type KbDocument = {
  id: number;
  filename: string;
  file_type: 'pdf' | 'txt' | 'docx';
  file_size_bytes: number;
  status: KbStatus;
  error_message: string | null;
  uploaded_by: string;
  created_at: string;
};

export type KbDocumentList = {
  items: KbDocument[];
  total: number;
  max_upload_bytes: number;
};

export class KbUploadError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.docx'];

export function getKbDocuments(limit = 50, offset = 0): Promise<KbDocumentList> {
  return apiFetch(`/admin/kb-documents?limit=${limit}&offset=${offset}`);
}

export async function uploadKbDocument(file: File): Promise<KbDocument> {
  const res = await fetch(`${BASE}/admin/kb-documents?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  });
  if (!res.ok) {
    const payload = (await res.json().catch(() => null)) as { detail?: { error?: { code?: string; message?: string } } } | null;
    const error = payload?.detail?.error;
    throw new KbUploadError(error?.code ?? 'upload_failed', error?.message ?? 'Upload failed.');
  }
  return res.json() as Promise<KbDocument>;
}

export function reindexKbDocument(id: number): Promise<KbDocument> {
  return apiFetch(`/admin/kb-documents/${id}/reindex`, { method: 'POST', body: '{}' });
}

export async function deleteKbDocument(id: number): Promise<void> {
  const res = await fetch(`${BASE}/admin/kb-documents/${id}`, { method: 'DELETE', credentials: 'include' });
  if (!res.ok) {
    const payload = (await res.json().catch(() => null)) as { detail?: { error?: { message?: string } } } | null;
    throw new Error(payload?.detail?.error?.message ?? 'Delete failed.');
  }
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatUtcDay(iso: string): string {
  const date = new Date(iso);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
}

export function needsPolling(documents: KbDocument[]): boolean {
  return documents.some(d => d.status === 'uploaded' || d.status === 'processing');
}
