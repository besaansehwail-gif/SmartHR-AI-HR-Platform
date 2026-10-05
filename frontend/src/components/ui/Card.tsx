import React from 'react';

/**
 * The single card surface used across every SmartHR page: white on the sand
 * canvas, one warm hairline border, a shadow shallow enough to read as paper
 * rather than a floating panel.
 */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: 'default' | 'hover' | 'bordered' | 'featured' | 'attention' | 'brand';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  className?: string;
}

const PADDING: Record<NonNullable<CardProps['padding']>, string> = {
  none: 'p-0',
  sm: 'p-4',
  md: 'p-5 sm:p-6',
  lg: 'p-6 sm:p-8',
};

const VARIANTS: Record<NonNullable<CardProps['variant']>, string> = {
  default: 'bg-white border border-stone-200/80 shadow-card rounded-2xl',
  hover:
    'bg-white border border-stone-200/80 shadow-card rounded-2xl transition-[box-shadow,border-color] duration-200 hover:shadow-card-hover hover:border-brand-200',
  bordered: 'bg-white border border-stone-200 rounded-2xl',
  featured:
    'bg-white border border-stone-200/80 border-t-[3px] border-t-brand-600 shadow-card rounded-2xl',
  attention:
    'bg-white border border-stone-200/80 border-t-[3px] border-t-amber-500 shadow-card rounded-2xl',
  brand: 'bg-brand-50 border border-brand-200 shadow-card rounded-2xl',
};

export const Card: React.FC<CardProps> = ({
  children,
  variant = 'default',
  padding = 'md',
  className = '',
  ...props
}) => (
  <div className={`${VARIANTS[variant]} ${PADDING[padding]} ${className}`} {...props}>
    {children}
  </div>
);

export const CardHeader: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}> = ({ title, subtitle, action, icon, className = '' }) => (
  <div
    className={`flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 pb-4 border-b border-stone-100 mb-5 ${className}`}
  >
    <div className="flex items-start gap-3 min-w-0">
      {icon && (
        <span className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shrink-0">
          {icon}
        </span>
      )}
      <div className="min-w-0">
        <h3 className="text-sm sm:text-base font-bold text-stone-900 tracking-tight">{title}</h3>
        {subtitle && <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">{subtitle}</p>}
      </div>
    </div>
    {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
  </div>
);

/** Label / value pair used across the profile and detail panels. */
export const Field: React.FC<{
  label: React.ReactNode;
  value: React.ReactNode;
  className?: string;
}> = ({ label, value, className = '' }) => (
  <div className={className}>
    <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">{label}</dt>
    <dd className="text-sm font-semibold text-stone-800 mt-1 break-words">{value}</dd>
  </div>
);

/** A quiet divider with an optional caption, for sectioning long cards. */
export const SectionLabel: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`flex items-center gap-3 ${className}`}>
    <span className="text-3xs font-extrabold uppercase tracking-[0.12em] text-stone-400 shrink-0">
      {children}
    </span>
    <span className="h-px flex-1 bg-stone-100" />
  </div>
);
