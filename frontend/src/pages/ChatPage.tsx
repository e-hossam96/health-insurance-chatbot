import { type ReactNode, useState } from 'react';
import { Header } from '../components/Header';
import { VisitsDrawer } from '../components/VisitsDrawer';

export function ChatPage(): ReactNode {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <Header onVisitsClick={() => setDrawerOpen(true)} />
      <main className="flex-1 flex items-center justify-center text-gray-500">
        Chat coming soon
      </main>
      <VisitsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
