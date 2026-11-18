const BASE = '/api';

const unauthorizedListeners = new Set<() => void>();

export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => { unauthorizedListeners.delete(listener); };
}

export function reportUnauthorized(status: number, path: string): void {
  if (status !== 401 || path.startsWith('/auth/')) return;
  for (const listener of unauthorizedListeners) listener();
}

export type ApiError = {
  error: { code: string; message: string };
};

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    reportUnauthorized(res.status, path);
    const body = (await res.json()) as { detail: ApiError };
    throw { status: res.status, ...body.detail };
  }
  return res.json() as Promise<T>;
}

export function errorMessage(err: unknown, fallback: string): string {
  const apiErr = err as { error?: { message?: string } } | null | undefined;
  return apiErr?.error?.message ?? fallback;
}
