import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { THEME_KEY, applyPreference, loadPreference, setPreference, useThemePreference } from './theme';

afterEach(() => {
  vi.restoreAllMocks();
  setPreference('system');
});

describe('theme preference', () => {
  it('reads a saved light or dark choice and ignores anything else', () => {
    localStorage.setItem(THEME_KEY, 'dark');
    expect(loadPreference()).toBe('dark');
    localStorage.setItem(THEME_KEY, 'light');
    expect(loadPreference()).toBe('light');
    localStorage.setItem(THEME_KEY, 'purple');
    expect(loadPreference()).toBe('system');
    localStorage.removeItem(THEME_KEY);
    expect(loadPreference()).toBe('system');
  });

  it('falls back to the system when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(loadPreference()).toBe('system');
  });

  it('still applies a choice for this page when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => setPreference('dark')).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('sets and clears the page attribute the stylesheet reads', () => {
    applyPreference('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    applyPreference('system');
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('follows a choice made in another tab', () => {
    const { result } = renderHook(() => useThemePreference());
    expect(result.current).toBe('system');

    act(() => {
      localStorage.setItem(THEME_KEY, 'dark');
      window.dispatchEvent(new StorageEvent('storage', { key: THEME_KEY, newValue: 'dark' }));
    });
    expect(result.current).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'unrelated', newValue: 'x' }));
    });
    expect(result.current).toBe('dark');
  });
});
