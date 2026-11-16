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
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className={`bg-white rounded-lg shadow-lg p-6 ${panelClassName}`} onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}
