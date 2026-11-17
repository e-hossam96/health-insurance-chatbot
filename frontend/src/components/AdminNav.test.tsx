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
  it('B5: names the current admin section on the trigger', () => {
    renderAt('/admin/slots');
    expect(screen.getByTestId('admin-nav-btn')).toHaveTextContent('Slots');
    expect(screen.getByTestId('admin-nav-btn')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('B5: lists every admin section with a hint and marks the current one', async () => {
    const user = userEvent.setup();
    renderAt('/admin/kb');
    await user.click(screen.getByTestId('admin-nav-btn'));

    const items = screen.getAllByRole('menuitem');
    expect(items.map(item => item.getAttribute('href'))).toEqual([
      '/admin/kb',
      '/admin/catalog',
      '/admin/slots',
      '/admin/visits',
      '/admin/complaints',
    ]);
    for (const [index, section] of ADMIN_SECTIONS.entries()) {
      expect(items[index]).toHaveTextContent(section.label);
      expect(items[index]).toHaveTextContent(section.hint);
    }
    expect(screen.getByTestId('admin-nav-kb')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByTestId('admin-nav-catalog')).not.toHaveAttribute('aria-current');
    expect(screen.getByTestId('admin-nav-kb')).toHaveFocus();
  });

  it('B5: picking a section navigates there and closes the menu', async () => {
    const user = userEvent.setup();
    renderAt('/admin/kb');
    await user.click(screen.getByTestId('admin-nav-btn'));
    await user.click(screen.getByTestId('admin-nav-complaints'));

    expect(screen.getByTestId('current-path')).toHaveTextContent('/admin/complaints');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByTestId('admin-nav-btn')).toHaveTextContent('Complaints');
  });

  it('moves through sections with the arrow keys and closes on Escape', async () => {
    const user = userEvent.setup();
    renderAt('/admin/kb');
    await user.click(screen.getByTestId('admin-nav-btn'));

    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId('admin-nav-catalog')).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}');
    expect(screen.getByTestId('admin-nav-complaints')).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByTestId('admin-nav-btn')).toHaveFocus();
  });

  it('closes when clicking outside', async () => {
    const user = userEvent.setup();
    renderAt('/admin/kb');
    await user.click(screen.getByTestId('admin-nav-btn'));
    await user.click(screen.getByTestId('current-path'));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
