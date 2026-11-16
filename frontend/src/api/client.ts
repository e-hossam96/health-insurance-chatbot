const BASE = '/api';

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
    const body = (await res.json()) as { detail: ApiError };
    throw { status: res.status, ...body.detail };
  }
  return res.json() as Promise<T>;
}

export function errorMessage(err: unknown, fallback: string): string {
  const apiErr = err as { error?: { message?: string } };
  return apiErr.error?.message ?? fallback;
}
