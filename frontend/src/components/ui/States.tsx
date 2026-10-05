import React from 'react';
import { AlertTriangle, Inbox, Loader2, Lock, RefreshCw, WifiOff } from 'lucide-react';
import { Button } from './Button';
import { useT } from '../../i18n';

/**
 * The three states every data screen needs besides "it worked": loading,
 * empty, and failed. They were previously improvised per page, which is why
 * some screens showed a bare spinner and others showed nothing at all.
 *
 * All three are deliberately quiet: a shape, a sentence, and at most one
 * action. They never invent numbers to fill the space.
 */

export const Spinner: React.FC<{ className?: string; label?: string }> = ({
  className = 'w-5 h-5',
  label,
}) => {
  const { t } = useT();

  return (
    <span role="status" aria-live="polite" className="inline-flex items-center">
      <Loader2 className={`animate-spin text-brand-600 ${className}`} aria-hidden="true" />
      <span className="sr-only">{label ?? t('ui.loading')}</span>
    </span>
  );
};

/** Grey block that stands in for text while a request is in flight. */
export const Skeleton: React.FC<{ className?: string }> = ({ className = 'h-4 w-full' }) => (
  <span className={`block rounded-md skeleton ${className}`} aria-hidden="true" />
);

/** Card-shaped placeholder. `rows` controls how tall the block reads. */
export const SkeletonCard: React.FC<{ rows?: number; className?: string }> = ({
  rows = 3,
  className = '',
}) => (
  <div
    className={`rounded-2xl border border-stone-200/80 bg-white shadow-card p-5 space-y-3 ${className}`}
    aria-hidden="true"
  >
    <Skeleton className="h-3 w-24" />
    <Skeleton className="h-7 w-32" />
    {Array.from({ length: rows }).map((_, i) => (
      <Skeleton key={i} className={`h-3 ${i % 2 === 0 ? 'w-full' : 'w-4/5'}`} />
    ))}
  </div>
);

export const LoadingState: React.FC<{
  title?: string;
  description?: string;
  className?: string;
}> = ({ title, description, className = '' }) => {
  const { t } = useT();

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center text-center py-12 px-6 ${className}`}
    >
      <Spinner className="w-6 h-6" />
      <p className="text-sm font-bold text-stone-800 mt-3">{title ?? t('ui.loading')}</p>
      <p className="text-xs text-stone-500 mt-1 max-w-sm leading-relaxed">
        {description ?? t('ui.loadingDescription')}
      </p>
    </div>
  );
};

export const ErrorState: React.FC<{
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
  /** Renders the permission variant: a lock instead of a warning triangle. */
  variant?: 'error' | 'forbidden' | 'offline';
}> = ({ title, message, onRetry, className = '', variant = 'error' }) => {
  const { t } = useT();

  const config = {
    error: {
      icon: <AlertTriangle className="w-5 h-5" aria-hidden="true" />,
      tone: 'bg-red-50 text-red-600 border-red-100',
      title: title || t('ui.errorTitle'),
    },
    forbidden: {
      icon: <Lock className="w-5 h-5" aria-hidden="true" />,
      tone: 'bg-amber-50 text-amber-600 border-amber-100',
      title: title || t('ui.forbiddenTitle'),
    },
    offline: {
      icon: <WifiOff className="w-5 h-5" aria-hidden="true" />,
      tone: 'bg-stone-100 text-stone-500 border-stone-200',
      title: title || t('ui.offlineTitle'),
    },
  }[variant];

  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center text-center py-10 px-6 rounded-2xl border border-stone-200/80 bg-white shadow-card ${className}`}
    >
      <span className={`w-11 h-11 rounded-xl border flex items-center justify-center mb-3 ${config.tone}`}>
        {config.icon}
      </span>
      <p className="text-sm font-bold text-stone-900">{config.title}</p>
      {message && (
        <p className="text-xs text-stone-500 mt-1.5 max-w-md leading-relaxed">{message}</p>
      )}
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          onClick={onRetry}
        >
          {t('ui.tryAgain')}
        </Button>
      )}
    </div>
  );
};

/**
 * Inline banner for a non-blocking explanation - typically "this account has
 * no linked employee record" or "this figure is not stored in the database".
 */
export const InfoPanel: React.FC<{
  title: React.ReactNode;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: 'info' | 'warning' | 'neutral' | 'brand';
  className?: string;
}> = ({ title, children, icon, tone = 'neutral', className = '' }) => {
  const tones = {
    info: 'bg-sky-50 border-sky-200 text-sky-900',
    warning: 'bg-amber-50 border-amber-200 text-amber-900',
    neutral: 'bg-sand-100 border-sand-300 text-stone-700',
    brand: 'bg-brand-50 border-brand-200 text-brand-900',
  } as const;

  return (
    <div className={`rounded-xl border p-4 flex items-start gap-3 ${tones[tone]} ${className}`}>
      {icon && <span className="shrink-0 mt-0.5 opacity-80">{icon}</span>}
      <div className="min-w-0">
        <p className="text-xs font-bold">{title}</p>
        {children && <div className="text-2xs mt-1 leading-relaxed opacity-90">{children}</div>}
      </div>
    </div>
  );
};

/** Small empty state that fits inside a card or a table body. */
export const InlineEmpty: React.FC<{
  title: string;
  description?: string;
  icon?: React.ReactNode;
  className?: string;
}> = ({ title, description, icon, className = '' }) => (
  <div className={`flex flex-col items-center justify-center text-center py-8 px-4 ${className}`}>
    <span className="w-10 h-10 rounded-xl bg-sand-100 border border-sand-200 text-stone-400 flex items-center justify-center mb-3">
      {icon || <Inbox className="w-4 h-4" aria-hidden="true" />}
    </span>
    <p className="text-xs font-bold text-stone-800">{title}</p>
    {description && (
      <p className="text-2xs text-stone-500 mt-1 max-w-xs leading-relaxed">{description}</p>
    )}
  </div>
);
