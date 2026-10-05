import React, { useState, useEffect } from 'react';
import {
  BarChart3,
  LayoutDashboard,
  Users,
  ShieldCheck,
  Building,
  Briefcase,
  History,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Shield,
  UserCheck,
  Calendar,
  GraduationCap,
  MessageCircle,
  Rss,
  TrendingUp,
  Bell,
  Eye,
  Clock,
  Star,
  CheckSquare,
  User,
  BookOpen,
  Compass,
  FileText,
  Send,
  Radio,
  Sparkles,
  X,
} from 'lucide-react';

import { workspacesFor, type Workspace } from '../../services/access';
import { useT } from '../../i18n';
import { MyEmployeeIdentity } from '../../types';

export type PageId =
  // Applicant Workspace (external job seekers, role 5)
  | 'app-dashboard'
  | 'app-opportunities'
  | 'app-profile'
  | 'app-cv'
  | 'app-applications'
  | 'app-agent'
  | 'app-ai-interview'
  // Social Hub (internal employee network, roles 1-4)
  | 'soc-feed'
  | 'soc-people'
  | 'soc-messages'
  | 'soc-notifications'
  // A profile is reached from the feed, a post or the People directory, so it
  // carries the person being viewed in App state rather than in the PageId.
  | 'soc-profile'
  // Employee Workspace (8 Pages)
  | 'emp-dashboard'
  | 'emp-profile'
  | 'emp-attendance'
  | 'emp-leave'
  | 'emp-training'
  | 'emp-performance'
  | 'emp-career'
  | 'emp-notifications'
  // Manager Workspace
  | 'mgr-dashboard'
  | 'mgr-team'
  | 'mgr-attendance'
  | 'mgr-leave'
  | 'mgr-performance'
  | 'mgr-insights'
  | 'mgr-notifications'
  // HR Workspace
  | 'hr-dashboard'
  | 'hr-employees'
  | 'hr-employee-360'
  | 'hr-jobs'
  | 'hr-candidates'
  | 'hr-ai-agent'
  | 'hr-ai-interview-analytics'
  | 'hr-interviews'
  | 'hr-social-moderation'
  | 'hr-training'
  | 'hr-reports'
  | 'hr-notifications'
  // Admin Workspace
  | 'dashboard'
  | 'users'
  | 'roles'
  | 'departments'
  | 'positions'
  | 'audit'
  | 'settings';

export interface SidebarProps {
  currentPage: PageId;
  /** Role of the signed-in user; decides which workspaces are offered. */
  roleId: number | null;
  onNavigate: (page: PageId) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  /** The signed-in person, when their account is linked to an employee row. */
  identity?: MyEmployeeIdentity | null;
  accountEmail?: string | null;
  /** Live unread count for the notifications entry. */
  unreadCount?: number;
}

/**
 * A nav entry holds no text. Its label is `nav.<PageId>` in the dictionary, so
 * the arrays below stay a pure description of structure and adding a language
 * never means touching them.
 */
type NavItem = { id: PageId; icon: React.ReactNode };

const iconClass = 'w-[18px] h-[18px]';

const EMPLOYEE_NAV: NavItem[] = [
  { id: 'emp-dashboard', icon: <LayoutDashboard className={iconClass} /> },
  { id: 'emp-profile', icon: <User className={iconClass} /> },
  { id: 'emp-attendance', icon: <Clock className={iconClass} /> },
  { id: 'emp-leave', icon: <Calendar className={iconClass} /> },
  { id: 'emp-training', icon: <BookOpen className={iconClass} /> },
  { id: 'emp-performance', icon: <Star className={iconClass} /> },
  { id: 'emp-career', icon: <TrendingUp className={iconClass} /> },
  { id: 'emp-notifications', icon: <Bell className={iconClass} /> },
];

const APPLICANT_NAV: NavItem[] = [
  { id: 'app-dashboard', icon: <LayoutDashboard className={iconClass} /> },
  { id: 'app-opportunities', icon: <Compass className={iconClass} /> },
  { id: 'app-profile', icon: <User className={iconClass} /> },
  { id: 'app-cv', icon: <FileText className={iconClass} /> },
  { id: 'app-applications', icon: <Send className={iconClass} /> },
  { id: 'app-agent', icon: <Sparkles className={iconClass} /> },
  { id: 'app-ai-interview', icon: <Radio className={iconClass} /> },
];

