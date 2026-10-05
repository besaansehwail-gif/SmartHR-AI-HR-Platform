export type UserRole = 'Admin' | 'HR' | 'Manager' | 'Employee';

export type UserStatus = 'Active' | 'Inactive' | 'Pending' | 'Suspended';

export type WorkMode = 'Remote' | 'Hybrid' | 'Onsite';

export interface User {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  role: UserRole;
  department: string;
  position: string;
  status: UserStatus;
  workMode: WorkMode;
  avatarUrl?: string;
  phone?: string;
  location: string;
  createdAt: string;
  lastLoginAt: string;
}

export interface Department {
  id: string;
  name: string;
  code: string;
  managerId: string;
  managerName: string;
  managerEmail: string;
  managerAvatar?: string;
  employeeCount: number;
  openPositionsCount: number;
  headcountBudget: number;
  status: 'Active' | 'Restructuring' | 'Archived';
  description: string;
  location: string;
  createdAt: string;
}

export type PositionLevel = 'Junior' | 'Mid' | 'Senior' | 'Lead' | 'Director' | 'Executive';

export interface Position {
  id: string;
  title: string;
  code: string;
  department: string;
  level: PositionLevel;
  employeeCount: number;
  openRequisitions: number;
  salaryRange: string;
  status: 'Active' | 'Draft' | 'Archived';
  description?: string;
}

export type PermissionCategory = 
  | 'Employees'
  | 'Recruitment'
  | 'Attendance'
  | 'Leave'
  | 'Training'
  | 'Performance'
  | 'Reports'
  | 'Users'
  | 'Settings'
  | 'Audit Logs';

export interface CategoryPermissions {
  view: boolean;
  create: boolean;
  edit: boolean;
  delete: boolean;
}

export type RolePermissionsMatrix = Record<PermissionCategory, CategoryPermissions>;

export interface RoleDefinition {
  id: string;
  name: UserRole;
  description: string;
  userCount: number;
  isSystemRole: boolean;
  permissions: RolePermissionsMatrix;
}

export type AuditActionType = 'CREATE' | 'UPDATE' | 'DELETE' | 'APPROVE' | 'LOGIN' | 'SECURITY' | 'EXPORT';

// =========================
// Audit trail - backend-backed types
//
// audit_logs holds exactly six columns:
// (id, user_id, action, entity_type, entity_id, timestamp).
// There is no details, ip_address, status or metadata column, so anything
// beyond those six is derived by the API at read time.
// =========================

/** The action tokens SmartHR writes into audit_logs.action. */
export type AuditActionToken =
  | 'CREATE'
  | 'UPDATE'
  | 'DELETE'
  | 'APPROVE'
  | 'REJECT'
  | 'STATUS_CHANGE'
  | 'ASSIGN'
  | 'ACTIVATE'
  | 'DEACTIVATE'
  | 'LOGIN'
  | 'LOGIN_FAILED'
  | 'EXPORT';

/** Resolved from audit_logs.user_id; users stores no name, so the display
 *  name comes from the linked employees row and falls back to the email. */
export interface AuditLogActor {
  id: number | null;
  name: string;
  email: string | null;
  role: string | null;
}

export interface AuditLogRecord {
  id: number;
  user_id: number | null;
  /** Free text in the database; SmartHR only writes AuditActionToken values. */
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  timestamp: string | null;
  /** Derived, not stored. */
  user: AuditLogActor;
  /** Derived, not stored - composed from action + entity_type + entity_id. */
  description: string;
}

export interface AuditLogPayload {
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
}

export interface AttentionItem {
  id: string;
  type: 'compliance' | 'probation' | 'contract' | 'leave' | 'security';
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  targetUser?: string;
  department?: string;
  dueDate: string;
  actionLabel: string;
}

export interface SystemNotification {
  id: string;
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  type: 'info' | 'success' | 'warning' | 'alert';
  linkPage?: string;
}

export interface AppSettings {
  general: {
    platformName: string;
    timezone: string;
    language: string;
    dateFormat: string;
    fiscalYearStart: string;
  };
  company: {
    companyName: string;
    legalName: string;
    taxId: string;
    website: string;
    contactEmail: string;
    phone: string;
    address: string;
    city: string;
    country: string;
  };
  security: {
    sessionTimeoutMinutes: number;
    enforce2FA: boolean;
    passwordExpirationDays: number;
    ipWhitelistEnabled: boolean;
    ipWhitelist: string;
    singleSignOn: boolean;
    failedLoginLockout: number;
  };
  notifications: {
    emailDigestFrequency: 'realtime' | 'daily' | 'weekly';
    notifyNewHires: boolean;
    notifyLeaveRequests: boolean;
    notifyComplianceAlerts: boolean;
    slackIntegration: boolean;
  };
  workMode: {
    defaultPolicy: 'Remote-first' | 'Hybrid' | 'On-site required';
    coreHoursStart: string;
    coreHoursEnd: string;
    minInOfficeDays: number;
    allowFlexibleHours: boolean;
  };
  system: {
    apiBaseUrl: string;
    useMockData: boolean;
    enableDebugLogs: boolean;
    telemetryEnabled: boolean;
  };
}

export type SystemSettings = AppSettings;

// ==========================================
// HR Workspace Types & Interfaces
// ==========================================

export type EmploymentType = 'Full-time' | 'Part-time' | 'Contract' | 'Probation';
export type EmployeeStatus = 'Active' | 'On Leave' | 'Probation' | 'Notice Period' | 'Terminated';

export interface Employee {
  id: string;
  employeeId: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  department: string;
  position: string;
  manager: string;
  managerId?: string;
  workMode: WorkMode;
  employmentType: EmploymentType;
  status: EmployeeStatus;
  hireDate: string;
  avatarUrl?: string;
  location: string;
  salary: string;
  gradeLevel: string;
  attendanceRate: number;
}

export type JobStatus = 'Open' | 'Draft' | 'Closed' | 'On Hold';
export type RecruitmentStage = 'Applied' | 'Screening' | 'Interview' | 'Assessment' | 'Offer' | 'Hired' | 'Rejected';

export interface Job {
  id: string;
  title: string;
  department: string;
  hiringManager: string;
  hiringManagerAvatar?: string;
  location: string;
  workMode: WorkMode;
  employmentType: EmploymentType;
  openings: number;
  applicationsCount: number;
  status: JobStatus;
  postedDate: string;
  salaryRange: string;
  description: string;
  pipelineCounts: {
    applied: number;
    screening: number;
    interview: number;
    assessment: number;
    offer: number;
    hired: number;
    rejected: number;
  };
}

export type CandidateStage = RecruitmentStage;

export interface Candidate {
  id: string;
  name: string;
  email: string;
  phone: string;
  avatarUrl?: string;
  appliedJobTitle: string;
  appliedJobId: string;
  department: string;
  stage: RecruitmentStage;
  status: 'In Review' | 'Scheduled' | 'Action Needed' | 'Offer Extended' | 'Hired' | 'Disqualified' | 'Application Received';
  location: string;
  appliedDate: string;
  experienceYears: number;
  currentCompany: string;
  matchScore: number;
  cvFileName: string;
  interviewStatus: string;
  notesCount: number;
  applicationHistory: {
    stage: RecruitmentStage;
    date: string;
    note: string;
    updatedBy: string;
  }[];
}

export type InterviewFormat = 'Google Meet' | 'On-site Room 3B' | 'Zoom' | 'Phone Call' | 'Boardroom A';
export type InterviewStatus = 'Scheduled' | 'Completed' | 'Cancelled' | 'In Progress';
export type InterviewType = 'Technical' | 'HR Screening' | 'Executive' | 'Culture Fit' | 'Architecture Review';

export interface Interview {
  id: string;
  candidateName: string;
  candidateAvatar?: string;
  candidateId?: string;
  candidateEmail?: string;
  jobTitle: string;
  jobId?: string;
  interviewerName: string;
  interviewerRole: string;
  interviewerAvatar?: string;
  date: string;
  time: string;
  durationMinutes: number;
  type: InterviewType;
  format: InterviewFormat | string;
  meetingLink?: string;
  status: InterviewStatus;
  feedbackScore?: number;
  notes?: string;
}

