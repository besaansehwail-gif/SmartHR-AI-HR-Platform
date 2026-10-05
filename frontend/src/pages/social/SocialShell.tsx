import React from 'react';
import { Bell, MessageCircle, Rss, Search, User, Users } from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { useT } from '../../i18n';
import { PageId } from '../../components/layout/Sidebar';
import { SocialPerson } from '../../types';
import { SocialAvatar } from './SocialBits';

/**
 * The frame every Social Hub screen sits in.
 *
 * SmartHR's `PageHeader` is the right header for an HR screen - a rule, an
 * icon tile, a title, a filter toolbar - and the wrong one here: it makes the
 * employee network read as another administrative table. So the Social Hub
 * has its own header and its own section furniture, built from the **same**
 * tokens (`brand`, `sand`, the same radii, the same type scale) so the two
 * are plainly one application rather than two.
 *
 * Nothing here fetches. A page owns its data; these only draw it.
 */

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

export interface SocialHeroProps {
  title: string;
  subtitle: string;
  /** The signed-in person, shown as the "you are here as" mark. */
  me?: SocialPerson | null;
  /** Unread social notifications, for the bell. */
  unread?: number;
  current: PageId;
  onNavigate: (page: PageId) => void;
  /** Search box or filters belonging to this screen. */
  toolbar?: React.ReactNode;
  actions?: React.ReactNode;
}

const TABS: { page: PageId; key: string; icon: React.ReactNode }[] = [
  { page: 'soc-feed', key: 'nav.soc-feed', icon: <Rss className="w-4 h-4" /> },
  { page: 'soc-people', key: 'nav.soc-people', icon: <Users className="w-4 h-4" /> },
  {
    page: 'soc-messages',
    key: 'nav.soc-messages',
    icon: <MessageCircle className="w-4 h-4" />,
  },
  { page: 'soc-profile', key: 'nav.soc-profile', icon: <User className="w-4 h-4" /> },
  {
    page: 'soc-notifications',
    key: 'nav.soc-notifications',
    icon: <Bell className="w-4 h-4" />,
  },
];

/**
 * A warm band, the five destinations, and who you are.
 *
 * The tab row repeats the sidebar deliberately: the Social Hub is a place
 * somebody moves around inside, and a social product puts its own navigation
 * on the page rather than making people aim at a global rail. It is the same
 * `PageId` set, so it cannot drift from the sidebar or from `access.ts`.
 */
