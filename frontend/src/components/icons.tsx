import type { ReactNode } from 'react';

function Icon({ size = 16, children }: { size?: number; children: ReactNode }): ReactNode {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function ChatPlusIcon({ size = 22 }: { size?: number }): ReactNode {
  return (
    <Icon size={size}>
      <path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-7l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
      <path d="M12 7.5v6M9 10.5h6" />
    </Icon>
  );
}

export function PlusIcon(): ReactNode {
  return (
    <Icon>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function UploadIcon(): ReactNode {
  return (
    <Icon size={22}>
      <path d="M12 16V4M7 9l5-5 5 5M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </Icon>
  );
}

export function CloseIcon(): ReactNode {
  return (
    <Icon size={18}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  );
}

export function SendIcon(): ReactNode {
  return (
    <Icon>
      <path d="M4 12l16-8-6 16-2.5-6.5z" />
    </Icon>
  );
}

export function InfoIcon(): ReactNode {
  return (
    <Icon size={14}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8v.01" />
    </Icon>
  );
}

export function MonitorIcon(): ReactNode {
  return (
    <Icon>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </Icon>
  );
}

export function SunIcon(): ReactNode {
  return (
    <Icon>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Icon>
  );
}

export function MoonIcon(): ReactNode {
  return (
    <Icon>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    </Icon>
  );
}

export function MenuIcon(): ReactNode {
  return (
    <Icon>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </Icon>
  );
}
