import React, { useCallback, useEffect, useState } from 'react';
import { GlobalLayout } from './components/layout/GlobalLayout';
import { PageId } from './components/layout/Sidebar';
import { canAccessPage, landingPageFor } from './services/access';
import { useT } from './i18n';
import { ToastProvider, useToast } from './components/ui/Toast';
import { CurrentUser, MyEmployeeIdentity, SystemNotification } from './types';
import { LoginPage } from "./pages/LoginPage";
import { ApplicantRegisterPage } from "./pages/ApplicantRegisterPage";
import { SmartHRApi } from "./services/api";
import { toSystemNotification } from "./services/notificationAdapters";

// Applicant Workspace Pages (external job seekers, role 5)
import { ApplicantDashboardPage } from './pages/applicant/ApplicantDashboardPage';
import { OpportunitiesPage } from './pages/applicant/OpportunitiesPage';
import { ApplicantProfilePage } from './pages/applicant/ApplicantProfilePage';
import { ApplicantCvPage } from './pages/applicant/ApplicantCvPage';
import { ApplicantApplicationsPage } from './pages/applicant/ApplicantApplicationsPage';
import { CareerAgentPage } from './pages/applicant/CareerAgentPage';
import { AiInterviewPage } from './pages/applicant/AiInterviewPage';

// Social Hub (internal employee network, roles 1-4)
import { SocialFeedPage } from './pages/social/SocialFeedPage';
import { PeoplePage } from './pages/social/PeoplePage';
import { SocialNotificationsPage } from './pages/social/SocialNotificationsPage';
import { MessagesPage } from './pages/social/MessagesPage';
import { SocialProfilePage } from './pages/social/SocialProfilePage';

// Employee Workspace Pages (8 Pages)
import { EmployeeDashboardPage } from './pages/employee/EmployeeDashboardPage';
import { MyProfilePage } from './pages/employee/MyProfilePage';
import { MyAttendancePage } from './pages/employee/MyAttendancePage';
import { MyLeavePage } from './pages/employee/MyLeavePage';
import { MyTrainingPage } from './pages/employee/MyTrainingPage';
import { MyPerformancePage } from './pages/employee/MyPerformancePage';
import { CareerGrowthPage } from './pages/employee/CareerGrowthPage';
import { EmployeeNotificationsPage } from './pages/employee/EmployeeNotificationsPage';

// Manager Workspace Pages (7 Pages)
import { ManagerDashboardPage } from './pages/manager/ManagerDashboardPage';
import { MyTeamPage } from './pages/manager/MyTeamPage';
import { ManagerAttendancePage } from './pages/manager/ManagerAttendancePage';
import { ManagerLeavePage } from './pages/manager/ManagerLeavePage';
import { ManagerPerformancePage } from './pages/manager/ManagerPerformancePage';
import { ManagerInsightsPage } from './pages/manager/ManagerInsightsPage';
import { ManagerNotificationsPage } from './pages/manager/ManagerNotificationsPage';

// HR Workspace Pages (9 Pages)
import { HRDashboardPage } from './pages/hr/HRDashboardPage';
import { EmployeesPage } from './pages/hr/EmployeesPage';
import { Employee360Page } from './pages/hr/Employee360Page';
import { RecruitmentJobsPage } from './pages/hr/RecruitmentJobsPage';
import { CandidatesPage } from './pages/hr/CandidatesPage';
import { HrAgentPage } from './pages/hr/HrAgentPage';
import { AiInterviewAnalyticsPage } from './pages/hr/AiInterviewAnalyticsPage';
import { SocialModerationPage } from './pages/hr/SocialModerationPage';
import { InterviewsPage } from './pages/hr/InterviewsPage';
import { TrainingHubPage } from './pages/hr/TrainingHubPage';
import { HRReportsPage } from './pages/hr/HRReportsPage';
import { HRNotificationsPage } from './pages/hr/HRNotificationsPage';

// Admin Pages (7 Pages)
import { DashboardPage } from './pages/DashboardPage';
import { UsersPage } from './pages/UsersPage';
import { RolesPermissionsPage } from './pages/RolesPermissionsPage';
import { DepartmentsPage } from './pages/DepartmentsPage';
import { PositionsPage } from './pages/PositionsPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { SettingsPage } from './pages/SettingsPage';

interface SmartHRAppProps {
  roleId: number | null;
  accountEmail: string | null;
  onSignOut: () => void;
}

/**
 * Typed as `React.FC` rather than a plain function so it accepts `key`: the
 * render site keys it on the role, and a plain function component's props
 * type does not include React's own reserved props.
 */
