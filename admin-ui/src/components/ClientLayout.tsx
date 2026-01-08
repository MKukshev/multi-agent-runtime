'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';

// Pages that should NOT show sidebar (auth pages)
const noSidebarPaths = ['/login', '/register'];

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  
  const showSidebar = !noSidebarPaths.some(path => pathname === path || pathname.startsWith(path + '/'));

  if (!showSidebar) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        {children}
      </main>
    </div>
  );
}
