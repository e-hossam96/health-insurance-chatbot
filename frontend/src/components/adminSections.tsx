import type { ReactNode } from 'react';
import { BookIcon, BuildingIcon, CalendarIcon, ClipboardCheckIcon, MessageAlertIcon } from './icons';

export type AdminSection = { path: string; label: string; hint: string; icon: ReactNode };

export const ADMIN_SECTIONS: AdminSection[] = [
  { path: '/admin/kb', label: 'KB documents', hint: 'Upload and index policy files', icon: <BookIcon /> },
  { path: '/admin/catalog', label: 'Catalog', hint: 'Locations, specialties, clinics, doctors', icon: <BuildingIcon /> },
  { path: '/admin/slots', label: 'Slots', hint: 'Open and remove appointment slots', icon: <CalendarIcon /> },
  { path: '/admin/visits', label: 'Visits', hint: 'Review and complete booked visits', icon: <ClipboardCheckIcon /> },
  { path: '/admin/complaints', label: 'Complaints', hint: 'Reply to and close complaints', icon: <MessageAlertIcon /> },
];
