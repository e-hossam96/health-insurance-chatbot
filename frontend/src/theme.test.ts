import { describe, expect, it } from 'vitest';
import html from '../index.html?raw';
import initScript from '../public/theme-init.js?raw';
import css from './index.css?raw';
import { THEME_KEY } from './theme';

function channel(value: number): number {
  const s = value / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(a: string, b: string): number {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

const root = /:root\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
const HEX = '(#[0-9a-fA-F]{6})';
const pairs = [...root.matchAll(new RegExp(`--([\\w-]+):\\s*light-dark\\(\\s*${HEX}\\s*,\\s*${HEX}\\s*\\)\\s*;`, 'g'))];
const THEMES: Record<'light' | 'dark', Record<string, string>> = {
  light: Object.fromEntries(pairs.map(match => [match[1], match[2]])),
  dark: Object.fromEntries(pairs.map(match => [match[1], match[3]])),
};

const TEXT_PAIRS: [string, string][] = [
  ['text', 'bg'],
  ['text', 'card'],
  ['text', 'surface'],
  ['muted', 'bg'],
  ['muted', 'card'],
  ['muted', 'surface'],
  ['link', 'card'],
  ['link', 'bg'],
  ['link', 'surface'],
  ['text', 'accent-soft'],
  ['accent-text', 'accent'],
  ['accent-text', 'accent-hover'],
  ['tag-text', 'tag-bg'],
  ['sand-text', 'sand'],
  ['rust-text', 'rust'],
  ['danger-text', 'card'],
  ['danger-text', 'surface'],
  ['danger-on', 'danger'],
  ['danger-on', 'danger-hover'],
  ['danger-text', 'danger-bg'],
  ['success-text', 'success-bg'],
  ['warn-text', 'warn-bg'],
  ['info-text', 'info-bg'],
];

const UI_PAIRS: [string, string][] = [
  ['border-strong', 'card'],
  ['border-strong', 'bg'],
  ['border-strong', 'surface'],
  ['accent', 'card'],
  ['accent', 'bg'],
  ['accent', 'surface'],
];

describe.each(['light', 'dark'] as const)('%s theme', scheme => {
  const tokens = THEMES[scheme];

  it('defines every color the pairs rely on', () => {
    for (const name of new Set([...TEXT_PAIRS, ...UI_PAIRS].flat())) {
      expect(tokens[name], `--${name}`).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it.each(TEXT_PAIRS)('%s text on %s reads at 4.5:1', (foreground, background) => {
    expect(contrastRatio(tokens[foreground], tokens[background])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)('%s control edge on %s stands out at 3:1', (outline, background) => {
    expect(contrastRatio(tokens[outline], tokens[background])).toBeGreaterThanOrEqual(3);
  });

  it('keeps divider lines soft against the card', () => {
    expect(contrastRatio(tokens.border, tokens.card)).toBeLessThan(1.6);
  });
});

describe('theme switching', () => {
  it('follows the system by default', () => {
    expect(root).toMatch(/color-scheme:\s*light dark\s*;/);
    expect(html).toContain('<meta name="color-scheme" content="light dark"');
  });

  it('lets a pinned choice override the system before first paint', () => {
    expect(css).toMatch(/:root\[data-theme='light'\]\s*\{\s*color-scheme:\s*light;/);
    expect(css).toMatch(/:root\[data-theme='dark'\]\s*\{\s*color-scheme:\s*dark;/);
    expect(html).toContain('<script src="/theme-init.js"></script>');
    expect(initScript).toContain(`localStorage.getItem('${THEME_KEY}')`);
  });
});
