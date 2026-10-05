# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SmartHR — an HR management system split into two independently-run halves in one folder:

- `app/` — FastAPI + SQLAlchemy 2.0 backend against PostgreSQL, served by uvicorn on `127.0.0.1:8000`.
- `frontend/` — React 19 + Vite 6 + Tailwind v4 SPA (TypeScript), dev server on port 3000.

Not a git repository. Schema changes since the initial dump live in `migrations/` and must be applied after a restore (see **Database and schema changes**). There is no test framework, no linter config beyond `tsc`, and no `requirements.txt` — backend dependencies exist only inside the checked-in `venv/`. The `*.zip` files at the root are snapshots of `app/` and `frontend/`; ignore them.

**The AI Interview is being rebuilt from scratch, in phases.** The old implementation (OpenAI Realtime, its own LiveKit worker, sessions/turns/reports tables, a question bank) was deleted and is *not* the code in `app/ai/interview/` - see **AI Interview (rebuild)** for what exists now (Phases 1-9: voice foundation, turn-taking, Question Bank, Job Context, CV Context, Matching Context, Answers & Analysis, Interview Report, workflow controls) and **Removed feature: rollback material** for where the old code went. The `interviews` table and the recruitment interview API are a *different* feature and are very much still here — see **Interview relationships**.

## Commands

Backend (run from the repo root — routers use absolute `app.*` imports, so the root must be the working directory):

```powershell
venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Interactive API docs at http://127.0.0.1:8000/docs.

**Production run profile** (Phase 10; development above is unchanged):

```powershell
$env:SMARTHR_ENV = "production"
venv\Scripts\python.exe -m app.serve                    # backend: uvicorn, reload=False, INFO
venv\Scripts\python.exe -m app.ai.interview.production  # worker: LiveKit 'start --log-level info'
venv\Scripts\python.exe -m scripts.test_production_config   # 74 checks, no model, no LiveKit
```

Both refuse to start unless `SMARTHR_ENV=production`. Production also needs
`SMARTHR_CORS_ORIGINS` (comma-separated https origins; unset in development
is `*` as before), and the worker needs an explicit
`SMARTHR_INTERVIEW_BACKEND_URL` that is `https://` unless it is loopback.
`SMARTHR_BACKEND_HOST` / `SMARTHR_BACKEND_PORT` default to 127.0.0.1:8000 -
TLS is meant to end at a reverse proxy. With `SMARTHR_ENV=production`,
`worker.py` itself refuses `dev`/`console`, DEBUG/TRACE logging and
`--api-key`/`--api-secret` on the command line (`app/ai/interview/production.py`).

If an endpoint unexpectedly returns 404, verify that the server is running
the current application version before investigating route definitions.

Frontend (from `frontend/`):

```powershell
npm install
npm run dev      # vite on port 3000, host 0.0.0.0
npm run lint     # tsc --noEmit — the only check that exists; use it as the test
npm run build
```

## Architecture

### Database and schema changes

- Keep schema changes in ordered SQL files under `migrations/` and update the corresponding models and services in the same change.
- Apply migrations through the approved deployment process; do not document database snapshots, restore state, account inventories, or environment-specific recovery commands here.
- Keep database credentials, local data, and backups in local or managed secret storage, never in this repository.
### Auth and roles

`app/routers/auth.py` owns everything: `POST /auth/login` takes an OAuth2 password form (`username` = email), verifies an argon2 hash via `pwdlib`, and returns a 60-minute HS256 JWT with `sub` = user id and `role_id`. `get_current_user` decodes it and reloads the `User`. `SECRET_KEY` comes from `SMARTHR_SECRET_KEY` (`app/settings.py`, same lookup); with `SMARTHR_ENV=production` the app refuses to start with a key under 32 characters or the old public development key. `scripts/test_core_settings.py` (28 checks, offline) covers both.

Role ids are fixed integers, seeded in the dump and referenced numerically throughout:

| id | role |
|----|------|
| 1 | Admin |
| 2 | HR |
| 3 | Manager |
| 4 | Employee |
| 5 | Applicant (external job seeker) |

Guard an endpoint with `dependencies=[Depends(require_roles(1, 2))]` from `app/dependencies.py`, or take `current_user: User = Depends(require_roles(1, 2))` when the handler needs the caller (for `created_by`, `approved_by`, audit attribution…). `require_roles` re-reads `role_id` **from the database**, not from the JWT claim, so a forged claim does not widen access.

**Every route now requires authentication.** The only exceptions are `GET /` (the health message) and `POST /applicant/register`, which necessarily cannot require a token for an account that does not exist yet. A batch of GETs used to be completely open — `/attendance/`, `/leave-requests/`, `/employee-trainings/`, `/performance-reviews/`, `/candidates/`, `/interviews/`, `/employees/{id}` and the whole of `cvs.py` including its POST — and they are all guarded now. If you add a route, guard it.

The access tiers:

| Tier | Roles | Routes |
|---|---|---|
| Catalogue | any **staff** role (1-4) | `/departments/`, `/positions/`, `/jobs/`, `/trainings/` (GET) |
| Workforce data | 1, 2, 3 | `/attendance/`, `/leave-requests/`, `/employee-trainings/`, `/performance-reviews/`, `/interviews/`, `/employees/roster`, `/dashboard/manager` |
| HR-owned | 1, 2 | `/employees/`, `/candidates/`, `/applications/`, `/cvs/`, `/audit-logs/`, `/dashboard/admin`, `/dashboard/hr`, `/dashboard/reports`, `/users/roles` |
| Admin-only | 1 | all of `/users/` except `/users/roles` |
| Applicant | 5 only | the whole of `/applicant/*`, including the Career Agent |
| HR Agent | 1, 2 | `/hr/agent/*` - the Internal HR Agent |
| Self-service | any **staff** role, scoped to them | the `/me` routes below |

**`require_staff` (roles 1-4) vs `get_current_user`.** A handful of routes used to be guarded with a bare `get_current_user`, meaning "any signed-in user" - which was a complete description of the population until role 5 existed. Adding an *external* role would have silently widened `/departments/`, `/positions/`, `/jobs/`, `/trainings/`, `/employees/{id}`, `/dashboard/employee`, `/ai/chat` and `/ai/status` to people outside the company, so those now take `require_staff` from `app/dependencies.py`. **If you add a route for staff, guard it with `require_staff`, not `get_current_user`** - the latter now includes job seekers. `/notifications/*` is the deliberate exception: it is already scoped to the caller's own rows.

`GET /employees/{id}` is the one hybrid: roles 1/2/3 may read any record, anyone else may read **only their own**, resolved through `resolve_employee()`. That keeps My Profile working for an Employee without letting them walk the directory by id.

### Router conventions

Each file in `app/routers/` is self-contained and follows the same shape: its own `router = APIRouter(prefix=..., tags=...)`, its own duplicated `get_db()` generator, and Pydantic request models defined either inline in the router (most of them) or in `app/schemas.py` (employees only). Routers are registered by hand in `app/main.py` — a new router needs an import plus an `app.include_router(...)` line there.

Endpoints return plain dicts, not response models. `employees.py` shows the pattern for enriched output: `employee_to_dict()` hand-joins department, position, manager, and user rows so the response carries `department_name`, `manager_name`, and `email` alongside the raw ids.

CORS is wide open (`allow_origins=["*"]`, `allow_credentials=False`) — the frontend passes the token as a Bearer header, never a cookie.

### Frontend structure

**No router library.** `App.tsx` renders a `switch` over a `currentPage` state variable typed as `PageId`, the union declared in `components/layout/Sidebar.tsx`. Adding a screen means three edits: extend the `PageId` union, add the sidebar nav entry, and add a `case` in `renderPage()`. Navigation between pages is done by passing `onNavigate`/`onViewEmployee360`-style callbacks down as props.

Pages are grouped by workspace: `pages/applicant/`, `pages/employee/`, `pages/manager/`, `pages/hr/`, and admin pages directly in `pages/`. Shared presentational components live in `components/ui/` (Button, Card, Modal, Toast, KpiCard, Charts…); `ToastProvider`/`useToast` wraps the whole app and is the standard way to surface feedback.

**Mock data vs. live API — this is the main thing to check before touching a page.** Most screens still render from `src/mock/*.ts`. Only these call the real backend through `SmartHRApi`: `LoginPage`, `UsersPage`, `DepartmentsPage`, `PositionsPage`, `RolesPermissionsPage`, `SettingsPage`, `hr/EmployeesPage`, `hr/RecruitmentJobsPage`, `hr/CandidatesPage`, `hr/InterviewsPage`, `manager/ManagerAttendancePage`, `manager/ManagerLeavePage`, `hr/TrainingHubPage`, `manager/ManagerPerformancePage`, `AuditLogsPage`, all four dashboards (`DashboardPage`, `hr/HRDashboardPage`, `manager/ManagerDashboardPage`, `employee/EmployeeDashboardPage`) and `hr/HRReportsPage`, and every notification surface (`App.tsx` bell, `hr/HRNotificationsPage`, `manager/ManagerNotificationsPage`, `employee/EmployeeNotificationsPage`, `employee/EmployeeDashboardPage` preview), `UsersPage`, the role list on `RolesPermissionsPage`, `DepartmentsPage`, and `PositionsPage`. Wiring a mock page up means replacing the mock import with a `SmartHRApi` call — and usually reconciling shapes, because the rich interfaces in `src/types/index.ts` were written against the mocks and are wider than what the backend returns (e.g. `Department` declares `code`, `managerName`, `status`, `headcountBudget`, while `GET /departments/` returns only `id` and `name`).

All HTTP goes through `src/services/api.ts`. `API_BASE_URL` is hardcoded to `http://127.0.0.1:8000`. `apiFetch` attaches `Authorization: Bearer <token>` by default and unwraps FastAPI's `detail` field into the thrown `Error`. The session lives in localStorage under `smarthr_access_token`, `smarthr_user_id`, `smarthr_role_id`; `App.tsx` validates it on mount by calling `/auth/me` and logs out on failure.

The frontend was scaffolded from a Google AI Studio template — hence the stale `README.md`, the `@google/genai` dependency, and the `GEMINI_API_KEY` in `.env.example`. None of that is used by SmartHR code.

## Jobs status values

`jobs.status` is a free-text `varchar(30)`, but the recruitment router constrains writes to four tokens: `open`, `on_hold`, `closed`, `draft`. `app/routers/jobs.py` normalizes aliases (`"On Hold"`, `"paused"`, …) on write and falls back to `draft` when reading an unrecognized legacy value. The React side maps tokens to the display labels; `STATUS_LABELS` in `frontend/src/pages/hr/RecruitmentJobsPage.tsx` is the only place that mapping lives.

## Recruitment stage values

A candidate's pipeline stage is **not** a column on `candidates` - it lives in `applications.status`, so moving a candidate through the funnel is a write to the applications table (`PATCH /applications/{id}/status`), not to the candidate. `app/routers/applications.py` owns the vocabulary: `applied, screening, shortlisted, interview, assessment, offer, hired, rejected`, strict on write and lenient on read, and `candidates.py` imports `normalize_stage`/`read_stage` from it rather than redefining them.

`GET /candidates/` joins `applications` -> `jobs` -> `departments` plus `cvs` and `interviews`, and assembles the dossier timeline from those rows; there is no history table, so the timeline is derived, never stored.

## Interview relationships

`interviews` never references a candidate directly - it hangs off `application_id`, so candidate and job are reached via `applications -> candidates` and `applications -> jobs`. Scheduling an interview therefore requires an existing application row.

`interviewer_id` points at `users`, which carries only an email and a role, so the display name comes from the `employees` row whose `user_id` matches (`describe_user()` in `app/routers/interviews.py`), falling back to the email. `GET /interviews/interviewers` exists because `/users/` is Admin-only and HR needs the picker - it is declared **before** `/{interview_id}` so the literal path wins the route match.

Status tokens: `scheduled, in_progress, completed, cancelled`, same strict-on-write / lenient-on-read pattern as jobs and applications.

## Attendance & leave status casing

Unlike jobs / applications / interviews, which use lowercase tokens, `attendance.status` and `leave_requests.status` hold **Title Case** values in this database (`Present`, `Late`, `Pending`, `Approved`). The routers normalize to Title Case to match, so existing rows are never rewritten. Check the data before assuming a casing convention for a new table.

`leave_requests.approved_by` is the only decision-maker column, so `apply_decision()` in `app/routers/leave_requests.py` sets it to the acting user for both `Approved` and `Rejected`, and clears it back to NULL when a request returns to `Pending`.

Derived, never stored: attendance `worked_hours` (check_out - check_in), leave `duration_days` (inclusive date span), and leave `overlapping_count` (other pending/approved requests intersecting the range).

`GET /employees/roster` is a narrow identity-only list allowed to roles 1/2/3, because the full `/employees/` list is Admin+HR only and Managers still need names for the attendance and leave pickers. Like `/interviews/interviewers`, it is declared **before** `/{employee_id}`.

## Training modules

`hr/TrainingHubPage` hosts **both** training modules in two tabs: the Course Catalog is the `trainings` table, and Employee Progress Tracking is `employee_trainings`. Both tables started empty, so lowercase status tokens were adopted (matching the `employee_trainings.status` column default `'assigned'`): `assigned, in_progress, completed, cancelled`.

`employee_trainings` has no progress or score column. `started_at` / `completed_at` are the only progress columns, and `apply_status()` in `app/routers/employee_trainings.py` maintains them from the status transition rather than accepting them from the client - moving to `in_progress` stamps `started_at`, `completed` stamps `completed_at`, and `assigned`/`cancelled` clears both.

Course counters (`enrolled_count`, `completed_count`, `completion_rate`) are derived in `training_to_dict()` from the assignment rows; the `trainings` table stores no counters, so the page re-reads `/trainings/` after any assignment change.

`POST` and `PUT` on `/employee-trainings/` return **409** if the same employee is already enrolled in the same training - there is no unique constraint on the table, so the guard lives in the router.

## Performance review rating constraint

`performance_reviews.rating` is an **INTEGER** carrying a database CHECK constraint, `performance_reviews_rating_check: CHECK (rating >= 1 AND rating <= 5)`. `validate_rating()` in `app/routers/performance_reviews.py` mirrors it so the API returns 422 rather than letting the insert fail with an IntegrityError, and the UI picker offers only the five whole values. Fractional scores (4.8, 4.5, ...) cannot be stored.

`reviewer_id` is a FK to **users**, not `employees` - the same asymmetry as `interviews.interviewer_id`. `performance_reviews.py` imports `describe_user()` from `app/routers/interviews.py` to resolve a user to an employee-backed display name, and exposes `GET /performance-reviews/reviewers` (declared before `/{review_id}`) because `/users/` is Admin-only.

## Notifications

`notifications` rows belong to exactly one user (`user_id` FK to `users`, NOT NULL), so `GET /notifications/` is **scoped to the caller by default**. `?scope=all` returns the whole table but is refused with 403 for anyone who is not Admin or HR. `is_read` is the real read/unread flag - there is no separate "dismissed" column, so the HR page's dismiss action marks the row read and hides it locally. There is no DELETE endpoint.

`/notifications/recipients` and `/notifications/read-all` are both declared **before** `/{notification_id}` so the literal paths win the route match.

Four different UI shapes render the same table - `SystemNotification` (bell + HR page), `ManagerNotificationItem`, and `EmployeeNotificationItem`. Rather than rewriting each page, `frontend/src/services/notificationAdapters.ts` maps a `NotificationRecord` into each one. The optional navigation hints on those shapes (`linkPage`, `actionType`, `targetPage`) have no column and are deliberately left undefined.

## Users, roles and password handling

`users` stores no name - the person's first/last name, department and position come from the `employees` row whose `user_id` matches, so an account with no linked employee legitimately shows blanks. `password_hash` is **never** returned by any endpoint; `user_to_dict()` omits it, and passwords are hashed with the same `pwdlib` `password_hash` instance the login flow verifies against (Argon2id). Update accepts an optional `password` and only re-hashes when a non-empty value is sent.

Administrative lockout protections are implemented in `app/routers/users.py`; keep account-specific details in private operational notes.

`users.email` is UNIQUE, surfaced as 409 rather than an IntegrityError. **Eight** tables hold a FK to `users`, so DELETE first counts references and returns **409** listing them, recommending deactivation instead. `candidates` is the eighth, added with the Applicant feature; without it in `count_references()` a job seeker's account failed the delete as a raw IntegrityError instead of that 409.

**Creating or promoting a role 5 account also creates its applicant profile.** `POST /users/` and `PUT /users/{id}` call `ensure_applicant_profile()`, which delegates to `link_candidate_profile()` in `app/services/applicant_service.py` - the same function registration uses. `UserCreate` therefore takes an optional `full_name`, meaningful only for role 5: `users` stores no name but `candidates.first_name`/`last_name` are NOT NULL, so without one the name is derived from the email address instead. Both calls are no-ops for staff roles. A role change *away* from 5 deliberately leaves the candidates row linked - unlinking would orphan their applications, CVs and interviews, and RBAC already keeps a non-applicant out of `/applicant/*`.

**There is no permissions table.** `roles` holds only `(id, name)`, and `roles.id` has no default/identity. So role *assignment* is real (`users.role_id`), but the permission matrix on `RolesPermissionsPage` is session-only and says so in its save toast.

## Identity and self-service

`app/identity.py` holds `resolve_employee(user, db)` and `employee_identity(employee, db)`. It imports **only** `app/models.py` on purpose: `dependencies.py` imports `get_current_user` from `routers/auth.py`, so anything the auth router needs must sit outside that chain or it is an import cycle. `app/audit.py` exists for the same reason.

`users` stores no name, department or position — the person is the `employees` row whose `user_id` matches, and that column is **nullable**. An account with no employee row is a legitimate state, not an error:

- `GET /auth/me` returns the **account** (id, email, role_id, is_active).
- `GET /auth/me/employee` returns the **person**, enriched with department, position, manager, email and role name. It returns **404** with an explanatory detail when the account is unlinked.
- `get_current_employee` in `app/dependencies.py` is the dependency every self-service route uses. It 404s the same way.

**The `/me` routes** — all scoped through `get_current_employee`, all declared **before** the matching `/{id}` route so the literal path wins:

| Route | Notes |
|---|---|
| `GET /attendance/me` | the caller's own attendance rows |
| `GET /leave-requests/me` | the caller's own requests |
| `POST /leave-requests/me` | takes `MyLeaveRequestCreate`, which has **no `employee_id` and no `status`** — the employee comes from the JWT and the status is forced to `Pending`, so a caller can neither file for somebody else nor self-approve |
| `GET /employee-trainings/me` | the caller's own assignments |
| `GET /performance-reviews/me` | the caller's own reviews |

Because the employee id never crosses the wire, widening the scope from the client is not possible — there is no parameter to tamper with.

Frontend: `src/services/access.ts` maps role → workspaces (`workspacesFor`, `canAccessPage`, `landingPageFor`). `App.tsx` reads the authoritative `role_id` from `/auth/me` (never from localStorage or the JWT), picks the landing page from it, refuses to render a page outside the role's workspaces, and passes `roleId` to `GlobalLayout` → `Sidebar`, which only offers the workspace switcher buttons that role may use. **This is convenience, not security** — the guards above are the boundary, and editing `access.ts` grants nobody any data.

`employee/MyAttendancePage`, `MyLeavePage` and `MyTrainingPage` read the `/me` routes. Things their mock versions showed that the schema cannot support, and which were therefore dropped: work mode, shift windows and a monthly calendar (attendance stores date/check_in/check_out/status only); leave entitlement and balances (no such table — only days taken are reported); and course progress percentage, modules, score, category, due date and instructor (`employee_trainings` records status plus `started_at`/`completed_at`, nothing more). Employees cannot clock themselves in either — `POST /attendance/` is roles 1/2/3 — so the page says so rather than offering a button that 403s.

## Dashboards & reports

`app/routers/dashboard.py` is the only **read-only aggregation** router: `GET /dashboard/admin`, `/hr`, `/manager`, `/employee` and `/reports`. Nothing there writes, and **no column was added for reporting** - every figure is counted or averaged from the existing tables on each request, so there is nothing to keep in sync.