const SOCIAL_NAV: NavItem[] = [
  { id: 'soc-feed', icon: <Rss className={iconClass} /> },
  { id: 'soc-people', icon: <Users className={iconClass} /> },
  { id: 'soc-messages', icon: <MessageCircle className={iconClass} /> },
  { id: 'soc-profile', icon: <User className={iconClass} /> },
  { id: 'soc-notifications', icon: <Bell className={iconClass} /> },
];

const MANAGER_NAV: NavItem[] = [
  { id: 'mgr-dashboard', icon: <LayoutDashboard className={iconClass} /> },
  { id: 'mgr-team', icon: <Users className={iconClass} /> },
  { id: 'mgr-attendance', icon: <Clock className={iconClass} /> },
  { id: 'mgr-leave', icon: <Calendar className={iconClass} /> },
  { id: 'mgr-performance', icon: <Star className={iconClass} /> },
  { id: 'mgr-insights', icon: <TrendingUp className={iconClass} /> },
  { id: 'mgr-notifications', icon: <Bell className={iconClass} /> },
];

const HR_NAV: NavItem[] = [
  { id: 'hr-dashboard', icon: <LayoutDashboard className={iconClass} /> },
  { id: 'hr-employees', icon: <Users className={iconClass} /> },
  { id: 'hr-employee-360', icon: <Eye className={iconClass} /> },
  { id: 'hr-jobs', icon: <Briefcase className={iconClass} /> },
  { id: 'hr-candidates', icon: <UserCheck className={iconClass} /> },
  { id: 'hr-ai-agent', icon: <Sparkles className={iconClass} /> },
  { id: 'hr-interviews', icon: <Calendar className={iconClass} /> },
  { id: 'hr-ai-interview-analytics', icon: <BarChart3 className={iconClass} /> },
  { id: 'hr-social-moderation', icon: <Shield className={iconClass} /> },
  { id: 'hr-training', icon: <GraduationCap className={iconClass} /> },
  { id: 'hr-reports', icon: <TrendingUp className={iconClass} /> },
  { id: 'hr-notifications', icon: <Bell className={iconClass} /> },
];

const ADMIN_NAV: NavItem[] = [
  { id: 'dashboard', icon: <LayoutDashboard className={iconClass} /> },
  { id: 'users', icon: <Users className={iconClass} /> },
  { id: 'roles', icon: <ShieldCheck className={iconClass} /> },
  { id: 'departments', icon: <Building className={iconClass} /> },
  { id: 'positions', icon: <Briefcase className={iconClass} /> },
  { id: 'audit', icon: <History className={iconClass} /> },
  { id: 'settings', icon: <Settings className={iconClass} /> },
];

/**
 * Workspace chrome. `label`, `short` and `section` are gone: they are
 * `workspace.<key>`, `workspace.<key>.short` and `workspace.<key>.section` in
 * the dictionary, looked up at render time.
 */
const WORKSPACE_META: Record<
  Workspace,
  { icon: React.ReactNode; home: PageId }
> = {
  applicant: {
    icon: <Compass className="w-3.5 h-3.5" />,
    home: 'app-dashboard',
  },
  employee: {
    icon: <User className="w-3.5 h-3.5" />,
    home: 'emp-dashboard',
  },
  social: {
    icon: <Rss className="w-3.5 h-3.5" />,
    home: 'soc-feed',
  },
  manager: {
    icon: <CheckSquare className="w-3.5 h-3.5" />,
    home: 'mgr-dashboard',
  },
  hr: {
    icon: <Users className="w-3.5 h-3.5" />,
    home: 'hr-dashboard',
  },
  admin: {
    icon: <Shield className="w-3.5 h-3.5" />,
    home: 'dashboard',
  },
};

