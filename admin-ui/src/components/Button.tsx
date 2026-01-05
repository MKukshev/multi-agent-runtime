import { ReactNode, ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const variantClasses = {
  primary: 'bg-[var(--primary)] hover:bg-[var(--primary-hover)] text-white',
  secondary: 'bg-[var(--card)] hover:bg-[var(--card-hover)] text-white border border-[var(--border)]',
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  ghost: 'hover:bg-[var(--card-hover)] text-[var(--muted)] hover:text-white',
};

const sizeClasses = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2',
  lg: 'px-6 py-3 text-lg',
};

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}

export default Button;

