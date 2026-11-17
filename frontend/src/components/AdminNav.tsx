import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { ADMIN_SECTIONS } from './adminSections';
import { ChevronDownIcon } from './icons';

export function AdminNav(): ReactNode {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const currentIndex = ADMIN_SECTIONS.findIndex(section => pathname.startsWith(section.path));
  const current = currentIndex >= 0 ? ADMIN_SECTIONS[currentIndex] : undefined;

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent): void => {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    itemRefs.current[Math.max(currentIndex, 0)]?.focus();
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, [open, currentIndex]);

  function close(): void {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function moveFocus(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const focused = itemRefs.current.findIndex(item => item === document.activeElement);
    const step = event.key === 'ArrowDown' ? 1 : -1;
    const next = (focused + step + ADMIN_SECTIONS.length) % ADMIN_SECTIONS.length;
    itemRefs.current[next]?.focus();
  }

  return (
    <div className="relative" ref={containerRef} onKeyDown={open ? moveFocus : undefined}>
      <button
        ref={triggerRef}
        type="button"
        className="btn btn-secondary btn-sm"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        data-testid="admin-nav-btn"
      >
        {current?.icon}
        {current?.label ?? 'Admin sections'}
        <ChevronDownIcon />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Admin sections"
          className="card rise absolute right-0 z-40 mt-2 w-72 p-1.5 shadow-raised"
          data-testid="admin-nav-menu"
        >
          {ADMIN_SECTIONS.map((section, index) => {
            const active = index === currentIndex;
            return (
              <Link
                key={section.path}
                ref={element => {
                  itemRefs.current[index] = element;
                }}
                to={section.path}
                role="menuitem"
                aria-current={active ? 'page' : undefined}
                onClick={() => setOpen(false)}
                className={`flex items-start gap-3 rounded-control px-3 py-2.5 no-underline transition-colors focus-visible:outline-offset-[-2px] ${
                  active ? 'bg-accent-soft text-accent' : 'text-fg hover:bg-surface'
                }`}
                data-testid={`admin-nav-${section.path.split('/').pop() ?? ''}`}
              >
                <span className={`mt-0.5 ${active ? 'text-accent' : 'text-muted'}`}>{section.icon}</span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold">{section.label}</span>
                  <span className="text-xs text-muted">{section.hint}</span>
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
