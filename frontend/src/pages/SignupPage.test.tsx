import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { SignupPage } from './SignupPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({ status: 'unauthenticated', refresh: vi.fn() }),
}));

vi.mock('../api/auth', () => ({
  signup: vi.fn(),
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <SignupPage />
    </MemoryRouter>,
  );
}

describe('SignupPage form errors', () => {
  it('shows error for empty fields', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /sign up/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('All fields are required');
  });

  it('shows error for password mismatch', () => {
    renderPage();
    const inputs = document.querySelectorAll('input');
    fireEvent.change(inputs[0]!, { target: { value: 'alice' } });
    fireEvent.change(inputs[1]!, { target: { value: 'password123' } });
    fireEvent.change(inputs[2]!, { target: { value: 'different' } });
    fireEvent.click(screen.getByRole('button', { name: /sign up/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match');
  });

  it('shows error for short password', () => {
    renderPage();
    const inputs = document.querySelectorAll('input');
    fireEvent.change(inputs[0]!, { target: { value: 'alice' } });
    fireEvent.change(inputs[1]!, { target: { value: 'short' } });
    fireEvent.change(inputs[2]!, { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: /sign up/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('at least 8 characters');
  });
});
