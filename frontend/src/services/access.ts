import { PageId } from '../components/layout/Sidebar';

/**
 * Which workspaces and pages each role may reach in the UI.
 *
 * This is a **convenience layer, not the security boundary**. Every endpoint
 * is guarded server-side in app/dependencies.py and the routers, so hiding a
 * nav item here only stops a user wandering into a page that would fail
 * anyway - editing this file grants nobody any data.
 *
 * Role ids are the fixed integers seeded in the database:
 *   1 Admin, 2 HR, 3 Manager, 4 Employee, 5 Applicant
 */

export type Workspace =
  | 'employee'
  | 'social'
  | 'manager'
  | 'hr'
  | 'admin'
  | 'applicant';

export const ROLE_NAMES: Record<number, string> = {
  1: 'Admin',
  2: 'HR',
  3: 'Manager',
  4: 'Employee',
  5: 'Applicant',
};

/**
 * Everyone gets the employee workspace: self-service is about the person, not
 * their privileges, and /auth/me/employee is scoped to the caller regardless
 * of role.
 */
const WORKSPACES_BY_ROLE: Record<number, Workspace[]> = {
  1: ['employee', 'social', 'manager', 'hr', 'admin'],
  2: ['employee', 'social', 'hr'],
  3: ['employee', 'social', 'manager'],
  4: ['employee', 'social'],
  // An Applicant is external: they get the applicant workspace and nothing
  // else, not even the employee self-service one. They are not staff, and the
  // /me endpoints behind those pages resolve an employees row they do not have.
  // The Social Hub is deliberately absent for the same reason - it is the
  // internal employee network, and every /social/* route is require_staff, so
  // an Applicant reaching one gets a 403 whatever this file says.
  5: ['applicant'],
};

export const workspacesFor = (roleId: number | null): Workspace[] =>
  WORKSPACES_BY_ROLE[roleId ?? 0] ?? ['employee'];

export const workspaceOf = (page: PageId): Workspace => {
  if (page.startsWith('app-')) return 'applicant';
  if (page.startsWith('soc-')) return 'social';
  if (page.startsWith('emp-')) return 'employee';
  if (page.startsWith('mgr-')) return 'manager';
  if (page.startsWith('hr-')) return 'hr';
  return 'admin';
};

export const canAccessPage = (roleId: number | null, page: PageId): boolean =>
  workspacesFor(roleId).includes(workspaceOf(page));

/** Where a role lands after signing in. */
export const landingPageFor = (roleId: number | null): PageId => {
  switch (roleId) {
    case 1:
      return 'dashboard';
    case 2:
      return 'hr-dashboard';
    case 3:
      return 'mgr-dashboard';
    case 5:
      return 'app-dashboard';
    default:
      return 'emp-dashboard';
  }
};