const NAV_BY_WORKSPACE: Record<Workspace, NavItem[]> = {
  applicant: APPLICANT_NAV,
  employee: EMPLOYEE_NAV,
  social: SOCIAL_NAV,
  manager: MANAGER_NAV,
  hr: HR_NAV,
  admin: ADMIN_NAV,
};

const workspaceOfPage = (page: PageId): Workspace => {
  if (page.startsWith('app-')) return 'applicant';
  if (page.startsWith('soc-')) return 'social';
  if (page.startsWith('emp-')) return 'employee';
  if (page.startsWith('mgr-')) return 'manager';
  if (page.startsWith('hr-')) return 'hr';
  return 'admin';
};

const initialsOf = (name?: string | null, fallback?: string | null) => {
  const source = (name || fallback || '').trim();
  if (!source) return '--';
  const parts = source.replace(/@.*$/, '').split(/[\s._-]+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join('') || source[0]).toUpperCase();
};

/**
 * The persistent left rail.
 *
 * Identity is the dark brand panel: on the sand canvas it anchors the whole
 * layout, and the active item is the one brand-orange surface in it, so where
 * you are is never ambiguous.
 *
 * Only workspaces the role may use are offered. That is convenience, not
 * security - every endpoint behind these pages is guarded server-side.
 */
