interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'muted';
  color?: 'green' | 'yellow' | 'red' | 'blue' | 'gray';
  className?: string;
}

const variantClasses = {
  default: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  success: 'bg-green-500/20 text-green-400 border-green-500/30',
  warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  danger: 'bg-red-500/20 text-red-400 border-red-500/30',
  muted: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

const colorClasses = {
  green: 'bg-green-500/20 text-green-400 border-green-500/30',
  yellow: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  red: 'bg-red-500/20 text-red-400 border-red-500/30',
  blue: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  gray: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export function Badge({ children, variant = 'default', color, className = '' }: BadgeProps) {
  const classes = color ? colorClasses[color] : variantClasses[variant];
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${classes} ${className}`}
    >
      {children}
    </span>
  );
}

export default Badge;
