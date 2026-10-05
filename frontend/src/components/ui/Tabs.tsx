import React from 'react';

/**
 * Tabs.
 *
 *   underline - section navigation inside a page (default)
 *   pills     - filter-style switches sitting above a table
 *
 * Both are a real tablist for assistive tech, scroll horizontally rather than
 * wrapping on narrow screens, and show the active tab in brand orange.
 */
export interface TabItem {
  id: string;
  label: string;
  count?: number | string;
  icon?: React.ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabId: string) => void;
  variant?: 'pills' | 'underline';
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  activeTab,
  onChange,
  variant = 'underline',
  className = '',
}) => {
  if (variant === 'pills') {
    return (
      <div
        role="tablist"
        className={`inline-flex max-w-full gap-1 p-1 bg-sand-100 rounded-xl border border-sand-200 overflow-x-auto no-scrollbar ${className}`}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={isActive}
              onClick={() => onChange(tab.id)}
              className={`flex items-center gap-2 px-3.5 h-8 text-2xs font-bold rounded-lg whitespace-nowrap transition-colors ${
                isActive
                  ? 'bg-white text-brand-700 shadow-2xs border border-stone-200/80'
                  : 'text-stone-600 hover:text-stone-900 hover:bg-white/60'
              }`}
            >
              {tab.icon && <span className="w-3.5 h-3.5 shrink-0" aria-hidden="true">{tab.icon}</span>}
              <span>{tab.label}</span>
              {tab.count !== undefined && (
                <span
                  className={`px-1.5 rounded-full text-3xs font-extrabold tabular-nums ${
                    isActive ? 'bg-brand-100 text-brand-800' : 'bg-stone-200 text-stone-600'
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={`border-b border-stone-200 ${className}`}>
      <nav role="tablist" className="-mb-px flex gap-5 sm:gap-7 overflow-x-auto no-scrollbar">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={isActive}
              onClick={() => onChange(tab.id)}
              className={`flex items-center gap-2 py-3 border-b-2 text-xs sm:text-sm font-bold whitespace-nowrap transition-colors ${
                isActive
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-stone-500 hover:text-stone-800 hover:border-stone-300'
              }`}
            >
              {tab.icon && <span className="w-4 h-4 shrink-0" aria-hidden="true">{tab.icon}</span>}
              <span>{tab.label}</span>
              {tab.count !== undefined && (
                <span
                  className={`px-1.5 py-0.5 rounded-full text-3xs font-extrabold tabular-nums ${
                    isActive ? 'bg-brand-100 text-brand-800' : 'bg-stone-100 text-stone-600'
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
};
