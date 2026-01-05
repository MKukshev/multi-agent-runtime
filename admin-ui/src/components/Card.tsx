import { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = '', onClick }: CardProps) {
  return (
    <div
      className={`bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 transition-all duration-200 ${
        onClick ? 'cursor-pointer hover:border-[var(--primary)] hover:bg-[var(--card-hover)]' : ''
      } ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  trend?: 'up' | 'down' | 'neutral';
}

export function StatCard({ title, value, icon }: StatCardProps) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[var(--muted)] text-sm">{title}</p>
          <p className="text-3xl font-bold mt-1">{value}</p>
        </div>
        <div className="text-4xl opacity-50">{icon}</div>
      </div>
    </Card>
  );
}

export default Card;