export type CourseStatus = 'Active' | 'Mandatory' | 'Optional';

export interface TrainingCourse {
  id: string;
  title: string;
  description: string;
  category: 'Security & Compliance' | 'Engineering' | 'Leadership' | 'Product' | 'HR Operations' | 'Soft Skills';
  provider: string;
  duration: string;
  enrolledCount: number;
  completionRate: number;
  status: CourseStatus;
  difficulty: 'Beginner' | 'Intermediate' | 'Advanced';
  modulesCount: number;
  instructor: string;
}

export interface AssignedTraining {
  id: string;
  employeeId: string;
  employeeName: string;
  employeeAvatar?: string;
  department: string;
  courseTitle: string;
  courseId: string;
  progressPercentage: number;
  status: 'In Progress' | 'Completed' | 'Overdue' | 'Not Started';
  dueDate: string;
  score?: number;
}

export interface LeaveRequest {
  id: string;
  employeeId: string;
  employeeName: string;
  employeeAvatar?: string;
  department: string;
  position: string;
  leaveType: 'Annual Leave' | 'Sick Leave' | 'Parental' | 'Bereavement' | 'Unpaid';
  startDate: string;
  endDate: string;
  daysCount: number;
  status: 'Pending' | 'Approved' | 'Rejected';
  reason: string;
  appliedOn: string;
}

export interface SkillRating {
  skill: string;
  category: 'Technical' | 'Domain' | 'Leadership' | 'Soft Skills';
  rating: number; // 1 to 5
  endorsements: number;
}

export interface CareerMilestone {
  date: string;
  title: string;
  department: string;
  type: 'Hire' | 'Promotion' | 'Lateral Move' | 'Award' | 'Certification';
  description: string;
}

export interface Employee360Profile {
  employee: Employee;
  personalInfo: {
    dob: string;
    gender: string;
    nationality: string;
    emergencyContactName: string;
    emergencyContactPhone: string;
    emergencyContactRelation: string;
    address: string;
  };
  attendanceSummary: {
    attendanceRate: number;
    onTimeRate: number;
    remoteDaysThisMonth: number;
    inOfficeDaysThisMonth: number;
    recentClockIns: {
      date: string;
      checkIn: string;
      checkOut: string;
      hours: string;
      mode: WorkMode;
      status: 'On-time' | 'Late' | 'WFH';
    }[];
  };
  leaveSummary: {
    annualBalance: number;
    annualTotal: number;
    sickBalance: number;
    sickTotal: number;
    pendingRequests: number;
    history: {
      id: string;
      type: string;
      dates: string;
      days: number;
      status: 'Approved' | 'Pending' | 'Rejected';
    }[];
  };
  performance: {
    overallRating: number;
    lastReviewDate: string;
    reviewerName: string;
    okrs: {
      title: string;
      progress: number;
      target: string;
      status: 'On Track' | 'At Risk' | 'Completed';
    }[];
    strengths: string[];
    growthAreas: string[];
    managerSummary: string;
  };
  trainingSummary: {
    completedCount: number;
    inProgressCount: number;
    totalHoursLogged: number;
    certifications: {
      name: string;
      issuer: string;
      date: string;
      credentialId: string;
    }[];
    currentCourses: {
      title: string;
      progress: number;
      dueDate: string;
    }[];
  };
  skills: SkillRating[];
  careerPath: CareerMilestone[];
  activityTimeline: {
    id: string;
    date: string;
    time: string;
    category: 'Performance' | 'Attendance' | 'Training' | 'HR Note' | 'Reward';
    title: string;
    description: string;
  }[];
}

// =========================
// Recruitment — backend-backed types
//
// These mirror the PostgreSQL `jobs` table and the enriched payload returned
// by the FastAPI /jobs/ router. Distinct from the mock-shaped `Job` interface
// above, which other recruitment pages still render from.
// =========================

export type JobStatusToken = 'open' | 'on_hold' | 'closed' | 'draft';

export interface JobPipelineCounts {
  applied: number;
  screening: number;
  shortlisted: number;
  interview: number;
  assessment: number;
  offer: number;
  hired: number;
  rejected: number;
}

export interface JobRecord {
  id: number;
  title: string;
  department_id: number;
  department_name: string | null;
  description: string | null;
  requirements: string | null;
  status: JobStatusToken;
  created_by: number | null;
  created_by_email: string | null;
  created_at: string;
  applications_count: number;
  pipeline_counts: JobPipelineCounts;
}

export interface JobPayload {
  title: string;
  department_id: number;
  description?: string | null;
  requirements?: string | null;
  status: JobStatusToken;
}

export interface DepartmentRecord {
  id: number;
  name: string;
  /** Counted from the referencing tables; departments stores only (id, name). */
  employee_count?: number;
  position_count?: number;
  job_count?: number;
  open_job_count?: number;
}


// =========================
// Candidates / ATS - backend-backed types
//
// These mirror the PostgreSQL `candidates` table joined with `applications`,
// `jobs`, `cvs` and `interviews`, as returned by the FastAPI /candidates/
// router. Distinct from the mock-shaped `Candidate` interface above, which
// other recruitment pages still render from.
// =========================

export type CandidateStageToken =
  | 'applied'
  | 'screening'
  | 'shortlisted'
  | 'interview'
  | 'assessment'
  | 'offer'
  | 'hired'
  | 'rejected';

export interface CandidateTimelineEvent {
  label: string;
  date: string | null;
  note: string;
}

export interface CandidateRecord {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  created_at: string;

  application_id: number | null;
  job_id: number | null;
  job_title: string | null;
  department_name: string | null;
  stage: CandidateStageToken | null;
  applied_at: string | null;
  applications_count: number;

  cv_file_name: string | null;
  interview_status: string | null;
  interview_scheduled_at: string | null;

  timeline: CandidateTimelineEvent[];
}

export interface CandidateCreatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  job_id?: number | null;
  stage?: CandidateStageToken;
}

export interface CandidateUpdatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
}

export interface ApplicationRecord {
  id: number;
  candidate_id: number;
  candidate_name: string | null;
  job_id: number;
  job_title: string | null;
  department_name: string | null;
  status: CandidateStageToken;
  applied_at: string;
}


// =========================
// Interviews - backend-backed types
//
// Mirrors the PostgreSQL `interviews` table joined through `applications`
// to `candidates` / `jobs`, plus the `users` row behind interviewer_id.
// Distinct from the mock-shaped `Interview` interface above.
// =========================

export type InterviewStatusToken =
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

export interface InterviewRecord {
  id: number;
  application_id: number;

  candidate_id: number | null;
  candidate_name: string | null;
  candidate_email: string | null;

  job_id: number | null;
  job_title: string | null;
  department_name: string | null;
  application_stage: string | null;

  interviewer_id: number | null;
  interviewer_name: string | null;
  interviewer_role: string | null;

  scheduled_at: string;
  location: string | null;
  status: InterviewStatusToken;
  notes: string | null;
  created_at: string;
}

export interface InterviewPayload {
  application_id: number;
  interviewer_id?: number | null;
  scheduled_at: string;
  location?: string | null;
  status: InterviewStatusToken;
  notes?: string | null;
}

export interface InterviewerOption {
  id: number;
  email: string;
  name: string | null;
  role: string | null;
}


// =========================
// Attendance & Leave - backend-backed types
//
// Mirrors the PostgreSQL `attendance` and `leave_requests` tables joined to
// `employees` / `departments` / `positions`. Status values are Title Case
// because that is how the rows in this database are already stored.
// =========================

export type AttendanceStatus =
  | 'Present'
  | 'Late'
  | 'Absent'
  | 'On Leave'
  | 'Half Day';

