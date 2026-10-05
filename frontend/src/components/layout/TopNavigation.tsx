import React, { useState, useRef, useEffect } from 'react';
import {
  Search,
  Bell,
  Menu,
  ChevronDown,
  User as UserIcon,
  Shield,
  Settings as SettingsIcon,
  LogOut,
  CheckCircle2,
  AlertTriangle,
  Info,
  ExternalLink,
  Plus,
  Building,
  Briefcase,
  History,
  Star,
  Clock,
  BellOff,
} from 'lucide-react';
import { Breadcrumbs } from '../ui/Breadcrumbs';
import { PageId } from './Sidebar';
import { MyEmployeeIdentity, SystemNotification } from '../../types';
import { LanguageSwitcher, useT } from '../../i18n';

export interface TopNavigationProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  onOpenMobileMenu: () => void;
  onOpenCommandPalette: () => void;
  notifications: SystemNotification[];
  onMarkNotificationRead: (id: string) => void;
  onMarkAllNotificationsRead: () => void;
  onQuickAction: (action: string) => void;
  roleId?: number | null;
  identity?: MyEmployeeIdentity | null;
  accountEmail?: string | null;
  onSignOut?: () => void;
}

/*
 * Page titles and quick-action labels used to be English literals here. They
 * are now `page.<PageId>` and `quick.<action>` in the dictionary, looked up at
 * render time, so this file describes structure and permissions only.
 */

/**
 * Quick actions, grouped by the role that is allowed to perform them.
 *
 * An Employee is not offered "Add System User", because the endpoint behind it
 * would return 403. The backend is still the boundary; this just avoids
 * offering a door that does not open.
 */
