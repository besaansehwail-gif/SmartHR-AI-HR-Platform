import React from 'react';
import { useT } from '../../i18n';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Pagination for the long directory tables (employees, users, audit logs).
 * Purely a view control - it pages through rows already in memory, so it never
 * changes what the API returned.
 */
export interface PaginationProps {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  className?: string;
  /** Noun for the row count line, e.g. "employees". */
  itemLabel?: string;
}

const pageWindow = (page: number, pageCount: number): (number | 'gap')[] => {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);

  const pages: (number | 'gap')[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(pageCount - 1, page + 1);

  if (start > 2) pages.push('gap');
  for (let p = start; p <= end; p += 1) pages.push(p);
  if (end < pageCount - 1) pages.push('gap');
  pages.push(pageCount);
  return pages;
};

export const Pagination: React.FC<PaginationProps> = ({
  page,
  pageCount,
  total,
  pageSize,
  onPageChange,
  className = '',
  itemLabel,
}) => {
  const { t } = useT();
  if (total === 0) return null;

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label={t('ui.pagination.label')}
      className={`flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 ${className}`}
    >
      <p className="text-2xs text-stone-500 font-medium order-2 sm:order-1">
        {t('ui.pagination.showing')}{' '}
        <span className="font-bold text-stone-800 tabular-nums">{first}</span>–
        <span className="font-bold text-stone-800 tabular-nums">{last}</span>{' '}
        {t('ui.pagination.of')}{' '}
        <span className="font-bold text-stone-800 tabular-nums">{total}</span>{' '}
        {itemLabel ?? t('ui.pagination.records')}
      </p>

      {pageCount > 1 && (
        <div className="flex items-center gap-1 order-1 sm:order-2">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            aria-label={t('ui.pagination.previousPage')}
            className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-stone-200 text-stone-500 hover:text-brand-700 hover:border-brand-200 hover:bg-brand-50 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-stone-500 disabled:hover:border-stone-200 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" data-flip-rtl />
          </button>

          {pageWindow(page, pageCount).map((entry, idx) =>
            entry === 'gap' ? (
              <span key={`gap-${idx}`} className="w-8 h-8 inline-flex items-center justify-center text-2xs text-stone-400">
                &hellip;
              </span>
            ) : (
              <button
                key={entry}
                type="button"
                onClick={() => onPageChange(entry)}
                aria-current={entry === page ? 'page' : undefined}
                className={`min-w-8 h-8 px-2 inline-flex items-center justify-center rounded-lg text-2xs font-bold tabular-nums transition-colors ${
                  entry === page
                    ? 'bg-brand-600 text-white shadow-2xs'
                    : 'border border-stone-200 text-stone-600 hover:text-brand-700 hover:border-brand-200 hover:bg-brand-50'
                }`}
              >
                {entry}
              </button>
            )
          )}

          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= pageCount}
            aria-label={t('ui.pagination.nextPage')}
            className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-stone-200 text-stone-500 hover:text-brand-700 hover:border-brand-200 hover:bg-brand-50 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-stone-500 disabled:hover:border-stone-200 transition-colors"
          >
            <ChevronRight className="w-4 h-4" data-flip-rtl />
          </button>
        </div>
      )}
    </nav>
  );
};

/**
 * Slices a list for the current page and keeps the page number in range when
 * filters shrink the result set.
 */
export function usePagination<T>(items: T[], pageSize = 10) {
  const [page, setPage] = React.useState(1);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));

  React.useEffect(() => {
    if (page > pageCount) setPage(1);
  }, [page, pageCount]);

  const slice = React.useMemo(
    () => items.slice((page - 1) * pageSize, page * pageSize),
    [items, page, pageSize]
  );

  return { page, setPage, pageCount, slice, pageSize, total: items.length };
}