export interface AttendanceRecord {
  id: number;
  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  position_title: string | null;
  date: string;
  check_in: string | null;
  check_out: string | null;
  worked_hours: number | null;
  status: AttendanceStatus;
  created_at: string;
}

export interface AttendancePayload {
  employee_id: number;
  date: string;
  check_in?: string | null;
  check_out?: string | null;
  status: AttendanceStatus;
}

export type LeaveStatus = 'Pending' | 'Approved' | 'Rejected' | 'Cancelled';

export interface LeaveRequestRecord {
  id: number;
  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  position_title: string | null;

  leave_type: string;
  start_date: string;
  end_date: string;
  duration_days: number;
  reason: string | null;
  status: LeaveStatus;

  approved_by: number | null;
  approved_by_email: string | null;

  overlapping_count: number;
  created_at: string;
}

export interface LeaveRequestPayload {
  employee_id: number;
  leave_type: string;
  start_date: string;
  end_date: string;
  reason?: string | null;
  status: LeaveStatus;
}

export interface EmployeeRosterEntry {
  id: number;
  name: string;
  department_name: string | null;
  position_title: string | null;
}


// =========================
// Training & Employee Training - backend-backed types
//
// Mirrors the PostgreSQL `trainings` and `employee_trainings` tables.
// Counters (enrolled/completed/completion_rate) are derived server-side from
// the assignment rows; the trainings table stores no counters.
// Distinct from the mock-shaped `TrainingCourse` / `AssignedTraining` above.
// =========================

export interface TrainingRecord {
  id: number;
  title: string;
  description: string | null;
  provider: string | null;
  duration_hours: number | null;
  created_at: string;
  enrolled_count: number;
  completed_count: number;
  completion_rate: number;
}

export interface TrainingPayload {
  title: string;
  description?: string | null;
  provider?: string | null;
  duration_hours?: number | null;
}

export type AssignmentStatus =
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

export interface EmployeeTrainingRecord {
  id: number;

  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  position_title: string | null;

  training_id: number;
  training_title: string | null;
  training_provider: string | null;
  training_duration_hours: number | null;

  status: AssignmentStatus;
  started_at: string | null;
  completed_at: string | null;
}

export interface EmployeeTrainingPayload {
  employee_id: number;
  training_id: number;
  status: AssignmentStatus;
}


// =========================
// Performance Reviews - backend-backed types
//
// Mirrors the PostgreSQL `performance_reviews` table. `rating` is an INTEGER
// constrained by CHECK (rating >= 1 AND rating <= 5), and `reviewer_id` is a
// FK to `users` (not `employees`).
// Distinct from the mock-shaped `PerformanceReview` interface above.
// =========================

export type ReviewRating = 1 | 2 | 3 | 4 | 5;

export interface PerformanceReviewRecord {
  id: number;

  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  position_title: string | null;

  reviewer_id: number;
  reviewer_name: string | null;
  reviewer_email: string | null;
  reviewer_role: string | null;

  rating: number;
  rating_label: string | null;
  feedback: string | null;
  review_date: string;
  created_at: string;
}

export interface PerformanceReviewPayload {
  employee_id: number;
  rating: number;
  reviewer_id?: number | null;
  feedback?: string | null;
  review_date?: string | null;
}

export interface ReviewerOption {
  id: number;
  email: string;
  name: string | null;
  role: string | null;
}


// =========================
// Notifications - backend-backed types
//
// Mirrors the PostgreSQL `notifications` table. `user_id` is a FK to `users`
// (NOT NULL), `is_read` is the real read/unread flag, and `type` is a
// nullable free-text varchar.
// Distinct from the mock-shaped `SystemNotification` above, which the bell
// and the per-role pages render; `toSystemNotification()` adapts between them.
// =========================

export interface NotificationRecord {
  id: number;
  user_id: number;
  user_email: string | null;
  user_name: string | null;
  user_role: string | null;
  title: string;
  message: string;
  type: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationPayload {
  title: string;
  message: string;
  type?: string | null;
  user_id?: number | null;
}

export interface NotificationRecipient {
  id: number;
  email: string;
  name: string | null;
  role: string | null;
}


// =========================
// Users & Roles - backend-backed types
//
// Mirrors the PostgreSQL `users` table (id, email, role_id, is_active,
// created_at) joined to `roles` and, where a link exists, to `employees`
// for the person's name / department / position. `password_hash` is never
// returned by the API and has no representation here.
// Distinct from the mock-shaped `User` interface above.
// =========================

export interface UserAccountRecord {
  id: number;
  email: string;
  role_id: number;
  role_name: string | null;
  is_active: boolean;
  created_at: string;

