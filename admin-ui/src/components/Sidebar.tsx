'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { UserMenu } from './UserMenu';

const navItems = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/prompts', label: 'Prompts', icon: '📝' },
  { href: '/tools', label: 'Tools', icon: '🔧' },
  { href: '/templates', label: 'Templates', icon: '📋' },
  { href: '/instances', label: 'Instances', icon: '⚡' },
  { href: '/sessions', label: 'Sessions', icon: '💬' },
  { href: '/chat', label: 'Chat', icon: '🤖' },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-[var(--card)] border-r border-[var(--border)] p-4 flex flex-col">
      <div className="mb-8">
        <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
          Multi Agentic Runtime
        </h1>
        <p className="text-xs text-[var(--muted)] mt-1">Admin Dashboard</p>
      </div>

      <nav className="flex-1 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                isActive
                  ? 'bg-[var(--primary)] text-white'
                  : 'text-[var(--muted)] hover:text-white hover:bg-[var(--card-hover)]'
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="pt-4 border-t border-[var(--border)] space-y-3">
        <UserMenu />
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
          <span className="w-2 h-2 rounded-full bg-[var(--success)] animate-pulse"></span>
          <span>Connected</span>
        </div>
      </div>
    </aside>
  );
}

