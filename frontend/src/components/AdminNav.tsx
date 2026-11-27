import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { ADMIN_SECTIONS } from './adminSections';

export function AdminNav(): ReactNode {
  const { pathname } = useLocation();
  return (
    <nav aria-label="Admin sections" className="flex gap-1 overflow-x-auto" data-testid="admin-nav">
      {ADMIN_SECTIONS.map(section => {
        const active = pathname.startsWith(section.path);
        return (
          <Link
            key={section.path}
            to={section.path}
            aria-current={active ? 'page' : undefined}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold no-underline transition-colors ${
              active ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg'
            }`}
            data-testid={`admin-nav-${section.path.split('/').pop() ?? ''}`}
          >
            {section.label}
          </Link>
        );
      })}
    </nav>
  );
}
