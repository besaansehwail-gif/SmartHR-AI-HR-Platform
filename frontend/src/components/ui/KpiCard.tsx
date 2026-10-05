import React from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';

/**
 * The metric tile every dashboard is built from.
 *
 * Layout is fixed on purpose so a row of them scans as a row: label on top,
 * the number as the largest thing on the card, then one line of context under
 * a hairline. `change` and `comparison` describe where the number came from -
 * they are passed in by the page from real API data, never invented here.
 */
export interface KpiCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  comparison?: string;
  icon: React.ReactNode;
  description?: string;
  /** Renders the tile as a button when the metric drills into a page. */
  onClick?: () => void;
  /** Highlights the primary metric of the screen with a brand rail. */
  emphasis?: boolean;
}

const CHANGE_TONES = {
  positive: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  negative: 'bg-red-50 text-red-700 border-red-100',
  neutral: 'bg-stone-100 text-stone-600 border-stone-200',
} as const;

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  change,
  changeType = 'neutral',
  comparison,
  icon,
  description,
  onClick,
  emphasis = false,
}) => {
  const Wrapper = onClick ? 'button' : 'div';

  return (
    <Wrapper
      {...(onClick ? { onClick, type: 'button' as const } : {})}
      className={`relative w-full text-start bg-white rounded-2xl p-4 sm:p-5 border border-stone-200/80 shadow-card overflow-hidden
        ${emphasis ? 'border-brand-200' : ''}
        ${
          onClick
            ? 'transition-[box-shadow,border-color] duration-200 hover:shadow-card-hover hover:border-brand-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2'
            : ''
        }`}
    >
      {emphasis && (
        <span className="absolute inset-x-0 top-0 h-1 bg-brand-500" aria-hidden="true" />
      )}

      <div className="flex items-start justify-between gap-3">
        <span className="text-3xs sm:text-2xs font-extrabold text-stone-500 uppercase tracking-wider leading-snug">
          {title}
        </span>
        <span
          className="w-9 h-9 rounded-xl bg-brand-50 text-brand-600 border border-brand-100 flex items-center justify-center shrink-0"
          aria-hidden="true"
        >
          {icon}
        </span>
      </div>

      <div className="mt-2.5">
        <span className="text-2xl sm:text-3xl font-extrabold text-stone-900 tracking-tight tabular-nums break-words">
          {value}
        </span>
      </div>

      {(change || comparison || description) && (
        <div className="mt-3 pt-3 border-t border-stone-100 flex items-center justify-between gap-2 text-2xs">
          <div className="flex items-center gap-1.5 min-w-0">
            {change && (
              <span
                className={`inline-flex items-center gap-0.5 font-bold px-1.5 py-0.5 rounded border text-3xs shrink-0 ${CHANGE_TONES[changeType]}`}
              >
                {changeType === 'positive' && <ArrowUpRight className="w-3 h-3" aria-hidden="true" />}
                {changeType === 'negative' && <ArrowDownRight className="w-3 h-3" aria-hidden="true" />}
                {changeType === 'neutral' && <Minus className="w-3 h-3" aria-hidden="true" />}
                {change}
              </span>
            )}
            {comparison && <span className="text-stone-500 text-3xs truncate">{comparison}</span>}
          </div>
          {description && (
            <span className="text-stone-400 text-3xs hidden sm:inline truncate shrink-0">
              {description}
            </span>
          )}
        </div>
      )}
    </Wrapper>
  );
};
