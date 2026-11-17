import type { ReactNode } from 'react';

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
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div className={`card rise p-6 shadow-raised ${panelClassName}`} onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-lg font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}
