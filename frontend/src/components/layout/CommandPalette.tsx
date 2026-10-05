import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Search,
  LayoutDashboard,
  Users,
  ShieldCheck,
  Building,
  Briefcase,
  History,
  Settings,
  ArrowRight,
  X,
  Zap,
  CornerDownLeft,
} from 'lucide-react';
import { PageId } from './Sidebar';
import { useT } from '../../i18n';
import { canAccessPage, type Workspace } from '../../services/access';

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (page: PageId) => void;
  onQuickAction: (action: string) => void;
  roleId?: number | null;
}

/*
 * Entries carry no text. A page is labelled `page.<PageId>` and an action
 * `quick.<action>` - the same keys the top bar uses, so the two surfaces
 * cannot drift apart and translating one translates both.
 */
type NavEntry = { id: PageId; icon: React.ReactNode; group: Workspace };
type ActionEntry = { id: string; icon: React.ReactNode; roles: number[] };

const icon = (Component: React.ElementType) => <Component className="w-4 h-4" />;

const NAV_ENTRIES: NavEntry[] = [
  { id: 'emp-dashboard', icon: icon(LayoutDashboard), group: 'employee' },
  { id: 'emp-profile', icon: icon(Users), group: 'employee' },
  { id: 'emp-attendance', icon: icon(History), group: 'employee' },
  { id: 'emp-leave', icon: icon(Building), group: 'employee' },
  { id: 'emp-training', icon: icon(ShieldCheck), group: 'employee' },
  { id: 'emp-performance', icon: icon(LayoutDashboard), group: 'employee' },
  { id: 'emp-career', icon: icon(ShieldCheck), group: 'employee' },
  { id: 'emp-notifications', icon: icon(Settings), group: 'employee' },

  { id: 'mgr-dashboard', icon: icon(LayoutDashboard), group: 'manager' },
  { id: 'mgr-team', icon: icon(Users), group: 'manager' },
  { id: 'mgr-attendance', icon: icon(History), group: 'manager' },
  { id: 'mgr-leave', icon: icon(Building), group: 'manager' },
  { id: 'mgr-performance', icon: icon(ShieldCheck), group: 'manager' },
  { id: 'mgr-insights', icon: icon(LayoutDashboard), group: 'manager' },
  { id: 'mgr-notifications', icon: icon(Settings), group: 'manager' },

  { id: 'hr-dashboard', icon: icon(LayoutDashboard), group: 'hr' },
  { id: 'hr-employees', icon: icon(Users), group: 'hr' },
  { id: 'hr-employee-360', icon: icon(Users), group: 'hr' },
  { id: 'hr-jobs', icon: icon(Briefcase), group: 'hr' },
  { id: 'hr-candidates', icon: icon(Users), group: 'hr' },
  { id: 'hr-interviews', icon: icon(History), group: 'hr' },
  { id: 'hr-training', icon: icon(ShieldCheck), group: 'hr' },
  { id: 'hr-reports', icon: icon(Building), group: 'hr' },
  { id: 'hr-notifications', icon: icon(Settings), group: 'hr' },

  { id: 'dashboard', icon: icon(LayoutDashboard), group: 'admin' },
  { id: 'users', icon: icon(Users), group: 'admin' },
  { id: 'roles', icon: icon(ShieldCheck), group: 'admin' },
  { id: 'departments', icon: icon(Building), group: 'admin' },
  { id: 'positions', icon: icon(Briefcase), group: 'admin' },
  { id: 'audit', icon: icon(History), group: 'admin' },
  { id: 'settings', icon: icon(Settings), group: 'admin' },
];

const ACTION_ENTRIES: ActionEntry[] = [
  { id: 'mgr-approve-leave', icon: icon(Building), roles: [1, 2, 3] },
  { id: 'mgr-conduct-review', icon: icon(ShieldCheck), roles: [1, 2, 3] },
  { id: 'mgr-check-attendance', icon: icon(History), roles: [1, 2, 3] },
  { id: 'add-employee', icon: icon(Users), roles: [1, 2] },
  { id: 'post-job', icon: icon(Briefcase), roles: [1, 2] },
  { id: 'schedule-interview', icon: icon(History), roles: [1, 2] },
  { id: 'add-user', icon: icon(Users), roles: [1] },
  { id: 'add-department', icon: icon(Building), roles: [1] },
  { id: 'export-audit', icon: icon(History), roles: [1] },
];

/**
 * Ctrl/Cmd-K palette.
 *
 * Only offers pages the signed-in role can open and actions it can perform,
 * for the same reason the sidebar does: the backend refuses the rest anyway,
 * and a result that 403s is not a result. Arrow keys move, Enter runs.
 */