const QUICK_ACTIONS: {
  groupKey: string;
  roles: number[];
  items: { action: string; icon: React.ReactNode }[];
}[] = [
  {
    groupKey: 'quick.group.teamManagement',
    roles: [1, 2, 3],
    items: [
      { action: 'mgr-approve-leave', icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
      { action: 'mgr-conduct-review', icon: <Star className="w-3.5 h-3.5" /> },
      { action: 'mgr-check-attendance', icon: <Clock className="w-3.5 h-3.5" /> },
    ],
  },
  {
    groupKey: 'quick.group.hrOperations',
    roles: [1, 2],
    items: [
      { action: 'add-employee', icon: <UserIcon className="w-3.5 h-3.5" /> },
      { action: 'post-job', icon: <Briefcase className="w-3.5 h-3.5" /> },
      { action: 'schedule-interview', icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
    ],
  },
  {
    groupKey: 'quick.group.administration',
    roles: [1],
    items: [
      { action: 'add-user', icon: <UserIcon className="w-3.5 h-3.5" /> },
      { action: 'add-department', icon: <Building className="w-3.5 h-3.5" /> },
      { action: 'export-audit', icon: <History className="w-3.5 h-3.5" /> },
    ],
  },
];

const initialsOf = (name?: string | null, fallback?: string | null) => {
  const source = (name || fallback || '').trim();
  if (!source) return '--';
  const parts = source.replace(/@.*$/, '').split(/[\s._-]+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join('') || source[0]).toUpperCase();
};

export const TopNavigation: React.FC<TopNavigationProps> = ({
  currentPage,
  onNavigate,
  onOpenMobileMenu,
  onOpenCommandPalette,
  notifications,
  onMarkNotificationRead,
  onMarkAllNotificationsRead,
  onQuickAction,
  roleId = null,
  identity,
  accountEmail,
  onSignOut,
}) => {
  const { t } = useT();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [quickActionOpen, setQuickActionOpen] = useState(false);

  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const quickActionRef = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
      if (quickActionRef.current && !quickActionRef.current.contains(event.target as Node)) {
        setQuickActionOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setNotificationsOpen(false);
        setProfileOpen(false);
        setQuickActionOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, []);

  const isEmp = currentPage.startsWith('emp-');
  const isMgr = currentPage.startsWith('mgr-');
  const isHR = currentPage.startsWith('hr-');
  // The Social Hub is a workspace of its own, and saying so here is what stops
  // the employee network introducing itself as "Admin > Social Feed": `soc-`
  // pages used to fall through to the admin default with everything else.
  const isSocial = currentPage.startsWith('soc-');
  // Applicant pages likewise: without this, an external job seeker was told
  // they were in "Admin > AI Interview".
  const isApplicant = currentPage.startsWith('app-');
  const workspaceKey = isSocial
    ? 'social'
    : isApplicant
    ? 'applicant'
    : isEmp
    ? 'employee'
    : isMgr
    ? 'manager'
    : isHR
    ? 'hr'
    : 'admin';
  // "Social Hub > People", not "Social > People": the section name is what
  // the sidebar calls it and what an employee would call it.
  const workspaceTitle = isSocial
    ? t('workspace.social.section')
    : t(`workspace.${workspaceKey}`);
  const workspaceHome: PageId = isSocial
    ? 'soc-feed'
    : isApplicant
    ? 'app-dashboard'
    : isEmp
    ? 'emp-dashboard'
    : isMgr
    ? 'mgr-dashboard'
    : isHR
    ? 'hr-dashboard'
    : 'dashboard';

  const notificationsPage: PageId = isSocial
    ? 'soc-notifications'
    : isMgr
    ? 'mgr-notifications'
    : isHR
    ? 'hr-notifications'
    : isEmp
    ? 'emp-notifications'
    : 'hr-notifications';

  const availableActions = QUICK_ACTIONS.filter((group) =>
    roleId === null ? false : group.roles.includes(roleId)
  );

  const displayName = identity?.full_name || accountEmail || t('role.smarthrUser');
  const roleLabel = roleId ? t(`role.${roleId}`) : t('role.signedIn');
  const pageTitle = t(`page.${currentPage}`);

  return (
    <header className="sticky top-0 z-30 h-16 bg-white/90 backdrop-blur-md border-b border-stone-200/80 px-3 sm:px-6 flex items-center justify-between gap-3">
      {/* Left: mobile menu + location */}
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          className="lg:hidden p-2 rounded-lg text-stone-600 hover:bg-sand-100 transition-colors"
          aria-label={t('topbar.openNavigation')}
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="hidden sm:block min-w-0">
          <Breadcrumbs
            onHomeClick={() => onNavigate(workspaceHome)}
            homeLabel={t('topbar.workspaceHome', { workspace: workspaceTitle })}
            items={[
              { label: workspaceTitle, onClick: () => onNavigate(workspaceHome) },
              { label: pageTitle },
            ]}
          />
          <h2 className="text-sm font-extrabold text-stone-900 tracking-tight truncate mt-0.5">
            {pageTitle}
          </h2>
        </div>

        <div className="sm:hidden font-extrabold text-sm text-stone-900 truncate">
          {pageTitle}
        </div>
      </div>

      {/* Right: search, quick action, notifications, profile */}
      <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
        <button
          type="button"
          onClick={onOpenCommandPalette}
          aria-label={t('topbar.searchAria')}
          className="hidden sm:flex items-center gap-2 h-9 ps-3 pe-2 rounded-lg border border-stone-200 bg-sand-50 hover:bg-sand-100 hover:border-stone-300 text-stone-500 text-xs font-medium transition-colors w-52 lg:w-72 justify-between group"
        >
          <span className="flex items-center gap-2 truncate">
            <Search className="w-3.5 h-3.5 text-stone-400 group-hover:text-brand-600 transition-colors" />
            <span className="truncate">{t('topbar.searchRecords')}</span>
          </span>
          <kbd className="hidden lg:inline-flex items-center px-1.5 py-0.5 text-3xs font-bold rounded bg-white text-stone-500 border border-stone-200">
            {t('topbar.commandHint')}
          </kbd>
        </button>

        <button
          type="button"
          onClick={onOpenCommandPalette}
          aria-label={t('action.search')}
          className="sm:hidden p-2 rounded-lg text-stone-600 hover:bg-sand-100 transition-colors"
        >
          <Search className="w-4 h-4" />
        </button>

        {/* Quick actions - only those this role can actually perform */}
        {availableActions.length > 0 && (
          <div className="relative" ref={quickActionRef}>
            <button
              type="button"
              onClick={() => setQuickActionOpen(!quickActionOpen)}
              aria-haspopup="menu"
              aria-expanded={quickActionOpen}
              className="flex items-center gap-1.5 h-9 px-3 rounded-lg bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white text-xs font-bold transition-colors shadow-[0_1px_2px_rgba(164,72,32,0.25)]"
            >
              <Plus className="w-3.5 h-3.5" />
              <span className="hidden md:inline">{t('topbar.quickAction')}</span>
              <ChevronDown className="w-3 h-3 opacity-70" aria-hidden="true" />
            </button>

            {quickActionOpen && (
              <div
                role="menu"
                className="absolute end-0 mt-2 w-60 rounded-xl bg-white border border-stone-200 shadow-pop py-1.5 z-50 animate-in fade-in zoom-in-95"
              >
                {availableActions.map((group, groupIdx) => (
                  <div key={group.groupKey}>
                    {groupIdx > 0 && <div className="my-1 border-t border-stone-100" />}
                    <p className="px-3 py-1 text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                      {t(group.groupKey)}
                    </p>
                    {group.items.map((item) => (
                      <button
                        key={item.action}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          onQuickAction(item.action);
                          setQuickActionOpen(false);
                        }}
                        className="w-full px-3 py-2 text-xs font-medium text-stone-700 hover:bg-brand-50 hover:text-brand-800 flex items-center gap-2.5 transition-colors text-start"
                      >
                        <span className="text-brand-600 shrink-0" aria-hidden="true">
                          {item.icon}
                        </span>
                        <span className="truncate">{t(`quick.${item.action}`)}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/*
          The global language switcher. One instance, in the application
          header, so it changes the language of everything rather than of the
          page it happens to be on.
        */}
        <LanguageSwitcher />

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => setNotificationsOpen(!notificationsOpen)}
            aria-haspopup="menu"
            aria-expanded={notificationsOpen}
            aria-label={
              unreadCount > 0
                ? t('topbar.notificationsUnreadAria', { count: unreadCount })
                : t('topbar.notifications')
            }
            className="relative p-2 rounded-lg text-stone-600 hover:bg-sand-100 hover:text-stone-900 transition-colors"
          >
            <Bell className="w-[18px] h-[18px]" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -end-0.5 min-w-4 h-4 px-1 rounded-full bg-brand-600 text-white text-3xs font-extrabold tabular-nums flex items-center justify-center ring-2 ring-white">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {notificationsOpen && (
            <div className="absolute end-0 mt-2 w-[min(22rem,calc(100vw-1.5rem))] rounded-xl bg-white border border-stone-200 shadow-pop z-50 overflow-hidden animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-stone-100">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-extrabold text-stone-900">
                    {t('topbar.notifications')}
                  </span>
                  {unreadCount > 0 && (
                    <span className="text-3xs font-extrabold px-1.5 py-0.5 rounded-full bg-brand-100 text-brand-800 tabular-nums">
                      {t('topbar.newCount', { count: unreadCount })}
                    </span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={onMarkAllNotificationsRead}
                    className="text-2xs font-bold text-brand-700 hover:text-brand-800 transition-colors"
                  >
                    {t('topbar.markAllRead')}
                  </button>
                )}
              </div>

              <div className="max-h-80 overflow-y-auto divide-y divide-stone-100">
                {notifications.length === 0 ? (
                  <div className="px-6 py-10 text-center">
                    <BellOff className="w-5 h-5 text-stone-300 mx-auto mb-2" aria-hidden="true" />
                    <p className="text-xs font-bold text-stone-700">{t('topbar.caughtUp')}</p>
                    <p className="text-2xs text-stone-500 mt-1">{t('topbar.caughtUpHint')}</p>
                  </div>
                ) : (
                  notifications.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        onMarkNotificationRead(item.id);
                        if (item.linkPage) {
                          onNavigate(item.linkPage as PageId);
                          setNotificationsOpen(false);
                        }
                      }}
                      className={`w-full text-start px-4 py-3 flex items-start gap-3 hover:bg-sand-50 transition-colors ${
                        !item.read ? 'bg-brand-50/40' : ''
                      }`}
                    >
                      <span className="mt-0.5 shrink-0" aria-hidden="true">
                        {item.type === 'alert' && <AlertTriangle className="w-4 h-4 text-red-600" />}
                        {item.type === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-500" />}
                        {item.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                        {item.type === 'info' && <Info className="w-4 h-4 text-brand-600" />}
                      </span>

                      <span className="flex-1 min-w-0">
                        <span className="flex items-baseline justify-between gap-2">
                          <span
                            className={`text-2xs truncate ${
                              !item.read ? 'font-extrabold text-stone-900' : 'font-semibold text-stone-700'
                            }`}
                          >
                            {item.title}
                          </span>
                          <span className="text-3xs text-stone-400 shrink-0">{item.timestamp}</span>
                        </span>
                        <span className="block text-3xs text-stone-500 mt-1 leading-relaxed line-clamp-2">
                          {item.message}
                        </span>
                      </span>

                      {!item.read && (
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-brand-600 mt-1.5 shrink-0"
                          aria-label={t('topbar.unread')}
                        />
                      )}
                    </button>
                  ))
                )}
              </div>

              <div className="px-4 py-2.5 border-t border-stone-100 bg-sand-50 flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => {
                    onNavigate(notificationsPage);
                    setNotificationsOpen(false);
                  }}
                  className="text-2xs font-bold text-brand-700 hover:text-brand-800 flex items-center gap-1"
                >
                  {t('topbar.openNotificationCenter')}{' '}
                  <ExternalLink className="w-2.5 h-2.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Signed-in account */}
        <div className="relative" ref={profileRef}>
          <button
            type="button"
            onClick={() => setProfileOpen(!profileOpen)}
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            aria-label={t('topbar.accountMenu')}
            className="flex items-center gap-2 p-1 pe-1.5 rounded-lg hover:bg-sand-100 transition-colors"
          >
            <span className="w-8 h-8 rounded-full bg-brand-600 text-white font-extrabold text-2xs flex items-center justify-center shrink-0">
              {initialsOf(identity?.full_name, accountEmail)}
            </span>
            <span className="hidden xl:block text-start min-w-0">
              <span className="block text-2xs font-bold text-stone-900 leading-tight truncate max-w-[10rem]">
                {displayName}
              </span>
              <span className="block text-3xs text-stone-500 truncate">
                {identity?.position_title || roleLabel}
              </span>
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 hidden xl:block" aria-hidden="true" />
          </button>

          {profileOpen && (
            <div
              role="menu"
              className="absolute end-0 mt-2 w-64 rounded-xl bg-white border border-stone-200 shadow-pop py-1.5 z-50 animate-in fade-in zoom-in-95"
            >
              <div className="px-4 py-3 border-b border-stone-100">
                <p className="text-xs font-extrabold text-stone-900 truncate">{displayName}</p>
                {accountEmail && (
                  <p className="text-2xs text-stone-500 truncate mt-0.5">{accountEmail}</p>
                )}
                <span className="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-50 text-brand-800 border border-brand-200 text-3xs font-bold">
                  <Shield className="w-2.5 h-2.5" aria-hidden="true" />
                  {roleLabel}
                  {identity?.department_name ? ` · ${identity.department_name}` : ''}
                </span>
              </div>

              <div className="py-1">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onNavigate('emp-profile');
                    setProfileOpen(false);
                  }}
                  className="w-full px-4 py-2 text-xs font-medium text-stone-700 hover:bg-brand-50 hover:text-brand-800 flex items-center gap-2.5 transition-colors text-start"
                >
                  <UserIcon className="w-3.5 h-3.5 text-stone-400" aria-hidden="true" />
                  {t('topbar.myProfile')}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onNavigate('emp-notifications');
                    setProfileOpen(false);
                  }}
                  className="w-full px-4 py-2 text-xs font-medium text-stone-700 hover:bg-brand-50 hover:text-brand-800 flex items-center gap-2.5 transition-colors text-start"
                >
                  <Bell className="w-3.5 h-3.5 text-stone-400" aria-hidden="true" />
                  {t('topbar.myNotifications')}
                </button>
                {roleId === 1 && (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onNavigate('settings');
                      setProfileOpen(false);
                    }}
                    className="w-full px-4 py-2 text-xs font-medium text-stone-700 hover:bg-brand-50 hover:text-brand-800 flex items-center gap-2.5 transition-colors text-start"
                  >
                    <SettingsIcon className="w-3.5 h-3.5 text-stone-400" aria-hidden="true" />
                    {t('nav.settings')}
                  </button>
                )}
              </div>

              {onSignOut && (
                <div className="border-t border-stone-100 pt-1">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setProfileOpen(false);
                      onSignOut();
                    }}
                    className="w-full px-4 py-2 text-xs font-bold text-red-700 hover:bg-red-50 flex items-center gap-2.5 text-start transition-colors"
                  >
                    <LogOut className="w-3.5 h-3.5" aria-hidden="true" data-flip-rtl />
                    {t('action.signOut')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
