import { useSyncExternalStore } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_KEY = 'health-chatbot.theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

const listeners = new Set<() => void>();
let current: ThemePreference | null = null;

function notifyAll(): void {
  listeners.forEach(listener => listener());
}

function getPreference(): ThemePreference {
  current ??= loadPreference();
  return current;
}

function darkQuery(): MediaQueryList | null {
  return typeof window.matchMedia === 'function' ? window.matchMedia(DARK_QUERY) : null;
}

export function loadPreference(): ThemePreference {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    return saved === 'light' || saved === 'dark' ? saved : 'system';
  } catch {
    return 'system';
  }
}

export function applyPreference(preference: ThemePreference): void {
  const root = document.documentElement;
  if (preference === 'system') delete root.dataset.theme;
  else root.dataset.theme = preference;
}

export function setPreference(preference: ThemePreference): void {
  try {
    if (preference === 'system') window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, preference);
  } catch {
    // storage blocked: the choice lasts until reload
  }
  current = preference;
  applyPreference(preference);
  notifyAll();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const query = darkQuery();
  query?.addEventListener('change', listener);
  const onStorage = (event: StorageEvent): void => {
    if (event.key !== THEME_KEY) return;
    current = loadPreference();
    applyPreference(current);
    listener();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    query?.removeEventListener('change', listener);
    window.removeEventListener('storage', onStorage);
  };
}

export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribe, getPreference, () => 'system');
}