Guards: `/admin`, `/hr` and `/reports` are `require_roles(1, 2)`; `/manager` is `require_roles(1, 2, 3)`; `/employee` is plain `get_current_user` so any signed-in role reaches it. `/manager` and `/employee` are additionally **scoped to the caller** - both call `resolve_employee()`, which finds the `employees` row whose `user_id` matches the JWT user. `/manager` then reads the team as `employees.manager_id == that row`, so two callers genuinely get different payloads.

An account with no `employees` row is normal (`users` stores no name and the link is nullable), so both endpoints return `is_linked: false` with truthful zeros rather than 404, and the pages render an explanatory panel instead of bare zeros.

**Two things the schema cannot answer, declared rather than guessed:**

- **Work mode** (remote / hybrid / on-site) - `employees` has no work-mode, location or workplace column. Payloads carry `work_mode_available: false, work_mode: null`, and the three pages that used to show it now show attendance instead.
- **Turnover / retention / exits** - there is no termination or exit date anywhere, and `employment_status` only ever holds `'active'`. `/reports` carries `turnover_available: false`, and `headcount.history` is a **cumulative hire curve** (`exits_tracked: false`), not a net headcount series. Do not present it as one.

Also unavailable and handled the same way: leave **entitlement/balance** (no such table - only days actually taken are reported, `entitlement_available: false`), career ladder / promotion readiness, and a skills matrix. The employee dashboard's career and skills cards were replaced with `performance_reviews` and removed respectively.

Percentages all go through `pct()`, which returns `0.0` on an empty dataset, so every rate is safe on a fresh database. Chart colours come from a cycled `PALETTE` by index - presentation, not stored data.

Frontend: `DashboardPage` (admin), `hr/HRDashboardPage`, `manager/ManagerDashboardPage`, `employee/EmployeeDashboardPage` and `hr/HRReportsPage` each read exactly one endpoint. `src/mock/dashboard.ts` and `src/mock/notifications.ts` were deleted, and `hrReportsData`, `managerActivityStream`, `managerAttentionCenterItems`, `initialManagerLeaves` and `initialEmployeeAttentionItems` were dropped from the remaining mock files. The other `src/mock/*` exports are still live for the pages listed below.

Attention Center items on every dashboard are **built from real pending records** (`build_attention_items()`): pending leave, interviews in the next 7 days, applications stuck at intake, open jobs with no applicants, employees with no user account, `LOGIN_FAILED` rows in the past week, and unfinished training. Nothing is emitted unless the rows exist, so a clean database yields an empty list. There is no dismissed column, so "acknowledge" hides an item for the session only and it returns on reload.

## Audit trail

`audit_logs` holds exactly six columns: **(id, user_id, action, entity_type, entity_id, timestamp)**. There is **no `details`, `ip_address`, `status` or `metadata` column** - the original `AuditLogsPage` mock had all four, and they were dropped rather than added to the schema. `timestamp` defaults to `CURRENT_TIMESTAMP`; `user_id` is a nullable FK to `users` (nullable so a failed sign-in against an unknown address can still be recorded).

`app/audit.py` holds the writer, `record_audit(db, user, action, entity_type, entity_id)`, plus the `ACTION_*` / `ENTITY_*` vocabularies. It lives **outside `app/routers/`** on purpose: nearly every router calls it, and `app/routers/audit_logs.py` imports `describe_user()` from `app/routers/interviews.py`, so putting the writer in the router would be an import cycle.

`record_audit()` is best-effort - it swallows its own exception and rolls back, because the trail is secondary to the write it describes. **Call it after the business `db.commit()`**, never before. Note that its own `commit()` expires the session, so anything read after it is re-loaded; for DELETE endpoints capture the id in a local before `db.delete()`.

Action tokens written (`action` is varchar(100), free text, but only these are emitted): `CREATE, UPDATE, DELETE, APPROVE, REJECT, STATUS_CHANGE, ASSIGN, ACTIVATE, DEACTIVATE, LOGIN, LOGIN_FAILED, EXPORT`. The frontend folds these onto the seven-value `AuditActionType` the `ActionTypeBadge` renders via `ACTION_CATEGORY` - that map is duplicated in `AuditLogsPage.tsx` and `DashboardPage.tsx` and the two must stay in step.

Which endpoints write a row: employees (C/U/D), jobs (C/U/status), candidates (C/U), applications (C/status), interviews (C/U/status), attendance (C/U/status), leave requests (C/U, and the decision itself as `APPROVE`/`REJECT` via `DECISION_ACTIONS`), trainings (C/U), employee-trainings (`ASSIGN`/U/status), performance reviews (C/U), users (C/U/D plus `ACTIVATE`/`DEACTIVATE`), departments (C/U/D), positions (C/U/D), and `auth.py` login (`LOGIN`, and `LOGIN_FAILED` on all three rejection paths).

`employees.py` create/update/delete and `users.py` create had no named `current_user` - their guards were bare `dependencies=[...]` - so a `current_user: User = Depends(get_current_user)` parameter was added. That adds no new auth requirement beyond the guard already in place.

Reads are **Admin+HR** (`require_roles(1, 2)`); `GET /audit-logs/` was previously unguarded. It is capped (`limit` default 500, max 5000) with `offset`, plus optional `action` / `entity_type` filters, newest first.

The trail is **append-only**: there is no update or delete endpoint. `POST /audit-logs/` exists but only accepts `EXPORT` (`CLIENT_RECORDABLE_ACTIONS`) - everything else returns 422, because rows are meant to be generated by the action they describe. It always takes `user_id` from the JWT and never from the request body.

`description` and the `user` block on a read are **derived, never stored**: `describe_event()` composes a sentence from action + entity_type + entity_id, and `describe_user()` resolves `user_id` to an employee-backed display name (falling back to the email, and to `"System"` when `user_id` is null).

## Departments & positions

Both tables are tiny: `departments` is **(id, name)** with a UNIQUE name, `positions` is **(id, title, department_id)** with department_id NOT NULL. Nothing else the pages show is stored - employee/position/job counts are counted from the referencing tables inside `department_to_dict()` and `position_to_dict()` on every read.

Four FKs point at these tables: `positions.department_id`, `employees.department_id`, `employees.position_id`, `jobs.department_id`. Both DELETE endpoints count references first and return **409** listing them rather than attempting a delete that Postgres would reject. Duplicate department names return 409 (real UNIQUE constraint); duplicate position titles within one department also return 409, which is a router-level guard - the table has no such constraint.

## TypeScript status

`npm run lint` (`tsc --noEmit`) is at **0 errors**. It got there by typing the `SmartHRApi` methods (`apiFetch<T>` has no default for `T`, so an untyped call returns `unknown`) and by adding backend-shaped `*Record`/`*Payload` types alongside the wider mock-shaped interfaces in `src/types/index.ts`. Keep new service methods generic-annotated or the count starts climbing again.

`tsconfig.json` does **not** set `strict`, so this is a non-strict zero. Turning on `strictNullChecks` would surface a fresh batch across the still-mock-shaped pages.

`npm run build` (`vite build`) uses esbuild and does not typecheck, so it passes regardless - run `tsc --noEmit` separately.

## Testing and verification

There is no test framework and no `httpx` in the venv, so `TestClient` is
unavailable. Every suite is a plain script driven with stdlib `urllib` against
a **running server** it usually launches itself, which is a truer end-to-end
test anyway: each request goes through real JWT authentication, the real
`require_roles` guard re-reading the role from `users`, and the real database.

```powershell
venv\Scripts\python.exe -m scripts.test_social_hub          # 154 checks, own server on 8041
venv\Scripts\python.exe -m scripts.test_social_moderation   # 116 checks, no network
venv\Scripts\python.exe -m scripts.test_social_moderation --live   # + the real model
venv\Scripts\python.exe -m scripts.test_celebration_agents  # 118 checks, offline
venv\Scripts\python.exe -m scripts.test_celebration_scheduler  # 59 checks, offline
venv\Scripts\python.exe -m scripts.test_celebration_occasions  # 71 checks, six occasions + employee API (own server on 8048)
cd frontend; npx tsc --noEmit                                 # the only static check
cd frontend; npx tsx scripts/check-social-access.ts           # role -> page map
```

`scripts/test_helpers.py` holds the shared HTTP and account helpers - `request`,
`login`, `register_applicant`, `ensure_staff_account`, `BASE`, `PASSWORD` - and
is imported by the suites rather than copied, so there is one definition of how
a test signs in. The `@smarthr.test` fixture accounts it creates are **left in
place**: `users` is referenced by eight tables including `audit_logs`, so
deleting them afterwards would mean deleting a real audit trail.

Suites that need a language model replace `provider.get_provider` or pass an
explicit `LlmSettings`, never an empty environment variable - `_setting` treats
an empty value as absent and falls through to `.env`, which would re-read the
real key.

## Localization: English + Arabic (RTL)

The whole frontend is bilingual. There is **no i18n dependency** - `src/i18n/`
is a React context, a flat dictionary and about a hundred lines, matching the
judgement that keeps `app/ai/provider.py` on `urllib`.

```
src/i18n/
  types.ts            Locale, Translation {en, ar} - BOTH required
  LocaleProvider.tsx  the provider, useT(), <html lang/dir>, localStorage
  LanguageSwitcher.tsx  English / العربية, compact and full variants
  format.ts           locale-aware dates/numbers + documentLocale()
  dictionaries/       eleven files, ~2,400 keys, spread into one flat map
```

**`Translation` requires both `en` and `ar`**, so a half-translated entry is a
`tsc` error rather than a blank cell in production. `t('key')` returns the
**key itself** when one is missing (and warns once in dev): a missing string
shows up on screen as `hr.candidates.title`, which gets noticed, where a
prettified guess would not. `t('key', { name })` fills `{name}` placeholders.

`LocaleProvider` is mounted in **`main.tsx`, outside `<App />`**. That is not
cosmetic: the switcher has to work on the sign-in screen before a session
exists, and signing in replaces the whole authenticated tree, which would reset
a provider mounted below it. Because the provider sits above `App`, changing
language re-renders but never remounts - the session survives, which is
asserted in the test below.

The stored locale is read **synchronously in `useState`'s initialiser**, not in
an effect, so an Arabic user never sees a frame of English sliding from LTR to
RTL.

### RTL is logical CSS, not a mirrored stylesheet

`LocaleProvider` sets `lang`, `dir` and `data-locale` on `<html>`. Everything
else follows from `dir`, because the components use **logical** Tailwind
utilities throughout - `ms-*`, `me-*`, `ps-*`, `pe-*`, `text-start`,
`text-end`, `start-*`, `end-*`, `border-s`, `border-e`, `rounded-ss/se/es/ee`.
Tailwind v4 resolves those against the document direction, so there is no
per-component `isRtl ? … : …`. **Use logical utilities in new code**; a
`ml-2` or a `text-left` is a bug that only shows up in Arabic.

Three things logical properties cannot express live in `src/index.css`:

* **the Arabic face** - IBM Plex Sans Arabic, applied only under `:lang(ar)`
  and listed *after* Plus Jakarta Sans so Latin runs inside Arabic text (an
  email, a job title from the database) keep the Latin face;
* **`uppercase` / `tracking-wider` are neutralised for Arabic** - Arabic has
  no capitals and letter-spacing breaks its cursive joins;
* **mirrored transforms** - the off-canvas sidebar's `-translate-x-full`, and
  `[dir=rtl] [data-flip-rtl] { scale: -1 1 }`.

`data-flip-rtl` is **opt-in per icon**, and that is the point: chevrons and
arrows that mean forward/back/next/previous are marked; clocks, users, warning
triangles and the logo are not. Blanket-flipping every icon is the classic RTL
mistake.

### What is translated, and what deliberately is not

Translated: every user-facing label, heading, empty state, loading state,
error, toast, confirmation, table header, filter, placeholder, button, status
label, form label, breadcrumb and tooltip, across all five workspaces plus
login, registration, the AI assistant, both agents, CV analysis and matching.

**Not** translated, on purpose:

* **database values** - candidate and employee names, emails, CV text, job
  titles, department names, providers. Only the labels *around* them.
* **AI output** - `/ai/chat`, `/applicant/agent/chat` and `/hr/agent/chat`
  responses are rendered verbatim. The model already answers in the language it
  is asked in; re-translating it in the browser would fabricate a second
  reading of it.
* **status tokens as values** - `applications.status`, `jobs.status`,
  `attendance.status` and friends stay English in state, in filters and in the
  CSV exports; the token is translated only where it renders, through
  `status.*` keys (`t(\`status.job.${token}\`)`). Translating the value would
  break every comparison.
* **identifiers shown as provenance** - `employees.manager_id` under a KPI is
  the name of a real column.

`leave_requests.leave_type` is free text, so `leaveTypeLabel()` translates the
four known values and shows anything else exactly as stored, rather than
rendering a missing key.

### Numbers and dates

`format.ts` pins Arabic to **`ar-u-nu-latn`** - Arabic month names, Western
digits. HR data sits beside Latin-script emails and ids, and mixing numeral
systems down one column is harder to scan. Changing `ARABIC_LOCALE` to `'ar'`
is the whole change if a deployment wants Arabic-Indic numerals, which is why
nothing calls `toLocaleDateString` inline. `documentLocale()` reads the choice
back off `<html lang>` for the handful of non-React modules that format dates
(`services/notificationAdapters.ts`).

### Adding a string

1. add the key to the right file in `dictionaries/` with **both** languages;
2. use it as `t('your.key')`;
3. `npx tsc --noEmit` catches a missing `ar`; the key rendering on screen
   catches a typo.

No key should be defined and unused - the dictionary was pruned of ~500
speculative entries for exactly that reason. A dictionary full of plausible
wrong answers (`admin.audit.title` beside `audit.title`) is worse than a
smaller correct one.

## AI Assistant

`app/ai/` is the assistant; `app/routers/ai.py` is its only entry point. It owns no
tables and queries nothing directly — every answer is the output of a **tool**, and
tools go through the same models and the same role rules as the REST endpoints.

```
POST /ai/chat -> app/ai/assistant.py -> app/ai/provider.py (pick a tool)
                                     -> app/ai/tools.py    (authorise + run)
                                     -> app/models.py      -> PostgreSQL
                                     -> app/ai/provider.py (phrase the result)
```

`app/ai/` lives outside `app/routers/` for the usual reason (`audit.py`, `identity.py`):
`tools.py` imports `read_status`/`duration_days` from `routers/leave_requests.py`
rather than redefining the status vocabulary, so the dependency must point one way.

**The model chooses; it never authorises.** `tools_for_role()` builds the tool list
from the caller's role so a model is never shown a tool the caller cannot use, and
`run_tool()` re-reads `role_id` **from `users`** before the handler runs — the JWT
claim is not consulted, exactly as `require_roles` behaves. A tool asked for out of
role returns `error_code: "forbidden"` with `data: None`.

`ToolSpec` carries `allowed_roles` and a `scope` (`self` / `team` / `organisation`)
which states what a handler must filter on. The one tool registered so far:

| tool | roles | scope | reads |
|---|---|---|---|
| `get_my_leave` | 1, 2, 3, 4 | `self` | `leave_requests` for the caller's own `employees` row |
| `parse_cv` | 1, 2 | `organisation` | a stored `cvs` row, re-parsed through `cv_service` |
| `search_hr_policies` | 1, 2, 3, 4 | `knowledge` | indexed HR policy documents (RAG) |

Eight more tools exist for role 5 only - the Career Agent's - and are listed under **AI Career Agent** below. Roles 1-4 are never offered them and role 5 is never offered these. Ten more exist for roles 1-2 only - the Internal HR Agent's - under **Internal HR Agent**. Twenty-one tools in total.

`get_my_leave` resolves the employee with `resolve_employee()` from the JWT, so — like
`GET /leave-requests/me` — **no employee id crosses the wire** and there is no argument
a caller or a model could change to read someone else's leave. It reports days
requested and days approved and sets `entitlement_available: false`: there is no
entitlement table, so a remaining balance is not derivable and is never implied.

**Diagnosing "No language model is configured":** run `python -m app.ai.check`
from the repo root. It prints which provider, model and endpoint are in effect
and *where each value came from* (environment variable vs `.env`), and when a
key is present it makes one real minimal request so a wrong key, a wrong
provider name and a blocked network are told apart in one command. It never
prints the key. Exit 0 means the provider answered.

**LLM configuration precedence.** `app/ai/config.py` reads each value through
`_setting()`: a real exported environment variable first, then `.env` at the
repository root, with an **empty value treated as absent**. It deliberately does
*not* use `load_dotenv`, and that is worth not undoing — `load_dotenv` writes the
file into `os.environ` and will not override a variable that already exists, so
the shipped `.env` line `SMARTHR_LLM_API_KEY=` would load as an empty string and
then permanently shadow the key somebody types in afterwards. Reading the file
into a separate dict (cached on its mtime/size) keeps the expected precedence and
means editing `.env` takes effect on the **next request, with no restart** — which
is how a key is normally added to a server that is already running.

