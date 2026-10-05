import React, { useEffect, useState } from 'react';
import { Sidebar, PageId } from './Sidebar';
import { TopNavigation } from './TopNavigation';
import { CommandPalette } from './CommandPalette';
import { AiAssistant } from '../ai/AiAssistant';
import { MyEmployeeIdentity, SystemNotification } from '../../types';
import { useT } from '../../i18n';

export interface GlobalLayoutProps {
  currentPage: PageId;
  roleId: number | null;
  onNavigate: (page: PageId) => void;
  children: React.ReactNode;
  notifications: SystemNotification[];
  onMarkNotificationRead: (id: string) => void;
  onMarkAllNotificationsRead: () => void;
  onQuickAction: (action: string) => void;
  identity?: MyEmployeeIdentity | null;
  accountEmail?: string | null;
  onSignOut?: () => void;
}

const COLLAPSE_KEY = 'smarthr_sidebar_collapsed';

/**
 * The application shell: fixed left rail, sticky top bar, and a centred page
 * container.
 *
 * Layout rules that the rest of the app leans on:
 *  - below `lg` the sidebar is an off-canvas drawer, so pages get the full
 *    viewport width on tablets and phones;
 *  - the main column is the only thing that scrolls vertically, and nothing
 *    scrolls horizontally except tables, which handle it themselves;
 *  - the collapsed/expanded choice is remembered per browser.
 */
export const GlobalLayout: React.FC<GlobalLayoutProps> = ({
  currentPage,
  roleId,
  onNavigate,
  children,
  notifications,
  onMarkNotificationRead,
  onMarkAllNotificationsRead,
  onQuickAction,
  identity,
  accountEmail,
  onSignOut,
}) => {
  const { t } = useT();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, sidebarCollapsed ? '1' : '0');
    } catch {
      // A browser with storage blocked simply forgets the preference.
    }
  }, [sidebarCollapsed]);

  // Close the mobile drawer whenever the page changes, so a tap on a nav item
  // reveals the page it opened rather than leaving the drawer covering it.
  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [currentPage]);

  // Ctrl/Cmd-K opens the palette from anywhere. The palette itself handles
  // Escape, arrows and Enter once it is open.
  useEffect(() => {
    const handleShortcut = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <div className="min-h-screen bg-sand-50 text-ink flex">
      <a
        href="#smarthr-main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:start-3 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-brand-600 focus:text-white focus:text-xs focus:font-bold"
      >
        {t('app.skipToContent')}
      </a>

      <Sidebar
        roleId={roleId}
        currentPage={currentPage}
        onNavigate={onNavigate}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        identity={identity}
        accountEmail={accountEmail}
        unreadCount={unreadCount}
      />

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[padding] duration-300 ease-in-out ${
          sidebarCollapsed ? 'lg:ps-20' : 'lg:ps-64'
        }`}
      >
        <TopNavigation
          currentPage={currentPage}
          onNavigate={onNavigate}
          onOpenMobileMenu={() => setMobileSidebarOpen(true)}
          onOpenCommandPalette={() => setCommandPaletteOpen(true)}
          notifications={notifications}
          onMarkNotificationRead={onMarkNotificationRead}
          onMarkAllNotificationsRead={onMarkAllNotificationsRead}
          onQuickAction={onQuickAction}
          roleId={roleId}
          identity={identity}
          accountEmail={accountEmail}
          onSignOut={onSignOut}
        />

        <main
          id="smarthr-main"
          className="flex-1 w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-7"
        >
          {children}
        </main>

        <footer className="px-4 sm:px-6 lg:px-8 py-4 border-t border-stone-200/70 text-3xs text-stone-400 flex flex-col sm:flex-row items-center justify-between gap-1.5">
          <span>
            {t('app.name')} — {t('app.tagline')}
          </span>
          <span>{t('app.connected')}</span>
        </footer>
      </div>

      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigate={onNavigate}
        onQuickAction={onQuickAction}
        roleId={roleId}
      />

      {/*
        Mounted once in the authenticated shell, for staff only. The assistant
        talks to /ai/chat, which is roles 1-4: an Applicant would get a 403 on
        every message. They have the Career Agent instead, which is its own
        page with its own endpoint and its own tools.
      */}
      {roleId !== 5 && <AiAssistant />}
    </div>
  );
};
