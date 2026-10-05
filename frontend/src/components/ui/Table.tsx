import React from 'react';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';

/**
 * Data-table primitives.
 *
 * SmartHR is mostly tables, so they get real structure rather than styling
 * repeated by hand on every page:
 *
 *   TableShell  - the rounded card + horizontal scroll container. Tables are
 *                 the one element allowed to scroll sideways on small screens;
 *                 the page body never does.
 *   Th / Td     - consistent padding, alignment and a sticky, quiet header.
 *   Tr          - zebra-free rows with a warm hover, because dense HR tables
 *                 read better with a single hairline separator than stripes.
 *
 * `numeric` right-aligns and switches to tabular figures so columns of counts
 * and hours line up.
 */

export const TableShell: React.FC<{
  children: React.ReactNode;
  className?: string;
  /** Caption for screen readers describing what the table lists. */
  caption?: string;
}> = ({ children, className = '', caption }) => (
  <div className={`w-full overflow-x-auto rounded-2xl border border-stone-200/80 bg-white shadow-card ${className}`}>
    <table className="w-full min-w-[640px] border-collapse text-start">
      {caption && <caption className="sr-only">{caption}</caption>}
      {children}
    </table>
  </div>
);

export const THead: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <thead className={`bg-sand-50 border-b border-stone-200 ${className}`}>{children}</thead>
);

export const TBody: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <tbody className={`divide-y divide-stone-100 ${className}`}>{children}</tbody>;

export const Tr: React.FC<
  React.HTMLAttributes<HTMLTableRowElement> & { interactive?: boolean; selected?: boolean }
> = ({ children, interactive = false, selected = false, className = '', ...props }) => (
  <tr
    className={`transition-colors ${
      selected ? 'bg-brand-50/70' : 'bg-white hover:bg-sand-50'
    } ${interactive ? 'cursor-pointer' : ''} ${className}`}
    {...props}
  >
    {children}
  </tr>
);

export type SortDirection = 'asc' | 'desc' | null;

export const Th: React.FC<{
  children?: React.ReactNode;
  numeric?: boolean;
  className?: string;
  /** Pass a handler to make the column sortable; `sort` shows the current state. */
  onSort?: () => void;
  sort?: SortDirection;
  scope?: 'col' | 'row';
}> = ({ children, numeric = false, className = '', onSort, sort = null, scope = 'col' }) => {
  const content = (
    <span className={`inline-flex items-center gap-1.5 ${numeric ? 'flex-row-reverse' : ''}`}>
      {children}
      {onSort &&
        (sort === 'asc' ? (
          <ChevronUp className="w-3 h-3 text-brand-600" aria-hidden="true" />
        ) : sort === 'desc' ? (
          <ChevronDown className="w-3 h-3 text-brand-600" aria-hidden="true" />
        ) : (
          <ChevronsUpDown className="w-3 h-3 text-stone-300" aria-hidden="true" />
        ))}
    </span>
  );

  return (
    <th
      scope={scope}
      aria-sort={sort === 'asc' ? 'ascending' : sort === 'desc' ? 'descending' : undefined}
      className={`px-4 py-3 text-3xs font-extrabold uppercase tracking-wider text-stone-500 whitespace-nowrap ${
        numeric ? 'text-end' : 'text-start'
      } ${className}`}
    >
      {onSort ? (
        <button
          type="button"
          onClick={onSort}
          className="inline-flex items-center gap-1.5 hover:text-brand-700 transition-colors uppercase tracking-wider"
        >
          {content}
        </button>
      ) : (
        content
      )}
    </th>
  );
};

export const Td: React.FC<{
  children?: React.ReactNode;
  numeric?: boolean;
  className?: string;
  colSpan?: number;
}> = ({ children, numeric = false, className = '', colSpan }) => (
  <td
    colSpan={colSpan}
    className={`px-4 py-3 text-xs text-stone-700 align-middle ${
      numeric ? 'text-end tabular-nums font-semibold text-stone-900' : ''
    } ${className}`}
  >
    {children}
  </td>
);

/** Primary cell: the thing the row is about, plus one line of context. */
export const TdPrimary: React.FC<{
  title: React.ReactNode;
  meta?: React.ReactNode;
  avatar?: React.ReactNode;
  className?: string;
}> = ({ title, meta, avatar, className = '' }) => (
  <td className={`px-4 py-3 align-middle ${className}`}>
    <div className="flex items-center gap-3 min-w-0">
      {avatar && <span className="shrink-0">{avatar}</span>}
      <div className="min-w-0">
        <div className="text-xs font-bold text-stone-900 truncate">{title}</div>
        {meta && <div className="text-2xs text-stone-500 truncate mt-0.5">{meta}</div>}
      </div>
    </div>
  </td>
);

/** Full-width row used for the empty / loading / error states inside a table. */
export const TrMessage: React.FC<{ colSpan: number; children: React.ReactNode }> = ({
  colSpan,
  children,
}) => (
  <tr>
    <td colSpan={colSpan} className="px-4 py-12">
      {children}
    </td>
  </tr>
);

/**
 * Round initials chip used in table rows and headers. Deterministic tint so
 * the same person keeps the same colour across pages.
 */
const AVATAR_TONES = [
  'bg-brand-100 text-brand-800',
  'bg-emerald-100 text-emerald-800',
  'bg-sky-100 text-sky-800',
  'bg-amber-100 text-amber-800',
  'bg-stone-200 text-stone-700',
];

export const Avatar: React.FC<{
  name?: string | null;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
}> = ({ name, size = 'sm', className = '' }) => {
  const label = (name || '?').trim();
  const initials =
    label
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase() || '?';

  let hash = 0;
  for (let i = 0; i < label.length; i += 1) hash = (hash * 31 + label.charCodeAt(i)) % 997;
  const tone = AVATAR_TONES[hash % AVATAR_TONES.length];

  const sizes = {
    xs: 'w-6 h-6 text-3xs',
    sm: 'w-8 h-8 text-2xs',
    md: 'w-10 h-10 text-xs',
    lg: 'w-14 h-14 text-base',
  } as const;

  return (
    <span
      aria-hidden="true"
      title={name || undefined}
      className={`inline-flex items-center justify-center rounded-full font-extrabold tracking-tight shrink-0 ${sizes[size]} ${tone} ${className}`}
    >
      {initials}
    </span>
  );
};