const SmartHRApp: React.FC<SmartHRAppProps> = ({
  roleId,
  accountEmail,
  onSignOut,
}) => {
  // Landing page follows the role, so an Employee does not open on a page
  // they cannot use and an Admin does not open on self-service.
  const { t } = useT();
  const [currentPage, setCurrentPage] = useState<PageId>(() => landingPageFor(roleId));
  const [selectedEmployee360Id, setSelectedEmployee360Id] = useState<string>('EMP-0102');

  // The person behind the signed-in account. users stores no name, so this is
  // the employees row whose user_id matches - and that link is nullable, so
  // null here is a legitimate state, not a failure.
  const [identity, setIdentity] = useState<MyEmployeeIdentity | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | undefined>(undefined);
  // Which opportunity the applicant has opened, e.g. "job-3". Undefined is
  // the list view - the same pattern the HR pages use for a selected record.
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | undefined>(
    undefined
  );
  // Which interview the AI Interview page should pre-select when it is opened
  // from My Applications or the dashboard. A preference only: the page still
  // lists the applicant's own interviews from the API and falls back to the
  // first when this one is not among them.
  const [selectedAiInterviewId, setSelectedAiInterviewId] = useState<number | null>(null);
  // Social Hub navigation state. A profile is reached from a post, a comment,
  // the People directory or a conversation header, so the person being viewed
  // travels in state rather than in the PageId - the same pattern
  // `selectedEmployee360Id` already uses. Null means "my own profile".
  const [socialProfileUserId, setSocialProfileUserId] = useState<number | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(
    null
  );

  // System notifications, loaded from PostgreSQL for the signed-in user.
  const [notifications, setNotifications] = useState<SystemNotification[]>([]);

  const { showToast } = useToast();

  const loadNotifications = useCallback(async () => {
    try {
      if (roleId === 5) {
        setNotifications([]);
        return;
      }
      const data = await SmartHRApi.getNotifications();
      setNotifications(data.map(toSystemNotification));
    } catch {
      // Non-fatal: the bell simply stays empty if the call fails.
      setNotifications([]);
    }
  }, [roleId]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  // The person behind the account, for the sidebar and the account menu.
  // An account with no employees row is a legitimate state, so a 404 here
  // just means the shell falls back to showing the email address.
  useEffect(() => {
    let cancelled = false;

    // An Applicant is not staff: /auth/me/employee correctly 404s for them,
    // so the call is skipped rather than fired to fail.
    if (roleId === 5) {
      setIdentity(null);
      return;
    }

    SmartHRApi.getMyEmployee()
      .then((me) => {
        if (!cancelled) setIdentity(me);
      })
      .catch(() => {
        if (!cancelled) setIdentity(null);
      });

    return () => {
      cancelled = true;
    };
  }, [roleId]);

  const handleMarkNotificationRead = async (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );

    try {
      await SmartHRApi.setNotificationRead(Number(id), true);
    } catch {
      // Roll the optimistic update back by re-reading the server state.
      loadNotifications();
    }
  };

  const handleMarkAllNotificationsRead = async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));

    try {
      await SmartHRApi.markAllNotificationsRead();
      showToast(t('quick.toast.notificationsUpdated'), {
        message: t('quick.toast.allMarkedRead'),
        type: 'info',
      });
    } catch {
      loadNotifications();
      showToast(t('quick.toast.notificationsFailed'), {
        message: t('quick.toast.notificationsFailedBody'),
        type: 'error',
      });
    }
  };

  const handleNavigateToEmployee360 = (employeeId: string) => {
    setSelectedEmployee360Id(employeeId);
    setCurrentPage('hr-employee-360');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  /**
   * Every quick action does the same thing: open a page and say so. It used
   * to be a ten-case switch with a hand-written English sentence in each, all
   * of which had to be translated; a map of action -> page says the same in
   * one place and the confirmation is one string naming the page it opened.
   */
  const QUICK_ACTION_PAGES: Record<string, PageId> = {
    'mgr-approve-leave': 'mgr-leave',
    'mgr-conduct-review': 'mgr-performance',
    'mgr-check-attendance': 'mgr-attendance',
    'add-employee': 'hr-employees',
    'post-job': 'hr-jobs',
    'schedule-interview': 'hr-interviews',
    'add-user': 'users',
    'add-department': 'departments',
    'add-position': 'positions',
    'export-audit': 'audit',
  };

  const handleQuickAction = (action: string) => {
    const targetPage = QUICK_ACTION_PAGES[action];
    if (!targetPage) return;

    setCurrentPage(targetPage);
    showToast(t('quick.toast.navigated', { page: t(`page.${targetPage}`) }), {
      type: 'info',
    });
  };

  /**
   * Moving between Social Hub screens.
   *
   * Opening Messages starts on the conversation list rather than on whichever
   * thread was last read, and opening the profile tab shows your own rather
   * than the last colleague you looked at - both are "go to that section",
   * not "go back to what I was doing".
   */
  const navigateSocial = (page: PageId) => {
    if (page === 'soc-messages') setActiveConversationId(null);
    if (page === 'soc-profile') setSocialProfileUserId(null);
    setCurrentPage(page);
  };

  const renderPage = () => {
    // Second line of defence only. Every endpoint behind these pages is
    // guarded server-side, so this stops a confusing half-loaded screen
    // rather than protecting the data.
    if (!canAccessPage(roleId, currentPage)) {
      return (
        <div className="max-w-lg mx-auto mt-16 p-8 rounded-2xl bg-white border border-stone-200 text-center">
          <h2 className="text-lg font-black text-stone-900">{t('access.restricted')}</h2>
          <p className="text-sm text-stone-600 mt-2 leading-relaxed">
            {t('access.restrictedBody', {
              role: roleId ? t(`role.${roleId}`) : t('state.unknown'),
            })}
          </p>
        </div>
      );
    }

    const openSocialProfile = (userId: number) => {
      setSocialProfileUserId(userId);
      setCurrentPage('soc-profile');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const openConversation = (conversationId: number) => {
      setActiveConversationId(conversationId);
      setCurrentPage('soc-messages');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const openAiInterview = (interviewId: number) => {
      setSelectedAiInterviewId(interviewId);
      setCurrentPage('app-ai-interview');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const openOpportunity = (opportunityId: string) => {
      setSelectedOpportunityId(opportunityId);
      setCurrentPage('app-opportunities');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    switch (currentPage) {
      // Applicant Workspace Pages (external job seekers, role 5)
      case 'app-dashboard':
        return (
          <ApplicantDashboardPage
            onNavigate={(page) => setCurrentPage(page)}
            onViewOpportunity={openOpportunity}
            onOpenAiInterview={openAiInterview}
          />
        );
      case 'app-opportunities':
        return (
          <OpportunitiesPage
            selectedOpportunityId={selectedOpportunityId}
            onSelectOpportunity={setSelectedOpportunityId}
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'app-profile':
        return <ApplicantProfilePage />;
      case 'app-cv':
        return <ApplicantCvPage onNavigate={(page) => setCurrentPage(page)} />;
      case 'app-applications':
        return (
          <ApplicantApplicationsPage
            onNavigate={(page) => setCurrentPage(page)}
            onViewOpportunity={openOpportunity}
            onOpenAiInterview={openAiInterview}
          />
        );
      case 'app-agent':
        return <CareerAgentPage onNavigate={(page) => setCurrentPage(page)} />;
      case 'app-ai-interview':
        return (
          <AiInterviewPage
            initialInterviewId={selectedAiInterviewId}
            onNavigate={(page) => setCurrentPage(page)}
          />
        );

      // Social Hub (internal employee network, roles 1-4). Every /social/*
      // endpoint behind these pages is require_staff, so an Applicant reaching
      // one gets a 403 regardless of what `canAccessPage` allows.
      case 'soc-feed':
        return (
          <SocialFeedPage
            onNavigate={navigateSocial}
            onOpenProfile={openSocialProfile}
            onOpenConversation={openConversation}
          />
        );
      case 'soc-people':
        return (
          <PeoplePage
            onNavigate={navigateSocial}
            onOpenProfile={openSocialProfile}
            onOpenConversation={openConversation}
          />
        );
      case 'soc-messages':
        return (
          <MessagesPage
            initialConversationId={activeConversationId}
            onNavigate={navigateSocial}
            onOpenProfile={openSocialProfile}
          />
        );
      case 'soc-profile':
        return (
          <SocialProfilePage
            userId={socialProfileUserId}
            onNavigate={navigateSocial}
            onBack={() => {
              setSocialProfileUserId(null);
              setCurrentPage('soc-people');
            }}
            onOpenProfile={openSocialProfile}
            onOpenConversation={openConversation}
          />
        );
      case 'soc-notifications':
        return (
          <SocialNotificationsPage
            onNavigate={navigateSocial}
            onOpenProfile={openSocialProfile}
            onOpenConversation={openConversation}
          />
        );

      // Employee Workspace Pages (8 Pages)
      case 'emp-dashboard':
        return (
          <EmployeeDashboardPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'emp-profile':
        return (
          <MyProfilePage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'emp-attendance':
        return <MyAttendancePage />;
      case 'emp-leave':
        return <MyLeavePage />;
      case 'emp-training':
        return <MyTrainingPage />;
      case 'emp-performance':
        return <MyPerformancePage />;
      case 'emp-career':
        return (
          <CareerGrowthPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'emp-notifications':
        return (
          <EmployeeNotificationsPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );

      // Manager Workspace Pages (7 Pages)
      case 'mgr-dashboard':
        return (
          <ManagerDashboardPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'mgr-team':
        return (
          <MyTeamPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
      case 'mgr-attendance':
        return <ManagerAttendancePage />;
      case 'mgr-leave':
        return <ManagerLeavePage />;
      case 'mgr-performance':
        return <ManagerPerformancePage />;
      case 'mgr-insights':
        return <ManagerInsightsPage />;
      case 'mgr-notifications':
        return (
          <ManagerNotificationsPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );

      // HR Workspace Pages (9 Pages)
      case 'hr-dashboard':
        return (
          <HRDashboardPage
            onNavigate={(page) => setCurrentPage(page)}
            onViewEmployee360={handleNavigateToEmployee360}
          />
        );
      case 'hr-employees':
        return (
          <EmployeesPage
            onViewEmployee360={handleNavigateToEmployee360}
          />
        );
      case 'hr-employee-360':
        return (
          <Employee360Page
            initialEmployeeId={selectedEmployee360Id}
            onBackToDirectory={() => setCurrentPage('hr-employees')}
          />
        );
      case 'hr-jobs':
        return (
          <RecruitmentJobsPage
            onViewCandidatesForJob={() => {
              setCurrentPage('hr-candidates');
            }}
          />
        );
      case 'hr-candidates':
        return (
          <CandidatesPage
            onScheduleInterview={(candidateId) => {
              setSelectedCandidateId(candidateId);
              setCurrentPage('hr-interviews');
            }}
          />
        );
      case 'hr-ai-interview-analytics':
        // AI Interview Analytics (Phase 11.5.4). Admin and HR only - the hr-
        // prefix keeps it in the HR workspace; GET /ai-interview/analytics 403s
        // everyone else regardless.
        return <AiInterviewAnalyticsPage />;
      case 'hr-ai-agent':
        // The Internal HR Agent. Admin and HR only - `canAccessPage` keeps it
        // out of other workspaces, and POST /hr/agent/chat 403s regardless.
        return <HrAgentPage onNavigate={(page) => setCurrentPage(page)} />;
      case 'hr-social-moderation':
        // Social Hub moderation. An HR-workspace page on purpose: every
        // 'soc-' PageId resolves to the social workspace, which roles 1-4
        // all have, so this one would have been offered to Managers and
        // Employees. The five /social/moderation* routes are
        // require_roles(1, 2) regardless.
        return <SocialModerationPage />;
      case 'hr-interviews':
        return (
          <InterviewsPage
            preselectedCandidateId={selectedCandidateId}
          />
        );
      case 'hr-training':
        return <TrainingHubPage />;
      case 'hr-reports':
        return <HRReportsPage />;
      case 'hr-notifications':
        return (
          <HRNotificationsPage
            onNavigate={(page) => setCurrentPage(page)}
            onSelectEmployee={handleNavigateToEmployee360}
          />
        );

      // Admin Workspace Pages (7 Pages preserved)
      case 'dashboard':
        return (
          <DashboardPage
            onNavigate={(page) => setCurrentPage(page)}
            onQuickAction={handleQuickAction}
          />
        );
      case 'users':
        return <UsersPage />;
      case 'roles':
        return <RolesPermissionsPage />;
      case 'departments':
        return (
          <DepartmentsPage
            onNavigatePositions={() => setCurrentPage('positions')}
          />
        );
      case 'positions':
        return <PositionsPage />;
      case 'audit':
        return <AuditLogsPage />;
      case 'settings':
        return <SettingsPage />;

      default:
        return (
          <ManagerDashboardPage
            onNavigate={(page) => setCurrentPage(page)}
          />
        );
    }
  };

  return (
    <GlobalLayout
      currentPage={currentPage}
      roleId={roleId}
      onNavigate={(page) => {
        setCurrentPage(page);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }}
      notifications={notifications}
      onMarkNotificationRead={handleMarkNotificationRead}
      onMarkAllNotificationsRead={handleMarkAllNotificationsRead}
      onQuickAction={handleQuickAction}
      identity={identity}
      accountEmail={accountEmail}
      onSignOut={onSignOut}
    >
      {renderPage()}
    </GlobalLayout>
  );
};

export default function App() {
  const { t } = useT();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  // Which unauthenticated screen to show. Registration is a real screen rather
  // than a modal because it is the one place in SmartHR a person arrives with
  // no account at all.
  const [showRegister, setShowRegister] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  // Authoritative role comes from /auth/me, which re-reads users.role_id
  // from the database - never from the JWT claim or localStorage.
  const [roleId, setRoleId] = useState<number | null>(null);
  // The account itself (id, email, role_id, is_active) as /auth/me returns it.
  const [account, setAccount] = useState<CurrentUser | null>(null);

  useEffect(() => {
    const validateSession = async () => {
      const token = localStorage.getItem('smarthr_access_token');

      if (!token) {
        setCheckingAuth(false);
        return;
      }

      try {
        const me = await SmartHRApi.getCurrentUser();
        setAccount(me);
        setRoleId(me.role_id);
        setIsAuthenticated(true);
      } catch {
        SmartHRApi.logout();
        setIsAuthenticated(false);
      } finally {
        setCheckingAuth(false);
      }
    };

    validateSession();
  }, []);

  /**
   * Notice when another tab replaces the session.
   *
   * `localStorage` is shared by every tab on this origin, so signing in as a
   * different role in a second tab overwrites `smarthr_access_token` for all
   * of them. Without this listener the first tab keeps its in-memory
   * `roleId` - it goes on rendering the HR workspace - while every request it
   * makes now carries the other account's token. The server refuses those
   * correctly, and the symptom is an HR screen reporting "You do not have
   * permission to perform this action" on an endpoint HR is plainly allowed:
   * the tab is no longer signed in as who it thinks it is.
   *
   * Testing the recruitment workflow end to end means being HR and an
   * Applicant at the same time, so this is the normal way to hit it rather
   * than an edge case.
   *
   * This changes no permission - the boundary is and remains the server's
   * `require_roles`. It only makes the client notice what the server already
   * enforces, instead of showing a confusing refusal.
   */
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      // `key === null` is localStorage.clear() from another tab.
      if (event.key !== null && event.key !== 'smarthr_access_token') return;

      const token = localStorage.getItem('smarthr_access_token');

      if (!token) {
        setAccount(null);
        setRoleId(null);
        setIsAuthenticated(false);
        return;
      }

      // Re-read the authoritative account for whatever token is now stored.
      SmartHRApi.getCurrentUser()
        .then((me) => {
          setAccount(me);
          setRoleId(me.role_id);
          setIsAuthenticated(true);
        })
        .catch(() => {
          SmartHRApi.logout();
          setAccount(null);
          setRoleId(null);
          setIsAuthenticated(false);
        });
    };

    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const handleLogin = async () => {
    try {
      const me = await SmartHRApi.getCurrentUser();
      setAccount(me);
      setRoleId(me.role_id);
    } catch {
      setAccount(null);
      setRoleId(null);
    }
    setIsAuthenticated(true);
  };

  // Clears the stored token and drops back to the sign-in screen. There is no
  // server-side session to end - the JWT simply stops being sent.
  const handleSignOut = () => {
    SmartHRApi.logout();
    setAccount(null);
    setRoleId(null);
    setIsAuthenticated(false);
  };

  if (checkingAuth) {
    return (
      <ToastProvider>
        <div className="min-h-screen flex flex-col items-center justify-center bg-sand-50 px-6">
          <div className="w-12 h-12 rounded-2xl bg-brand-600 text-white font-black text-xl flex items-center justify-center">
            S
          </div>
          <p className="mt-4 text-sm font-bold text-stone-800">SmartHR</p>
          <p className="mt-1 text-2xs text-stone-500">{t('app.restoringSession')}</p>
        </div>
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      {isAuthenticated ? (
        // Keyed on the role so that a session replaced in another tab lands
        // on the new role's own landing page instead of keeping the previous
        // role's `currentPage`. Today the role only ever changes at sign-in
        // and sign-out, which already mount and unmount this tree, so the key
        // is inert except in exactly that case.
        <SmartHRApp
          key={roleId ?? 'none'}
          roleId={roleId}
          accountEmail={account?.email ?? null}
          onSignOut={handleSignOut}
        />
      ) : showRegister ? (
        <ApplicantRegisterPage
          onRegistered={() => setShowRegister(false)}
          onBackToLogin={() => setShowRegister(false)}
        />
      ) : (
        <LoginPage onLogin={handleLogin} onRegister={() => setShowRegister(true)} />
      )}
    </ToastProvider>
  );
}
