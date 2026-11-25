import { type ReactNode, useEffect, useId } from 'react';

export function Dialog({
  open,
  title,
  onClose,
  children,
  panelClassName = 'min-w-80',
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  panelClassName?: string;
}): ReactNode {
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`card p-6 shadow-raised ${panelClassName}`}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId} className="mb-4 text-lg font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}
