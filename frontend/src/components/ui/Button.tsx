import React from 'react';
import { Loader2 } from 'lucide-react';

/**
 * SmartHR button.
 *
 * Hierarchy is deliberate and only three levels deep:
 *   primary   - the one action that matters on the screen (brand orange)
 *   outline   - everything else (white on a warm border)
 *   ghost     - icon-only / in-row affordances that must not compete
 *
 * `soft` is the light-orange chip button; `purple-soft` is kept as an alias so
 * existing call sites keep working after the rebrand.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost' | 'soft' | 'purple-soft';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

const BASE =
  'inline-flex items-center justify-center font-semibold tracking-tight rounded-lg select-none whitespace-nowrap ' +
  'transition-[background-color,border-color,box-shadow,color] duration-150 ' +
  'focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-white disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none';

const SIZES: Record<NonNullable<ButtonProps['size']>, string> = {
  xs: 'text-2xs px-2.5 gap-1.5 h-7',
  sm: 'text-xs px-3 gap-1.5 h-8',
  md: 'text-sm px-4 gap-2 h-10',
  lg: 'text-sm px-5 gap-2.5 h-11',
};

const VARIANTS: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary:
    'bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white ' +
    'shadow-[0_1px_2px_rgba(164,72,32,0.25)] hover:shadow-[0_2px_8px_-2px_rgba(164,72,32,0.45)] ' +
    'focus-visible:ring-brand-600',
  secondary:
    'bg-sand-100 hover:bg-sand-200 active:bg-sand-300 text-stone-800 border border-sand-300 ' +
    'focus-visible:ring-brand-600',
  outline:
    'bg-white hover:bg-sand-50 active:bg-sand-100 text-stone-700 hover:text-stone-900 ' +
    'border border-stone-200 hover:border-stone-300 shadow-2xs focus-visible:ring-brand-600',
  soft:
    'bg-brand-50 hover:bg-brand-100 active:bg-brand-200 text-brand-700 border border-brand-200 ' +
    'focus-visible:ring-brand-600',
  'purple-soft':
    'bg-brand-50 hover:bg-brand-100 active:bg-brand-200 text-brand-700 border border-brand-200 ' +
    'focus-visible:ring-brand-600',
  danger:
    'bg-red-600 hover:bg-red-700 active:bg-red-800 text-white shadow-2xs focus-visible:ring-red-600',
  ghost:
    'bg-transparent hover:bg-sand-100 active:bg-sand-200 text-stone-600 hover:text-stone-900 ' +
    'focus-visible:ring-brand-600',
};

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  fullWidth = false,
  className = '',
  disabled,
  ...props
}) => (
  <button
    className={`${BASE} ${SIZES[size]} ${VARIANTS[variant]} ${fullWidth ? 'w-full' : ''} ${className}`}
    disabled={disabled || isLoading}
    aria-busy={isLoading || undefined}
    {...props}
  >
    {isLoading ? (
      <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden="true" />
    ) : (
      leftIcon && <span className="inline-flex shrink-0" aria-hidden="true">{leftIcon}</span>
    )}
    {children && <span className="truncate">{children}</span>}
    {!isLoading && rightIcon && (
      <span className="inline-flex shrink-0" aria-hidden="true">{rightIcon}</span>
    )}
  </button>
);

/** Square, label-less button for table rows and toolbars. Always needs a label. */
export const IconButton: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    label: string;
    icon: React.ReactNode;
    tone?: 'default' | 'danger';
    size?: 'sm' | 'md';
  }
> = ({ label, icon, tone = 'default', size = 'md', className = '', ...props }) => (
  <button
    type="button"
    title={label}
    aria-label={label}
    className={`inline-flex items-center justify-center rounded-lg border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:opacity-40 ${
      size === 'sm' ? 'w-7 h-7' : 'w-8 h-8'
    } ${
      tone === 'danger'
        ? 'border-stone-200 text-stone-500 hover:text-red-700 hover:bg-red-50 hover:border-red-200 focus-visible:ring-red-600'
        : 'border-stone-200 text-stone-500 hover:text-brand-700 hover:bg-brand-50 hover:border-brand-200 focus-visible:ring-brand-600'
    } ${className}`}
    {...props}
  >
    <span aria-hidden="true">{icon}</span>
  </button>
);
