import type { ReactNode } from 'react';
import { Header } from '../components/Header';

export function AdminKbPage(): ReactNode {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 flex items-center justify-center text-gray-500">
        Knowledge Base management coming soon
      </main>
    </div>
  );
}
