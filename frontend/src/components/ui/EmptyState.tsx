import React from 'react';
import { Button } from './Button';

/**
 * Full-card empty state. Used when a list legitimately has nothing in it -
 * which, on a freshly restored database, is most of them. It says what would
 * appear here and offers the one action that would create it, rather than
 * padding the screen with sample rows.
 */
export interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  secondary?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  secondary,
  className = '',
}) => (
  <div
    className={`flex flex-col items-center justify-center text-center px-6 py-12 sm:py-16 bg-white rounded-2xl border border-dashed border-stone-300 ${className}`}
  >
    <div
      className="w-14 h-14 rounded-2xl bg-brand-50 border border-brand-100 text-brand-500 flex items-center justify-center mb-4"
      aria-hidden="true"
    >
      {icon}
    </div>
    <h3 className="text-base font-extrabold text-stone-900 tracking-tight">{title}</h3>
    <p className="text-xs sm:text-sm text-stone-500 mt-1.5 max-w-md leading-relaxed">
      {description}
    </p>

    {(actionLabel || secondary) && (
      <div className="flex flex-wrap items-center justify-center gap-2.5 mt-6">
        {actionLabel && onAction && (
          <Button variant="primary" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        )}
        {secondary}
      </div>
    )}
  </div>
);