export const SocialHero: React.FC<SocialHeroProps> = ({
  title,
  subtitle,
  me,
  unread = 0,
  current,
  onNavigate,
  toolbar,
  actions,
}) => {
  const { t } = useT();

  return (
    <header className="rounded-3xl border border-sand-200 bg-gradient-to-b from-sand-100 to-sand-50 overflow-hidden">
      <div className="px-5 sm:px-7 pt-6 pb-5">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <p className="text-3xs font-extrabold uppercase tracking-wider text-brand-700">
              {t('workspace.social.section')}
            </p>
            <h1 className="mt-1.5 text-xl sm:text-2xl font-extrabold text-stone-900 tracking-tight">
              {title}
            </h1>
            <p className="mt-1.5 text-xs sm:text-sm text-stone-600 leading-relaxed max-w-2xl">
              {subtitle}
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {actions}

            {me && (
              <button
                type="button"
                onClick={() => onNavigate('soc-profile')}
                title={t('nav.soc-profile')}
                className="rounded-full"
              >
                <SocialAvatar person={me} size="md" ring="brand" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* The Social Hub's own navigation. Same PageIds as the sidebar. */}
      <nav
        aria-label={t('workspace.social.section')}
        className="px-3 sm:px-5 border-t border-sand-200/80 bg-white/60"
      >
        <ul className="flex items-center gap-1 overflow-x-auto no-scrollbar">
          {TABS.map((tab) => {
            const active = current === tab.page;

            return (
              <li key={tab.page}>
                <button
                  type="button"
                  onClick={() => onNavigate(tab.page)}
                  aria-current={active ? 'page' : undefined}
                  className={`relative shrink-0 h-12 px-3 sm:px-4 inline-flex items-center gap-2 text-2xs font-bold transition-colors ${
                    active
                      ? 'text-brand-700'
                      : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  <span aria-hidden="true">{tab.icon}</span>
                  <span className="whitespace-nowrap">{t(tab.key)}</span>

                  {tab.page === 'soc-notifications' && unread > 0 && (
                    <span className="min-w-4 h-4 px-1 rounded-full bg-brand-600 text-white text-[10px] font-black leading-4 text-center tabular-nums">
                      {unread > 99 ? '99+' : unread}
                    </span>
                  )}

                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-2 sm:inset-x-3 bottom-0 h-0.5 rounded-t-full bg-brand-600"
                    />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {toolbar && (
        <div className="px-5 sm:px-7 py-3.5 bg-white border-t border-stone-200/70">
          {toolbar}
        </div>
      )}
    </header>
  );
};

// ---------------------------------------------------------------------------
// Section heading
// ---------------------------------------------------------------------------

export const SocialSection: React.FC<{
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}> = ({ title, action, children, className = '' }) => (
  <section className={className}>
    <div className="flex items-center justify-between gap-3 mb-3">
      <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500">
        {title}
      </h2>
      {action}
    </div>
    {children}
  </section>
);

// ---------------------------------------------------------------------------
// Empty states
// ---------------------------------------------------------------------------

export interface SocialEmptyProps {
  icon: React.ReactNode;
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
}

/**
 * Compact on purpose.
 *
 * The full-page `EmptyState` left a screen of whitespace under two lines of
 * text, which reads as unfinished rather than as calm. This is one bordered
 * panel, the height of a post card, that says what would appear here and
 * offers the one action that would cause it.
 */
export const SocialEmpty: React.FC<SocialEmptyProps> = ({
  icon,
  title,
  body,
  actionLabel,
  onAction,
}) => {
  return (
    <div className="rounded-2xl border border-dashed border-stone-300 bg-white px-5 py-8 text-center">
      <span
        aria-hidden="true"
        className="w-11 h-11 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 inline-flex items-center justify-center"
      >
        {icon}
      </span>
      <h3 className="mt-3 text-sm font-extrabold text-stone-900">{title}</h3>
      <p className="mt-1.5 text-2xs text-stone-500 leading-relaxed max-w-sm mx-auto">
        {body}
      </p>
      {actionLabel && onAction && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Skeletons
// ---------------------------------------------------------------------------

/** A post-shaped placeholder, so loading does not collapse the layout. */
export const PostSkeleton: React.FC = () => (
  <div className="bg-white rounded-2xl border border-stone-200/80 p-5">
    <div className="flex items-center gap-3">
      <span className="w-11 h-11 rounded-full skeleton shrink-0" />
      <span className="flex-1 space-y-2">
        <span className="block h-3 w-1/3 rounded skeleton" />
        <span className="block h-2.5 w-1/4 rounded skeleton" />
      </span>
    </div>
    <div className="mt-4 space-y-2">
      <span className="block h-3 w-full rounded skeleton" />
      <span className="block h-3 w-5/6 rounded skeleton" />
    </div>
  </div>
);

/** A search-box-and-filters row. */
export const SocialToolbar: React.FC<{
  value: string;
  placeholder: string;
  onChange: (next: string) => void;
  children?: React.ReactNode;
}> = ({ value, placeholder, onChange, children }) => (
  <div className="flex flex-col sm:flex-row sm:items-center gap-2.5">
    <div className="relative flex-1 min-w-0">
      <Search
        className="w-4 h-4 text-stone-400 absolute top-1/2 -translate-y-1/2 start-3"
        aria-hidden="true"
      />
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="w-full h-10 ps-9 pe-3 rounded-xl border border-stone-200 bg-sand-50 text-xs text-stone-800 placeholder:text-stone-400 focus:bg-white focus:border-brand-300 focus:outline-none transition-colors"
      />
    </div>
    {children}
  </div>
);