export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  roleId,
  onNavigate,
  isCollapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
  identity,
  accountEmail,
  unreadCount = 0,
}) => {
  const { t } = useT();
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace>(workspaceOfPage(currentPage));

  useEffect(() => {
    setActiveWorkspace(workspaceOfPage(currentPage));
  }, [currentPage]);

  const allowedWorkspaces = workspacesFor(roleId);
  const mayUse = (workspace: Workspace) => allowedWorkspaces.includes(workspace);
  const navItems = NAV_BY_WORKSPACE[activeWorkspace];

  const handleSelectWorkspace = (workspace: Workspace) => {
    if (!mayUse(workspace)) return;
    setActiveWorkspace(workspace);
    if (workspaceOfPage(currentPage) !== workspace) {
      onNavigate(WORKSPACE_META[workspace].home);
    }
  };

  // The person's name and their position title are database values and are
  // shown exactly as stored. Only the fallbacks - which are SmartHR's own
  // words, not anybody's data - are translated.
  const displayName = identity?.full_name || accountEmail || t('role.smarthrUser');
  const displayRole =
    identity?.position_title ||
    (roleId ? t(`role.${roleId}`) : '') ||
    t('role.signedIn');

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-stone-900/50 backdrop-blur-[2px] lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label={t('topbar.mainNavigation')}
        className={`fixed top-0 bottom-0 start-0 z-40 flex flex-col bg-brand-950 text-brand-100 transition-[width,transform] duration-300 ease-in-out ${
          isCollapsed ? 'w-20' : 'w-64'
        } ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        {/* Brand */}
        <div className="h-16 flex items-center justify-between gap-2 px-4 border-b border-white/10 shrink-0">
          <button
            type="button"
            onClick={() => onNavigate(WORKSPACE_META[activeWorkspace].home)}
            className="flex items-center gap-2.5 min-w-0 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
          >
            <span className="w-9 h-9 rounded-xl bg-brand-500 text-brand-950 font-black flex items-center justify-center shrink-0 text-base tracking-tighter">
              S
            </span>
            {!isCollapsed && (
              <span className="min-w-0 text-start">
                <span className="block text-base font-extrabold text-white tracking-tight leading-none">
                  Smart<span className="text-brand-400">HR</span>
                </span>
                <span className="block text-3xs text-brand-200/60 tracking-wide truncate mt-1">
                  {t('app.tagline')}
                </span>
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? t('topbar.expandSidebar') : t('topbar.collapseSidebar')}
            className="hidden lg:inline-flex items-center justify-center w-8 h-8 rounded-lg text-brand-200/70 hover:text-white hover:bg-white/10 transition-colors shrink-0"
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-4 h-4" data-flip-rtl />
            ) : (
              <PanelLeftClose className="w-4 h-4" data-flip-rtl />
            )}
          </button>

          <button
            type="button"
            onClick={onCloseMobile}
            aria-label={t('action.close')}
            className="lg:hidden inline-flex items-center justify-center w-8 h-8 rounded-lg text-brand-200/70 hover:text-white hover:bg-white/10 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Workspace switcher - only the workspaces this role may use */}
        {allowedWorkspaces.length > 1 && (
          <div className="px-3 pt-3 shrink-0">
            <div
              className={`p-1 rounded-xl bg-black/25 ${
                isCollapsed ? 'flex flex-col gap-1' : 'grid grid-cols-2 gap-1'
              }`}
            >
              {(['applicant', 'employee', 'social', 'manager', 'hr', 'admin'] as Workspace[])
                .filter(mayUse)
                .map((workspace) => {
                  const meta = WORKSPACE_META[workspace];
                  const isActive = activeWorkspace === workspace;
                  return (
                    <button
                      key={workspace}
                      type="button"
                      onClick={() => handleSelectWorkspace(workspace)}
                      title={t('workspace.switch')}
                      aria-current={isActive ? 'true' : undefined}
                      className={`h-8 rounded-lg text-2xs font-bold transition-colors flex items-center justify-center gap-1.5 ${
                        isActive
                          ? 'bg-brand-600 text-white'
                          : 'text-brand-200/70 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      <span className="shrink-0" aria-hidden="true">
                        {meta.icon}
                      </span>
                      {!isCollapsed && (
                        <span className="truncate">{t(`workspace.${workspace}`)}</span>
                      )}
                    </button>
                  );
                })}
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
          {!isCollapsed && (
            <p className="px-2 pb-2 pt-1 text-3xs font-extrabold uppercase tracking-[0.14em] text-brand-200/40">
              {t(`workspace.${activeWorkspace}.section`)}
            </p>
          )}

          {navItems.map((item) => {
            const isActive = currentPage === item.id;
            const isNotifications = item.id.endsWith('notifications');
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id);
                  onCloseMobile();
                }}
                aria-current={isActive ? 'page' : undefined}
                title={isCollapsed ? t(`nav.${item.id}`) : undefined}
                className={`group relative w-full flex items-center gap-3 h-10 rounded-lg text-xs font-semibold transition-colors ${
                  isCollapsed ? 'justify-center px-0' : 'px-3'
                } ${
                  isActive
                    ? 'bg-brand-600 text-white'
                    : 'text-brand-100/70 hover:text-white hover:bg-white/10'
                }`}
              >
                <span
                  className={`shrink-0 ${isActive ? 'text-white' : 'text-brand-300/70 group-hover:text-brand-200'}`}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>

                {!isCollapsed && (
                  <span className="flex-1 text-start truncate">{t(`nav.${item.id}`)}</span>
                )}

                {isNotifications && unreadCount > 0 && (
                  <span
                    className={`shrink-0 min-w-4 h-4 px-1 rounded-full text-3xs font-extrabold tabular-nums flex items-center justify-center ${
                      isCollapsed
                        ? 'absolute top-1.5 end-2 bg-brand-400 text-brand-950'
                        : 'bg-brand-400 text-brand-950'
                    }`}
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Signed-in person, read from /auth/me + /auth/me/employee */}
        <div className="p-3 border-t border-white/10 shrink-0">
          <button
            type="button"
            onClick={() => {
              onNavigate(
                workspacesFor(roleId).includes('applicant') ? 'app-profile' : 'emp-profile'
              );
              onCloseMobile();
            }}
            title={isCollapsed ? displayName : undefined}
            className={`w-full flex items-center gap-2.5 rounded-xl p-2 transition-colors hover:bg-white/10 ${
              isCollapsed ? 'justify-center' : ''
            }`}
          >
            <span className="w-8 h-8 rounded-full bg-brand-500 text-brand-950 font-extrabold text-2xs flex items-center justify-center shrink-0">
              {initialsOf(identity?.full_name, accountEmail)}
            </span>
            {!isCollapsed && (
              <span className="min-w-0 flex-1 text-start">
                <span className="block text-xs font-bold text-white truncate">{displayName}</span>
                <span className="block text-3xs text-brand-200/60 truncate">{displayRole}</span>
              </span>
            )}
          </button>
        </div>
      </aside>
    </>
  );
};