**LLM configuration is environment-only** (`app/ai/config.py`, `.env.example`):
`SMARTHR_LLM_PROVIDER` (`anthropic` | `openai`), `SMARTHR_LLM_API_KEY` (the provider's
own `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is accepted too), plus optional
`SMARTHR_LLM_MODEL`, `SMARTHR_LLM_BASE_URL`, `SMARTHR_LLM_MAX_TOKENS`,
`SMARTHR_LLM_TIMEOUT`. Settings are re-read per request, so adding a key needs no
restart. No key ever reaches the browser — the frontend only calls `/ai/chat`.

**With no key configured the assistant still answers.** It resolves the intent by
keyword (`INTENT_KEYWORDS`, English and Arabic), runs the real tool, and renders the
real figures, flagged `generated_by: "tool"` with a `notice` saying a model is
pending configuration. The same path catches an `LlmError`, so an unreachable model
degrades to real data rather than to nothing. Nothing is ever fabricated: every
number in every reply came out of a tool result.

HTTP to the provider uses `urllib` — the venv has no HTTP client and two POSTs do not
justify a dependency. There is no LangChain, no RAG and no agent framework.

Frontend: `components/ai/AiAssistant.tsx`, mounted once in `GlobalLayout` so it is on
every authenticated page. It posts only `{message, history}`; the panel shows which
tool answered and whether a model phrased it, so a reply is auditable rather than
taken on trust.

## AI CV analysis

`POST /cvs/upload` takes a PDF or DOCX, stores it, extracts its text and returns
structured candidate information. The pipeline has one implementation, in
`app/services/cv_service.py`, and two entry points — the REST router and the
`parse_cv` MCP tool both call `analyse_cv_bytes()`.

```
app/ai/cv_extraction.py   file bytes -> plain text   (pypdf / python-docx)
app/ai/cv_parser.py       text -> ParsedCv           (LLM tool call -> Pydantic)
app/cv_storage.py         bytes -> uploads/cvs/...   (generated filename)
app/services/cv_service.py  the pipeline the router and the MCP tool share
```

Extraction and AI are deliberately separate: one knows file formats and nothing
about models, the other knows models and nothing about file formats, and only a
string crosses between them. **The file is never sent to the model** — only the
extracted text, which is asserted in the tests.

File type comes from the **signature** (`%PDF-`, `PK`), not the extension,
so a renamed `.exe` is refused. Limits: 5 MB, 40 000 characters, and a minimum of
120 extracted characters — below that the upload is rejected as `no_text_layer`,
which is what a scanned image-only CV produces. Other codes: `unsupported_type`,
`empty_file`, `file_too_large`, `corrupt_file`, `encrypted_file`. All map to 422
except `file_too_large`, which is 413.

Stored files get a **generated** name (`uploads/cvs/<timestamp>-<random>.pdf`);
the client's name is sanitised and kept only in `cvs.file_name` for display. That
closes path traversal and name collisions at once. Nothing is served from that
directory and nothing is executed.

`cv_parser.py` asks the model to return the result **by calling a tool** whose
parameters are `CV_SCHEMA` — that is how both Anthropic and OpenAI express "reply
in exactly this shape". **The response is never trusted**: it goes through
`validate_parsed_cv()`, which is Pydantic (`ParsedCv` and the `CvExperience` /
`CvEducation` / `CvCertification` / `CvLanguage` row models). Validation is
lenient about *shape* and strict about *content* — a model that returns
`"Python, SQL"` where a list belongs, or `["AWS Certified"]` where objects
belong, is coerced by `mode="before"` validators rather than rejected, because
that is a formatting slip; a payload that is not an object at all raises
`CvParseError("invalid_structure")` and nothing is shown or stored. `pruned()`
then drops rows the model emitted entirely blank, so an empty experience card
never implies a job the CV does not mention.

Structured fields worth knowing: `experience[].technologies` is per-role (the
signal a future matcher wants), `certifications` are `{name, issuer, date}` and
`languages` are `{language, proficiency}` — with proficiency null unless the CV
states one. The prompt's central rule is that every value must be copied from the
document or left null; it also forbids evaluating, ranking or recommending the
candidate, and forbids inferring sensitive characteristics.

**What is persisted.** `cvs` has five columns — (id, candidate_id, file_name,
file_path, uploaded_at) — and none of them hold text or parsed fields. The schema
was not changed to add any, so the structured result is returned to the caller
and re-derived on request (`POST /cvs/{cv_id}/analyse` re-reads the stored file).
The one exception is contact detail: `candidates` already has `phone` and
`location`, so those two extracted values have an existing home. They are written
**only** through `POST /cvs/{cv_id}/apply-to-candidate`, from values a recruiter
reviewed and submitted — nothing the model produced reaches the database on its
own. Lengths are checked against the real columns (varchar(30) / varchar(150)) so
an over-long value is a 422 rather than a driver error. Every response carries a
`persistence` block saying all of this outright.

`cvs.candidate_id` is NOT NULL, so an upload always targets an existing
candidate; this endpoint never creates one — that stays with the Candidates
workflow, which owns the duplicate rules.

Guard: `require_roles(1, 2)` — Admin and HR, on all five CV routes. Manager and
Employee get 403, and a forged role claim is ignored because the role is re-read
from `users`. Each upload writes an audit row (`CREATE` / `CV`); applying details
to a candidate writes `UPDATE` / `Candidate`.

With no LLM key configured the upload still succeeds and the response carries
`analysis_error_code: "llm_not_configured"` plus `contact_found_in_text` — an
email and phone found by literal regex search of the extracted text, labelled in
the UI as "Found in the document text (no AI)". That is a search result, not
model output, and every other field stays empty rather than being guessed.

**Privacy:** nothing in the CV path logs CV text, names, emails, phone numbers or
any extracted value — the log lines carry counts, file types and error codes
only. A Pydantic validation failure reports field *names*, never values, so an
error message cannot become a leak.

**Extending to CV → job matching** (the next feature): `ParsedCv` is the hand-off
point. Add `app/ai/cv_matching.py` with its own schema, call it with the
`ParsedCv` this module returns plus the `Job` row; nothing in extraction or
parsing changes.

Frontend: `components/ai/CvAnalysisModal.tsx`, opened per candidate from the
Resume / CV column of `hr/CandidatesPage`. A field the CV did not state renders as
"Not stated in the CV" — never as an empty string or a plausible guess. The panel
leads with an "Extracted by AI — please review" notice and ends with the
`ReviewAndApply` block, which is the only route from analysis to the database.
`apiFetch` drops its JSON content type when the body is `FormData`, so the
browser can set the multipart boundary.

## RAG: HR policy documents

The assistant answers two different kinds of question, and the difference
matters: **MCP tools read the database** (what a person actually did), **RAG
reads documents** (what the rules say). RAG did not replace MCP - it is another
tool behind it.

```
knowledge/demo/*.md          the corpus (demo policies; company/ is for real ones)
  -> app/rag/service.py      ingest: read -> chunk -> embed -> store
  -> app/rag/chunking.py     paragraphs packed to ~900 chars, 150 overlap
  -> app/rag/embeddings.py   text -> vector
  -> app/rag/store.py        rag_index/index.json
                                 |
POST /ai/chat -> MCP -> search_hr_policies -> service.search_policies()
```

Index with `python -m app.rag.ingest`. Re-run after editing any document or
changing the embedding backend; `/ai/status` reports `knowledge_base`.

**Re-indexing needs a backend restart.** Unlike `.env`, which is re-read per
request, `VectorStore._index` is cached in memory for the life of the process
and only dropped by `invalidate()`. A running server keeps serving the old
index - and if the backend changed, every search returns `backend_mismatch`
until it is restarted.

**`knowledge/demo/` vs `knowledge/company/`.** The folder is what marks a
document, not a header, so a file cannot be mislabelled by forgetting one.
Everything under `demo/` is flagged `is_demo: true`, cited as "DEMO SmartHR HR
Policy - ..." and announced as demo content in the answer. `company/` is empty
on purpose. Replacing demo with real means moving files and re-running ingest -
no code change.

**Embeddings are not the LLM, and Anthropic cannot supply them.** Anthropic has
no embeddings endpoint, so `app/ai/provider.py` cannot be reused here. With an
OpenAI key (`OPENAI_API_KEY`, honoured even when the chat provider is
Anthropic) `text-embedding-3-small` gives real semantic search. Without one,
`LexicalEmbeddings` runs locally: an explicit vocabulary with IDF weighting.
`describe()` says which one answered and that reaches the UI.

Three things in the lexical backend exist because retrieval was measurably
broken without them, and removing any one of them breaks it again:

* **An explicit vocabulary, not feature hashing.** Hashing into 2**18 buckets
  still collided: `"late"` and `"30"` shared a bucket, so "what happens if I am
  late?" returned the onboarding section "First 30 days". A corpus this size
  does not need hashing.
* **IDF weighting.** Without it a question matches every document through its
  common words and the least-irrelevant one reads like an answer.
* **Two stopword lists.** `_STOPWORDS` is English function words - including
  prepositions like "during", which is *rare* in this corpus and so scored as
  highly distinctive. `_DOMAIN_STOPWORDS` is corpus-generic HR vocabulary
  ("company", "employee", "policy"); without it, "the company's policy on
  international relocation" scored 0.15 on the word "company" alone and
  returned a leave-policy passage for a topic no document mentions. **Review
  `_DOMAIN_STOPWORDS` when real documents replace the demo ones** - anything
  listed there becomes unsearchable.

**The relevance floor is per backend** (`MIN_SCORE_BY_BACKEND` in
`app/rag/service.py`): `local-lexical` 0.12, `openai` 0.50. The two score on
different scales - sparse overlap gives low numbers where anything above noise
means something, while dense embeddings put everything in one high band, so an
entirely unrelated question still scores ~0.4 and 0.12 would admit it. Below
the floor nothing is returned: an empty result is a correct answer, and the
tool says so explicitly rather than returning a weak passage a model would
answer from.

**Calibrate against the query the model actually sends, not the user's.** The
assistant lets the model choose the `query` argument, and it condenses -
"What is the company's policy on international relocation?" becomes
"international relocation". Short phrases embed differently: that question
scores 0.533 in full and 0.401 condensed, while a genuinely absent topic
("company car allowance") scores 0.464. **The bands overlap for short
queries**, so no threshold separates them. 0.50 resolves the overlap towards
precision - an indirectly-covered topic is reported as not covered, and
nothing is ever answered out of a weak passage. Re-measure if the documents
change; these numbers are calibrated against this corpus.

**Storage is a JSON file, not pgvector** - checked, not assumed:
`SELECT * FROM pg_available_extensions WHERE name ILIKE '%vector%'` returns 0
rows on this PostgreSQL 18.6, so `CREATE EXTENSION vector` fails. Installing it
is a server-side job and SmartHR has no migration tool. For 4 documents / 25
chunks, brute-force cosine is exact and instant. `VectorStore` has four methods
(`add`, `search`, `clear`, `stats`); a `PgVectorStore` implementing them is the
only change needed later. **No schema change was made for RAG.**

Vectors are sparse (`{slot: weight}`), and the learned vocabulary and IDF
weights are stored **with** the index - score a question with different weights
than its chunks and every number is quietly wrong. A backend mismatch between
index and configuration is refused rather than scored.

Guard: `search_hr_policies` is allowed to **all four roles** (published policy
is for everyone) with scope `knowledge`. It returns document passages, never
anybody's records, so there is nothing personal to scope - but `authorise()`
still runs, so a deactivated account is refused.

**Known limitation - cross-language.** OpenAI embeddings *are* multilingual
and do put an Arabic policy question nearest the right document - but only at
~0.31, below the 0.50 precision floor, so it is still reported as not covered.
Fixing it needs an Arabic copy of the documents, not a lower floor (which
would admit off-topic English passages). `get_my_leave` still answers Arabic correctly
because it reads the database, not documents. A multilingual embedding model
fixes this; it is asserted in the tests so it cannot regress silently.

## MCP layer

The assistant reaches SmartHR **only** through the Model Context Protocol.
`app/ai/` no longer contains any query, table name or role rule; `app/mcp/` owns
the tool surface and `app/services/` owns the behaviour.

```
POST /ai/chat                       FastAPI authenticates, binds the principal
  -> app/ai/assistant.py            orchestrates the turn
  -> app/mcp/client.py   MCP client ─┐ real JSON-RPC session
  -> app/mcp/server.py   MCP server ─┘ (initialize, tools/list, tools/call)
  -> app/mcp/tools/*.py             @smarthr_mcp.tool() registrations
  -> app/services/*.py              SmartHR business logic
  -> app/models.py                  SQLAlchemy -> PostgreSQL
```

SDK is **mcp 2.2.0**, where v1's `FastMCP` is `MCPServer`
(`from mcp.server.mcpserver import MCPServer`) and result fields are snake_case
(`input_schema`, `structured_content`, `is_error`). v1 examples will not run.

**Identity never travels as a tool argument.** `get_my_leave` declares only
`status` and `year`; there is no `employee_id` for a model — or a crafted request
body — to set. The caller is carried out of band in a `contextvars` binding
(`app/mcp/identity.py`) that FastAPI sets from the verified JWT before the
session opens. `app/mcp/permissions.py::authorise()` then re-reads `role_id` from
`users` before any tool body runs, exactly as `require_roles` does for REST.
`app/mcp/client.py` additionally drops (and logs) any argument the tool's schema
does not declare.

**Two entry points, same server.** In process, `Client(smarthr_mcp)` over the
SDK's in-memory transport — that is what `/ai/chat` uses, one session per
operation, no subprocess. Standalone, `python -m app.mcp` speaks stdio to any
external MCP client; set `SMARTHR_MCP_USER_ID` to bind an identity for
inspection. **Do not** add an entry point inside `server.py`: `python -m
app.mcp.server` would execute it as `__main__` while the tool modules import
`app.mcp.server`, producing two `MCPServer` instances and an empty tool list.
That bug is why `app/mcp/__main__.py` exists.

Adding a tool: write the service in `app/services/`, add a module under
`app/mcp/tools/`, add a `ToolPolicy` in `permissions.py`, import it from
`register_tools()`. Nothing else changes — `/ai/chat` and `/ai/status` pick it up
from `tools/list`.

Logging (`smarthr.ai`, `smarthr.mcp.*`) traces a turn end to end: turn start,
tool-selection call, tool chosen, tools/call in and out, tool result counts,
wording call, turn done with elapsed ms. Ids and counts only — never leave
reasons, names, tokens or keys.

`app/ai/tools.py` was **removed**: it was a second tool registry with its own
copy of the role rules. Its RBAC moved to `app/mcp/permissions.py` and its leave
logic to `app/services/leave_service.py`, which `GET /leave-requests/me` and the
MCP tool now share.

## Applicant / Job Seeker experience

An **Applicant** is an external job seeker with a SmartHR account: role 5, a
`users` row, and a `candidates` row linked to it. They browse opportunities,
upload a CV, apply, track their applications and talk to an AI Career Agent.

The whole feature is built on tables recruitment already had. There is no
parallel application pipeline and no second candidate table:

```
users (role 5) --1:1--> candidates --< applications >-- jobs
                            |                             ^
                            +--< cvs                      |
                                                   trainings (learning only)
```

### What the migration added, and why

`migrations/2026-09-14_applicant.sql`. Nine changes, each with a reason:

| Change | Why |
|---|---|
| `roles` + `(5, 'Applicant')` | `roles.id` has no default, so ids are explicit |
| **`candidates.user_id`** int NULL UNIQUE FK | **the only structurally necessary one.** `employees.user_id` already ties a staff account to a person; `candidates` had no equivalent, so a signed-in applicant could not be resolved to their own row. Nullable because every candidate HR keyed in by hand has no account |
| `candidates.skills` text | the applicant's own words, typed by them. The input for matching that needs no LLM, and the reason a match score can never contain an invented skill |
| `jobs.employment_type` varchar(30) NOT NULL DEFAULT `'full_time'` | separates Jobs from Internships in one column instead of a second table holding the same shape of row |
| `jobs.location`, `jobs.deadline` | public listing information the table could not answer |
| `trainings.category` varchar(30) DEFAULT `'training'` | `'training'` or `'free_course'` - the two learning sections |
| `trainings.url` | how an external applicant reaches a course; they cannot be enrolled through `employee_trainings`, which keys on `employees.id` |

Reused **unchanged**: `users`, `applications`, `cvs`, `interviews`,
`departments`, `audit_logs`.

### Opportunities are a projection, not a table

`app/services/opportunity_service.py` maps two existing tables onto four
applicant-facing types:

```
jobs       -> job | internship        (employment_type)
trainings  -> training | free_course  (category)
```

`public_job()` builds its dictionary **field by field from scratch** rather
than filtering `job_to_dict()`. That is deliberate: a projection that starts
from everything and removes the private parts leaks the next field somebody
adds, so `created_by`, `created_by_email`, `applications_count` and
`pipeline_counts` are absent because they were never put in. Only
`status = 'open'` jobs are listed - a draft or on-hold requisition is internal
planning, and its existence is itself information.

**Only jobs and internships accept applications.** `applications.job_id` is
NOT NULL and enrolment lives in `employee_trainings` (keyed on `employees.id`),
so SmartHR genuinely cannot enrol an applicant in a course. Those listings
carry `can_apply: false` and say why rather than offering a button that would
fail.

Search (`_matches_search`) drops filler words, stems plurals and requires
**every** remaining content word to appear. Matching on *any* word would make
"quantum cryptography jobs in Antarctica" return every job through the word
"jobs"; requiring all of them means an absent topic returns nothing, which is
the truthful answer.

### Linking an account to its profile

An Applicant account is unusable until `candidates.user_id` points at it -
`get_current_candidate` resolves the profile from the JWT on every
`/applicant/*` request and 404s with "not linked to an applicant profile"
when there is nothing to resolve. **That link has exactly one definition**,
`link_candidate_profile()` in `app/services/applicant_service.py`, and every
path that can produce a role 5 account goes through it:

| path | calls it via |
|---|---|
| `POST /applicant/register` | `register_applicant()` |
| `POST /users/` (Admin) | `ensure_applicant_profile()` in `routers/users.py` |
| `PUT /users/{id}` promoting to role 5 | the same |
| existing accounts | `scripts/link_applicant_profiles.py` |

It is **idempotent** and has three outcomes, first match wins:
`already_linked` (nothing is written, which is what makes a second call
harmless), `linked_existing` (an unlinked candidate HR keyed in by hand
carries the same address, so it is adopted - their CV, applications and
interview history stay one history), `created` (the address is genuinely
new). An adopted row keeps its phone, location and everything hanging off
it; only the name is overwritten, and only when the person themselves
supplied one.

Use synthetic accounts from the reserved test domain for Social Hub verification; do not document real account identifiers or login results.

Accounts already in that state are a data problem no code change reaches, so:

```powershell
venv\Scripts\python.exe -m scripts.link_applicant_profiles           # report
venv\Scripts\python.exe -m scripts.link_applicant_profiles --apply   # fix
```

Reports by default, writes only with `--apply`, and is safe to re-run.

`POST /applicant/register` itself is the only unauthenticated write in
SmartHR. A duplicate address returns the same 409 whether or not the address
is known, so the endpoint cannot be used to enumerate accounts. The form takes
three fields and **no role** - the role is set server-side; a registration
form that accepted one would be a privilege-escalation endpoint.

### Scoping: there is no id to tamper with

Every `/applicant/*` route except registration depends on
`get_current_candidate` (`app/dependencies.py`), the twin of
`get_current_employee`. **No route and no MCP tool accepts a candidate id, a
user id or an email.** `application_service.submit()` takes a `Candidate`
object obtainable only from the JWT, so "Applicant A cannot apply for
Applicant B" is not a check that could be forgotten - there is no argument in
which to name B. `application_for_candidate()` puts ownership *in the query*,
so somebody else's id is a 404 rather than a 403: an applicant cannot learn
that another application exists by probing ids.

**A dependency and its handler must share one session.** `/applicant/*` routes
import `get_db` from `app/dependencies.py` rather than declaring their own.
FastAPI caches a dependency by its callable, so sharing that one generator
means `get_current_candidate` and the handler get the same `Session`. With two
sessions, committing a row the dependency resolved raises
`InvalidRequestError: Instance <Candidate> is not persistent within this
Session` - which is exactly what `PUT /applicant/me` did before the fix.

### Applicant-facing stage labels

`applications.status` is the same eight-token column HR moves through.
`APPLICANT_STAGE_LABELS` in `app/services/application_service.py` is a
*presentation* map, not a second vocabulary - nothing in the database changes.
Note `screening` -> **"Under Review"**: recruiter stage names describe what the
team is doing, these describe what the applicant may know. `interviews.notes`,
the interviewer's identity, other candidates and pipeline position are never
sent to an applicant.

## AI matching

`app/services/matching_service.py`. Two lists of strings are compared, and
saying so is the point.

* applicant skills come from `candidates.skills` - **typed by the applicant**;
* requirements come from `jobs.requirements`, split by `requirement_tokens()`,
  which splits and never interprets, so every requirement shown or counted as
  a gap is a literal substring of the posting;
* the score is coverage of the *job's* requirements, so listing forty skills
  does not inflate it.

Deliberately arithmetic rather than a model: an applicant must be able to see
why the number is what it is, two identical questions must give the same
answer, and it must work with no API key configured. The Career Agent calls
this as a tool and explains the result; it never computes one.

Every payload carries `label: "AI Match / Recommendation"`,
`is_hiring_decision: false` and a `disclaimer`, and the UI renders all three -
a bare percentage beside a person's name reads as a verdict on them. An
applicant with no skills gets `score: null` and an explanation, never `0%`,
which would read as "unsuitable" when it means "we know nothing yet". **No HR
screen reads a match score**; it exists only on the applicant's side.

## AI Career Agent

`app/ai/career_agent.py`, reached at `POST /applicant/agent/chat`. The staff
assistant (`/ai/chat`) is untouched: two audiences, two endpoints, **one MCP
server** underneath.

The difference from the assistant is the loop. The assistant makes one tool
call and phrases the result; the agent keeps going until it has what it needs,
up to `MAX_STEPS = 6`:

```
"What opportunities are suitable for me?"
  -> get_my_profile -> get_my_cv -> search_opportunities
  -> match_my_profile_to_opportunity -> final answer
```

Feeding a tool result back needs the provider's native format, so
`app/ai/provider.py` gained `ToolCall.id` and `tool_exchange()` - Anthropic
answers a `tool_use` block with a `tool_result` block, OpenAI answers an
assistant message carrying `tool_calls` with a `role: "tool"` message. Both
additions are backwards-compatible; the single-turn assistant is unaffected.

**Two gates stand in front of the one tool that writes.**

1. `submit_application` is **removed from the tool list entirely** unless
   `apply_intent(message)` is true. A model cannot choose a tool it was never
   shown, so "Find Data Analyst jobs" cannot end in an application no matter
   what the model decides. `apply_intent` requires an apply verb *and* that the
   message is not a question, so "What jobs can I apply to?" does not open it.
2. The tool itself requires `confirmed_by_applicant` and refuses without it.

Gate 1 is code and holds regardless of the model; gate 2 is the model's own
assertion. Both must pass. The agent has **no tool** to change an application
status, withdraw an application, or hire or reject anybody - so those are not
matters of the model choosing well.

With no model configured the agent still answers: it resolves intent by
keyword, runs the real tool and renders the real figures, flagged
`generated_by: "tool"`. It will **not** submit an application on that path -
applying is a consequential write and a keyword match is not consent.

The eight tools (`app/mcp/tools/career.py`, all role 5 only):

| tool | scope | writes |
|---|---|---|
| `get_my_profile`, `get_my_cv`, `get_my_applications`, `get_my_application_status` | `self` | no |
| `match_my_profile_to_opportunity` | `self` | no |
| `search_opportunities`, `get_opportunity` | `opportunities` | no |
| `submit_application` | `self` | **yes** - one `applications` row, audited |

They are role 5 **only**, not "5 plus Admin": they answer "my profile" for an
external job seeker, and an Admin calling them would resolve to a `candidates`
row that does not exist. HR reads applicant data through the recruitment
endpoints they already have. Conversely role 5 gets **none** of
`get_my_leave`, `parse_cv` or `search_hr_policies` - HR policy documents are
internal.

`GET /applicant/agent/status` reports the tool list, the step limit and the
apply gate, and the UI shows the agent's **tool trace** under every answer, so
a reply with nothing behind it is visibly a reply with nothing behind it.

## Applicant frontend

Same shell, same design system, no second architecture. Six pages under
`src/pages/applicant/` plus `src/pages/ApplicantRegisterPage.tsx`:

| PageId | Page |
|---|---|
| `app-dashboard` | `ApplicantDashboardPage` |
| `app-opportunities` | `OpportunitiesPage` (list **and** detail, via `selectedOpportunityId`) |
| `app-profile` | `ApplicantProfilePage` |
| `app-cv` | `ApplicantCvPage` |
| `app-applications` | `ApplicantApplicationsPage` |
| `app-agent` | `CareerAgentPage` |

`access.ts` maps role 5 to the single `applicant` workspace - deliberately
**not** `employee` as well, since the `/me` routes resolve an `employees` row
an applicant does not have. `workspaceOf` keys on the `app-` prefix.
`landingPageFor(5)` is `app-dashboard`.

Three things in the shell are role-aware because an applicant is not staff:
`GlobalLayout` mounts `<AiAssistant />` only for roles 1-4 (it talks to
`/ai/chat`, which would 403); `App.tsx` skips `/auth/me/employee` for role 5
rather than firing a call known to 404; and the notification bell stays empty.

An opportunity is rendered by the shared `OpportunityCard` / `MatchPanel`
(`src/pages/applicant/OpportunityCard.tsx`) wherever it appears.
`ApplicantCvPage` uploads through `POST /applicant/cv`, which calls the
**same** `analyse_cv_bytes()` as `POST /cvs/upload` - there is no second parser
- and skills the CV suggests are shown with "not saved" and a button that
copies them to the profile form. `candidates.skills` changes only when the
applicant saves it, which is what keeps matching free of model-invented skills.

## DEMO opportunity data

`scripts/seed_demo_opportunities.py` adds 3 jobs and 4 trainings, every title
prefixed **`DEMO - `**, because the real data has four full-time jobs and zero
trainings, so Internships, Training and Free Courses would each render empty.

```powershell
venv\Scripts\python.exe -m scripts.seed_demo_opportunities            # add
venv\Scripts\python.exe -m scripts.seed_demo_opportunities --remove   # undo
```

It only inserts - the four real jobs keep their titles, requirements and
(absent) location and deadline - and `--remove` keeps any DEMO job that has a
real application against it. **No applicant-facing code contains seeded,
sample or placeholder data**: delete these rows and the pages correctly report
that SmartHR has nothing on offer.

## Applicant QA fixtures

`scripts/create_applicant_test_accounts.py` creates **ten** Applicant accounts,
their candidate rows and a CV each, for repeatedly testing the applicant half
of SmartHR: sign-in, the dashboard, CV upload, the AI CV parser, matching,
applications and reports.

```powershell
venv\Scripts\python.exe -m scripts.create_applicant_test_accounts             # create or reuse
venv\Scripts\python.exe -m scripts.create_applicant_test_accounts --dry-run   # writes nothing
venv\Scripts\python.exe -m scripts.create_applicant_test_accounts --verify    # check what exists
venv\Scripts\python.exe -m scripts.create_applicant_test_accounts --parse     # + run the real CV parser
```

Set `TEST_ACCOUNT_PASSWORD=<LOCAL_TEST_PASSWORD>` in the local environment
before running the fixture script; AI Interview scenarios also need
`AI_INTERVIEW_HR_EMAIL=<TEST_ACCOUNT_EMAIL>`. Replace placeholders locally and
never commit these values or real account identifiers.

**It is not a second implementation of anything.** The account is hashed with
the `password_hash` the login route verifies against, the candidate row comes
from `link_candidate_profile()` - the one definition of that link, which
registration and Admin user management also call - and the bytes go through
`cv_storage.store_cv_file()`. A CV it creates is indistinguishable from one
uploaded through `POST /cvs/upload`.

**DOCX, not PDF**: `python-docx` can write a document and `pypdf` can only read
one,
and `cv_extraction` detects the type from the file **signature** and treats
both identically. A PDF-writing dependency would buy a file the pipeline
handles the same way.

**Nothing is faked.** No parsed field, no analysis result and **no match score**
is written. `--parse` runs the real `analyse_cv_bytes()` and reports what came
back; matching is whatever `matching_service` computes at the time. Against the
current jobs the ten score between 0% and 100% on the same posting, which is
the point of having ten.

Use synthetic fixture accounts when exercising the account and role flows; keep real account inventories private.

Note the domain is the same one the Social Hub directory excludes, so these
never appear as colleagues - and they are role 5, which that directory
excludes anyway.

## Internal HR Agent

SmartHR's third AI surface, and the third audience for the **one** MCP server:

| endpoint | audience | roles | shape |
|---|---|---|---|
| `/ai/chat` | staff assistant | 1-4 | one tool, one turn |
| `/applicant/agent/*` | Career Agent | 5 | multi-step, job seeker |
| `/hr/agent/*` | **Internal HR Agent** | **1, 2** | multi-step, recruiter |

`app/ai/hr_agent.py` reached at `POST /hr/agent/chat`. The staff assistant and
the Career Agent are untouched.

```
"Find the best candidates for the Data Analyst position."
  -> search_jobs / get_job          which requisition is this?
  -> get_job_requirements           what does it actually ask for?
  -> rank_candidates_for_job        score the real candidates
  -> get_candidate_cv               read evidence for the strongest few
  -> final answer
```

The sequence is the model's; nothing scripts it. `MAX_STEPS = 8`.

### The two agents cannot reach each other's data

Not by convention - **`tools_for_role(2)` and `tools_for_role(5)` are disjoint
sets**, so neither agent could reach the other's tools even if its prompt were
replaced wholesale. The HR Agent has none of `get_my_profile`, `get_my_cv` or
`submit_application`; the Career Agent has none of the ten below. That is
asserted in the tests.

### Why it cannot hire anybody

**Every HR Agent tool reads.** There is no tool to change an application's
stage, create an interview, write a note or contact a candidate - so "the
agent must never hire or reject" is not a rule the model is asked to obey, it
is a verb it has no way to express. The Career Agent needed the two-gate
arrangement around `submit_application` because it has one write; this agent
needs none because it has none, which is the stronger arrangement.

The ten tools (`app/mcp/tools/screening.py`, all roles 1-2, scope
`recruitment`, **all read**):

| tool | reads |
|---|---|
| `search_jobs`, `get_job`, `get_job_requirements` | `jobs` |
| `search_candidates`, `get_candidate` | `candidates` (+ `applications`, `cvs`) |
| `get_candidate_cv` | the stored CV, through `analyse_cv_bytes()` |
| `search_applications`, `get_application` | `applications`, `interviews` |
| `match_candidate_to_job`, `rank_candidates_for_job` | the above, scored |

**Manager (role 3) is deliberately absent.** A Manager reaches their own
team's attendance, leave and performance, and no existing access tier gives
them the candidate pipeline - `/candidates/`, `/applications/` and `/cvs/` are
all `require_roles(1, 2)`. Giving their agent one would have widened access
through the AI layer that the REST layer refuses. If a business rule ever
brings Managers into recruitment it is one tuple in `permissions.py` and one
in `routers/hr_agent.py`, not a rewrite.

**Ids here are subjects, not identity claims** - the opposite of the Career
Agent's rule, for a stated reason. The Career Agent's tools take no ids
because they answer "my profile" and a candidate_id would be the whole
vulnerability. These answer "that candidate", about organisation-scoped data
roles 1-2 may already read in full, exactly as `parse_cv` takes a
candidate_id. Who is *asking* still comes from the bound principal, and
`authorise()` still re-reads `users.role_id` before any handler runs.

### Screening: where a candidate's skills come from

`app/services/screening_service.py`. The recruiter-facing counterpart to
`matching_service.py`, and **not** a second implementation of matching - the
score itself is `matching_service.match_skills()`, imported, so a recruiter and
a candidate looking at the same pair see the same number. What it adds is
provenance:

| source | when |
|---|---|
| `candidates.skills` | only when the person registered through the Applicant portal and typed it |
| the stored CV | parsed by `analyse_cv_bytes()` - the **same** function `POST /cvs/upload` and `parse_cv` use. There is no second CV parser |

Every skill returned carries `skills_sources` naming which one it came from.
Nothing is inferred from a name, a location, a job title or an education line.

**A candidate with neither scores `null`, never `0`.** This is the single most
important rule in the module and it is enforced in three places: the service
sets `score: None` with a reason, the prompt tells the model that a null is
missing evidence rather than a low score, and the UI renders "Not scored"
rather than a percentage. `0%` beside somebody's name reads as a verdict on
them when it means "we have never seen a CV". For the same reason an
unevidenced candidate's requirements come back as `unevidenced_requirements`,
not `skill_gaps` - SmartHR has not established that they lack them.

`relevance` on experience, education and certifications is a band over a
**counted** number ("2 of 3 roles on the CV mention this job's requirements"),
returned with its `basis` so the sentence can be checked. `unknown` (no CV
read) is deliberately distinct from `none_evidenced` (CV read, mentioned
nothing).

**Reading a CV is a model call**, so it is opt-in: `search_candidates` is
cheap and says who has a CV worth reading, `match_candidate_to_job` and
`rank_candidates_for_job` read them, and `MAX_CV_READS = 8` caps one ranking.

**`search_candidates` does not search CV text** - SmartHR stores CV files, not
their contents - and the tool says so in `not_searched` rather than letting a
model imply the search was exhaustive. Note also that `candidates` stores the
name in two columns, so `find_candidates` matches `first_name || ' ' ||
last_name` as well; without that, asking the agent about "Samer Ali" matched
neither column and it truthfully but uselessly reported no such person.

### No schema change

`jobs`, `candidates`, `cvs`, `applications`, `interviews`, `departments`,
`users` - all reused as they are. **No column, table or migration was added
for this feature**, and nothing in it writes.

### Frontend

`src/pages/hr/HrAgentPage.tsx`, PageId **`hr-ai-agent`**, in the HR workspace
(so `workspaceOf` puts it behind roles 1-2 with no change to `access.ts`).
Nav entry "AI Screening Agent" under Candidates.

The candidate cards render from `response.candidates` - real screening rows
the backend lifts out of the tool results - **not** parsed back out of the
model's prose. So whatever the model wrote above them, the cards show what the
tools actually returned, and a reply with no tool calls behind it renders no
cards. Each card shows Match Score, Matching Skills, Skill Gaps, Relevant
Experience with its basis, education and certifications when the CV stated
them, and where the evidence came from. `null` renders as "Not scored" with
the reason, never as a percentage.

## Social Hub

SmartHR's internal employee network: a feed, stories, profiles, a directory,
connections and direct messages, for **staff only** (roles 1-4).

```
GET /social/feed -> app/routers/social.py    require_staff, error -> status
                 -> app/services/social_service.py   the behaviour
                 -> app/models.py -> PostgreSQL (social_* tables only)
```

No AI, by design and by absence: nothing in `app/routers/social.py` or
`app/services/social_service.py` imports `app/ai/` or `app/mcp/`, and there is
no Social Hub MCP tool. A later AI People Search is a tool over
`social_profiles.skills` plus the existing `employees` joins; it needs no
change here.

### Every table keys on `users.id`, not `employees.id`

Employee/profile relationships are resolved from database state at runtime; avoid documenting individual account-to-row associations here.

The participant in a social network is the signed-in **account**: it is what
posts, what reacts and what receives a message. `users.id` is NOT NULL and
always exists. The *person* - name, department, position - is still read from
the linked `employees` row on every response, through
`social_service.actor_map()`, falling back to the email exactly as
`describe_user()` already does. `employee_id: null` is a rendered, explained
state on a profile, not a blank.

Applicants are excluded by `require_staff` on the router, not by the choice of
key.

### Schema: ten tables, nothing altered

`migrations/2026-09-16_social_hub.sql`. **No existing table or column was
changed.** In particular `employees` did *not* gain a bio, an avatar or a
skills column - those are self-authored presentational fields, and `employees`
is read by nine other features.

| table | why it exists |
|---|---|
| `social_profiles` | 1:1 with `users`. Headline, bio, skills, interests, location, avatar. Created empty on first use, so "has not written a bio" is a row, not a missing one. |
| `social_posts` | The feed. `department_id` is the author's department **as it was when they posted** - stored so the "My Department" filter is not a three-hop join per row, and so a post stays in the department it was written for after its author transfers. |
| `social_comments`, `social_reactions` | Both `ON DELETE CASCADE` from the post. |
| `social_stories`, `social_story_views` | `expires_at` stored, not derived. |
| `social_connections` | **One row per pair, forever.** |
| `social_conversations`, `social_conversation_members`, `social_messages` | Messaging. Three tables, for one non-speculative reason: an unread count needs a per-participant read marker and a `(from, to, body)` table has nowhere to put one. |

**Four constraints replace logic a handler could forget**, and they are the
reason several "rules" below are not code at all:

* `UNIQUE (post_id, user_id)` on `social_reactions` - liking twice cannot
  create a second row, so a like count is a `COUNT` that cannot be inflated by
  a repeated request.
* `CHECK (requester_user_id <> receiver_user_id)` - a self-connection is
  unstorable.
* `CREATE UNIQUE INDEX ... ON social_connections (LEAST(a, b), GREATEST(a, b))`
  - "A asked B" and "B asked A" are the **same row**, so a duplicate active
  request is refused by Postgres rather than by a check that could lose a race.
  A rejection therefore leaves no tombstone: re-requesting revives that row,
  swapping requester and receiver when it is the other person asking.
* `UNIQUE (story_id, viewer_user_id)` - seeing a story twice is one view.

### Scoping: ownership in the query, 404 not 403

`post_for_author()`, `conversation_for_member()` and the connection and
notification lookups all filter on the caller **inside** the query, so somebody
else's row returns None and the router answers **404**. That is the rule
`application_for_candidate()` already follows, and it is what stops ids being
probed.

`conversation_for_member()` is the sharpest case: it joins through
`social_conversation_members` filtered on the caller, so **membership is the
authorisation**. There is no separate "may they read this" check to forget.

**There is no Admin override anywhere in this module**, and that is deliberate:
deleting a colleague's post or reading their messages is moderation, V1 has no
moderation surface, and it is not smuggled in as a side effect of being an
Admin. `scripts/test_social_hub.py` asserts an Admin gets 404 on both.

### The social projection is built, not filtered

`actor_map()` assembles a person field by field and carries id, name,
initials, email, role, department, position, headline and avatar - nothing
else. It is never a trimmed `employee_identity()`, for the same reason
`opportunity_service.public_job()` is built from scratch: a projection that
starts from everything and removes the private parts leaks the next field
somebody adds.

Attendance, leave, performance ratings, reviews, employment status and manager
are simply never read here. SmartHR has no salary column anywhere, so there is
nothing there to exclude. The test asserts this by scanning the serialised
profile for those field names, so a field added later that happens to be called
`rating` fails it.

`achievements()` is the one place that touches adjacent data, and it is limited
on purpose to **completed `employee_trainings` and the `employees.hire_date`
anniversary** - professional development and how long somebody has been here.
The tab says so in a line under the list rather than leaving the omission to be
guessed at.

### Fixture accounts are not colleagues

The People experience lists eligible users according to account and employee rules; verify it with synthetic fixture accounts.

`search_people()` excludes them, and `hub_status()` counts the directory the
same way, so the rail's figure is the number of people the page will actually
show. Filtering in the browser could not have done this honestly: the count
would still have said 13 while the list showed 2.

`SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS=true` lists them anyway, and
`test_social_hub.py` sets it for its own server - asserting that its fixture
appears in the directory is precisely what that test is for. Read through
`bool_setting`, so it has the same env-then-`.env` precedence as every other
setting. **Nothing else changes**: the accounts still sign in, and
authentication, RBAC and every other module are untouched.

### People lists accounts, not employee records

`search_people()` returns internal **accounts** (roles 1-4, active). An
`employees` row with no account cannot accept a connection, reply to a message
or post, so listing it would be two buttons that can never complete - the same
reasoning that makes a training listing carry `can_apply: false` rather than
offering a button that would fail. The page states this rather than letting a
short list imply an empty company.

Each search term must appear somewhere in the person's text, so an absent name
returns nothing instead of returning everybody through one common word -
`opportunity_service._matches_search()`'s rule.

### Notifications: the existing table

**No second notification system.** A Social Hub notification is an ordinary
`notifications` row whose `type` begins `social_`
(`social_connection_request`, `_connection_accepted`, `social_comment`,
`social_reaction`, `social_message`), so it appears in the existing bell and
the existing per-role notification pages with no change to either.
`GET /social/notifications` is that same table narrowed to those types, and
marking one read is the same row the bell marks read.

`notify()` is **best-effort**, in the same spirit as `record_audit()`: it
swallows its own exception and rolls back, because a notification is secondary
to the post, like or message it describes. It never notifies the actor about
their own action.

The sentence on a notification is stored English text, following the existing
rule that database values are shown as stored and only the labels around them
are translated - the UI localises the *category* from `type`.

### Images

`app/social_storage.py`, `cv_storage.py`'s sibling and the same two rules: the
stored name is **generated**, never the client's, and the type comes from the
file's **signature**, not its extension. 4 MB cap; PNG / JPEG / GIF / WebP.

The one real difference is that these files have to be *shown*, so
`GET /social/media/{name}` serves them - **behind `require_staff` like every
other route in the module**, so an Applicant cannot fetch a colleague's
photograph by guessing a URL. `uploads/social/` is not a static mount. The name
is matched against `STORED_NAME_RE` *before* it is joined to a directory, so a
traversal attempt never becomes a path, and the result is re-checked to be
inside the upload directory.

The detector is fed real MP4 and WebM headers in testing and must refuse both:
the Social Hub accepts still images only, and a video renamed `.png` is not one.

### Audit

Only **posts** are audited (`ENTITY_SOCIAL_POST`, CREATE / UPDATE / DELETE): a
post is content an organisation may need to account for. Likes, comments,
stories, connections and messages are not - an audit row per like would bury
the trail, and a private message between two colleagues is not an
administrative event.

### Frontend

| PageId | Page |
|---|---|
| `soc-feed` | `social/SocialFeedPage` - stories, composer, filtered feed, rail |
| `soc-people` | `social/PeoplePage` - directory, connections **and** incoming requests |
| `soc-messages` | `social/MessagesPage` - two-column chat |
| `soc-profile` | `social/SocialProfilePage` - mine **and** anybody's |
| `soc-notifications` | `social/SocialNotificationsPage` - the `social_` rows |

`soc-notifications` was added by the redesign and needed **no backend work**:
`GET /social/notifications` and its mark-read already existed, with nowhere to
read them. It is the same `notifications` table the top-bar bell reads, so a
row marked read here is read in the bell.

**The Social Hub has its own frame**, `social/SocialShell.tsx` - `SocialHero`
(a warm band, the five destinations as tabs, and who you are), `SocialSection`,
`SocialEmpty` and `PostSkeleton`. It exists because `PageHeader` is the right
header for an HR screen and the wrong one here: the brand rail, the icon tile
and the `Toolbar` strip are what made the employee network read as another
administrative table. It is built from the **same** tokens - `brand`, `sand`,
the same radii and type scale - so the two are plainly one application. The tab
row carries the same `PageId` values the sidebar does, so it cannot drift from
`access.ts`.

`TopNavigation` resolves `soc-` pages to a **social** workspace. Without that
they fell through to the admin default and the employee network introduced
itself as "Admin > Social Feed"; it now reads "Social Hub > People", and the
top-bar bell on a Social Hub page goes to `soc-notifications`.

**Empty states are compact on purpose.** The shared `EmptyState` left a screen
of whitespace under two lines, which reads as unfinished rather than as calm;
`SocialEmpty` is one bordered panel the height of a post card that names what
would appear and offers the one action that would cause it.

**No Share button.** The brief asked for Like / Comment / Share, and there is
no share endpoint, no repost table and no column to record one - so the card
offers the two actions that exist rather than a third that would do nothing.

A sixth workspace, `social`, in `access.ts`, given to roles 1-4 and
deliberately not to 5. `workspaceOf` keys on the `soc-` prefix. Which person a
profile is showing travels in `App.tsx` state, not in the PageId - the pattern
`selectedEmployee360Id` already uses.

**Counts are the server's answer, never arithmetic in the browser.** Every
like, unlike and comment re-reads the post from the API response, so a second
tab or a failed write can never leave a number on screen the database does not
agree with.

**Nothing is invented to fill space.** SmartHR has no events table, so the rail
says that in one line instead of showing a plausible calendar; an empty feed
names the filter that produced it; the directory count is the real number of
colleagues with an account.

Messaging is REST - `POST` then re-read, plus a refresh when the window regains
focus. That is the cheap version of realtime and the code says so; there is no
polling interval pretending to be live, and no WebSocket was introduced.

Localisation: `src/i18n/dictionaries/social.ts`, both languages, none unused -
the redesign added the notifications page, the people filters and the profile
headings, and **pruned 22 keys that referenced nothing**. Eight of those were a
second, older spelling of the notification strings (`social.notify.*` beside
`social.notifications.*`), which is exactly the "plausible wrong answer beside
the right one" the dictionary rule warns about; three more were orphaned by the
redesign itself. Not translated, following the existing rules: **post content, comments,
story captions and messages** (written by colleagues in the language they
chose), people's names, emails, department and position names, training titles,
and the stored notification sentences.

`formatRelativeTime()` was added to `src/i18n/format.ts` and uses
`Intl.RelativeTimeFormat`, so Arabic's dual form comes from the platform rather
than from a `{count}` in a hand-written string.

### Tests

```powershell
venv\Scripts\python.exe -m scripts.test_social_hub            # launches its own server
venv\Scripts\python.exe -m scripts.test_social_hub --keep     # leave its rows behind
cd frontend; npx tsx scripts/check-social-access.ts            # role -> page, in the browser's own map
```

`check-social-access.ts` asserts all five Social Hub pages for roles 1-4 and
**none** for role 5, plus that an Applicant's landing page is not one of them.
That is convenience rather than security - `require_staff` on every `/social/*`
route is the boundary, and `test_social_hub.py` proves it - but a nav entry an
Applicant could reach would still be a bug, and adding a page is when it
happens.

Launches its own uvicorn on **8041**, so it needs no server running and cannot
collide with 8000. It imports the HTTP helpers and account fixtures from
`scripts/test_helpers.py` rather than copying them. 154 checks in ten groups:
features, RBAC (all four internal roles allowed; Applicant 403 and anonymous
401 on every shape of route, media included), ownership (each asserted to be
**404, not 403**), story expiry (proven by ageing the row, not by waiting 24
hours), and containment (eight HR tables counted before and after, so the
module is shown to have written to none of them). Its rows are deleted at the
end unless `--keep`; the `.test` accounts it creates persist, like the `e2e.*`
ones.

### AI Moderation V1

Posts, comments and story captions are classified by the configured model
before they appear, and anything flagged is **held for a person to decide
on**. The Social Hub itself was not rebuilt: this is one service, one table,
one column on each content table, five routes and one page.

```
POST /social/posts          social_service.create_post()
  -> social_moderation_service.moderate_and_record()
       -> app/ai/provider.py    one tool call, one structured decision
       -> validate_moderation() strict about content, lenient about shape
  -> social_posts.moderation_status = published | pending_review
  -> social_moderation_reviews row, when it is not a clean allow
```

**The model classifies; it never decides.** `app/ai/moderation` does not
exist and there is no moderation MCP tool - this follows `cv_parser.py`'s
shape, not an agent's: the model is shown one piece of text, answers through
a tool schema, and has no tool with which to hide, delete or publish
anything. The schema has five fields (`decision`, `categories`, `severity`,
`confidence`, `reason`) and **no field an employment decision could go in**,
which is asserted in the tests rather than left to the prompt. The only two
decisions are `allow` and `flag`; there is no `remove`.

**Fail closed, never destructively.** No model configured, an unreachable
model, a timeout, or output that does not validate all produce
`ai_decision='unavailable'` with an `error_code`, and the content goes to
`pending_review`. `moderate_text()` **never raises** - a moderation layer that
could raise is a moderation layer that could take the Social Hub down. Nothing
is ever deleted: `remove` is a status, so the post, the classification and the
reviewer's decision all stay readable afterwards.

**The consequence of fail-closed, stated plainly:** on a deployment with no
language model, *every* post goes to the queue. `SMARTHR_SOCIAL_MODERATION=false`
is the escape hatch and restores exactly the pre-moderation behaviour;
`test_social_hub.py` sets it for its own server so that suite does not depend
on OpenAI being reachable.

### Two tables holding one truth, on purpose

`social_moderation_reviews` is the record; `moderation_status` on
`social_posts` / `social_comments` / `social_stories` is the visibility flag.
They could have been one, and are not:

The feed reads ten posts a page and already runs three grouped count queries
for them. Deriving visibility from the review table would mean a correlated
`NOT EXISTS` on every row of every feed, comment list and story bar, for a
value that is `published` on virtually every row. The cost of the
denormalisation is that two places hold one truth, so **every write that
changes either goes through the same transaction** - `create_post` flushes,
moderates, sets the status and commits once. That is the arrangement
`leave_requests.approved_by` already has with `status`.

`DEFAULT 'published' NOT NULL` means every pre-existing row, and every row
written by a path that has not been taught about moderation, is visible
exactly as before. Moderation can only take visibility away from content it
has actually looked at.

### Visibility, and what an author is told

| status | who sees it |
|---|---|
| `published` | everybody |
| `pending_review` | **only its author**, labelled "Pending review" |
| `removed` | nobody on the feed; the row still exists |

The author keeps sight of their own held content deliberately: content that
vanishes after somebody presses Post reads as a bug and they post it again.

**The author is told the status and nothing else.** `_moderation_fields()`
returns two keys - `moderation_status` and `pending_review` - and
`pending_review` is true only for the author, so a colleague's payload cannot
even imply that something is under review. The categories, severity,
confidence and the model's reasoning exist **only** on
`review_view()`, which is built for the HR endpoints. That is the same
"projection built, not filtered" rule `public_job()` follows. Fetching a held post by id is a **404**,
not a 403 - ids cannot be probed to learn that something is being reviewed.

### RBAC: narrower than the Social Hub

The five `/social/moderation*` routes carry `require_roles(1, 2)` on top of
the router's `require_staff`, so **Manager and Employee get 403** while
keeping the Social Hub itself. That matches every other recruitment-grade
surface (`/candidates/`, `/applications/`, `/cvs/`).

The page is **`hr-social-moderation`**, in the HR workspace, and the `hr-`
prefix is load-bearing: `workspaceOf()` maps every `soc-` page to the social
workspace, which roles 1-4 all have, so `soc-moderation` would have put a nav
entry in front of Managers and Employees. `check-social-access.ts` asserts
this so a rename cannot quietly undo it.

### Taxonomy

Eight tokens, deliberately small enough for a reviewer to hold in their head:
`harassment`, `bullying`, `threats`, `abusive_language`, `hate_speech`,
`sexual_content`, `spam`, `profanity`. Anything the model returns outside that
list is **dropped**, not stored, so a category cannot be invented into
existence. A `flag` whose severity is unusable defaults to `medium` and stays
a flag; a `decision` that is neither `allow` nor `flag` is refused outright,
because guessing which was meant is exactly the guess this module must not
make. `confidence` is clamped to 0-1, and **null renders as "Not scored",
never 0%** - the rule `matching_service` and `screening_service` follow.

### Prompt injection

The moderated content is untrusted text written by somebody who may be trying
to talk the classifier out of a flag. It is delimited, and both the system
prompt and the content block state that nothing inside the markers is an
instruction. **That is a mitigation, not a guarantee**, and it is worth
knowing when reading a queue: a determined injection is a reason the human
review step exists.

### Audit, and no second trail

Three events go to the existing `audit_logs` through `record_audit()`, under
`ENTITY_SOCIAL_MODERATION`: content held (`STATUS_CHANGE`, attributed to the
author), approved (`APPROVE`) and removed (`REJECT`), the latter two
attributed to the reviewer. A clean `allow` writes nothing - an audit row per
post would bury the trail, which is the judgement `ENTITY_SOCIAL_POST`
already made about likes.

### Performance

A model call happens on **create**, and on an edit **only when the text
actually changed**. Reading a feed, opening a profile, scrolling, liking and
reading comments make no call at all. Empty text (an image-only story) and
text over 8 000 characters are not sent to the model - the first publishes,
the second is held.

**There is no image classifier in V1.** Only a story's caption is moderated,
so an image-only story publishes. Said here rather than left to be discovered.

### Tests

```powershell
venv\Scripts\python.exe -m scripts.test_social_moderation          # 116 checks, no network
venv\Scripts\python.exe -m scripts.test_social_moderation --live   # + the real model
```

**The default run makes no API call and needs no key**, which is the point:
a moderation layer whose suite breaks when a third party is slow is one
nobody can refactor. It gets there two ways, neither of which mocks SmartHR:

* a **fake provider** implementing `app/ai/provider.py`'s two methods, so the
  real schema, validator, service and database are all exercised;
* a second server launched with `SMARTHR_LLM_PROVIDER=none`, so the model is
  genuinely absent - that is not a trick to dodge the network, it *is* the
  fail-closed path, and the hardest one to reach on demand otherwise. Note
  `none` rather than an empty value: `_setting` treats empty as absent and
  falls through to `.env`, which would re-read the real key.

`--live` adds seven checks against the real model (the brief's five cases plus
taxonomy containment and "the reason never recommends action about a person").
It is labelled an **integration test**: its failure means the model or the
prompt moved, not that the application is broken.

### DEMO social data

`scripts/seed_demo_social.py` - reports by default, `--apply` writes,
`--remove` undoes. Every post, comment and story it writes begins `DEMO - `, so
what it wrote is identifiable by reading it.

It **creates no users and no employees** - it posts as accounts that already
exist and stops if fewer than two do. It deliberately seeds **no connections
and no conversations**: a connection is a statement that two colleagues agreed
to something and a message is private correspondence, and inventing either
would put words between two real accounts. Labelled content is a different
thing.

## AI Employee Celebration

SmartHR's fifth AI surface, and the first built as a **multi-agent
workflow**. Three agents with three different jobs decide, in order, what is
being celebrated, what the message should say, and whether it may be
published - and only an approved message reaches the Social Hub composer.

```
scripts/run_daily_celebrations.py          once a day, by Task Scheduler
  -> celebration_service.run_daily()       who has an anniversary TODAY?
       (SQL over employees.hire_date - no model spent on an ordinary day)
  -> for EACH of them, separately:
       app/ai/celebration/graph.py         LangGraph: nodes, edges, retries
         prepare_context -> occasion -> message -> review -.
                                          ^                |
                                          '---- revise <---'  (bounded)
                                                   |
                                              finalise -> END
  -> celebration_drafts row, status 'pending'      NOTHING IS POSTED
                                                 |
HR opens the Social Hub, reads it, presses Post   |
  -> POST /social/celebration/drafts/{id}/approve  |
  -> social_service.create_post()  <---------------'
       ordinary post, ordinary moderation, ordinary audit row
```

**The workflow starts itself; a person still publishes.** That split is the
whole design: AI = detection + generation + review, HR = the decision. The
sweep's most consequential act is writing a `pending` draft.

**LangGraph is new; everything else is the existing architecture.** The
agents call `app/ai/provider.py` with a tool schema and validate the reply
with Pydantic, exactly as `cv_parser.py` does. There
is no LangChain model wrapper, no agent executor and no MCP tool - the graph
is used for what a graph is for, which is the one conditional edge below.

### The agents cannot reach the database, and cannot write anything

`app/services/celebration_service.py` runs every query and the router hands
the result to the graph as plain dictionaries, so "a model cannot read a
record it was not shown" holds because there is no connection to reach.
`test_celebration_agents.py` asserts it by reading the five modules in
`app/ai/celebration/` for `db.add` / `db.commit` / `db.delete` /
`SessionLocal` and for any import of `app.models` or `app.database`.

Nothing in the feature writes at all: there is no tool to post, to store a
message or to change an employee, so "the model must not publish" is not a
rule it is asked to obey - it is a verb it cannot express, the same
arrangement the HR Agent has. A run is proven to leave `social_posts` and
`employees` unchanged.

### Six occasions, each from one employee date

`migrations/2026-09-27_employee_celebration_dates.sql` added five nullable
`DATE` columns to `employees`, named like `hire_date`. Each occasion is
detected from exactly one column - `celebration_service.OCCASION_FIELDS` is
the single source of truth, read by detection, the events tool, the status
endpoint and the tests:

| occasion | column | rule |
|---|---|---|
| `work_anniversary` | `hire_date` | yearly on the month/day, >= 1 completed year - **unchanged**, still `anniversaries_today()` |
| `birthday` | `birth_date` | yearly on the month/day (29 Feb -> 1 Mar in a common year, the anniversary's rule); **no age is computed or sent** |
| `promotion` | `promotion_date` | once, on that date |
| `graduation` | `graduation_date` | once, on that date |
| `wedding` | `wedding_date` | once, on that date |
| `new_baby` | `new_baby_date` | once, on that date |
| `none` | - | the correct answer on almost every day |

The windows are the anniversary's: the sweep (`celebrations_today()`) matches
TODAY (UTC) only; `get_employee_events()` looks up to
`ANNIVERSARY_WINDOW_DAYS` (7) ahead. A one-off date already past, or the same
month/day in an earlier year, is not an occasion. A NULL column is reported
**per employee** in `not_recorded` ("SmartHR holds no birth date for this
employee"), and the Occasion Agent's prompt says a not-recorded occasion can
never be its answer - "no date on file" and "not today" stay different
findings. `NOT_RECORDED` (occasions with no column at all) is now empty.

**One run per (employee, occasion).** Two occasions on one day are two drafts,
de-duplicated by the existing `UNIQUE (employee_id, occasion, occasion_date)`
(no change to `celebration_drafts` - `occasion` is free VARCHAR(30)). The
graph is shown only the ONE detected event; if the Occasion Agent names a
different occasion, the draft is stored `no_occasion` with
`error_code='occasion_mismatch'`. `years` is stored only for anniversaries.

The Message Agent gets a per-occasion guide (`prompts.OCCASION_GUIDE`: what
the post is about, one example opening, fitting emoji) - guidance, never the
text. For a wedding or new baby it knows nothing about the partner or child
and says nothing about them. The Review Agent accepts the verified occasion
as given: measured, it had been second-guessing it **from the employee's
name** ("CELEBTEST Anniversary-A" made it reject a new-baby post), so criterion
1 now says a name is not evidence of any occasion.

The dates are edited on the HR Employees page (add/edit forms, "Celebration
dates (optional)") through the existing `/employees/` CRUD. `PUT` changes only
the date fields a request sends (`model_fields_set`), so a client that omits
them cannot erase them; `birth_date` must be in the past. They are returned
to Admin/HR and to the employee's own record only - a Manager reading another
employee through `GET /employees/{id}` does not see birth, wedding or baby dates.

### The Review Agent's veto is real

`final_celebration` is set **only** on the approved path, so a rejected or
unreviewable message has nowhere to go, and the UI offers no post button for
one. Three consequences worth keeping:

* an **unreachable reviewer is not an approval** - the node returns
  `approved: False` with the reason, rather than letting a 504 publish
  something unreviewed;
* the retry loop is bounded **in Python**, in `_after_review`:
  `MAX_RETRIES = 2`, so a reviewer that rejects everything ends the run after
  three drafts. LangGraph's `recursion_limit` (25) is a second floor under
  it, not the mechanism;
* `ReviewResult.approved` coerces anything that is not plainly an approval to
  `False`. A rejected good message costs a rewrite; an approved bad one is
  published under a real person's name.

Measured against the real model: an invented `$2.4 million` achievement and a
wrong years figure were both rejected, naming the check that failed.

### Two things measured against the real model, not assumed

Both were found by running the workflow end to end rather than by reading it,
and both are the kind of thing only a real model surfaces.

**A reply in the wrong envelope is not a refusal.** `app/ai/provider.py` has
no forced-tool setting for either vendor, and gpt-4o answers these prompts
with a **fenced JSON block instead of a tool call in roughly one call in
ten** - carrying the right answer in the right shape. That used to be read as
an unusable reviewer, which cost a rewrite of a message that was already
fine, and left `error_code: "no_tool_call"` on a run that went on to succeed.
`_ask()` now salvages it through `cv_parser._json_from_text` - imported, not
copied, because two salvage implementations would eventually disagree about
what a fenced block is. **The salvage recovers an envelope, never a verdict**:
JSON that does not carry `approved` is still refused rather than read as
approval.

**A fact SmartHR does not hold is omitted, never sent as `null`.**
`employees.position_id` and `department_id` are both nullable, so an employee
with no job title is ordinary rather than exceptional. With
`"position_title": null` in the payload the Review Agent **rejected clean
messages 3 times in 10**, reading a fact SmartHR does not have as an
inconsistency in a message that had correctly left it out. `_facts()` now
drops null fields entirely and both prompts say what an absent field means.
Measured after the change: 10 clean messages in 10 approved, no tool-call
failures.

Invented content was never approved either way - 0 approvals in 10 against a
message full of fabricated achievements, the failures landing on "rejected"
or "unusable", which the graph treats identically.

### The daily sweep, and why it is a script

`scripts/run_daily_celebrations.py`, registered once with Windows Task
Scheduler. **SmartHR has no scheduler and this did not add one** - no
APScheduler, no Celery, no lifespan loop. Everything else in SmartHR that
needs periodic work does it on read instead.

An in-process loop was rejected for three measurable reasons: `uvicorn
--reload` runs a reloader *and* a worker, so a loop inside the application
fires **twice**; a loop dies with its process and says nothing; and it makes
the API responsible for wall-clock time, which the operating system already
does. `POST /social/celebration/run` calls the same function on demand, so
the scheduled path and the manual path cannot drift into two behaviours.

Detection is **SQL, not a model**: `anniversaries_today()` matches
`extract(month/day)` against today and requires a completed year, so an
ordinary day with nobody celebrating costs zero model calls. A `hire_date` of
NULL is skipped, and a leap-day hire is picked up on 1 March in a common year -
the same day `_next_anniversary()` moves them to, so the two halves agree.

**Each employee gets their own run of the graph and their own draft row.**
Three anniversaries today are three celebrations, never one post listing
three people.

### Duplicate protection is a constraint, not a check

`celebration_drafts` carries `UNIQUE (employee_id, occasion, occasion_date)`,
so a second run of the day **cannot** create a second celebration for the same
person's same anniversary - Postgres refuses it, the way
`social_reactions UNIQUE (post_id, user_id)` makes a like idempotent. The
service looks for the row first as well, so the second run spends no model
calls; the constraint is what holds when two runs race past that check, and
`run_daily()` catches the `IntegrityError` and counts it as "already
prepared" rather than as a failure.

`no_occasion` is a stored status rather than a skipped row, so a day on which
the agent found nothing is remembered instead of being re-asked of the model
on every run.

### It generates; a person publishes

There is **no automatic publishing anywhere**. The sweep writes a `pending`
draft and stops. A celebration reaches the feed only through
`approve_draft()`, which takes the signed-in recruiter and calls
`social_service.create_post()` - so the post is moderated and attributed to
*them*, exactly as a post they typed, and the router writes the
`ENTITY_SOCIAL_POST` audit row immediately afterwards.

**That audit row is written by the router, not by `create_post()`**, which is
easy to get wrong: `app/routers/social.py` writes its own after its commit,
so a service-level caller that forgets it produces the one post in SmartHR
that reaches the feed untraced. The first end-to-end run of this feature did
exactly that, and the audit count is what caught it - the assertion that
should have caught it earlier used `>=`, which passes whatever happens. The scheduler has no
`User` and therefore cannot reach that path at all, which
`test_celebration_scheduler.py` asserts by parsing the module and requiring
that exactly one function - `approve_draft` - calls `create_post`.

**The Review Agent's veto survives into this half.** A draft it rejected is
still stored (so "the AI tried and could not" is distinguishable from
"nothing happened"), is marked `postable: false` by the server, is offered no
Post button, and is refused with 409 if somebody posts its id anyway.

### RBAC

`require_roles(1, 2)` - Admin and HR, because the workflow reads any
employee's hire date and job title, which is `/employees/`-grade data.
Manager, Employee and Applicant get 403, measured. Its **own router** rather
than a route inside `app/routers/social.py`: that file is guarded with
`require_staff` (roles 1-4) at the router, and two different access rules in
one file is how one of them is eventually forgotten. The path still sits
under `/social/` because it is a Social Hub feature.

Frontend: `pages/social/CelebrationPanel.tsx`, one card in the feed's rail,
shown when `status.me.role_id` is 1 or 2. That is convenience, not security -
the guard is the boundary - and `SocialFeedPage` is otherwise unchanged apart
from the block that renders it.

### Tests

```powershell
venv\Scripts\python.exe -m scripts.test_celebration_agents          # 108, offline
venv\Scripts\python.exe -m scripts.test_celebration_agents --live   # + the real model
venv\Scripts\python.exe -m scripts.test_celebration_scheduler       # 59, offline
venv\Scripts\python.exe -m scripts.test_celebration_occasions       # 71, the six occasions
```

`test_celebration_scheduler.py` covers only what the sweep added - detection
(including the employee with no `hire_date`, the one celebrating tomorrow and
the one hired today), one workflow per employee, idempotence proved by a
**model-call counter** rather than by inspection, the UNIQUE constraint
refusing a hand-written duplicate, and HR's approve/dismiss. It also asserts
that a full sweep writes no `social_posts` row.

Offline and in-process. The model is replaced by a **fake provider**
implementing `provider.py`'s two methods - not by clearing
`SMARTHR_LLM_API_KEY`, which `_setting` treats as absent before falling
through to `.env` and the real key. Everything downstream of the model is
real: the prompts, the tool schemas, the Pydantic validation, the compiled
graph, the service and the database.

The fake returns a **list** per tool, consumed in order, so "reject the first
draft, approve the second" exercises the loop rather than asserting it
exists. Covered: the tools and their window arithmetic, each agent's
validation, the approved path, the no-occasion path (the writer and reviewer
never run), rejection and retry, the retry limit stopping at exactly
`MAX_RETRIES`, an unreachable model, an unreachable reviewer, an empty draft,
and containment, plus the fenced-JSON salvage and the omission of null
facts described above.

`--live` adds one real run plus the two rejection cases above. It is an
integration test: its failure means the model or a prompt moved.

**Not covered:** whether the real model always chooses well. Its judgement is
sampled by `--live`, not guaranteed, which is why the Review Agent exists and
why a person still presses Post.

## AI Interview (rebuild)

A new implementation, built phase by phase. **Phases 1-6 exist**: an applicant
joins a LiveKit Cloud room (Phase 1, voice foundation), holds a real-time
spoken conversation with correct turn-taking (Phase 2), is asked the
Question Bank's MAIN questions in a fixed order (Phase 3), for one of their
own scheduled interviews, with the interviewer aware of that interview's job
(Phase 4), of the applicant's CV (Phase 5) and of SmartHR's existing
matching result for that candidate and job (Phase 6); every accepted answer is
stored by the backend and analysed by GPT-4o into a structured, evidence-only
reading for HR (Phase 7), which HR reads as an Interview Report (Phase 8). No
follow-up generation, HR decision workflow, scheduling or camera yet.

```
AiInterviewPage (app-ai-interview)
  -> POST /ai-interview/session       role 5 via get_current_candidate
       app/services/ai_interview_service.py   mints the LiveKit token
  -> LiveKit Cloud room               microphone audio both ways
  -> app/ai/interview/worker.py       separate process, livekit-agents 1.8
       VAD (local) -> STT -> openai/gpt-4o -> TTS    all via LiveKit Inference
```

```powershell
venv\Scripts\python.exe -m app.ai.interview.worker dev      # the agent worker
venv\Scripts\python.exe -m scripts.test_ai_interview_foundation   # 94 checks, offline
venv\Scripts\python.exe -m scripts.test_ai_interview_turns        # 83 checks, offline
venv\Scripts\python.exe -m scripts.test_ai_interview_questions    # 77 checks, offline (progress, directives, reply shaping, split answers)
venv\Scripts\python.exe -m scripts.test_ai_interview_question_bank  # 77 checks, own server on 8045 (CRUD, RBAC, agent plan)
venv\Scripts\python.exe -m scripts.test_ai_interview_job_context    # 83 checks, offline + own server on 8046 (Phase 4)
venv\Scripts\python.exe -m scripts.test_ai_interview_cv_context     # 85 checks, no model; --live parses a real CV (89) - own server on 8047
venv\Scripts\python.exe -m scripts.test_ai_interview_matching_context  # 126 checks, no model; --live parses a real CV (131) - own server on 8049
venv\Scripts\python.exe -m scripts.test_ai_interview_answers           # 166 checks, no model, no LiveKit - own server on 8050 (Phase 7)
venv\Scripts\python.exe -m scripts.test_ai_interview_report            # 75 checks, no model, no LiveKit - own server on 8051 (Phase 8)
venv\Scripts\python.exe -m scripts.test_ai_interview_follow_ups        # 88 checks, no model, no LiveKit (Phase 11.1)
venv\Scripts\python.exe -m scripts.test_ai_interview_adaptive          # 81 checks, no model, no LiveKit (Phase 11.2)
venv\Scripts\python.exe -m scripts.test_ai_interview_grounding         # 36 checks, no model, no LiveKit, no DB (Phase 11.3)
venv\Scripts\python.exe -m scripts.test_ai_interview_report_flow       # 42 checks, no model, no LiveKit - own server on 8056 (Phase 11.4)
venv\Scripts\python.exe -m scripts.test_ai_interview_analytics         # 32 checks, no model, no LiveKit - own server on 8057 (Phase 11.5.3)
venv\Scripts\python.exe -m scripts.test_ai_interview_turn_taking       # 44 checks, offline (Phase 11.6.2)
venv\Scripts\python.exe -m scripts.test_ai_interview_voice_recovery    # 101 checks, offline (Phase 11.6.3)
venv\Scripts\python.exe -m scripts.test_ai_interview_state_integrity   # 48 checks, offline (Phase 11.6.4)
venv\Scripts\python.exe -m scripts.test_ai_interview_observability     # 107 checks, offline (Phase 11.6.5)
venv\Scripts\python.exe -m scripts.test_ai_interview_multi_agent       # 80 checks, fake model, own server on 8058 (Phase 12)
venv\Scripts\python.exe -m scripts.test_ai_interview_utterance_classifier  # 55 checks, classifier unit tests
venv\Scripts\python.exe -m scripts.test_ai_interview_turn_labels       # 85 checks, turn state machine / never silent / welcome / capture
venv\Scripts\python.exe -m scripts.test_ai_interview_simulated        # 36 checks, real AgentSession + fakes (~40 s)
venv\Scripts\python.exe -m scripts.check_stt_arabic                  # REAL LiveKit Inference calls: Arabic STT per model
cd frontend; npx tsx scripts/check-ai-report.ts                          # report UI: labels en+ar, RTL, sections
venv\Scripts\python.exe -m scripts.test_ai_interview_workflow          # 105 checks, no model, no LiveKit - own server on 8052 (Phase 9)

venv\Scripts\python.exe -m scripts.seed_interview_questions       # 12 MAIN + 2 FOLLOW_UP test questions (--dry-run, --remove)
venv\Scripts\python.exe -m scripts.verify_ai_interview_voice      # live loop, needs creds + worker
venv\Scripts\python.exe -m scripts.verify_ai_interview_turns      # 11 live scenarios incl. `job`, `split`, `cv` (--only cv); needs :8000 + worker
venv\Scripts\python.exe -m scripts.verify_ai_interview_browser    # real browser flow with a local applicant fixture; needs :8000 + :3000
```

**Turn-taking (Phase 2) is four separate mechanisms**, all in
`app/ai/interview/turn_policy.py` with every number justified there: local
**VAD** (is there speech?), LiveKit's **turn detector** model (finished, or
only pausing?), **endpointing** delays (`min_delay` 1.2 s after a
finished-sounding sentence, `max_delay` 4.0 s when mid-thought), and
`classify_utterance()` (empty / filler / short / answer). `min_delay` was
**measured**, not guessed: at 0.6 s a five-sentence answer was split into four
turns by the ~0.6 s gaps between sentences. Filler/empty turns are refused in
`InterviewerAgent.on_user_turn_completed` with `StopResponse`, so GPT-4o never
sees them; a short turn gets a system note in the *temporary* turn context.

**The interview state machine is Python, not prompt** (`state.py`):
WAITING, INTRO, ASKING, LISTENING, PROCESSING, SPEAKING, ENDING, COMPLETED,
with an explicit `TRANSITIONS` table; an illegal move raises. `controller.py`
drives it from LiveKit's `agent_state_changed` / `user_state_changed` /
`speech_created` events, runs the fixed opening (welcome not interruptible,
question interruptible), gives ONE model-free nudge after 15 s of silence,
ends at `SMARTHR_INTERVIEW_MAX_SECONDS` (default 600), and publishes
`smarthr.interview.state` / `smarthr.interview.turns` (counts only) as the
agent's participant attributes - which the page and the live tests read.
Two traps it already hit: every transition must go through
`controller.set_state` (the agent receives it as `set_state`) or it is never
published; and an interruption counts only if the interviewer was audibly
speaking - LiveKit's *preemptive* speculative replies are discarded unheard
and must not count. `ctx.room.local_participant` does not exist until
`session.start()` has connected, so it is resolved lazily.

Provider model availability changes over time. Configure a currently supported text model through local environment settings and keep service incident details in private operational notes.

**Credentials: env -> `.env.local` -> `.env`, for this feature only.**
`LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` live in `.env.local`
(fill with `lk app env -w -e livekit.env.example`). `app/ai/interview/config.py`
adds the `.env.local` layer; `app/ai/config.py` is **untouched**, so the
assistant, agents, moderation and Celebration still read only env + `.env`.
The worker exports exactly those three into its own `os.environ`, because
LiveKit Inference reads them from there. No OpenAI key is used on this path.

**The token is the security boundary** (`mint_applicant_token`): one random
room, `can_publish_sources=["microphone", "camera"]` (Stage 4A video), no data publishing, no metadata,
display name "Applicant", identity `applicant-<candidate id>`, 10-minute
join window, and a `RoomAgentDispatch` naming `smarthr-interviewer`. The
worker registers under that name, so LiveKit sends it only into rooms whose
token asks for it. No name, email, CV or job reaches LiveKit.

**The worker never touches the database** - nothing in `app/ai/interview/`
imports `app.models`, `app.database` or SQLAlchemy; the foundation suite
parses the files to assert it. Later phases give the worker a trimmed context
over HTTP. Worker logs carry room names, states and word counts, never what
was said.

`/ai-interview/*` is its own prefix so it can never collide with the
recruitment `/interviews/{interview_id}` route.

### Question Bank (Phase 3)

`interview_questions` (`migrations/2026-09-26_ai_interview_question_bank.sql`,
`InterviewQuestion` in `app/models.py`): `question_text` (English, 5-500 chars)
and `question_text_ar` (Arabic, 5-500 chars),
`category` (general / behavioral / technical / situational / role_specific),
`difficulty` (easy / medium / hard), `question_type` (`main` / `follow_up`),
`evaluation_focus`, `parent_question_id`, `position`, `is_active`, timestamps.
Lowercase tokens, and every vocabulary is a CHECK constraint as well as a
service-level validation (422, not an IntegrityError). A `follow_up` must have
a parent and a `main` must not - also a CHECK. Follow-ups are asked since
Phase 11.1 - see **Follow-up questions (Phase 11.1)**.

`/ai-interview/questions` (`app/routers/interview_questions.py`,
`app/services/question_bank_service.py`): list / create / get / partial update /
`PATCH /{id}/status`. **Roles 1-2 only on every route**; Manager, Employee and
Applicant get 403. There is **no DELETE** - a question an interview may already
have asked is deactivated, not erased. Audited as `InterviewQuestion`
(CREATE / UPDATE / ACTIVATE / DEACTIVATE; a no-op status change writes nothing).
No HR page yet - API only.

**The interview plan is deterministic**: active `main` questions ordered by
`(position, id)`, the first `SMARTHR_INTERVIEW_QUESTION_COUNT` (default 5,
1-20). Each database row remains one logical question id; the protected agent
plan selects its English or Arabic text from the bound session language.
Follow-ups and adaptive ordering use those same logical ids and selected text.
Missing Arabic text refuses an Arabic plan rather than silently asking English.
Question Bank create requires both language variants, and changing English
text requires its Arabic counterpart in the same update. No randomness was
added; adaptive choice still selects an id from the same plan.

**How the worker gets it without a database.** `POST /ai-interview/agent/plan`
takes a Bearer **agent token** (`app/ai/interview/agent_auth.py`): a 2-minute
LiveKit JWT signed with the existing LiveKit secret, identity
`smarthr-interview-agent`, `agent=True`, no join/publish/subscribe grants,
scoped to one `smarthr-ai-interview-*` room. No new secret. An applicant's room
token is refused (403). The plan carries id, position, category and text only.
`plan_client.py` fetches it from `SMARTHR_INTERVIEW_BACKEND_URL`
(default `http://127.0.0.1:8000`) before the session starts; if that fails the
interviewer says it cannot start and ends - it never improvises questions.

**GPT-4o never chooses a MAIN question.** `questions.QuestionProgress` holds the
plan and the current index, records each answer against the question that
caused it (in memory only), then decides `advance` / `elaborate` (a short
answer, at most once per question) / `finish`. The agent attaches that decision
to the turn as a system message (`extra["smarthr_directive"]`, a plain dict),
and `InterviewerAgent.llm_node` enforces it: for `advance`/`finish`, GPT-4o's
text is cut to at most two non-question sentences (an acknowledgement) and the
next bank question - or the closing line - is appended **verbatim by code**.
Q1 is spoken with `session.say` and never reaches the model. Preemptive
generation is **off** (`turn_policy.PREEMPTIVE_GENERATION`), so the model
always sees the completed answer together with its directive. The page reads
`smarthr.interview.question` (`{number, total}`) and shows "Question N of M".

**A decision is provisional until it is heard.** If the turn detector ends
the turn at a pause inside an answer and the applicant keeps talking, LiveKit
cancels the reply before any audio plays (agent thinking -> listening). The
controller then `reopen`s the decision: the question does not advance, and the
next turn is merged into the same answer (`QuestionProgress.resumed`) - even a
filler-only tail. Without this, the rest of the answer was recorded against
the next question and that question was never asked (seen live in `long`).

Known limitations: "can you repeat that?" is recorded as an answer and
advances; interrupting the acknowledgement+question reply still advances.

### Job Context (Phase 4)

**A session is for one interview.** `GET /ai-interview/interviews` lists the
caller's own interviews whose status is `scheduled` or `in_progress` (id, job
title, time, status). `POST /ai-interview/session` takes `{interview_id}` and
an optional `language` (`en` or `ar`); other fields are rejected
(`extra="forbid"`). Ownership is in the query -
`interviews -> applications.candidate_id = caller` - so another applicant's
interview is the same 404 as a missing one. The browser never names a job:
the job is whatever the application points at.

`app/services/interview_context_service.py` resolves it and records the room
in **`ai_interview_sessions`** (`migrations/2026-09-26_ai_interview_sessions.sql`):
`room_name` UNIQUE, `interview_id`, `candidate_id`, `created_at`, `expires_at`
(the token's join window), and optional `language` (`en` / `ar`). One row per
session, no conversation data; the job/application/interview rows are not
copied. Timestamps are **UTC**
(`datetime.utcnow`) - Postgres `now()` here is local time, so compare with
Python's clock, not SQL's.

The applicant selects English or Arabic before a session is created. That
language is stored on the room binding and returned only by the protected
agent plan endpoint. The worker uses it for STT, TTS and GPT-generated
interviewer replies; the protected plan selects the matching Question Bank
variants, and fixed spoken phrases are localized. A missing value (including
legacy sessions) falls back to `SMARTHR_INTERVIEW_LANGUAGE` and then the
existing `en` default. TTS remains `cartesia/sonic-3` unless configured
otherwise; that model supports `en` and `ar`, and Arabic is refused explicitly
for any model not in the worker's verified Arabic-TTS allowlist.

**The worker gets the job through the same call as the questions.**
`POST /ai-interview/agent/plan` returns the room's stored language alongside
`job`: it looks the room up in
`ai_interview_sessions`, **re-checks** the live rows (still that candidate's
application? still scheduled/in progress? binding not expired?) and answers
404 otherwise - no binding, no interview. The worker cannot ask for a job; it
names only the room, inside its signed agent token. Nothing about the job or
the interview goes into LiveKit metadata (asserted in the tests).

The **Job Context** is built field by field (`job_context()`): `job_id`,
`title`, `department`, `employment_type`, `description`, `requirements` (the
posting split by `requirement_tokens()`, so each item is a literal phrase).
`jobs` has no responsibilities or skills column; nothing is invented to fill
one. Not included: status, created_by, location, deadline, counts, the
application's stage, `interviews.notes`, the interviewer, anything about the
candidate. `app/ai/interview/job_context.py` re-validates it in the worker and
drops unknown keys.

**How it reaches GPT-4o:** one delimited block appended to the agent's
instructions (`build_instructions`), labelled as data, telling GPT-4o it may
name the role and note relevance but must not quiz on requirements or judge
fit. The welcome names the title - spoken by code, not GPT-4o. The Question
Bank is still the only source of MAIN questions: `llm_node` still drops
question-like sentences and appends the bank's next question verbatim, and
the short-answer note forbids turning elaboration into a requirements
question. The bank is not per-job yet: every job gets the same questions.

Test fixtures: `test_helpers.ensure_ai_interview(token)` applies to an
EXISTING job ("DEMO - AI Engineering Intern" by default) and has HR schedule
the interview through the real endpoints, reusing both on later runs; it
stores a minimal fixture CV through `cv_storage` because applying requires
one.

### CV Context (Phase 5)

**No new CV system.** `cvs` stores file metadata only (no text, no parsed
fields), so the structured CV is re-derived from the stored file by the one
pipeline, `analyse_cv_bytes()` -> `ParsedCv`. `app/services/interview_cv_service.py`
resolves room -> interview -> application -> **candidate** (`resolve_room`,
the same re-checked binding as the Job Context) -> that candidate's **latest**
CV - SmartHR's existing rule everywhere (`ORDER BY uploaded_at DESC, id DESC`,
`screening_service.latest_cv`). A candidate may have several CVs; applications
carry no cv_id. The stored path must resolve inside `uploads/cvs/`.

`POST /ai-interview/agent/cv` - same agent token, same room binding, 404 for
an unbound / expired / no-longer-scheduled room - returns
`{"cv": {"status": "available"|"none"|"unavailable", "context": ...}}`. It is a
separate call from `/agent/plan` only because parsing is a model call: the
backend starts it when the applicant presses Start (`prewarm`, a 2-thread
pool), the worker asks in the background while the welcome and Q1 play, and
`InterviewerAgent.set_cv` adds it to the instructions (`update_instructions`).
Parsed results are cached **in memory only**, keyed by CV row + file
size/mtime, for 30 minutes; nothing CV-derived is written to the database or
logged. `none`/`unavailable` do not stop the interview - the prompt then says
no CV is available.

**The CV Context is a whitelist of ParsedCv** (`cv_context()`): summary,
skills, experience (job_title, company, dates, description, technologies),
education, certifications, languages - trimmed and with empty values omitted.
**Excluded:** full_name, email, phone, home location, each role's location,
file name/path, cv id, upload time, and anything from candidate / application
/ interview rows. ParsedCv has no projects field, so neither does this. The
worker re-validates it (`app/ai/interview/cv_context.py`) and drops unknown
keys. The browser receives nothing CV-related; LiveKit metadata and the
agent's participant attributes carry none of it (asserted live).

**Against invented CV facts**, two layers: the CV block tells GPT-4o the list
is the complete CV context and that what the applicant says is attributed to
the applicant ("you mentioned..."), never to the CV; and in code,
`unsupported_cv_claim` drops any spoken sentence that mentions the CV/resume
while naming a specific term (capitalised, mixed-case, digits, +/#) that is
not in the CV context or the job. It runs on the advance path (inside
`shape_reply`) and the elaborate path (`filter_sentences`). It is a net for
false citations, not a proof - a claim made only in common lowercase words
can pass it. The Question Bank still supplies every MAIN question.

Tests that do not exercise CVs start their servers with
`SMARTHR_LLM_PROVIDER=none`, because every session now prewarms a CV parse.

### Matching Context (Phase 6)

**No new matching.** SmartHR stores no match result; every score is computed
on request by `matching_service.match_skills()`. For a candidate and a job the
existing result is `screening_service.screen_candidate()` - HR's comparison,
the one the AI Screening Agent's `match_candidate_to_job` tool returns - over
`candidate_evidence()`: the candidate's own profile skills plus the skills of
their LATEST CV. `app/services/interview_matching_service.py` calls exactly
that for the room's candidate and job (`resolve_room`, the same re-checked
binding as Job and CV Context) and keeps three of its fields, under their
existing names: `score`, `matching_skills` (the candidate's wording),
`skill_gaps` (the job's wording). Not sent: matched_requirements,
additional_skills, basis, disclaimers, the evidence dump (CV id / file name),
the candidate and job views.

**The CV is parsed once.** `screen_candidate` would read the CV itself; the
interview already parsed that CV for its CV Context, so `interview_cv_service`
now also caches the ParsedCv (`CvResult.parsed`, contact fields cleared,
memory only, never serialised) and passes it through the one small change to
screening: `candidate_evidence(..., parsed_cv=...)`, used exactly where
`_read_cv`'s result would be.

`POST /ai-interview/agent/matching` - same agent token, same 404 for an
unbound / expired / cancelled room - returns
`{"matching": {"status": "available"|"unavailable", "context": ...}}`. The
worker asks right after the CV (`_load_candidate_context`) and
`InterviewerAgent.set_matching` adds a delimited MATCHING block after the JOB
and CV blocks. **No result, no context - never a 0**: `unavailable` when the
candidate has no profile skills and no readable CV (screen_candidate itself
refuses to score), when the job lists no requirements, or when a CV is on file
but could not be analysed right now (the thinner profile-only result is not
presented as the match). The prompt then says none is available. A REAL 0
(evidence exists, nothing covered) is sent as the result it is.

**A signal, not a verdict.** The block tells GPT-4o the score is a text-overlap
signal, never to mention / recalculate it, that matching skills are not proof
of ability, that gaps only mean the evidence did not mention something (the
applicant's own statement is not contradicted), not to ask about gaps, and
never to imply hire / reject / offer / pass / fail / suitability. In code,
`matching_context.decision_or_score_claim` drops any spoken sentence stating a
score, percentage or match, a hiring verdict, or "you lack / don't know / have
no experience" - on both reply paths, beside the CV guard
(`InterviewerAgent.drops_sentence`). The Question Bank still supplies every
MAIN question. Nothing about matching reaches the browser or LiveKit metadata.

The applicant's own Opportunities page scores on profile skills only
(`match_skills(candidates.skills, ...)`), so it can show a different number
from the interview's HR-side result when the CV adds skills. That is the
existing difference between the two views, not a new one.

### Answers & Analysis (Phase 7)

**Persistence.** An answer is FINAL once the next question in the reply to it
has been HEARD (`QuestionProgress.commit`, from the reply's speech handle:
finished, or interrupted after the whole question was played - the same rule
as a re-ask / skip; the closing line after the last answer still commits when
it starts) - before that it may still be reopened and merged with the rest of
a paused answer. Committing is what sends it to the backend, which has no way
to take an answer back, so the send is HELD rather than retracted. If the next
question is cut off while the applicant talks, their turn is merged into the
pending answer; if it is cut off with nobody talking (playback failure), the
same question is spoken again ("Let me repeat the question.") and must be
heard before the answer is sent. `commit` numbers final answers in order (`sequence`, 1-based,
never reused) and the controller hands them to `on_commit`; `flush` (called
from the worker's shutdown callback) makes whatever is left final - an answer
whose reply never played (time limit, applicant left) and the first half of a
reopened answer whose rest never came. Ignored filler, a turn cut by a pause
and an interruption never become answers of their own.

`app/ai/interview/answer_client.py` (`AnswerSink`) posts each final answer to
`POST /ai-interview/agent/answers` - same agent token, one at a time, in
order, retried on network errors / 5xx, never on 4xx, drained for at most 8 s
at shutdown (livekit-agents allows a job 10 s). The body is six fields:
`question_id`, `question_number`, `sequence`, `kind`, `transcript`,
`answered_at` - `extra="forbid"`, so a `candidate_id`, `interview_id` or
`question_text` is a 422. The backend (`interview_answer_service`) resolves
room -> session -> interview through `resolve_binding` (the refactored core
of `resolve_room`, with a **grace period** of the interview's max length +
5 min after the JOIN window, because an interview outlives it), requires the
id to be the bank plan's question at that number (409 otherwise), and copies
`question_text` **from the bank row**. The transcript is stored exactly as
accepted.

**Duplicates are a constraint**: `UNIQUE (session_id, sequence)` on
`ai_interview_answers`. A retry of the same answer is 200 `created: false`;
different content under a used sequence is 409, so nothing can overwrite a
stored answer. Rows are never updated.

**Analysis** (`app/ai/interview_analysis.py`, `interview_analysis_service.py`)
follows `cv_parser.py`'s shape: one tool call (`record_answer_analysis`),
validated. Input: the stored question and transcript (plus earlier parts of
the same question's answer), the Job Context, the CV Context and the matching
skills / skill gaps - each from its phase's own builder. **The Match Score is
never sent**, so there is nothing to restate or recalculate. The schema has no
field for a score, rating, match or decision (asserted); `addresses_question`,
`summary`, `evidence[{point, quote, type}]`, `skills_mentioned[{skill, quote}]`
(stored with `source: applicant_statement`), `job_requirements_referenced`,
`cv_relation[{statement, also_in_cv|not_in_cv}]`, `specificity`, `clarity`,
`not_covered`, plus `meta` (version, which contexts were present, what the
guards removed, `is_hiring_decision: false`). Validation drops any quote not
in the transcript, any "requirement" not in the job, `cv_relation` without a
CV, any sentence with a verdict / score / "lacks" (`verdict_claim` plus the
interviewer's `decision_or_score_claim`) or naming a specific term found in
none of the inputs; an unknown enum refuses the whole result. No temperature
is set (`provider.py` has none and is shared) - stability comes from the
schema, the validation, and storing a completed analysis once.

It runs in the background after each new answer (a 2-thread pool, like the CV
prewarm) and again only when HR asks. No model / a model error / invalid
output is stored as `failed` with its code, never as a guess.
`JSONB(none_as_null=True)` on `analysis` matters: without it a failed row
stores JSON `null` and breaks the `(status='completed') = (analysis IS NOT
NULL)` CHECK.

Review routes, **Admin and HR only** (Manager, Employee, Applicant 403):
`GET /ai-interview/answers/{interview_id}` (sessions -> answers in order ->
analysis) and `POST /ai-interview/answers/{interview_id}/analyse[?force=true]`.
No frontend page yet. Nothing about answers reaches the browser's session or
LiveKit metadata; the worker logs sequence numbers and status codes, the
backend ids and word counts - never a transcript.

### Interview Report (Phase 8)

`app/services/interview_report_service.py` -> `GET /ai-interview/report/{interview_id}[?session_id=]`,
**Admin and HR only** (Manager, Employee, Applicant 403 - including the
applicant whose interview it is). Opened from the HR Interviews page
("View AI Interview Report" on every card) as
`components/ai/InterviewReportModal.tsx`; no PageId, no sidebar entry.

**Read-only and deterministic, no model call.** The report is the stored
Phase 7 rows reshaped: (A) job, department, `scheduled_at`, interview status,
`answered_count`, `highest_question_reached`; (B) each answer with its bank
question, exact transcript and the nine stored analysis fields (never the
stored `meta`); (C) counts of `addresses_question`, the job's requirement
phrases referenced / not referenced, skills (as the applicant's statement),
up to 20 evidence quotes, not-covered items. **No score, rating, percentage,
ranking or decision field exists**, and `is_hiring_decision` is false.

**One session, never merged.** Default: the latest session with answers;
`session_id` picks another; a session that is not one of THIS interview's
answered sessions is a 404. No answered session is a valid report with
`meta.state = "no_answers"`.

**Missing is not negative.** Failed / pending analyses are counted as such and
contribute to no aggregate - never to "not addressed". With no completed
analysis, "requirements not referenced" is empty and
`requirements_basis = "no_completed_analyses"`; with some, `complete: false`.
The UI renders "Not analysed" / "Not analysed yet" and offers **Re-run
analysis**, which is the existing `POST /ai-interview/answers/{id}/analyse`.

**No planned total.** The number of questions planned for a session is not
stored and the current bank may differ, so the report never says "N of M".

The button shows on every interview card: nothing in the interview list says
whether AI answers exist, and they survive any status change, so the modal's
"No AI Interview answers recorded" state is the answer for the rest. Counts are
one neutral badge style - "Not addressed" is not coloured as a mark against a
person. Transcripts and AI text render as stored (`dir="auto"`), untranslated;
labels are `hr.aiReport.*` in `dictionaries/hr.ts`.

### Workflow controls (Phase 9)

The recruitment workflow decides when an AI Interview may be held; nothing
in the frontend is relied on. One rule, `interview_context_service.ineligibility()`,
used by `POST /ai-interview/session` (checked against now) and by
`resolve_binding` - every agent call - (checked against when the room's
session was started):

1. **status** `scheduled` or `in_progress` - a `completed` interview cannot be
   started again (409 `completed`); cancelled is the old 404;
2. **HR approval** = the application's stage is `interview` (409
   `not_approved`). Moving the candidate on or back closes an open room too;
3. **start window** around `scheduled_at` - `SMARTHR_INTERVIEW_EARLY_MINUTES`
   (15) before to `SMARTHR_INTERVIEW_LATE_MINUTES` (30) after, env ->
   `.env.local` -> `.env` (409 `too_early` / `too_late`, naming the time).
   `scheduled_at` is LOCAL time (what HR typed; the dashboards compare it with
   `datetime.now()`), while `ai_interview_sessions` is UTC - `utc_to_local`
   bridges them. Rescheduling an interview closes a room started before it.

`GET /ai-interview/interviews` lists open, HR-approved interviews **without**
the window filter, so an upcoming one is visible and starting it early says
when it opens. The applicant's Applications page shows its AI button from the
same list.

**Status follows the agent, not the page** (`interview_progress_service`,
`POST /ai-interview/agent/progress`, agent token, body `{event}` only). The
worker (`progress_client.py`) reports `started` BEFORE fetching the plan
(scheduled -> in_progress; refused = the interview does not go ahead) and,
after draining the answers, `completed` (the closing line after the last
question or the time limit -> completed) or `ended` (anything else - the
applicant left, an error -> back to scheduled, answers kept). Opening the
page, listing, creating a session or a refused start change nothing. Each
change writes a `STATUS_CHANGE` / `Interview` audit row with no user.

**One running session per interview, with no new column.** `in_progress`
means "an agent is running it now": a Start is refused (409 `session_active`)
while the interview is in_progress and its newest session is within the
answer grace. Only the NEWEST session may report progress (older rooms get
409), so a second Start before the first agent joined supersedes the first
room. A crashed worker that never reports stops blocking once its session is
past the grace (join TTL + max length + 5 min). Analysis and the report read
stored rows, never the eligibility rule, so completing an interview does not
affect them.

**At most 2 STARTED attempts per interview** (`MAX_STARTED_ATTEMPTS`,
Phase 10). An attempt = a session whose agent's `started` report was
accepted. A room created and never joined, or whose agent was refused, is
not one. With no column for it, acceptance writes ONE `audit_logs` row
(STATUS_CHANGE / `AiInterviewSession` / session id, no user) **in the same
transaction** as in_progress - directly, not via best-effort `record_audit` -
and `started_attempts()` counts the interview's session rows that have one.
Checked on Start (409 `attempts_exhausted`) and on the agent's `started`
(409), so refreshing or extra rooms cannot get a third run; a started
session re-reporting `started` after its attempt ended is refused
(`attempt_finished`), since its join token may still be valid. `/session`
refusals are `{"detail", "code"}` - `code` for the page to translate. There is
no HR action to grant more attempts; sessions started before this rule have
no record and do not count.

### Permanent development AI Interview

Use a synthetic applicant account when verifying interview-session reuse; do not tie interview operations to a real account.

```powershell
venv\Scripts\python.exe -m scripts.ensure_permanent_ai_interview
```

The marker is recognized only outside production. The AI Interview list always
includes it for its owning Applicant and labels it as a development test.
Session start still creates a fresh `ai_interview_sessions` binding and a
random LiveKit room, but reuses the same Interview ID. When a test run ends,
the status returns to `TEST`; after a completed run, the next explicit Start
resets it to `TEST`. Test runs do not consume the ordinary two-attempt limit.
The usual per-room LiveKit token and `smarthr-interviewer` dispatch are
unchanged. Real interviews retain the normal stage, time-window, completion
and attempt rules.

The local-only frontend contract check is
`cd frontend; npx tsx scripts/check-ai-interview-permanent-test.ts`. Backend
state-transition coverage is included in
`venv\Scripts\python.exe -m scripts.test_ai_interview_state_integrity`.

### Follow-up questions (Phase 11.1)

A MAIN question may be followed by ONE predefined follow-up from the Question
Bank, then the interview moves on to the next main question. The main
questions and their order are unchanged; `interview_plan` only attaches
`follow_up` to each - the first ACTIVE `follow_up` row whose
`parent_question_id` is that main question, by (position, id), or None.

**GPT-4o decides yes/no, never the words.** `app/ai/interview/follow_up.py`
makes one forced call to a one-field tool,
`record_follow_up_decision({"ask_follow_up": <bool>})`, showing the main
question, the answer and the candidate follow-up as delimited data.
`parse_decision` accepts exactly that one key with a real boolean; an extra
field (e.g. a "question"), a string, prose, no tool call, an error or the 4 s
timeout all mean "no". The follow-up's text is the bank row's, appended
verbatim by `llm_node`/`shape_reply`, which still drops any question GPT-4o
writes.

**When.** Only when an answer to a main question would otherwise move on (a
short answer still earns its one elaboration first), the main question has a
follow-up, and it has not been asked: `QuestionProgress.follow_up_candidate`.
Then the state goes PROCESSING -> **FOLLOW_UP_DECISION** -> ASKING (the
follow-up, or the next main question - both are bank questions spoken
verbatim). A follow-up's answer always moves on: no elaboration, no second
follow-up (`followed_up`), so no loop. A decision whose reply was cancelled
unheard is undone like any other and decided again on the merged answer. No
decider configured = exactly the earlier behaviour.

**Storage.** A follow-up answer is stored with the follow-up's own
`question_id`, the bank's follow-up text, under the MAIN question's
`question_number` (the page still says "Question N of M"). The backend accepts
it only if it is the plan's follow-up for that number (409 otherwise). The
type is read from the bank row, not stored: `question_type` in the answers
view and the report, labelled "Follow-up to question N" in the HR modal.
Analysis is unchanged - the follow-up answer is analysed with its own question
and transcript.

Cost: one extra GPT-4o call per main question that HAS an eligible follow-up
(two in the seeded bank), which adds its latency before that reply.

### Adaptive question order (Phase 11.2)

When NO follow-up is asked, GPT-4o may choose WHICH predefined main question
comes next - by Question Bank id, never by text. `app/ai/interview/adaptive.py`
makes one forced call to `select_next_question({"next_question_id": <int>})`,
showing only the current main question, the answer and the plan's main
questions not asked yet (id | category | bank text) as delimited data - no
CV, job or match. `parse_choice` accepts exactly that one key holding an int
that is one of the offered ids; the controller and `QuestionProgress` check it
again. Question text, an id outside the offered list (hallucinated, already
asked, inactive, a follow-up, not in this plan), a string/bool/float, prose,
no tool call, an error or the 4 s timeout all fall back to the **Question
Bank's own order** (the first main question not yet asked), which is also what
happens with no selector configured.

**When.** Only after the follow-up path is ruled out (no eligible follow-up,
or its decision was "no") and only when two or more main questions are left.
State: PROCESSING or FOLLOW_UP_DECISION -> **ADAPTIVE_SELECTION** -> ASKING.
After a follow-up's answer the next main question is always the bank's order
(Phase 11.1 unchanged; enforced in `decide`, not only in the flow).
`QuestionProgress.asked` holds the plan indices in the order asked: nothing is
asked twice, and the interview ends after `total` main questions.

**Numbering.** `question_number` is the order HEARD ("Question N of M"), as
the model column always said; with no adaptive choice that equals the plan
position, as before. The backend therefore checks consistency instead of
position (`_plan_question_text`): the id is a main question of the current
plan or the plan follow-up of one; within a session a main question keeps one
number and a number holds one main question (no revisits); a follow-up sits
under its own main question's number. The report's "highest question reached"
is then the number of main questions asked.

Cost: at most one extra GPT-4o call per answered main question with two or
more questions left (3 in a 5-question plan), in addition to the Phase 11.1
follow-up call; a declined follow-up plus a selection is two calls before
that reply.

### Grounded adaptive selection (Phase 11.3)

The Phase 11.2 selector is also shown the interview's Job, CV and Matching
context - the objects the worker ALREADY holds (fetched by `/agent/plan`,
`/agent/cv`, `/agent/matching` and re-validated by the Phase 4/5/6 parsers);
nothing new is fetched and the worker still never reads the database.
`adaptive.grounding_from` builds a `SelectorGrounding` field by field:

* Job: title, department, employment type, description, requirements (never `job_id`);
* CV: summary, skills, experience (title, company, description, technologies),
  education, certifications, languages - the Phase 5 whitelist, so no name,
  email, phone, location, file path or CV id can be in it;
* Matching: `matching_skills` and `skill_gaps` only - **never the score**
  (`MatchingContext` carries it; the grounding type has no field for it).

They go into `<<<JOB>>>`, `<<<CV>>>`, `<<<MATCHING>>>` data blocks after the
Phase 11.2 ones, only when present; `_neutral` breaks any `<<<`/`>>>` inside
data (the answer included) so nothing can close its block early. The prompt
says the CV is not verified, matching is text overlap not proof, the posting
is exactly as listed, and none of it is a question or a reason to judge.

The contract, the validation and the fallback are Phase 11.2's, unchanged.
`grounded_selector(session.llm, agent)` reads the agent's `job` / `cv` /
`matching` at each choice, so the CV and match - which arrive after the
interview starts - are used once they exist and simply absent before.
Follow-ups (11.1) are still decided first and never see this context.

Cost: no extra call - the same selection call as 11.2 with a longer prompt
(the CV block is the bulk: up to a few hundred tokens more per selection).

### The report as the interview actually ran (Phase 11.4)

`interview_report` adds three derived sections - no migration, nothing
stored, nothing from model output (REPORT_FIELDS now also lists them):

* `question_flow` - one entry per MAIN question in the order heard
  (`question_number`): `main` {question_id, stored question_text,
  `bank_position` in the CURRENT plan or null, `answered`,
  `answer_sequences`} and `follow_up` {id, text, its own `answer_sequences`}
  or null. A main question known only through its follow-up (its own answer
  was not stored) is named from the follow-up's parent row with
  `answered: false` - never an invented answer.
* `coverage` - main questions answered (in order) and count, follow-ups
  answered and count, `highest_main_question_reached`, `not_reached` (main
  questions of the CURRENT plan not answered, `not_reached_basis:
  "current_question_bank"` - the plan a session used is not stored), and
  `order_matches_current_bank` (true / false / null when an answered question
  is no longer in the plan).
* `context` - job / cv / matching booleans from the completed analyses'
  stored `meta.context` (the only part of `meta` read), or all null with
  basis `no_completed_analyses`.

`session` also carries `first_answer_at` / `last_answer_at` and
`duration_recorded: false` - the interview's length is not recorded, so none
is claimed. The HR modal shows an overview with those times, a Coverage
section, a Context section (availability only, "no score"), and a "Question
flow" tab: each main question with its answers, its follow-up nested and
labelled "Follow-up to question N" (English and Arabic).

### Analytics (Phase 11.5.3)

`GET /ai-interview/analytics` (Admin, HR; Manager / Employee / Applicant 403)
-> `app/services/ai_interview_analytics_service.py`. Read-only counts - no
model, no write, no migration - over sessions, answers, analyses and the
Question Bank; the queries select ids, statuses, question numbers and the
stored analysis `meta.context` booleans only, so no transcript, prose,
candidate data or score is ever loaded. Every value is an int, bool or null.

* `overview` - interviews with >= 1 AI Interview session, by CURRENT status
  (cancelled ones are in `total_interviews` but have no bucket);
* `activity` - answers stored; main questions reached = distinct main ids
  per session, summed; follow-up answers stored; highest MAIN question_number;
* `analysis` - completed / failed rows, pending = answers with no row;
* `context` - completed analyses whose stored meta.context flag is true;
* `question_flow` - distinct main / follow-up ids ever answered; `not_reached`
  = main questions of TODAY's plan never answered (the session's plan is not
  stored - no planned total); `order_comparable` = something was answered and
  every answered main question is still in today's plan.

The service takes an internal `interview_ids` scope (not exposed over HTTP)
so the tests can assert exact figures on temporary fixtures only.

Frontend (Phase 11.5.4): `pages/hr/AiInterviewAnalyticsPage.tsx`, PageId
**`hr-ai-interview-analytics`** (HR workspace, so roles 1-2; sidebar entry
"AI Interview Analytics" after Interviews). KPI cards per section, a "not a
hiring decision" notice, loading / error / zero-data states, Matching labelled
"Skills only - no score", and a note that today's Question Bank is not
necessarily a session's original plan. Labels `hr.aiAnalytics.*` in
`dictionaries/hr.ts` (nav/page title in `nav.ts`). Checked by
`cd frontend; npx tsx scripts/check-ai-interview-analytics.ts` (33 checks).

### Voice UX (Phase 11.6.1)

The applicant page (`AiInterviewPage.tsx`) shows only states backed by a real
source. `viewStateOf` in `pages/applicant/aiInterviewRules.ts` folds, in
order: the page phase, LiveKit's `ConnectionState` (`RoomEvent.ConnectionStateChanged`
-> connecting / connected / reconnecting / disconnected), whether the agent is
in the room, the controller's `smarthr.interview.state` and LiveKit's
`lk.agent.state` - into connecting / waiting / reconnecting / speaking /
yourTurn / thinking / ending / stopped / failed; completed is the separate
finished card. A turn strip (interviewer / your turn / thinking, current step
marked with text + `aria-current`), a connection pill, a microphone pill from
`setMicrophoneEnabled`'s real outcome (`micFailureOf` -> blocked / not found /
problem, each with an instruction), and "You are speaking" from LiveKit's
`ParticipantEvent.IsSpeakingChanged`. The level bar is the published track's
AnalyserNode. No exception text is shown; "Try again" is hidden after a final
backend refusal (`FINAL_START_ERRORS`). Checked by
`cd frontend; npx tsx scripts/check-ai-interview-voice-ux.ts` (45 checks).

### Turn-taking hardening (Phase 11.6.2)

The Phase 2 numbers are unchanged (VAD 0.1 s, endpointing 1.2 s / 4.0 s,
barge-in 0.6 s, no preemptive generation). Added:

* **barge-in also needs one transcribed word** (`MIN_INTERRUPTION_WORDS`,
  LiveKit `interruption.min_words`) - noise that makes no words no longer
  stops the interviewer; the 0.6 s threshold still applies;
* **one turn is decided at a time** - `InterviewerAgent._turn_lock` around the
  controller decision (incl. the 11.1 follow-up and 11.2 adaptive calls), and
  before deciding, `controller.absorb_unheard()` reopens a previous decision
  whose reply has not started playing, so a turn that continues an answer is
  MERGED and decided once again instead of being recorded against the next
  question (the "agent went back to listening" path did this already, but only
  if that event arrived first);
* an exact duplicate delivery of an open answer's words is one turn, not
  "words words" (`QuestionProgress._merged`);
* the published question number is the one last SPOKEN (`_spoken_number`, set
  on entering ASKING), not the progress index, which moves at decision time.

`user_turn_limit` is deliberately not configured: it makes the agent reply
mid-answer. A turn ends by endpointing; the nudge and the session time limit
bound the rest.

### Voice error recovery (Phase 11.6.3)

What each failure does - most of it was already the design; the suite pins it:

* **LiveKit drop / reconnect** - the page shows `reconnecting` from LiveKit's
  ConnectionState and returns to the same state; the agent receives nothing
  meanwhile, so nothing is replayed, stored or advanced. A reconnect that
  fails ends the session as `ended` (retriable), never `completed`.
* **Microphone** - blocked / missing / failing are classified from the
  browser's error name; a microphone that stops mid-interview (the track's
  `ended` event) shows the microphone-problem state. No turn, no answer.
* **STT** - no transcript or an empty one is not a turn; nothing is stored or
  decided, the question does not move.
* **Model decisions** - follow-up and adaptive failures fall back (no
  follow-up / bank order) within their timeouts; never stuck in a decision state.
* **TTS** - a reply that never plays is undone (`reopen`): no answer made
  final, no question number published; the next turn joins the same answer.
* **Backend** - answers retried on network / 5xx (not 4xx), idempotent per
  sequence. **Progress reports are now retried too** (`progress_client`:
  started x2, end x2 on transient failure only) so a lost "completed" cannot
  leave a finished interview in_progress; the answer drain went 8 -> 6.5 s so
  drain + end report with retry stays inside LiveKit's 10 s job shutdown.
* **Leaving / replacement** - early leave is `ended`, answers kept; only the
  newest room can report progress; a completed interview cannot restart.

### Session state integrity (Phase 11.6.4)

Sources of truth: the interview's status is `interviews.status`
(scheduled / in_progress / completed); "ended / retriable" is in_progress ->
scheduled; a session is ACTIVE when the interview is in_progress and its
newest session is within the answer grace; REPLACED = not the newest session;
an attempt is a session with its start record, and EXHAUSTED = 2 of them
(`started_attempts`). The agent's WAITING...COMPLETED live only in the worker
and are published to the page, never persisted.

Enforced in `interview_progress_service.agent_event`: completed / ended only
from a session that actually STARTED (`not_started`), completed only from
in_progress (`invalid_transition`), and completed is terminal - a repeated
"completed" or a late "ended" from the session that completed it returns
"completed" unchanged (`_completed_repeat`) instead of a 404. Answers are
accepted only for a started session (`not_started`, 409) - a superseded room
that never started cannot hold answers. **Test fixtures that store answers
record the start with `test_helpers.mark_session_started(room)`** (the same
audit row, without changing the interview status).

The applicant list carries `attempts_exhausted` (the backend's count), so a
refreshed page offers no Start / restart the backend would refuse; the list is
re-read when a session ends or fails. Refreshing creates nothing: a session
and an attempt exist only after Start and the agent's accepted "started".

### Observability (Phase 11.6.5)

`app/ai/interview/diagnostics.py`: one structured line per lifecycle event on
the `smarthr.interview.diag` logger - `diag {"event":...,"room":...,"n":..,
"t_ms":..,...}` - also attached to the record as `smarthr_diag`. **Correlate by
room**: the worker knows only the room; the backend's `backend_*` events carry
the same room plus `session_id` and `interview_id`. `n` is the worker's
per-room counter, `t_ms` the time since the room's first event.

**What may be logged is decided in `emit()`, not at the call site**: only the
fields in `FIELDS`, ints only for numbers, and every string field is a closed
vocabulary (states, outcomes, categories, codes, reasons) or a strict pattern
(the room name, an exception CLASS name). Anything else becomes "redacted";
unknown fields are dropped; there is no free-text field. `emit()` never
raises. Errors are categories (`connection_error`, `microphone_error`,
`stt_error`, `llm_error`, `tts_error`, `backend_error`, `state_error`,
`answer_persistence_error`, `progress_report_error`, `unknown_error`) with an
exception class and a code (`timeout` / `network` / `http_NNN` / a backend
refusal code) - never a message.

Events are emitted only once the thing happened: `question_spoken` when the
interviewer's audio carrying it starts (Q1: at the latest when its playout
ends); `answer_persisted` after the backend's 200; `session_started`,
`interview_completed`, `interview_ended` only when the backend ACCEPTED the
report (`progress_client.ACCEPTED_EVENT`); `reconnected` / `microphone_ready`
from LiveKit's own room events (`worker.attach_room_diagnostics`). Retries:
`answer_retry` / `progress_retry` (operation, attempt, category, code), then
`*_persisted` / `*_accepted` or `*_failed` / `*_refused`. `follow_up.ask_model`
and `adaptive.choose_with_model` take an optional `on_error(code, exc)` hook -
diagnostics only, the decision is unchanged. No timing, retry, policy or
schema changed; the frontend logs nothing.

### Turn classifier, turn behaviour, never-silent replies

Every completed turn that is not empty/filler-only (still ignored silently)
is classified FIRST in `InterviewerAgent._decide`, in PROCESSING, before any
follow-up / adaptive call:

1. `turn_policy.noise_reason` - deterministic, no model: low STT confidence
   (`new_message.transcript_confidence` < `SMARTHR_INTERVIEW_MIN_STT_CONFIDENCE`,
   default 0.35, only when the provider reports one), speech < 300 ms (VAD),
   or a 1-2 word fragment ending in a function word ("That's", "and the")
   -> NOISE_OR_INCOMPLETE.
2. `utterance.classify_with_model` - the session's GPT-4o, forced one-field
   tool `{"classification": "ANSWER" | "SIDE_QUESTION" | "REPEAT_REQUEST" |
   "NOISE_OR_INCOMPLETE"}`, delimited untrusted data, worked examples in the
   prompt. **ANSWER is the default**: short, negative, unexpected and "I don't
   know" answers are answers. Anything invalid / error / 4 s timeout = ANSWER.

| label | behaviour (`controller.non_answer_directive`) |
|---|---|
| ANSWER | saved -> analysed -> follow-up / adaptive -> next question. **No "say a bit more" invitation for short answers** (removed). |
| SIDE_QUESTION | `side_reply`: one very short GPT sentence + the current question verbatim. Nothing saved. |
| REPEAT_REQUEST | `repeat`: "Of course." + the current question (no model call). Nothing saved. |
| NOISE_OR_INCOMPLETE | `reask` ("Sorry, I didn't catch that." + the question) at most `MAX_NOISE_REASKS` (2) times per question; the next one `skip`s to the next question (or the closing line) with nothing saved for it. |

**A re-ask / skip takes effect only when HEARD.** `QuestionProgress.note_noise`
/ `skip` keep a provisional `_pending` snapshot (separate from the answers'
`_undo`): `confirm_pending` when the reply starts playing, `revert_pending`
when it is dropped unheard, when the applicant speaks again first
(`absorb_unheard`), or when TTS never plays - the watchdog then re-speaks
"Sorry, I didn't catch that." + the CURRENT question instead of moving on.

**Speech during the welcome.** LiveKit 1.8.3 discards a user turn that ends
while `allow_interruptions=False` speech plays (no option buffers it;
`discard_audio_if_uninterruptible=False` still drops it). So the welcome stays
uninterruptible but is short and ends with "please answer after each one. Here
is the first."; VAD still hears the applicant, and if they spoke during it
(`speech_during_welcome`), Q1 is preceded by "Sorry, I couldn't hear you while
I was speaking."

**Never silent.** `llm_node` completes the reply with a fixed fallback plus
the bank text it owes if GPT-4o's first sentence takes more than
`LLM_FIRST_SENTENCE_TIMEOUT_S` (6 s) or the model fails; the session's GPT
calls use 6 s x 1 retry (`worker.LLM_CONNECT`, was LiveKit's 10 s x 4); and
`controller.reply_expected` speaks the fallback itself if no reply audio has
started `REPLY_DEADLINE_S` (15 s) after a decided turn (`pipeline_error
no_reply`).

**STT / timing.** `SMARTHR_INTERVIEW_LANGUAGE` (en | ar | multi | xx-YY,
validated, default en) - Arabic speech on the English default comes back as
Latin-letter text. The turn detector follows the language STT reports.
`SMARTHR_INTERVIEW_ENDPOINT_MIN_S` / `_MAX_S` / `SMARTHR_INTERVIEW_VAD_MIN_SILENCE_S`
override the measured defaults (1.2 / 4.0 / 0.25 s), within bounds.

**Observability.** Every turn has a `turn` id on its diag events: `stt_turn`
(words, confidence_pct, speech_ms), `turn_classified` (label, noise_reason,
fallback, duration_ms), decisions, `turn_decided`, `llm_reply` (pieces,
fallback, code, duration_ms), `reply_started` (latency_ms). Metadata only.
`SMARTHR_INTERVIEW_DEBUG_CAPTURE=true` (development only - **never in
production**: `capture_enabled()` is false and the production worker refuses to
start) writes `debug_captures/<room>/turn-<n>.wav` - the turn's speech only,
LiveKit's `started/stopped_speaking_at` +- 300 ms on a sample clock - and
`.json` (transcript, confidence, label, directive, reply text, timings,
`trimmed`). `=raw` also writes the untrimmed `turn-<n>.raw.wav`. The only place
speech or transcripts are written; `debug_captures/` is git-ignored. Delete it
after debugging.

**Configuration** (`.env.example`): `SMARTHR_INTERVIEW_LANGUAGE` (en | ar |
multi), `SMARTHR_INTERVIEW_STT_MODEL` (default deepgram/nova-3),
`SMARTHR_INTERVIEW_DEBUG_CAPTURE` (false | true | raw). The worker logs one
`stt configuration:` line per process (language, models, capture on/off) and
warns when language is ar/multi on deepgram/nova-3.

**Arabic, measured** (`scripts/check_stt_arabic.py` - real LiveKit Inference
calls on a synthetic Arabic clip; `--wav` for a human recording):
deepgram/nova-3 + `ar` ~77-85% of words (e.g. "BYthon"); deepgram/nova-3 +
`multi` English / Latin transliteration ("It's my salad.") - **never use multi
for Arabic on nova-3**; speechmatics/enhanced + `ar` 100%. For Arabic
interviews: `SMARTHR_INTERVIEW_LANGUAGE=ar`, `SMARTHR_INTERVIEW_STT_MODEL=speechmatics/enhanced`.

**Simulated interviews.** `scripts/sim_interview_harness.py` runs a REAL
livekit-agents `AgentSession` (scheduler, chat context, speech handles,
interruptions, transcript synchronizer) with a scripted LLM, a silent TTS and
a paced audio sink, committing turns through `AgentActivity.on_end_of_turn`
(private API, pinned to 1.8.3). `scripts/test_ai_interview_simulated.py` uses
it: the answer/noise/side/repeat flow, LLM raise/hang/mid-reply failures with
timings, TTS that never starts, interruptions during a skip / re-ask, speech
during the welcome, and an answer held until the next question is heard. A re-ask / skip / answer's reply counts as HEARD only when it
finished or the played text (LiveKit records an interrupted reply as the
words actually played) contains the whole bank text; a new turn first waits
up to 1 s for the interrupted reply to settle (`controller.settle_reply`).

### Multi-Agent HR Intelligence (Phase 12)

Four AI roles around the interview, declared in `app/ai/hr_intelligence/roles.py`
and checked against the code by `test_ai_interview_multi_agent.py`:

| role | stage | model | implemented by | never |
|---|---|---|---|---|
| Interviewer | live | GPT-4o via LiveKit Inference | `app/ai/interview/` (unchanged) | analyses for HR, builds the report, scores |
| Analysis | post-interview | GPT-4o via `provider.py`, one call per answer | `interview_analysis` + its service (unchanged, plus an input contract) | controls the interview, sees the score |
| Report | post-interview | **none** | `hr_intelligence/report_agent.py` over `interview_report_service` | invents evidence, scores / ranks / recommends |
| Recruitment | post-interview | **none** | `hr_intelligence/matching_agent.py` over `interview_matching_service` | recalculates the match, shows the score, decides |

`POST /ai-interview/intelligence/{interview_id}[?analyse=false&session_id=]`
(Admin, HR) runs `orchestrator.run_post_interview`: Analysis (answers without
a completed analysis only - a second run makes no model call) -> Report (a
readable brief: fixed templates filled with STORED summaries / quotes /
skills, each with its answer sequence; a quote not found in what was said is
dropped) -> Recruitment (one templated sentence per existing matching skill
and per requirement not evidenced - "missing evidence", never "lacks"; the
score is not even in its input). Plain Python calls in a fixed order; no role
calls another. Each step is isolated: a failure is `{"status": "failed",
"error_code"}` and the rest still run; a failed report produces no brief.
The interview's status and stored answers are snapshotted before and
compared after (`interview_unchanged`).

`contracts.assert_safe_input` runs on every role's input (and inside
`interview_analysis_service.build_input` - refused = stored `failed` /
`unsafe_input`, before any model call): no key naming a credential, token or
contact PII (email, phone, names), no bearer/JWT-shaped value, no object.
The interviewer package imports none of this, and the report / recruitment
agents import no model provider, LiveKit, service or DB module.

## Removed feature: rollback material

The AI Interview System and its LiveKit / OpenAI Realtime transport were
deleted from this project. **This is archive material, not implementation** -
nothing in `app/`, `scripts/` or `frontend/` reads any of it, and none of it is
on a code path.

Historical source and runtime artifacts are not active implementation.
Do not restore archived interview code or runtime data into the public project.

What went with it: six database tables, three migrations, the interview and
question-bank routers and services, the interviewer and intent-classification
modules, the LiveKit worker, supervisor, dispatch, token and agent-context
code, the realtime and video-analysis services, both interview rooms and their
frontend services, and the interview-only packages (`livekit*`, plus
`livekit-client` and `@mediapipe/tasks-vision` in the frontend).

**`websockets` was kept** - it looks like a LiveKit dependency but
`langgraph-sdk` and `langsmith` require it, so the Celebration workflow needs
it. `openai` was kept for the same kind of reason: the assistant, the CV
parser, both agents and moderation all use it.

The feature is to be rebuilt from scratch; the archive is there to be read, not
restored. The rebuild (above) re-installed `livekit-agents` 1.8.3 and
`livekit-client` 2.22.3 as new, independent code - none of it came from here.

Use one project virtual environment per checkout and recreate it from the declared dependencies when needed.