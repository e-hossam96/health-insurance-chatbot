import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { APP_NAME, Logo } from './Logo';

describe('Logo', () => {
  it('shows the product name next to the mark', () => {
    render(<Logo />);
    expect(screen.getByTestId('app-logo').textContent).toBe(APP_NAME);
    expect(APP_NAME).toBe('Health Insurance Chatbot');
    expect(screen.getByTestId('app-logo').querySelector('svg')).toBeTruthy();
  });
});
