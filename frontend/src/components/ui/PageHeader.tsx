import React from 'react';

/**
 * The first thing on every page: what this screen is, one line on what it
 * shows, and the actions that belong to it.
 *
 * The brand rail on the left is the recurring identity mark across all 31
 * pages - it is what makes an unfamiliar screen read as part of the same
 * product.
 */
export interface PageHeaderProps {
  title: string;
  subtitle?: React.ReactNode;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: React.ReactNode;
  /** Optional secondary row: filters, tabs, a search box. */
  toolbar?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  badge,
  actions,
  icon,
  toolbar,
}) => (
  <div className="mb-6">
    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 pb-5 border-b border-stone-200/80">
      <div className="flex items-start gap-3.5 min-w-0">
        <span className="mt-1 w-1 h-9 rounded-full bg-brand-500 shrink-0" aria-hidden="true" />

        {icon && (
          <span className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shrink-0">
            {icon}
          </span>
        )}

        <div className="min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg sm:text-xl lg:text-2xl font-extrabold text-stone-900 tracking-tight">
              {title}
            </h1>
            {badge}
          </div>
          {subtitle && (
            <p className="text-xs sm:text-sm text-stone-500 mt-1 max-w-3xl leading-relaxed">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      {actions && (
        <div className="flex items-center gap-2 flex-wrap lg:justify-end shrink-0">{actions}</div>
      )}
    </div>

    {toolbar && <div className="pt-4">{toolbar}</div>}
  </div>
);

/**
 * Toolbar strip for the filter row that sits under most page headers:
 * a search field that grows, then selects and buttons that do not.
 */
export const Toolbar: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <div
    className={`flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2.5 p-3 rounded-xl bg-white border border-stone-200/80 shadow-card ${className}`}
  >
    {children}
  </div>
);