export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onNavigate,
  onQuickAction,
  roleId = null,
}) => {
  const { t } = useT();
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    // Filtering on the translated label, not the key, so a search typed in
    // Arabic finds the Arabic rows rather than silently matching nothing.
    const matches = (label: string) => !needle || label.toLowerCase().includes(needle);

    const pages = NAV_ENTRIES.filter(
      (entry) => canAccessPage(roleId, entry.id) && matches(t(`page.${entry.id}`))
    );
    const actions = ACTION_ENTRIES.filter(
      (entry) =>
        roleId !== null && entry.roles.includes(roleId) && matches(t(`quick.${entry.id}`))
    );

    return { pages, actions, total: pages.length + actions.length };
  }, [query, roleId]);

  useEffect(() => {
    setHighlight(0);
  }, [query, isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlight((prev) => (results.total === 0 ? 0 : (prev + 1) % results.total));
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlight((prev) => (results.total === 0 ? 0 : (prev - 1 + results.total) % results.total));
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (highlight < results.pages.length) {
          const page = results.pages[highlight];
          if (page) {
            onNavigate(page.id);
            onClose();
          }
        } else {
          const action = results.actions[highlight - results.pages.length];
          if (action) {
            onQuickAction(action.id);
            onClose();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, onNavigate, onQuickAction, results, highlight]);

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-highlighted="true"]')
      ?.scrollIntoView({ block: 'nearest' });
  }, [highlight]);

  if (!isOpen) return null;

  const rowClass = (isActive: boolean) =>
    `w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors text-start ${
      isActive ? 'bg-brand-50 text-brand-800' : 'text-stone-700 hover:bg-sand-100'
    }`;

  return (
    <div className="fixed inset-0 z-[55]" role="presentation">
      <div className="fixed inset-0 bg-stone-900/50 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />

      <div className="relative flex min-h-full items-start justify-center p-4 pt-16 sm:pt-24">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t('palette.placeholder')}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-xl rounded-2xl bg-white border border-stone-200 shadow-pop overflow-hidden animate-in fade-in zoom-in-95"
        >
          <div className="flex items-center gap-2 px-4 border-b border-stone-200">
            <Search className="w-4 h-4 text-brand-600 shrink-0" aria-hidden="true" />
            <input
              type="text"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('palette.placeholder')}
              aria-label={t('palette.placeholder')}
              className="w-full py-3.5 px-1 text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none bg-transparent"
            />
            <button
              type="button"
              onClick={onClose}
              aria-label={t('action.close')}
              className="p-1 rounded text-stone-400 hover:text-stone-700 transition-colors shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div ref={listRef} className="max-h-[22rem] overflow-y-auto p-2 space-y-3">
            {results.pages.length > 0 && (
              <div>
                <p className="px-3 py-1 text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                  {t('palette.pages')}
                </p>
                <div className="space-y-0.5 mt-1">
                  {results.pages.map((item, idx) => {
                    const isActive = highlight === idx;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        data-highlighted={isActive}
                        onMouseEnter={() => setHighlight(idx)}
                        onClick={() => {
                          onNavigate(item.id);
                          onClose();
                        }}
                        className={rowClass(isActive)}
                      >
                        <span className="flex items-center gap-3 min-w-0">
                          <span
                            className={isActive ? 'text-brand-600' : 'text-stone-400'}
                            aria-hidden="true"
                          >
                            {item.icon}
                          </span>
                          <span className="truncate">{t(`page.${item.id}`)}</span>
                        </span>
                        <span className="flex items-center gap-2 shrink-0">
                          <span className="text-3xs font-bold text-stone-400">
                            {t(`workspace.${item.group}`)}
                          </span>
                          <ArrowRight
                            data-flip-rtl
                            className={`w-3.5 h-3.5 ${isActive ? 'text-brand-600' : 'text-stone-300'}`}
                            aria-hidden="true"
                          />
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {results.actions.length > 0 && (
              <div>
                <p className="px-3 py-1 text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                  {t('palette.actions')}
                </p>
                <div className="space-y-0.5 mt-1">
                  {results.actions.map((action, idx) => {
                    const index = results.pages.length + idx;
                    const isActive = highlight === index;
                    return (
                      <button
                        key={action.id}
                        type="button"
                        data-highlighted={isActive}
                        onMouseEnter={() => setHighlight(index)}
                        onClick={() => {
                          onQuickAction(action.id);
                          onClose();
                        }}
                        className={rowClass(isActive)}
                      >
                        <span className="flex items-center gap-3 min-w-0">
                          <span
                            className={isActive ? 'text-brand-600' : 'text-stone-400'}
                            aria-hidden="true"
                          >
                            {action.icon}
                          </span>
                          <span className="truncate">{t(`quick.${action.id}`)}</span>
                        </span>
                        <span className="inline-flex items-center gap-1 text-3xs font-extrabold px-1.5 py-0.5 rounded bg-brand-100 text-brand-800 shrink-0">
                          <Zap className="w-2.5 h-2.5" aria-hidden="true" /> {t('palette.run')}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {results.total === 0 && (
              <div className="py-10 text-center">
                <p className="text-xs font-bold text-stone-700">{t('palette.noMatches')}</p>
                <p className="text-2xs text-stone-500 mt-1">
                  {t('palette.noMatchesFor', { query })}
                </p>
              </div>
            )}
          </div>

          <div className="px-4 py-2 border-t border-stone-100 bg-sand-50 text-3xs text-stone-400 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5">
              <CornerDownLeft className="w-3 h-3" aria-hidden="true" data-flip-rtl />{' '}
              {t('palette.toOpen')}
              <span className="mx-1">·</span>
              <kbd className="px-1 py-0.5 bg-white border border-stone-200 rounded text-stone-600">
                Esc
              </kbd>
              {t('palette.close')}
            </span>
            <span className="tabular-nums">
              {t('palette.resultCount', { count: results.total })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
