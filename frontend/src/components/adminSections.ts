export type AdminSection = { path: string; label: string };

export const ADMIN_SECTIONS: AdminSection[] = [
  { path: '/admin/kb', label: 'Knowledge base' },
  { path: '/admin/catalog', label: 'Catalog' },
  { path: '/admin/slots', label: 'Slots' },
  { path: '/admin/visits', label: 'Visits' },
  { path: '/admin/complaints', label: 'Complaints' },
];
