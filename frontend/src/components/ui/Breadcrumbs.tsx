import React from 'react';
import { useT } from '../../i18n';
import { ChevronRight, Home } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  onHomeClick?: () => void;
  homeLabel?: string;
}

/**
 * Where you are, in the top bar. The last crumb is the current page and is not
 * a link; everything before it navigates back up the workspace.
 */
export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({
  items,
  onHomeClick,
  homeLabel,
}) => {
  const { t } = useT();
  const home = homeLabel ?? t('ui.breadcrumb.home');
  return (
  <nav aria-label={t('ui.breadcrumb.label')}>
    <ol className="flex items-center gap-1.5 text-2xs text-stone-500">
      <li className="flex items-center">
        <button
          type="button"
          onClick={onHomeClick}
          aria-label={home}
          title={home}
          className="flex items-center p-1 -m-1 rounded hover:text-brand-700 transition-colors"
        >
          <Home className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </li>

      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1.5 min-w-0">
            <ChevronRight className="w-3 h-3 text-stone-300 shrink-0" aria-hidden="true" data-flip-rtl />
            {isLast ? (
              <span
                aria-current="page"
                className="font-bold text-stone-800 truncate max-w-[180px] sm:max-w-xs"
              >
                {item.label}
              </span>
            ) : (
              <button
                type="button"
                onClick={item.onClick}
                className="hover:text-brand-700 transition-colors truncate max-w-[140px] font-semibold"
              >
                {item.label}
              </button>
            )}
          </li>
        );
      })}
    </ol>
  </nav>
  );
};
