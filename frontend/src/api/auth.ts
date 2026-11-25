import { apiFetch } from './client';

export type MeResponse = {
  username: string;
  role: 'user' | 'admin';
  has_profile: boolean;
  mode: 'user' | 'admin';
  name: string | null;
};

export type LocationItem = {
  id: number;
  name: string;
};

export function signup(username: string, password: string): Promise<{ message: string }> {
  return apiFetch('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<{ message: string }> {
  return apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ message: string }> {
  return apiFetch('/auth/logout', { method: 'POST', body: '{}' });
}

export function getMe(): Promise<MeResponse> {
  return apiFetch('/auth/me');
}

export function setMode(mode: 'admin' | 'user'): Promise<{ mode: string }> {
  return apiFetch('/auth/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export function getLocations(): Promise<LocationItem[]> {
  return apiFetch('/locations');
}

export function createProfile(name: string, location_id: number): Promise<unknown> {
  return apiFetch('/me/profile', {
    method: 'POST',
    body: JSON.stringify({ name, location_id }),
  });
}
