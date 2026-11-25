import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { AdminNav } from './AdminNav';
import { ADMIN_SECTIONS } from './adminSections';

function CurrentPath(): string {
  return useLocation().pathname;
}

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AdminNav />
      <Routes>
        <Route path="*" element={<p data-testid="current-path"><CurrentPath /></p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AdminNav', () => {
  it('B5: lists every admin section as a visible tab, in order', () => {
    renderAt('/admin/kb');
    const tabs = screen.getAllByRole('link');
    expect(tabs.map(tab => tab.getAttribute('href'))).toEqual([
      '/admin/kb',
      '/admin/catalog',
      '/admin/slots',
      '/admin/visits',
      '/admin/complaints',
    ]);
    expect(tabs.map(tab => tab.textContent)).toEqual(ADMIN_SECTIONS.map(section => section.label));
  });

  it('B5: marks only the current section', () => {
    renderAt('/admin/slots');
    expect(screen.getByTestId('admin-nav-slots')).toHaveAttribute('aria-current', 'page');
    expect(screen.getAllByRole('link').filter(tab => tab.hasAttribute('aria-current'))).toHaveLength(1);
  });

  it('B5: clicking a tab navigates there and moves the marker', async () => {
    const user = userEvent.setup();
    renderAt('/admin/kb');
    await user.click(screen.getByTestId('admin-nav-complaints'));

    expect(screen.getByTestId('current-path')).toHaveTextContent('/admin/complaints');
    expect(screen.getByTestId('admin-nav-complaints')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByTestId('admin-nav-kb')).not.toHaveAttribute('aria-current');
  });
});