  employee_id: number | null;
  first_name: string | null;
  last_name: string | null;
  full_name: string | null;
  phone: string | null;
  department_name: string | null;
  position_title: string | null;
}

export interface UserCreatePayload {
  email: string;
  password: string;
  role_id: number;
  is_active: boolean;
}

export interface UserUpdatePayload {
  email: string;
  role_id: number;
  is_active: boolean;
  /** Omitted or empty leaves the existing hash untouched. */
  password?: string | null;
}

export interface RoleRecord {
  id: number;
  name: string;
  user_count: number;
  active_user_count: number;
}


// =========================
// Departments & Positions - backend-backed types
//
// The real tables are tiny: departments is (id, name) with a UNIQUE name,
// positions is (id, title, department_id). Everything else the pages show is
// counted from employees / jobs at read time.
// Distinct from the mock-shaped `Department` / `Position` interfaces above.
// =========================

export interface DepartmentPayload {
  name: string;
}

export interface PositionRecord {
  id: number;
  title: string;
  department_id: number;
  department_name: string | null;
  employee_count: number;
}

export interface PositionPayload {
  title: string;
  department_id: number;
}


// =========================
// Employees - backend-backed type
//
// Mirrors the payload from `employee_to_dict()` in app/routers/employees.py:
// the PostgreSQL `employees` row plus the resolved department name, position
// title, manager name and the linked user's email.
// Distinct from the mock-shaped `Employee` interface above, which the HR
// directory renders after mapping.
// =========================

export interface EmployeeRecord {
  id: number;
  user_id: number | null;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  department_id: number | null;
  department_name: string | null;
  position_id: number | null;
  position_title: string | null;
  manager_id: number | null;
  manager_name: string | null;
  hire_date: string | null;
  employment_status: string;
  // Celebration dates. Present only where the caller may see them (Admin/HR,
  // or the employee's own record) - hence optional.
  birth_date?: string | null;
  promotion_date?: string | null;
  graduation_date?: string | null;
  wedding_date?: string | null;
  new_baby_date?: string | null;
}

export interface EmployeePayload {
  first_name: string;
  last_name: string;
  phone?: string | null;
  department_id?: number | null;
  position_id?: number | null;
  manager_id?: number | null;
  hire_date?: string | null;
  employment_status?: string;
  birth_date?: string | null;
  promotion_date?: string | null;
  graduation_date?: string | null;
  wedding_date?: string | null;
  new_baby_date?: string | null;
}

// =========================
// Dashboards & reports - backend-backed types
//
// Every figure below is aggregated by app/routers/dashboard.py from the
// existing tables. Nothing here has a column of its own; the endpoints are
// read-only and compute on each request.
//
// Two gaps are declared rather than guessed at, because the schema cannot
// answer them: work mode (employees has no such column) and turnover/exits
// (there is no termination or exit date anywhere).
// =========================

export interface DepartmentSlice {
  department: string;
  department_id: number | null;
  count: number;
  percentage: number;
  color: string;
}

export interface PipelineStage {
  stage: string;
  token: string;
  count: number;
  rate: string;
  color: string;
}

export interface RecruitmentPipeline {
  stages: PipelineStage[];
  total_applications: number;
  rejected: number;
}

export interface StatusSlice {
  status: string;
  count: number;
  percentage: number;
}

export interface AttendanceSummary {
  date: string | null;
  total_records: number;
  by_status: StatusSlice[];
  present: number;
  late: number;
  absent: number;
  on_leave: number;
  half_day: number;
  /** On-time share of all logged records. */
  punctuality_rate: number;
  /** Turned up at all, on time or late. */
  attendance_rate: number;
  avg_worked_hours: number | null;
}

/** Derived from real pending records only - never a fabricated alert. */
export interface AttentionItemRecord {
  id: string;
  type: string;
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  context: string;
  due_label: string;
  action_label: string;
  target_page: string;
  count: number;
}

export interface EmployeeBrief {
  id: number;
  name: string | null;
  department_id: number | null;
  department_name: string | null;
  position_id: number | null;
  position_title: string | null;
  hire_date: string | null;
  employment_status: string | null;
  user_id: number | null;
}

export interface TeamMemberBrief extends EmployeeBrief {
  today_status: string | null;
  check_in: string | null;
  check_out: string | null;
  on_leave_today: boolean;
}

export interface InterviewBrief {
  id: number;
  candidate_name: string | null;
  job_title: string | null;
  scheduled_at: string | null;
  location: string | null;
  status: string;
  interviewer_name: string | null;
}

export interface LeaveBrief {
  id: number;
  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  leave_type: string | null;
  start_date: string | null;
  end_date: string | null;
  duration_days: number;
  status: string | null;
  reason: string | null;
}

export interface AdminDashboardData {
  generated_at: string;
  kpis: {
    total_employees: number;
    active_employees: number;
    new_hires_30d: number;
    total_users: number;
    active_user_accounts: number;
    signed_in_30d: number;
    departments: number;
    positions: number;
    open_jobs: number;
    total_jobs: number;
  };
  department_distribution: DepartmentSlice[];
  recruitment: RecruitmentPipeline;
  attendance_today: AttendanceSummary;
  attention_items: AttentionItemRecord[];
  work_mode_available: boolean;
  work_mode: null;
}

export interface HRDashboardData {
  generated_at: string;
  kpis: {
    total_employees: number;
    new_hires_30d: number;
    new_hires_90d: number;
    open_positions: number;
    interviews_upcoming: number;
    interviews_total: number;
    active_candidates: number;
    total_candidates: number;
    pending_leave_requests: number;
    training_courses: number;
    training_assignments: number;
    training_completed: number;
    training_completion_rate: number;
  };
  attendance_today: AttendanceSummary;
  department_distribution: DepartmentSlice[];
  recruitment: RecruitmentPipeline;
  upcoming_interviews: InterviewBrief[];
  pending_leave: LeaveBrief[];
  recent_hires: EmployeeBrief[];
  attention_items: AttentionItemRecord[];
  work_mode_available: boolean;
  work_mode: null;
}

export interface ManagerDashboardData {
  generated_at: string;
  linked_employee: EmployeeBrief | null;
  is_linked: boolean;
  has_team: boolean;
  kpis: {
    team_size: number;
    present_today: number;
    late_today: number;
    on_leave_today: number;
    not_logged_today: number;
    pending_leave_requests: number;
    performance_reviews: number;
    average_rating: number | null;
    training_assignments: number;
    training_completed: number;
    interviews_upcoming: number;
  };
  team: TeamMemberBrief[];
  attendance_today: AttendanceSummary;
  department_distribution: DepartmentSlice[];
  pending_leave: LeaveBrief[];
  upcoming_interviews: InterviewBrief[];
}

export interface EmployeeTrainingItemBrief {
  id: number;
  training_id: number;
  title: string | null;
  provider: string | null;
  duration_hours: number | null;
  status: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface EmployeeDashboardData {
  generated_at: string;
  is_linked: boolean;
  employee: EmployeeBrief | null;
  attendance_today: {
    status: string | null;
    check_in: string | null;
    check_out: string | null;
    logged: boolean;
  } | null;
  attendance_30d: {
    total_records: number;
    present: number;
    late: number;
    absent: number;
    punctuality_rate: number;
    by_status: StatusSlice[];
  } | null;
  leave: {
    total_requests: number;
    pending: number;
    approved: number;
    rejected: number;
    approved_days_taken: number;
    /** No leave_balances table exists, so entitlement is not reported. */
    entitlement_available: boolean;
    days_by_type: { leave_type: string; days: number }[];
  } | null;
  upcoming_leave: LeaveBrief[];
  training: {
    total: number;
    assigned: number;
    in_progress: number;
    completed: number;
    completion_rate: number;
    items: EmployeeTrainingItemBrief[];
  } | null;
  performance: {
    reviews: number;
    average_rating: number | null;
    latest_rating: number | null;
    latest_label: string | null;
    latest_review_date: string | null;
    latest_feedback: string | null;
  } | null;
}

export interface ReportsData {
  generated_at: string;
  headcount: {
    total: number;
    active: number;
    by_status: StatusSlice[];
    avg_tenure_years: number | null;
    with_hire_date: number;
    /** Cumulative hire curve - see exits_tracked. */
    history: { month: string; label: string; hires: number; cumulative: number }[];
    /** Always false: no termination or exit date exists in the schema. */
    exits_tracked: boolean;
  };
  department_breakdown: DepartmentSlice[];
  attendance: AttendanceSummary;
  leave: {
    total_requests: number;
    total_days: number;
    by_type: {
      leave_type: string;
      requests: number;
      days: number;
      percentage: number;
      color: string;
    }[];
    by_status: StatusSlice[];
  };
  recruitment: {
    total_candidates: number;
    total_applications: number;
    rejected_applications: number;
    hired: number;
    conversion_rate: number;
    stages: PipelineStage[];
    jobs_by_status: { status: string; count: number }[];
    interviews_by_status: { status: string; count: number }[];
  };
  training: {
    courses: number;
    assignments: number;
    completed: number;
    completion_rate: number;
    by_status: StatusSlice[];
    by_department: {
      department: string;
      assigned: number;
      completed: number;
      rate: number;
    }[];
  };
  performance: {
    reviews: number;
    rated: number;
    average_rating: number | null;
    by_rating: {
      rating: number;
      label: string | null;
      count: number;
      percentage: number;
      color: string;
    }[];
  };
  work_mode_available: boolean;
  work_mode: null;
  turnover_available: boolean;
  turnover: null;
}

// =========================
// Signed-in identity
//
// GET /auth/me returns the account (users). GET /auth/me/employee returns the
// person - the employees row whose user_id points back at that account, with
// the names hanging off its foreign keys resolved. employees.user_id is
// nullable, so the endpoint 404s for an account with no linked record.
// =========================

/** GET /auth/me - the account, not the person. See MyEmployeeIdentity. */
export interface CurrentUser {
  id: number;
  email: string;
  /** Re-read from users.role_id on every request, never the JWT claim. */
  role_id: number;
  is_active: boolean;
}

export interface MyEmployeeIdentity {
  id: number;
  user_id: number | null;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string | null;
  department_id: number | null;
  department_name: string | null;
  position_id: number | null;
  position_title: string | null;
  manager_id: number | null;
  manager_name: string | null;
  hire_date: string | null;
  employment_status: string | null;
  /** From the linked users row - employees stores neither. */
  email: string | null;
  role_id: number | null;
  role_name: string | null;
}

/** Self-service leave submission: no employee_id (taken from the JWT) and no
 *  status (always Pending server-side). */
export interface MyLeaveRequestPayload {
  leave_type: string;
  start_date: string;
  end_date: string;
  reason?: string | null;
}

/* ==========================================================================
   AI Assistant
   --------------------------------------------------------------------------
   Mirrors the envelope returned by POST /ai/chat (app/ai/assistant.py).

   `data` is the raw result of whichever tool answered the question, carried
   back so the panel can show exactly what the reply was based on. Every field
   below is produced server-side; the client sends only a message and the
   visible transcript.
   ========================================================================== */

export interface AiChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiChatPayload {
  message: string;
  history: AiChatTurn[];
}

export interface AiChatResponse {
  reply: string;
  /** 'llm' when a model phrased it, 'tool' when it is the raw tool result. */
  generated_by: 'llm' | 'tool';
  llm_configured: boolean;
  provider: string;
  model: string | null;
  /** Set when something about the run needs saying, e.g. no model configured. */
  notice: string | null;
  tool_used: string | null;
  tool_ok: boolean | null;
  /** 'forbidden' | 'no_employee_link' | 'database_error' | 'unknown_tool' ... */
  tool_error_code: string | null;
  data: Record<string, unknown> | null;
  available_tools: string[];
  /** Always 'mcp': tools are reached over the Model Context Protocol. */
  tool_transport: string;
  mcp_server: string;
  elapsed_ms: number;
}

export interface AiToolSummary {
  name: string;
  description: string;
  /** 'self' | 'team' | 'organisation' - what the tool is filtered to. */
  scope: string | null;
  /** Argument names the tool declares. Never includes an identity field. */
  parameters: string[];
}

export interface AiStatus {
  llm_configured: boolean;
  provider: string;
  model: string | null;
  role_id: number;
  employee_linked: boolean;
  tool_transport: string;
  mcp: {
    available: boolean;
    server: { name: string; transport: string };
    registered_tools: string[];
  };
  tools: AiToolSummary[];
}

/* ==========================================================================
   AI CV analysis
   --------------------------------------------------------------------------
   Mirrors the envelope from POST /cvs/upload (app/routers/cvs.py).

   Note `persistence`: the cvs table has five columns and none of them hold the
   analysis, so `analysis` is returned to the client and not stored. The
   endpoint reports that explicitly rather than leaving it to be discovered.
   ========================================================================== */

export interface CvEducationEntry {
  degree: string | null;
  institution: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface CvExperienceEntry {
  job_title: string | null;
  company: string | null;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  /** Technologies this particular role names; [] when the CV attaches none. */
  technologies: string[];
}

export interface CvCertificationEntry {
  name: string | null;
  issuer: string | null;
  date: string | null;
}

export interface CvLanguageEntry {
  language: string | null;
  /** Null unless the CV states a level - a proficiency is never estimated. */
  proficiency: string | null;
}

/** Exactly the shape the model is required to return; every field may be empty. */
export interface ParsedCv {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  summary: string | null;
  skills: string[];
  education: CvEducationEntry[];
  experience: CvExperienceEntry[];
  certifications: CvCertificationEntry[];
  languages: CvLanguageEntry[];
}

export interface CvRecord {
  id: number;
  candidate_id: number;
  file_name: string;
  file_path: string;
  uploaded_at: string | null;
}

export interface CvUploadResponse {
  cv: CvRecord;
  candidate: CvCandidateSummary;
  extraction: {
    file_type: string;
    unit_count: number;
    character_count: number;
    word_count: number;
    truncated: boolean;
  };
  analysis: ParsedCv | null;
  analysis_available: boolean;
  analysis_error: string | null;
  /** 'llm_not_configured' | 'llm_error' | 'malformed_response' | ... */
  analysis_error_code: string | null;
  llm_configured: boolean;
  provider: string;
  model: string | null;
  /** Literal matches found in the document text, with no model involved. */
  contact_found_in_text: { email: string | null; phone: string | null };
  persistence: CvPersistence;
  /** AI output is a reading of the document, never a verified fact. */
  review_required: boolean;
  analysed_at: string;
}

export interface CvCandidateSummary {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
}

export interface CvPersistence {
  stored_in_postgres: {
    cvs: string[];
    candidates_on_confirmation: string[];
  };
  not_stored: string[];
  applied_to_candidate: Record<string, string | null> | null;
  note: string;
}

/** Result of a recruiter confirming reviewed contact details onto a candidate. */
export interface CvApplyResponse {
  candidate: CvCandidateSummary;
  applied_fields: string[];
  persistence: CvPersistence;
}

/* ==========================================================================
   Applicant / Job Seeker
   --------------------------------------------------------------------------
   Backend-shaped types for the `/applicant/*` surface. Like the other
   `*Record` types in this file, these describe what FastAPI actually returns
   rather than what a mock once looked like - `apiFetch<T>` casts without
   inspecting, so a type that lies here becomes a runtime crash on a page.
   ========================================================================== */

export type OpportunityType = 'job' | 'internship' | 'training' | 'free_course';

/** An opportunity as an applicant may see it. Note the absence of
 *  `created_by`, `applications_count` and `pipeline_counts`: those are HR's
 *  view of a job, and the applicant projection never includes them. */
export interface OpportunityRecord {
  opportunity_id: string;
  source: 'job' | 'training';
  id: number;
  title: string;
  organization: string;
  department_name: string | null;
  opportunity_type: OpportunityType;
  opportunity_type_label: string;
  employment_type: string | null;
  employment_type_label: string | null;
  location: string | null;
  description: string | null;
  requirements: string | null;
  skills: string[];
  requirement_phrases: string[];
  duration_hours?: number | null;
  deadline: string | null;
  is_expired: boolean;
  posted_at: string | null;
  can_apply: boolean;
  how_to_apply: string;
  external_url: string | null;
  match?: MatchResult;
}

/** A skill-overlap suggestion. `is_hiring_decision` is always false and is
 *  carried in the payload so the UI states it rather than assuming it. */
export interface MatchResult {
  label: string;
  is_hiring_decision: boolean;
  score: number | null;
  score_available: boolean;
  score_basis: string;
  matching_skills: string[];
  matched_requirements: string[];
  skill_gaps: string[];
  additional_skills: string[];
  applicant_skill_count: number;
  requirement_count: number;
  disclaimer: string;
  method: string;
  skills_source: string;
}

export interface ApplicantCvRecord {
  id: number;
  file_name: string;
  uploaded_at: string | null;
}

export interface ApplicantProfile {
  candidate_id: number;
  user_id: number | null;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  skills: string[];
  skills_raw: string | null;
  created_at: string | null;
  cv: ApplicantCvRecord | null;
  has_cv: boolean;
  completeness: {
    fields: Record<string, boolean>;
    complete: number;
    total: number;
    percent: number;
  };
}

export interface ApplicantProfilePayload {
  first_name?: string;
  last_name?: string;
  phone?: string;
  location?: string;
  skills?: string;
}

export interface ApplicantRegistrationPayload {
  full_name: string;
  email: string;
  password: string;
}

export interface ApplicantRegistrationResult {
  message: string;
  user_id: number;
  candidate_id: number;
  role_id: number;
  linked_to_existing_candidate: boolean;
}

export interface ApplicantInterview {
  id: number;
  scheduled_at: string | null;
  location: string | null;
  status: string;
}

export interface ApplicantApplication {
  id: number;
  applied_at: string | null;
  status: string;
  status_label: string;
  step: number | null;
  total_steps: number;
  is_closed: boolean;
  is_successful: boolean;
  opportunity: OpportunityRecord | null;
  job_id: number;
  job_title: string | null;
  interviews: ApplicantInterview[];
}

export interface ApplicantApplicationSummary {
  total: number;
  active: number;
  by_stage: Record<string, number>;
  by_stage_label: Record<string, number>;
}

export interface ApplicantDashboardData {
  profile: ApplicantProfile;
  cv: ApplicantCvRecord | null;
  recommended: { skills_available: boolean; items: OpportunityRecord[] };
  applications: {
    recent: ApplicantApplication[];
    summary: ApplicantApplicationSummary;
  };
  opportunity_counts: Record<OpportunityType, number>;
}

export interface OpportunityListResponse {
  opportunities: OpportunityRecord[];
  count: number;
  counts_by_type: Record<OpportunityType, number>;
}

export interface OpportunityDetailResponse {
  opportunity: OpportunityRecord;
  match: MatchResult;
  my_application: {
    status: string;
    status_label: string;
    step: number | null;
    total_steps: number;
    is_closed: boolean;
    is_successful: boolean;
  } | null;
  has_cv: boolean;
}

export interface RecommendedResponse {
  skills_available: boolean;
  skills_used: string[];
  recommendations: OpportunityRecord[];
  note: string | null;
}

export interface ApplicantCvListResponse {
  cvs: ApplicantCvRecord[];
  current: ApplicantCvRecord | null;
  has_cv: boolean;
  note: string;
}

/** The CV upload response is the existing `CvUploadResponse` plus the skills
 *  the CV suggested. `applied` is always false: nothing extracted by AI is
 *  written to the profile unless the applicant saves it themselves. */
export interface ApplicantCvUploadResponse extends CvUploadResponse {
  suggested_skills: {
    skills: string[];
    applied: boolean;
    note: string;
  };
}

export interface ApplySubmissionResult {
  message: string;
  application: ApplicantApplication;
  cv_id: number | null;
  warnings: string[];
}

/* ---- Career Agent ---- */

export interface AgentStep {
  step: number;
  tool: string;
  arguments: string[];
  ok: boolean;
  error_code: string | null;
  data: Record<string, unknown> | null;
}

export interface CareerAgentResponse {
  reply: string;
  steps: AgentStep[];
  tools_used: string[];
  tool_used: string | null;
  data: Record<string, unknown> | null;
  generated_by: 'llm' | 'tool' | 'none';
  tool_transport: string;
  llm_configured: boolean;
  provider: string;
  model: string | null;
  apply_intent_detected: boolean;
  notice: string | null;
}

export interface CareerAgentStatus {
  llm_configured: boolean;
  provider: string;
  model: string | null;
  role_id: number;
  applicant_linked: boolean;
  tool_transport: string;
  max_steps: number;
  mcp: { available: boolean; server: { name: string; transport: string } };
  tools: {
    name: string;
    description: string;
    scope: string | null;
    parameters: string[];
    requires_explicit_request: boolean;
  }[];
  apply_gate: {
    description: string;
    example_that_applies: string;
    example_that_does_not: string;
  };
}

/* ---------------------------------------------------------------------------
 * Internal HR Agent (roles 1-2)
 *
 * Deliberately separate types from the Career Agent's above: the two agents
 * share an MCP server and a response envelope shape, but not a single tool and
 * not an audience. Merging the types would invite merging the screens.
 * ------------------------------------------------------------------------ */

/** A match score, the skills behind it, and where that evidence came from. */
export interface ScreeningMatch {
  label: string;
  is_hiring_decision: boolean;
  /** null means SmartHR holds no evidence - NOT a low score. Never render 0. */
  score: number | null;
  score_available: boolean;
  score_basis: string;
  matching_skills: string[];
  matched_requirements: string[];
  skill_gaps: string[];
  additional_skills: string[];
  /** Present only when the score is null: the requirements nothing speaks to. */
  unevidenced_requirements?: string[];
  requirement_count: number;
  disclaimer: string;
  method: string;
}

export interface ScreeningEvidence {
  evidence_available: boolean;
  skills: string[];
  skills_sources: string[];
  profile_skills: string[];
  cv_skills: string[];
  summary: string | null;
  experience: Record<string, unknown>[];
  education: Record<string, unknown>[];
  certifications: Record<string, unknown>[];
  languages: Record<string, unknown>[];
  has_cv: boolean;
  cv_read: boolean;
  cv_id: number | null;
  cv_file_name: string | null;
  cv_error_code: string | null;
  cv_error: string | null;
  evidence_note: string;
}

export interface ScreeningJob {
  job_id: number;
  title: string;
  department_name: string | null;
  description: string | null;
  employment_type: string | null;
  location: string | null;
  status: string;
  deadline: string | null;
  requirements: string[];
  requirements_text: string | null;
  requirement_count: number;
  requirements_available: boolean;
  applications_count?: number;
  pipeline_counts?: Record<string, number>;
  note?: string;
}

export interface ScreeningCandidate {
  candidate_id: number;
  full_name: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  has_applicant_account: boolean;
  profile_skills: string[];
  has_cv: boolean;
  cv_id: number | null;
  cv_file_name: string | null;
  cv_uploaded_at: string | null;
  applications_count: number;
  evidence_note?: string;
}

export interface RelevantExperience {
  relevance: 'strong' | 'some' | 'none_evidenced' | 'none_stated' | 'unknown';
  basis: string;
  matching_roles: {
    title: string | null;
    company: string | null;
    start_date: string | null;
    end_date: string | null;
    requirements_mentioned: string[];
  }[];
  roles_considered: number;
  roles_matching: number;
}

export interface CvRelevanceBlock {
  available: boolean;
  basis: string;
  entries: Record<string, unknown>[];
  matching_entries: Record<string, unknown>[];
}

/** One candidate screened against one job - the card the HR agent renders. */
export interface ScreeningRow {
  candidate: ScreeningCandidate;
  job?: ScreeningJob;
  match: ScreeningMatch;
  evidence: ScreeningEvidence;
  relevant_experience: RelevantExperience;
  education?: CvRelevanceBlock;
  certifications?: CvRelevanceBlock;
}

export interface HrAgentResponse {
  reply: string;
  steps: AgentStep[];
  tools_used: string[];
  tool_used: string | null;
  data: Record<string, unknown> | null;
  /** Real screening rows from the tools - not parsed back out of the prose. */
  candidates: ScreeningRow[];
  job: ScreeningJob | null;
  generated_by: 'llm' | 'tool' | 'none';
  tool_transport: string;
  llm_configured: boolean;
  provider: string;
  model: string | null;
  is_hiring_decision: boolean;
  read_only: boolean;
  notice: string | null;
}

export interface HrAgentStatus {
  llm_configured: boolean;
  provider: string;
  model: string | null;
  role_id: number;
  tool_transport: string;
  max_steps: number;
  read_only: boolean;
  mcp: { available: boolean; server: { name: string; transport: string } };
  tools: {
    name: string;
    description: string;
    scope: string | null;
    parameters: string[];
    writes: boolean;
  }[];
  guarantees: {
    read_only: string;
    decision_owner: string;
    no_invention: string;
  };
  examples: string[];
}


// ===========================================================================
// Social Hub
//
// Backend-shaped, like every other `*Record` type here: these describe exactly
// what `/social/*` returns, rather than the wider mock-shaped interfaces above.
//
// `SocialPerson` is the one identity shape the whole module uses. It is
// deliberately narrow and mirrors `social_service.actor_map()` field for
// field - there is no salary, attendance, leave or performance data in it
// because the endpoint does not send any, and a wider type here would invite
// a page to render something the API will never provide.
// ===========================================================================

export interface SocialPerson {
  user_id: number;
  name: string;
  initials: string;
  email: string;
  role_id: number;
  role_name: string | null;
  /** Null when the account has no employees row - a legitimate state. */
  employee_id: number | null;
  department_id: number | null;
  department_name: string | null;
  position_title: string | null;
  headline: string | null;
  avatar_url: string | null;
}

export type SocialConnectionState =
  | 'self'
  | 'none'
  | 'pending_outgoing'
  | 'pending_incoming'
  | 'connected'
  | 'rejected';

export interface SocialConnectionInfo {
  state: SocialConnectionState;
  connection_id: number | null;
}

export type SocialFeedScope = 'all' | 'department' | 'following' | 'company';

/**
 * What a content author is told about moderation, and the whole of it.
 *
 * Deliberately two fields. The categories, severity, confidence and the
 * model's reasoning exist only on `SocialModerationReview`, which is an
 * HR-only payload from an HR-only endpoint - an employee's own post never
 * carries them, so there is nothing here for a curious author to read.
 */
export interface SocialModerated {
  moderation_status: 'published' | 'pending_review' | 'removed';
  /** True only on the viewer's own content while it waits for review. */
  pending_review: boolean;
}

export interface SocialPost extends SocialModerated {
  id: number;
  author: SocialPerson | null;
  content: string;
  image_url: string | null;
  audience: 'company' | 'department';
  department_id: number | null;
  created_at: string;
  edited_at: string | null;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
  is_mine: boolean;
}

export interface SocialFeedResponse {
  posts: SocialPost[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
  scope: SocialFeedScope;
  /** False when the caller's account has no department to filter on. */
  department_available: boolean;
}

export interface SocialComment extends SocialModerated {
  id: number;
  author: SocialPerson | null;
  content: string;
  created_at: string;
  is_mine: boolean;
}

export interface SocialCommentsResponse {
  post_id: number;
  comments: SocialComment[];
  total: number;
}

export interface SocialStory extends SocialModerated {
  id: number;
  caption: string | null;
  image_url: string | null;
  created_at: string;
  expires_at: string;
  seen: boolean;
  is_mine: boolean;
}

export interface SocialStoryGroup {
  author: SocialPerson | null;
  stories: SocialStory[];
  has_unseen: boolean;
  is_mine: boolean;
}

export interface SocialStoriesResponse {
  groups: SocialStoryGroup[];
  total: number;
}

export interface SocialStoryDetail extends SocialStory {
  author: SocialPerson | null;
  expired: boolean;
  /** Only the author is told how many people watched; null for everyone else. */
  view_count: number | null;
}

/** The moderation taxonomy. Mirrors CATEGORIES in the backend service. */
export type SocialModerationCategory =
  | 'harassment'
  | 'bullying'
  | 'threats'
  | 'abusive_language'
  | 'hate_speech'
  | 'sexual_content'
  | 'spam'
  | 'profanity';

export type SocialModerationStatus = 'pending' | 'approved' | 'removed';

/**
 * One moderation record, as HR sees it.
 *
 * This shape comes only from `/social/moderation*`, which is roles 1-2. It is
 * never merged into a feed payload, so the reasoning cannot leak into a page
 * an employee can open.
 */
export interface SocialModerationReview {
  id: number;
  content_type: 'post' | 'comment' | 'story';
  content_id: number;
  content_exists: boolean;
  /** The words being judged, exactly as written. Null if since deleted. */
  content: string | null;
  content_status: 'published' | 'pending_review' | 'removed' | null;
  author: SocialPerson | null;
  /** 'unavailable' means moderation could not run - see error_code. */
  ai_decision: 'allow' | 'flag' | 'unavailable';
  categories: SocialModerationCategory[];
  severity: 'low' | 'medium' | 'high' | null;
  /** 0-1, or null when no model ran. Never rendered as 0% in that case. */
  confidence: number | null;
  reason: string | null;
  error_code: string | null;
  status: SocialModerationStatus;
  reviewer: SocialPerson | null;
  reviewer_decision: SocialModerationStatus | null;
  reviewer_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface SocialModerationResponse {
  reviews: SocialModerationReview[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  status: string;
}

export interface SocialModerationSummary {
  counts: Record<SocialModerationStatus, number>;
  enabled: boolean;
  categories: SocialModerationCategory[];
  severities: Array<'low' | 'medium' | 'high'>;
  provider: string | null;
  model: string | null;
  model_configured: boolean;
  note: string;
}

export interface SocialAchievement {
  kind: 'tenure' | 'training';
  /** The training title, exactly as stored. Null for a tenure milestone. */
  title: string | null;
  date: string | null;
  years: number | null;
}

export interface SocialProfile extends SocialPerson {
  is_me: boolean;
  bio: string | null;
  skills: string[];
  interests: string[];
  location: string | null;
  cover_url: string | null;
  connection: SocialConnectionInfo;
  connections_count: number;
  achievements: SocialAchievement[];
  posts?: SocialPost[];
}

export interface SocialProfilePayload {
  headline?: string;
  bio?: string;
  skills?: string;
  interests?: string;
  location?: string;
}

export interface SocialDirectoryPerson extends SocialPerson {
  connection: SocialConnectionInfo;
}

export interface SocialPeopleResponse {
  people: SocialDirectoryPerson[];
  total: number;
  query: string;
  department_id: number | null;
}

export interface SocialConnectionRecord {
  id: number;
  status: 'pending' | 'accepted' | 'rejected';
  direction: 'incoming' | 'outgoing';
  person: SocialPerson | null;
  created_at: string;
  updated_at: string;
}

export interface SocialConnectionsResponse {
  connections: SocialConnectionRecord[];
  incoming_requests: SocialConnectionRecord[];
  outgoing_requests: SocialConnectionRecord[];
  counts: { connections: number; incoming: number; outgoing: number };
}

export interface SocialConversationSummary {
  id: number;
  /** A list, not a single person, so group threads need no new shape later. */
  participants: SocialPerson[];
  last_message: { body: string; created_at: string; from_me: boolean } | null;
  last_message_at: string | null;
  unread_count: number;
}

export interface SocialConversationsResponse {
  conversations: SocialConversationSummary[];
  total: number;
  unread_total: number;
}

export interface SocialConversation {
  id: number;
  participants: SocialPerson[];
  created_at: string;
  last_message_at: string | null;
}

export interface SocialMessage {
  id: number;
  sender: SocialPerson | null;
  body: string;
  created_at: string;
  from_me: boolean;
}

export interface SocialMessagesResponse {
  conversation: SocialConversation;
  messages: SocialMessage[];
  total: number;
}

export type SocialNotificationType =
  | 'social_connection_request'
  | 'social_connection_accepted'
  | 'social_comment'
  | 'social_reaction'
  | 'social_message';

export interface SocialNotification {
  id: number;
  type: SocialNotificationType | string;
  /** Stored text, shown as written - a database value, like every other
   *  notification in SmartHR. Only the category label around it is translated. */
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export interface SocialHubStatus {
  me: SocialPerson | null;
  connections: number;
  pending_requests: number;
  unread_messages: number;
  unread_notifications: number;
  /** Colleagues with an account, excluding the caller. */
  directory_size: number;
  posts: number;
  active_stories: number;
}


/* ==========================================================================
   AI Employee Celebration  (Admin + HR, /social/celebration)

   A three-agent LangGraph workflow: one agent identifies the occasion from
   SmartHR's own rows, one writes the message, one reviews it. Nothing is
   published - `final_celebration` is a draft the person puts in the Social
   Hub composer themselves, so it goes through the ordinary post path.
   ========================================================================== */

export type CelebrationOccasion =
  | 'birthday'
  | 'work_anniversary'
  | 'promotion'
  | 'graduation'
  | 'wedding'
  | 'new_baby'
  | 'none';

export interface CelebrationReview {
  approved: boolean;
  reason: string;
  /** Present only on a rejection. */
  suggestions: string | null;
}

export interface CelebrationResult {
  employee: {
    employee_id: number;
    name: string;
    position_title: string | null;
    department_name: string | null;
  };
  occasion: CelebrationOccasion;
  /** Only when the data stated it; never estimated. */
  years: number | null;
  occasion_reason: string;
  /** The draft, whether or not the reviewer approved it. */
  message: string | null;
  /** The image the post would carry - an API path, needs the session token. */
  image_url: string | null;
  /** avatar | graphic | none - where that image came from. */
  image_source: string;
  review: CelebrationReview;
  /** Null unless the Review Agent approved. This is the only postable text. */
  final_celebration: string | null;
  retry_count: number;
  max_retries: number;
  /** Set when an agent could not run at all - never an invented result. */
  error_code: string | null;
  /** One line per node, in the order they ran. */
  trace: string[];
  published: boolean;
}

export interface CelebrationStatus {
  llm_configured: boolean;
  provider: string;
  model: string | null;
  workflow: string;
  agents: string[];
  max_retries: number;
  occasions: CelebrationOccasion[];
  /** What this schema can actually evidence. */
  occasions_available: CelebrationOccasion[];
  /** Occasion -> why SmartHR holds no data for it. */
  occasions_unavailable: Record<string, string>;
  anniversary_window_days: number;
  publishes: boolean;
  writes: boolean;
}


export interface CelebrationDraft {
  id: number;
  employee_id: number;
  employee_name: string | null;
  occasion: CelebrationOccasion;
  /** The anniversary this draft is for - part of its uniqueness key. */
  occasion_date: string;
  years: number | null;
  message: string | null;
  review: CelebrationReview;
  retry_count: number;
  error_code: string | null;
  /** pending | posted | dismissed | no_occasion */
  status: string;
  /** Set only once HR posted it, through the ordinary post path. */
  post_id: number | null;
  created_at: string | null;
  decided_at: string | null;
  /** The server's rule, not the browser's: approved, pending, has words. */
  postable: boolean;
}

export interface CelebrationDraftsResponse {
  drafts: CelebrationDraft[];
  status: string;
}

export interface CelebrationSweep {
  date: string;
  found: number;
  prepared: number;
  skipped_existing: number;
  no_occasion: number;
  failed: number;
  dry_run: boolean;
  drafts: CelebrationDraft[];
}

/* ============================================================================
   AI Interview (Phase 1: voice foundation)

   Shapes returned by /ai-interview/*. The status carries which LiveKit
   variables are *missing* - names only, never values. The session carries the
   LiveKit server URL and a short-lived token for exactly one room.
   ========================================================================== */

export interface AiInterviewModels {
  stt: string;
  llm: string;
  tts: string;
}

export interface AiInterviewStatus {
  phase: number;
  configured: boolean;
  missing: string[];
  agent_name: string;
  models: AiInterviewModels;
  language: string;
  transport: string;
  inference: string;
  camera: boolean;
}

export interface AiInterviewSession {
  server_url: string;
  participant_token: string;
  room_name: string;
  participant_identity: string;
  agent_name: string;
  expires_in_seconds: number;
  models: AiInterviewModels;
  camera: boolean;
  /** The interview this room is for, resolved by the backend - title only. */
  interview: { interview_id: number; job_title: string };
}

/** One of the applicant's own interviews that an AI Interview can be held for. */
export interface AiInterviewListing {
  interview_id: number;
  job_title: string;
  scheduled_at: string | null;
  status: string;
  /** Development-only permanent fixture; not a real recruitment interview. */
  is_test: boolean;
  /** Phase 10: when Start becomes available / stops being available (local
   *  time, like scheduled_at), from the backend's own start-window rule. */
  opens_at: string | null;
  closes_at: string | null;
  /** Phase 11.6.4: the backend's started-attempt count has reached the limit,
   *  so Start is not offered (the backend refuses it regardless). */
  attempts_exhausted: boolean;
}

/* ==========================================================================
   AI Interview - Phase 8 Interview Report (Admin / HR)

   GET /ai-interview/report/{interview_id}[?session_id=] - built read-only from
   the answers and analyses Phase 7 stored. Field names are the backend's.
   There is deliberately no score, rating, percentage or decision anywhere,
   and no planned question total (it is not recorded).
   ========================================================================== */

export type AiReportAddresses = 'fully' | 'partially' | 'not_addressed' | 'unclear';
export type AiReportAnalysisStatus = 'completed' | 'failed' | 'pending';

/** One stored Phase 7 analysis - only its nine fields. */
export interface AiReportAnalysis {
  addresses_question: AiReportAddresses;
  summary: string;
  evidence: { point: string; quote: string; type: string }[];
  skills_mentioned: { skill: string; quote: string; source: 'applicant_statement' }[];
  job_requirements_referenced: string[];
  cv_relation: { statement: string; relation: 'also_in_cv' | 'not_in_cv' }[];
  specificity: 'specific' | 'general' | 'vague';
  clarity: 'clear' | 'partly_clear' | 'unclear';
  not_covered: string[];
}

export interface AiReportAnswer {
  question_id: number;
  question_number: number;
  question_text: string;
  /** Phase 11.1: a main question, or its predefined follow-up (same number). */
  question_type: 'main' | 'follow_up';
  sequence: number;
  answer_kind: 'answer' | 'short' | 'filler';
  transcript: string;
  word_count: number;
  answered_at: string;
  analysis_status: AiReportAnalysisStatus;
  /** Present only when analysis_status is 'completed'. */
  analysis: AiReportAnalysis | null;
  /** Present only when analysis_status is 'failed'. */
  error_code: string | null;
}

export interface AiReportInterview {
  interview_id: number;
  job_id: number | null;
  job_title: string | null;
  department: string | null;
  scheduled_at: string | null;
  status: InterviewStatusToken;
  answered_count: number;
  highest_question_reached: number | null;
}

export interface AiReportSessionRef {
  session_id: number;
  started_at: string;
  answered_count?: number;
}

export interface AiReportSkill {
  skill: string;
  source: 'applicant_statement';
  mentions: { sequence: number; question_number: number; quote: string | null }[];
}

export interface AiReportSummary {
  answered_count: number;
  analysis_status_counts: Record<AiReportAnalysisStatus, number>;
  addresses_question_counts: {
    addressed: number;
    partially_addressed: number;
    not_addressed: number;
    unclear: number;
  };
  requirements_referenced: string[];
  requirements_not_referenced: string[];
  requirements_basis: 'completed_analyses' | 'no_completed_analyses';
  /** False when some answers have no completed analysis. */
  complete: boolean;
  skills_mentioned: AiReportSkill[];
  key_evidence: { sequence: number; question_number: number; type: string; point: string; quote: string }[];
  key_evidence_total: number;
  not_covered: { sequence: number; question_number: number; items: string[] }[];
}

/** Phase 11.4: one MAIN question in the order heard, with its follow-up. */
export interface AiReportFlowEntry {
  number: number;
  main: {
    question_id: number | null;
    question_text: string | null;
    /** Its position in the CURRENT Question Bank plan, or null if not in it. */
    bank_position: number | null;
    /** False when only its follow-up's answer was stored. */
    answered: boolean;
    answer_sequences: number[];
  } | null;
  follow_up: { question_id: number; question_text: string; answer_sequences: number[] } | null;
}

export interface AiReportCoverage {
  main_questions_answered: { number: number; question_id: number }[];
  main_questions_answered_count: number;
  follow_ups_answered: { number: number; question_id: number }[];
  follow_ups_answered_count: number;
  highest_main_question_reached: number | null;
  not_reached: { question_id: number; question_text: string; bank_position: number }[];
  not_reached_basis: 'current_question_bank';
  order_matches_current_bank: boolean | null;
}

/** Which contexts the answer analyses had - never their content. */
export interface AiReportContext {
  job: boolean | null;
  cv: boolean | null;
  matching: boolean | null;
  basis: 'completed_analyses' | 'no_completed_analyses';
}

export interface AiInterviewReport {
  interview: AiReportInterview;
  session: (AiReportSessionRef & {
    first_answer_at?: string | null;
    last_answer_at?: string | null;
    duration_recorded?: false;
  }) | null;
  /** Every answered session of the interview, newest first. */
  sessions: AiReportSessionRef[];
  answers: AiReportAnswer[];
  question_flow: AiReportFlowEntry[];
  coverage: AiReportCoverage | null;
  context: AiReportContext | null;
  summary: AiReportSummary;
  meta: {
    state: 'ready' | 'no_answers';
    label: string;
    disclaimer: string;
    is_hiring_decision: false;
    planned_question_count_recorded: false;
    generated_by: 'stored_analyses';
  };
}

/**
 * GET /ai-interview/analytics (Phase 11.5.3) - counts over recorded AI
 * Interview activity. Exactly the backend's shape: numbers, one boolean,
 * one nullable number - no text, no score, nothing about a candidate.
 */
export interface AiInterviewAnalytics {
  overview: {
    total_interviews: number;
    scheduled: number;
    in_progress: number;
    completed: number;
  };
  activity: {
    answers_recorded: number;
    main_questions_reached: number;
    follow_ups_answered: number;
    highest_question_reached: number | null;
  };
  analysis: {
    completed: number;
    pending: number;
    failed: number;
  };
  context: {
    job: number;
    cv: number;
    matching: number;
  };
  question_flow: {
    main_questions: number;
    follow_ups: number;
    not_reached: number;
    order_comparable: boolean;
  };
}

/** POST /ai-interview/answers/{interview_id}/analyse - how many were re-run. */
export interface AiReanalyseResult {
  attempted: number;
}
