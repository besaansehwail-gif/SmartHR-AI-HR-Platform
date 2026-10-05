import {
  AdminDashboardData,
  AiChatPayload,
  AiChatResponse,
  AiStatus,
  CvRecord,
  CvApplyResponse,
  CvUploadResponse,
  CurrentUser,
  ApplicationRecord,
  AuditLogPayload,
  AuditLogActor,
  AuditLogRecord,
  EmployeeDashboardData,
  HRDashboardData,
  ManagerDashboardData,
  MyEmployeeIdentity,
  MyLeaveRequestPayload,
  ReportsData,
  EmployeePayload,
  EmployeeRecord,
  CelebrationDraft,
  CelebrationDraftsResponse,
  CelebrationResult,
  CelebrationStatus,
  CelebrationSweep,
  DepartmentPayload,
  DepartmentRecord,
  PositionPayload,
  PositionRecord,
  RoleRecord,
  UserAccountRecord,
  UserCreatePayload,
  UserUpdatePayload,
  NotificationPayload,
  NotificationRecipient,
  NotificationRecord,
  PerformanceReviewPayload,
  PerformanceReviewRecord,
  ReviewerOption,
  AssignmentStatus,
  EmployeeTrainingPayload,
  EmployeeTrainingRecord,
  TrainingPayload,
  TrainingRecord,
  AttendancePayload,
  AttendanceRecord,
  AttendanceStatus,
  EmployeeRosterEntry,
  LeaveRequestPayload,
  LeaveRequestRecord,
  LeaveStatus,
  InterviewPayload,
  InterviewRecord,
  InterviewStatusToken,
  InterviewerOption,
  CandidateCreatePayload,
  CandidateRecord,
  CandidateStageToken,
  CandidateUpdatePayload,
  JobPayload,
  JobRecord,
  JobStatusToken,
  ApplicantApplication,
  ApplicantCvListResponse,
  ApplicantCvUploadResponse,
  ApplicantDashboardData,
  ApplicantProfile,
  ApplicantProfilePayload,
  ApplicantRegistrationPayload,
  ApplicantRegistrationResult,
  ApplicantApplicationSummary,
  ApplySubmissionResult,
  CareerAgentResponse,
  CareerAgentStatus,
  HrAgentResponse,
  HrAgentStatus,
  OpportunityDetailResponse,
  OpportunityListResponse,
  OpportunityType,
  RecommendedResponse,
  SocialComment,
  SocialCommentsResponse,
  SocialConnectionRecord,
  SocialConnectionsResponse,
  SocialConversation,
  SocialConversationsResponse,
  SocialDirectoryPerson,
  SocialFeedResponse,
  SocialFeedScope,
  SocialHubStatus,
  SocialMessage,
  SocialMessagesResponse,
  SocialModerationResponse,
  SocialModerationReview,
  SocialModerationSummary,
  SocialNotification,
  SocialPeopleResponse,
  SocialPost,
  SocialProfile,
  SocialProfilePayload,
  SocialStoriesResponse,
  SocialStoryDetail,
  AiInterviewListing,
  AiInterviewReport,
  AiReanalyseResult,
  AiInterviewAnalytics,
  AiInterviewSession,
  AiInterviewStatus,
} from "../types";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const localDevelopmentApiBaseUrl =
  import.meta.env.DEV && typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "";
const API_BASE_URL = (configuredApiBaseUrl || localDevelopmentApiBaseUrl).replace(/\/+$/, "");

type RequestOptions = RequestInit & {
  auth?: boolean;
};

/**
 * Fetch an authenticated media file and return an object URL for it.
 *
 * `/social/media/{name}` is behind `require_staff`, and an `<img src>` sends
 * no Authorization header - so the tag's own request is answered 401. The
 * bytes are fetched here with the session token instead, and `AuthedImage`
 * renders the result. The caller revokes the URL.
 */
export async function fetchMediaObjectUrl(path: string): Promise<string> {
  const token = localStorage.getItem("smarthr_access_token");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`The image could not be loaded (${response.status}).`);
  }

  return URL.createObjectURL(await response.blob());
}

/**
 * A failed API call. Still an `Error` whose message is the backend's
 * `detail` (every existing `e.message` keeps working); `code` is the backend's
 * machine-readable reason when it sends one, otherwise null.
 */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null = null) {
    super(message);
    this.name = 'ApiError';
  }
}

async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { auth = true, headers, ...fetchOptions } = options;

  const token = localStorage.getItem("smarthr_access_token");

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string> | undefined),
  };

  // A multipart upload has to carry its own boundary, which only the browser
  // can generate - so the JSON content type is removed rather than overridden.
  if (fetchOptions.body instanceof FormData) {
    delete finalHeaders["Content-Type"];
  }

  if (auth && token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...fetchOptions,
    headers: finalHeaders,
  });

  if (!response.ok) {
    const errorText = await response.text();

    let message = `API Error: ${response.status}`;
    let code: string | null = null;

    try {
      const errorData = JSON.parse(errorText);
      message = errorData.detail || message;
      // Some endpoints (e.g. POST /ai-interview/session) also send a
      // machine-readable `code` beside `detail`, for a translated message.
      if (typeof errorData.code === 'string') code = errorData.code;
    } catch {
      if (errorText) {
        message = errorText;
      }
    }

    throw new ApiError(message, response.status, code);
  }

  return response.json();
}

/* ==========================================================================
   Audit log normalisation
   --------------------------------------------------------------------------
   `apiFetch<T>` casts the parsed JSON to T without inspecting it, so the
   declared type is a promise the service layer never actually keeps. That is
   how `log.user.name` came to throw at runtime: `AuditLogRecord.user` is
   declared non-optional, but a response without it still type-checks.

   `user` and `description` are the two fields on an audit row that are
   *derived at read time* rather than stored - audit_logs holds only
   (id, user_id, action, entity_type, entity_id, timestamp). Deriving them
   here as well means the record handed to a page always satisfies its type,
   so no caller has to guard the same field, and a row that arrives without
   them degrades to a truthful "System" / composed sentence instead of a
   white screen.

   The vocabulary below mirrors VERB_PHRASES / ENTITY_LABELS in
   app/routers/audit_logs.py so both sides read the same way.
   ========================================================================== */

const AUDIT_VERB_PHRASES: Record<string, string> = {
  CREATE: "Created",
  UPDATE: "Updated",
  DELETE: "Deleted",
  APPROVE: "Approved",
  REJECT: "Rejected",
  STATUS_CHANGE: "Changed the status of",
  ASSIGN: "Assigned",
  ACTIVATE: "Activated",
  DEACTIVATE: "Deactivated",
  LOGIN: "Signed in",
  LOGIN_FAILED: "Failed sign-in attempt",
  EXPORT: "Exported",
};

const AUDIT_ENTITY_LABELS: Record<string, string> = {
  Employee: "employee record",
  Job: "job opening",
  Candidate: "candidate",
  Application: "application",
  Interview: "interview",
  Attendance: "attendance record",
  LeaveRequest: "leave request",
  Training: "training course",
  EmployeeTraining: "training assignment",
  PerformanceReview: "performance review",
  User: "user account",
  Department: "department",
  Position: "position",
  AuditLog: "audit trail",
  Session: "session",
};

/** The row as it may arrive over the wire - every field treated as optional. */
type RawAuditLog = Omit<Partial<AuditLogRecord>, "user"> & {
  user?: Partial<AuditLogActor> | null;
};

const describeAuditEvent = (row: RawAuditLog): string => {
  const action = row.action ?? "";
  const phrase =
    AUDIT_VERB_PHRASES[action] ??
    (action ? action.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "Activity");

  if (action === "LOGIN" || action === "LOGIN_FAILED") return phrase;

  const entityType = row.entity_type ?? "";
  const label = AUDIT_ENTITY_LABELS[entityType] ?? entityType;
  if (!label) return phrase;

  return row.entity_id === null || row.entity_id === undefined
    ? `${phrase} ${label}`
    : `${phrase} ${label} #${row.entity_id}`;
};

const toAuditLogRecord = (row: RawAuditLog): AuditLogRecord => {
  const actor = row.user ?? {};
  const userId = actor.id ?? row.user_id ?? null;

  // user_id is nullable so that a failed sign-in from an unknown address can
  // still be recorded; those rows genuinely have no actor.
  const name =
    actor.name ?? actor.email ?? (userId === null ? "System" : `User #${userId}`);

  return {
    id: row.id ?? 0,
    user_id: row.user_id ?? null,
    action: row.action ?? "",
    entity_type: row.entity_type ?? null,
    entity_id: row.entity_id ?? null,
    timestamp: row.timestamp ?? null,
    user: {
      id: userId,
      name,
      email: actor.email ?? null,
      role: actor.role ?? null,
    },
    description: row.description ?? describeAuditEvent(row),
  };
};

export const SmartHRApi = {
  // =========================
  // Authentication
  // =========================

  async login(email: string, password: string) {
    const body = new URLSearchParams();

    body.append("username", email);
    body.append("password", password);

    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Login failed");
    }

    const data = await response.json();

    localStorage.setItem("smarthr_access_token", data.access_token);
    localStorage.setItem("smarthr_user_id", String(data.user_id));
    localStorage.setItem("smarthr_role_id", String(data.role_id));

    return data;
  },

  async getCurrentUser(): Promise<CurrentUser> {
    return apiFetch<CurrentUser>("/auth/me");
  },

  logout() {
    localStorage.removeItem("smarthr_access_token");
    localStorage.removeItem("smarthr_user_id");
    localStorage.removeItem("smarthr_role_id");
  },

  // =========================
  // Employees
  // =========================

  async getEmployees(): Promise<EmployeeRecord[]> {
    return apiFetch<EmployeeRecord[]>("/employees/");
  },

  async getEmployee(id: number): Promise<EmployeeRecord> {
    return apiFetch<EmployeeRecord>(`/employees/${id}`);
  },

  async createEmployee(employee: EmployeePayload): Promise<EmployeeRecord> {
    return apiFetch<EmployeeRecord>("/employees/", {
      method: "POST",
      body: JSON.stringify(employee),
    });
  },

  async updateEmployee(
    id: number,
    employee: EmployeePayload
  ): Promise<EmployeeRecord> {
    return apiFetch<EmployeeRecord>(`/employees/${id}`, {
      method: "PUT",
      body: JSON.stringify(employee),
    });
  },

  async deleteEmployee(id: number): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/employees/${id}`, {
      method: "DELETE",
    });
  },

  // =========================
  // Departments
  // =========================

  async getDepartments(): Promise<DepartmentRecord[]> {
    return apiFetch<DepartmentRecord[]>("/departments/");
  },

  async createDepartment(
    data: DepartmentPayload
  ): Promise<DepartmentRecord> {
    return apiFetch<DepartmentRecord>("/departments/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateDepartment(
    id: number,
    data: DepartmentPayload
  ): Promise<DepartmentRecord> {
    return apiFetch<DepartmentRecord>(`/departments/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async deleteDepartment(
    id: number
  ): Promise<{ message: string; id: number }> {
    return apiFetch<{ message: string; id: number }>(`/departments/${id}`, {
      method: "DELETE",
    });
  },

  // =========================
  // Positions
  // =========================

  async getPositions(): Promise<PositionRecord[]> {
    return apiFetch<PositionRecord[]>("/positions/");
  },

  async createPosition(data: PositionPayload): Promise<PositionRecord> {
    return apiFetch<PositionRecord>("/positions/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updatePosition(
    id: number,
    data: PositionPayload
  ): Promise<PositionRecord> {
    return apiFetch<PositionRecord>(`/positions/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async deletePosition(id: number): Promise<{ message: string; id: number }> {
    return apiFetch<{ message: string; id: number }>(`/positions/${id}`, {
      method: "DELETE",
    });
  },

  // =========================
  // Jobs
  // =========================

  async getJobs(): Promise<JobRecord[]> {
    return apiFetch<JobRecord[]>("/jobs/");
  },

  async getJob(id: number): Promise<JobRecord> {
    return apiFetch<JobRecord>(`/jobs/${id}`);
  },

  async createJob(data: JobPayload): Promise<JobRecord> {
    return apiFetch<JobRecord>("/jobs/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateJob(id: number, data: JobPayload): Promise<JobRecord> {
    return apiFetch<JobRecord>(`/jobs/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async updateJobStatus(
    id: number,
    status: JobStatusToken
  ): Promise<JobRecord> {
    return apiFetch<JobRecord>(`/jobs/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  // =========================
  // Candidates
  // =========================

  async getCandidates(): Promise<CandidateRecord[]> {
    return apiFetch<CandidateRecord[]>("/candidates/");
  },

  async getCandidate(id: number): Promise<CandidateRecord> {
    return apiFetch<CandidateRecord>(`/candidates/${id}`);
  },

  async createCandidate(
    data: CandidateCreatePayload
  ): Promise<CandidateRecord> {
    return apiFetch<CandidateRecord>("/candidates/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateCandidate(
    id: number,
    data: CandidateUpdatePayload
  ): Promise<CandidateRecord> {
    return apiFetch<CandidateRecord>(`/candidates/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  // =========================
  // Applications
  // =========================

  async getApplications(): Promise<ApplicationRecord[]> {
    return apiFetch<ApplicationRecord[]>("/applications/");
  },

  async createApplication(data: {
    candidate_id: number;
    job_id: number;
    status?: CandidateStageToken;
  }): Promise<ApplicationRecord> {
    return apiFetch<ApplicationRecord>("/applications/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateApplicationStage(
    applicationId: number,
    status: CandidateStageToken
  ): Promise<ApplicationRecord> {
    return apiFetch<ApplicationRecord>(
      `/applications/${applicationId}/status`,
      {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }
    );
  },

  // =========================
  // Interviews
  // =========================

  async getInterviews(): Promise<InterviewRecord[]> {
    return apiFetch<InterviewRecord[]>("/interviews/");
  },

  async getInterview(id: number): Promise<InterviewRecord> {
    return apiFetch<InterviewRecord>(`/interviews/${id}`);
  },

  async getInterviewers(): Promise<InterviewerOption[]> {
    return apiFetch<InterviewerOption[]>("/interviews/interviewers");
  },

  async createInterview(data: InterviewPayload): Promise<InterviewRecord> {
    return apiFetch<InterviewRecord>("/interviews/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateInterview(
    id: number,
    data: InterviewPayload
  ): Promise<InterviewRecord> {
    return apiFetch<InterviewRecord>(`/interviews/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async updateInterviewStatus(
    id: number,
    status: InterviewStatusToken,
    notes?: string | null
  ): Promise<InterviewRecord> {
    return apiFetch<InterviewRecord>(`/interviews/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify(
        notes === undefined ? { status } : { status, notes }
      ),
    });
  },

  // =========================
  // CVs
  // =========================

  async getCVs(): Promise<CvRecord[]> {
    return apiFetch<CvRecord[]>("/cvs/");
  },

  /**
   * Upload a PDF/DOCX CV for an existing candidate and get the structured
   * analysis back. The file goes to FastAPI, which extracts the text and asks
   * the model - the browser never talks to a model and holds no API key.
   */
  async uploadCv(
    candidateId: number,
    file: File,
    analyse = true
  ): Promise<CvUploadResponse> {
    const form = new FormData();
    form.append("file", file);
    form.append("candidate_id", String(candidateId));
    form.append("analyse", String(analyse));

    return apiFetch<CvUploadResponse>("/cvs/upload", {
      method: "POST",
      body: form,
    });
  },

  /**
   * Re-run the analysis for a CV already on file. The parsed result is not
   * persisted anywhere, so this is how it is produced again later - including
   * for a CV uploaded before a model was configured.
   */
  async analyseStoredCv(cvId: number): Promise<CvUploadResponse> {
    return apiFetch<CvUploadResponse>(`/cvs/${cvId}/analyse`, {
      method: "POST",
    });
  },

  /**
   * Write recruiter-reviewed contact details onto the candidate record.
   *
   * Only phone and location are sent, because they are the only extracted
   * fields the candidates table has a column for. The values come from what
   * the recruiter confirmed on screen, not straight from the model.
   */
  async applyCvToCandidate(
    cvId: number,
    values: { phone?: string | null; location?: string | null }
  ): Promise<CvApplyResponse> {
    return apiFetch<CvApplyResponse>(`/cvs/${cvId}/apply-to-candidate`, {
      method: "POST",
      body: JSON.stringify(values),
    });
  },

  async createCV(data: Record<string, unknown>) {
    return apiFetch("/cvs/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  // =========================
  // Attendance
  // =========================

  async getAttendance(): Promise<AttendanceRecord[]> {
    return apiFetch<AttendanceRecord[]>("/attendance/");
  },

  async createAttendance(
    data: AttendancePayload
  ): Promise<AttendanceRecord> {
    return apiFetch<AttendanceRecord>("/attendance/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateAttendance(
    id: number,
    data: AttendancePayload
  ): Promise<AttendanceRecord> {
    return apiFetch<AttendanceRecord>(`/attendance/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async updateAttendanceStatus(
    id: number,
    status: AttendanceStatus
  ): Promise<AttendanceRecord> {
    return apiFetch<AttendanceRecord>(`/attendance/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  // =========================
  // Leave Requests
  // =========================

  async getLeaveRequests(): Promise<LeaveRequestRecord[]> {
    return apiFetch<LeaveRequestRecord[]>("/leave-requests/");
  },

  async createLeaveRequest(
    data: LeaveRequestPayload
  ): Promise<LeaveRequestRecord> {
    return apiFetch<LeaveRequestRecord>("/leave-requests/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateLeaveRequest(
    id: number,
    data: LeaveRequestPayload
  ): Promise<LeaveRequestRecord> {
    return apiFetch<LeaveRequestRecord>(`/leave-requests/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async updateLeaveStatus(
    id: number,
    status: LeaveStatus
  ): Promise<LeaveRequestRecord> {
    return apiFetch<LeaveRequestRecord>(`/leave-requests/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  async getEmployeeRoster(): Promise<EmployeeRosterEntry[]> {
    return apiFetch<EmployeeRosterEntry[]>("/employees/roster");
  },

  // =========================
  // Trainings
  // =========================

  async getTrainings(): Promise<TrainingRecord[]> {
    return apiFetch<TrainingRecord[]>("/trainings/");
  },

  async getTraining(id: number): Promise<TrainingRecord> {
    return apiFetch<TrainingRecord>(`/trainings/${id}`);
  },

  async createTraining(data: TrainingPayload): Promise<TrainingRecord> {
    return apiFetch<TrainingRecord>("/trainings/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateTraining(
    id: number,
    data: TrainingPayload
  ): Promise<TrainingRecord> {
    return apiFetch<TrainingRecord>(`/trainings/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  // =========================
  // Employee Trainings
  // =========================

  async getEmployeeTrainings(): Promise<EmployeeTrainingRecord[]> {
    return apiFetch<EmployeeTrainingRecord[]>("/employee-trainings/");
  },

  async createEmployeeTraining(
    data: EmployeeTrainingPayload
  ): Promise<EmployeeTrainingRecord> {
    return apiFetch<EmployeeTrainingRecord>("/employee-trainings/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateEmployeeTraining(
    id: number,
    data: EmployeeTrainingPayload
  ): Promise<EmployeeTrainingRecord> {
    return apiFetch<EmployeeTrainingRecord>(`/employee-trainings/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async updateEmployeeTrainingStatus(
    id: number,
    status: AssignmentStatus
  ): Promise<EmployeeTrainingRecord> {
    return apiFetch<EmployeeTrainingRecord>(
      `/employee-trainings/${id}/status`,
      {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }
    );
  },

  // =========================
  // Performance Reviews
  // =========================

  async getPerformanceReviews(): Promise<PerformanceReviewRecord[]> {
    return apiFetch<PerformanceReviewRecord[]>("/performance-reviews/");
  },

  async getPerformanceReview(id: number): Promise<PerformanceReviewRecord> {
    return apiFetch<PerformanceReviewRecord>(`/performance-reviews/${id}`);
  },

  async getReviewers(): Promise<ReviewerOption[]> {
    return apiFetch<ReviewerOption[]>("/performance-reviews/reviewers");
  },

  async createPerformanceReview(
    data: PerformanceReviewPayload
  ): Promise<PerformanceReviewRecord> {
    return apiFetch<PerformanceReviewRecord>("/performance-reviews/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updatePerformanceReview(
    id: number,
    data: PerformanceReviewPayload
  ): Promise<PerformanceReviewRecord> {
    return apiFetch<PerformanceReviewRecord>(`/performance-reviews/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  // =========================
  // Notifications
  // =========================

  async getNotifications(
    scope: "mine" | "all" = "mine"
  ): Promise<NotificationRecord[]> {
    return apiFetch<NotificationRecord[]>(`/notifications/?scope=${scope}`);
  },

  async getNotificationRecipients(): Promise<NotificationRecipient[]> {
    return apiFetch<NotificationRecipient[]>("/notifications/recipients");
  },

  async createNotification(
    data: NotificationPayload
  ): Promise<NotificationRecord> {
    return apiFetch<NotificationRecord>("/notifications/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async setNotificationRead(
    id: number,
    isRead: boolean
  ): Promise<NotificationRecord> {
    return apiFetch<NotificationRecord>(`/notifications/${id}/read`, {
      method: "PATCH",
      body: JSON.stringify({ is_read: isRead }),
    });
  },

  async markAllNotificationsRead(): Promise<{
    updated: number;
    user_id: number;
  }> {
    return apiFetch<{ updated: number; user_id: number }>(
      "/notifications/read-all",
      { method: "PATCH" }
    );
  },



  // =========================
  // Self-service ("me")
  //
  // Every endpoint below is scoped server-side to the employees row linked to
  // the JWT user. No employee id is sent, so the scope cannot be widened from
  // the client.
  // =========================

  async getMyEmployee(): Promise<MyEmployeeIdentity> {
    return apiFetch<MyEmployeeIdentity>("/auth/me/employee");
  },

  async getMyAttendance(): Promise<AttendanceRecord[]> {
    return apiFetch<AttendanceRecord[]>("/attendance/me");
  },

  async getMyLeaveRequests(): Promise<LeaveRequestRecord[]> {
    return apiFetch<LeaveRequestRecord[]>("/leave-requests/me");
  },

  async createMyLeaveRequest(
    data: MyLeaveRequestPayload
  ): Promise<LeaveRequestRecord> {
    return apiFetch<LeaveRequestRecord>("/leave-requests/me", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getMyTrainings(): Promise<EmployeeTrainingRecord[]> {
    return apiFetch<EmployeeTrainingRecord[]>("/employee-trainings/me");
  },

  async getMyReviews(): Promise<PerformanceReviewRecord[]> {
    return apiFetch<PerformanceReviewRecord[]>("/performance-reviews/me");
  },

  // =========================
  // Dashboards & reports
  //
  // Read-only aggregation endpoints. Each is role-guarded server-side; see
  // app/routers/dashboard.py.
  // =========================

  async getAdminDashboard(): Promise<AdminDashboardData> {
    return apiFetch<AdminDashboardData>("/dashboard/admin");
  },

  async getHRDashboard(): Promise<HRDashboardData> {
    return apiFetch<HRDashboardData>("/dashboard/hr");
  },

  async getManagerDashboard(): Promise<ManagerDashboardData> {
    return apiFetch<ManagerDashboardData>("/dashboard/manager");
  },

  async getEmployeeDashboard(): Promise<EmployeeDashboardData> {
    return apiFetch<EmployeeDashboardData>("/dashboard/employee");
  },

  async getReports(): Promise<ReportsData> {
    return apiFetch<ReportsData>("/dashboard/reports");
  },

  // =========================
  // Audit Logs
  // =========================

  async getAuditLogs(params?: { limit?: number }): Promise<AuditLogRecord[]> {
    const query = params?.limit ? `?limit=${params.limit}` : "";
    const rows = await apiFetch<RawAuditLog[]>(`/audit-logs/${query}`);
    return (Array.isArray(rows) ? rows : []).map(toAuditLogRecord);
  },

  async createAuditLog(data: AuditLogPayload): Promise<AuditLogRecord> {
    const row = await apiFetch<RawAuditLog>("/audit-logs/", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return toAuditLogRecord(row);
  },

  // =========================
  // Users
  // =========================

  async getUsers(): Promise<UserAccountRecord[]> {
    return apiFetch<UserAccountRecord[]>("/users/");
  },

  async getUser(id: number): Promise<UserAccountRecord> {
    return apiFetch<UserAccountRecord>(`/users/${id}`);
  },

  async getRoles(): Promise<RoleRecord[]> {
    return apiFetch<RoleRecord[]>("/users/roles");
  },

  async createUser(data: UserCreatePayload): Promise<UserAccountRecord> {
    return apiFetch<UserAccountRecord>("/users/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateUser(
    id: number,
    data: UserUpdatePayload
  ): Promise<UserAccountRecord> {
    return apiFetch<UserAccountRecord>(`/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async setUserStatus(
    id: number,
    isActive: boolean
  ): Promise<UserAccountRecord> {
    return apiFetch<UserAccountRecord>(`/users/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
  },

  async deleteUser(id: number): Promise<{ message: string; id: number }> {
    return apiFetch<{ message: string; id: number }>(`/users/${id}`, {
      method: "DELETE",
    });
  },

  // =========================
  // AI Assistant
  //
  // The request carries a message and the visible transcript - nothing else.
  // The caller, their role and their employee record are all resolved
  // server-side from the JWT, so there is no identity field to tamper with.
  // =========================

  async aiChat(payload: AiChatPayload): Promise<AiChatResponse> {
    return apiFetch<AiChatResponse>("/ai/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getAiStatus(): Promise<AiStatus> {
    return apiFetch<AiStatus>("/ai/status");
  },

  // =========================
  // Applicant / Job Seeker
  //
  // Registration is the only unauthenticated call in this file (auth: false).
  // Everything else is scoped server-side to the signed-in applicant: notice
  // that no method here takes a candidate id, because no endpoint accepts one.
  // =========================

  async registerApplicant(
    data: ApplicantRegistrationPayload
  ): Promise<ApplicantRegistrationResult> {
    return apiFetch<ApplicantRegistrationResult>("/applicant/register", {
      method: "POST",
      auth: false,
      body: JSON.stringify(data),
    });
  },

  async getApplicantDashboard(): Promise<ApplicantDashboardData> {
    return apiFetch<ApplicantDashboardData>("/applicant/dashboard");
  },

  async getApplicantProfile(): Promise<ApplicantProfile> {
    return apiFetch<ApplicantProfile>("/applicant/me");
  },

  async updateApplicantProfile(
    data: ApplicantProfilePayload
  ): Promise<ApplicantProfile> {
    return apiFetch<ApplicantProfile>("/applicant/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async getOpportunities(params?: {
    search?: string;
    opportunity_type?: OpportunityType;
    location?: string;
  }): Promise<OpportunityListResponse> {
    const query = new URLSearchParams();
    if (params?.search) query.set("search", params.search);
    if (params?.opportunity_type) query.set("opportunity_type", params.opportunity_type);
    if (params?.location) query.set("location", params.location);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<OpportunityListResponse>(`/applicant/opportunities${suffix}`);
  },

  async getOpportunity(opportunityId: string): Promise<OpportunityDetailResponse> {
    return apiFetch<OpportunityDetailResponse>(
      `/applicant/opportunities/${encodeURIComponent(opportunityId)}`
    );
  },

  async getRecommendedOpportunities(limit = 5): Promise<RecommendedResponse> {
    return apiFetch<RecommendedResponse>(
      `/applicant/opportunities/recommended?limit=${limit}`
    );
  },

  async getMyCvs(): Promise<ApplicantCvListResponse> {
    return apiFetch<ApplicantCvListResponse>("/applicant/cv");
  },

  async uploadMyCv(file: File, analyse = true): Promise<ApplicantCvUploadResponse> {
    const form = new FormData();
    form.append("file", file);
    form.append("analyse", String(analyse));
    // No candidate_id: the owner is the caller, resolved from the JWT.
    return apiFetch<ApplicantCvUploadResponse>("/applicant/cv", {
      method: "POST",
      body: form,
    });
  },

  async getMyApplications(): Promise<{
    applications: ApplicantApplication[];
    summary: ApplicantApplicationSummary;
  }> {
    return apiFetch<{
      applications: ApplicantApplication[];
      summary: ApplicantApplicationSummary;
    }>("/applicant/applications");
  },

  async applyToOpportunity(jobId: number): Promise<ApplySubmissionResult> {
    return apiFetch<ApplySubmissionResult>("/applicant/applications", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, confirm: true }),
    });
  },

  // =========================
  // AI Career Agent
  // =========================

  async careerAgentChat(payload: {
    message: string;
    history: { role: string; content: string }[];
  }): Promise<CareerAgentResponse> {
    return apiFetch<CareerAgentResponse>("/applicant/agent/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getCareerAgentStatus(): Promise<CareerAgentStatus> {
    return apiFetch<CareerAgentStatus>("/applicant/agent/status");
  },

  // =========================
  // Internal HR Agent (Admin + HR)
  //
  // A separate endpoint from the Career Agent, not a parameter on it. The
  // backend guards it with require_roles(1, 2), so calling this as a Manager,
  // Employee or Applicant is a 403 rather than a different answer.
  // =========================

  async hrAgentChat(payload: {
    message: string;
    history: { role: string; content: string }[];
  }): Promise<HrAgentResponse> {
    return apiFetch<HrAgentResponse>("/hr/agent/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getHrAgentStatus(): Promise<HrAgentStatus> {
    return apiFetch<HrAgentStatus>("/hr/agent/status");
  },

  // =========================
  // Social Hub
  //
  // Every route below is `require_staff` on the server (roles 1-4), so an
  // Applicant reaching one of these gets a 403 regardless of what the UI
  // offers. Posts and stories go up as multipart because they may carry an
  // image; `apiFetch` drops its JSON content type for FormData so the browser
  // can set the boundary.
  // =========================

  async getSocialStatus(): Promise<SocialHubStatus> {
    return apiFetch<SocialHubStatus>("/social/status");
  },

  async getSocialFeed(params?: {
    scope?: SocialFeedScope;
    page?: number;
    pageSize?: number;
  }): Promise<SocialFeedResponse> {
    const query = new URLSearchParams();
    if (params?.scope) query.set("scope", params.scope);
    if (params?.page) query.set("page", String(params.page));
    if (params?.pageSize) query.set("page_size", String(params.pageSize));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<SocialFeedResponse>(`/social/feed${suffix}`);
  },

  async createSocialPost(payload: {
    content: string;
    audience?: "company" | "department";
    image?: File | null;
  }): Promise<SocialPost> {
    const form = new FormData();
    form.append("content", payload.content);
    form.append("audience", payload.audience ?? "company");
    if (payload.image) form.append("image", payload.image);

    return apiFetch<SocialPost>("/social/posts", {
      method: "POST",
      body: form,
    });
  },

  async getSocialPost(postId: number): Promise<SocialPost> {
    return apiFetch<SocialPost>(`/social/posts/${postId}`);
  },

  async updateSocialPost(postId: number, content: string): Promise<SocialPost> {
    return apiFetch<SocialPost>(`/social/posts/${postId}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  },

  async deleteSocialPost(postId: number): Promise<{ id: number; deleted: boolean }> {
    return apiFetch<{ id: number; deleted: boolean }>(`/social/posts/${postId}`, {
      method: "DELETE",
    });
  },

  async getSocialComments(postId: number): Promise<SocialCommentsResponse> {
    return apiFetch<SocialCommentsResponse>(`/social/posts/${postId}/comments`);
  },

  async addSocialComment(postId: number, content: string): Promise<SocialComment> {
    return apiFetch<SocialComment>(`/social/posts/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  async deleteSocialComment(
    commentId: number
  ): Promise<{ id: number; deleted: boolean }> {
    return apiFetch<{ id: number; deleted: boolean }>(
      `/social/comments/${commentId}`,
      { method: "DELETE" }
    );
  },

  async likeSocialPost(postId: number): Promise<SocialPost> {
    return apiFetch<SocialPost>(`/social/posts/${postId}/like`, { method: "POST" });
  },

  async unlikeSocialPost(postId: number): Promise<SocialPost> {
    return apiFetch<SocialPost>(`/social/posts/${postId}/like`, { method: "DELETE" });
  },

  async getSocialStories(): Promise<SocialStoriesResponse> {
    return apiFetch<SocialStoriesResponse>("/social/stories");
  },

  async createSocialStory(payload: {
    caption?: string;
    image?: File | null;
  }): Promise<SocialStoryDetail> {
    const form = new FormData();
    form.append("caption", payload.caption ?? "");
    if (payload.image) form.append("image", payload.image);

    return apiFetch<SocialStoryDetail>("/social/stories", {
      method: "POST",
      body: form,
    });
  },

  async getSocialStory(storyId: number): Promise<SocialStoryDetail> {
    return apiFetch<SocialStoryDetail>(`/social/stories/${storyId}`);
  },

  async viewSocialStory(storyId: number): Promise<SocialStoryDetail> {
    return apiFetch<SocialStoryDetail>(`/social/stories/${storyId}/view`, {
      method: "POST",
    });
  },

  async deleteSocialStory(
    storyId: number
  ): Promise<{ id: number; deleted: boolean }> {
    return apiFetch<{ id: number; deleted: boolean }>(`/social/stories/${storyId}`, {
      method: "DELETE",
    });
  },

  async getSocialPeople(params?: {
    q?: string;
    departmentId?: number | null;
  }): Promise<SocialPeopleResponse> {
    const query = new URLSearchParams();
    if (params?.q) query.set("q", params.q);
    if (params?.departmentId) query.set("department_id", String(params.departmentId));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<SocialPeopleResponse>(`/social/people${suffix}`);
  },

  async getSocialSuggestions(limit = 5): Promise<{ people: SocialDirectoryPerson[] }> {
    return apiFetch<{ people: SocialDirectoryPerson[] }>(
      `/social/people/suggested?limit=${limit}`
    );
  },

  async getSocialProfile(userId: number): Promise<SocialProfile> {
    return apiFetch<SocialProfile>(`/social/profile/${userId}`);
  },

  async getMySocialProfile(): Promise<SocialProfile> {
    return apiFetch<SocialProfile>("/social/profile/me");
  },

  async updateMySocialProfile(
    payload: SocialProfilePayload
  ): Promise<SocialProfile> {
    return apiFetch<SocialProfile>("/social/profile/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async uploadMySocialAvatar(file: File): Promise<SocialProfile> {
    const form = new FormData();
    form.append("image", file);
    return apiFetch<SocialProfile>("/social/profile/me/avatar", {
      method: "POST",
      body: form,
    });
  },

  async getSocialConnections(): Promise<SocialConnectionsResponse> {
    return apiFetch<SocialConnectionsResponse>("/social/connections");
  },

  async requestSocialConnection(userId: number): Promise<SocialConnectionRecord> {
    return apiFetch<SocialConnectionRecord>(`/social/connections/${userId}`, {
      method: "POST",
    });
  },

  async acceptSocialConnection(
    connectionId: number
  ): Promise<SocialConnectionRecord> {
    return apiFetch<SocialConnectionRecord>(
      `/social/connections/${connectionId}/accept`,
      { method: "POST" }
    );
  },

  async rejectSocialConnection(
    connectionId: number
  ): Promise<SocialConnectionRecord> {
    return apiFetch<SocialConnectionRecord>(
      `/social/connections/${connectionId}/reject`,
      { method: "POST" }
    );
  },

  async removeSocialConnection(
    connectionId: number
  ): Promise<{ id: number; removed: boolean }> {
    return apiFetch<{ id: number; removed: boolean }>(
      `/social/connections/${connectionId}`,
      { method: "DELETE" }
    );
  },

  async getSocialConversations(): Promise<SocialConversationsResponse> {
    return apiFetch<SocialConversationsResponse>("/social/conversations");
  },

  async startSocialConversation(userId: number): Promise<SocialConversation> {
    return apiFetch<SocialConversation>("/social/conversations", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  },

  async getSocialMessages(conversationId: number): Promise<SocialMessagesResponse> {
    return apiFetch<SocialMessagesResponse>(
      `/social/conversations/${conversationId}/messages`
    );
  },

  async sendSocialMessage(
    conversationId: number,
    body: string
  ): Promise<SocialMessage> {
    return apiFetch<SocialMessage>(
      `/social/conversations/${conversationId}/messages`,
      { method: "POST", body: JSON.stringify({ body }) }
    );
  },

  async getSocialNotifications(): Promise<{ notifications: SocialNotification[] }> {
    return apiFetch<{ notifications: SocialNotification[] }>(
      "/social/notifications"
    );
  },

  async readSocialNotification(
    notificationId: number
  ): Promise<{ id: number; is_read: boolean }> {
    return apiFetch<{ id: number; is_read: boolean }>(
      `/social/notifications/${notificationId}/read`,
      { method: "POST" }
    );
  },

  // --- AI moderation (Admin + HR only) ------------------------------------
  //
  // Every one of these returns 403 for Manager and Employee. The page is
  // behind the HR workspace so it is never offered to them, but that is
  // convenience - `require_roles(1, 2)` on the router is the boundary.

  async getSocialModeration(params?: {
    status?: string;
    contentType?: string;
    page?: number;
  }): Promise<SocialModerationResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.contentType) query.set("content_type", params.contentType);
    if (params?.page) query.set("page", String(params.page));

    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<SocialModerationResponse>(`/social/moderation${suffix}`);
  },

  async getSocialModerationSummary(): Promise<SocialModerationSummary> {
    return apiFetch<SocialModerationSummary>("/social/moderation/summary");
  },

  async approveSocialModeration(
    reviewId: number,
    note?: string
  ): Promise<SocialModerationReview> {
    return apiFetch<SocialModerationReview>(
      `/social/moderation/${reviewId}/approve`,
      { method: "POST", body: JSON.stringify({ note: note ?? null }) }
    );
  },

  async removeSocialModeration(
    reviewId: number,
    note?: string
  ): Promise<SocialModerationReview> {
    return apiFetch<SocialModerationReview>(
      `/social/moderation/${reviewId}/remove`,
      { method: "POST", body: JSON.stringify({ note: note ?? null }) }
    );
  },

  // =========================
  // AI Employee Celebration  (Admin + HR)
  //
  // Generates only. There is no publish endpoint here on purpose: an approved
  // draft goes into the Social Hub composer, where the person whose name will
  // be on it presses Post and it travels the ordinary /social/posts path,
  // moderation and audit row included.
  // =========================

  async generateCelebration(employeeId: number): Promise<CelebrationResult> {
    return apiFetch<CelebrationResult>("/social/celebration", {
      method: "POST",
      body: JSON.stringify({ employee_id: employeeId }),
    });
  },

  /** HR's queue of celebrations the scheduled sweep prepared. */
  async getCelebrationDrafts(
    statusFilter?: string
  ): Promise<CelebrationDraftsResponse> {
    const suffix = statusFilter
      ? `?status_filter=${encodeURIComponent(statusFilter)}`
      : "";
    return apiFetch<CelebrationDraftsResponse>(
      `/social/celebration/drafts${suffix}`
    );
  },

  /** Runs today's detection now. Idempotent - the daily job calls the same code. */
  async runCelebrationSweep(dryRun = false): Promise<CelebrationSweep> {
    return apiFetch<CelebrationSweep>("/social/celebration/run", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    });
  },

  /** The human approval step: posts the draft through the ordinary post path. */
  async approveCelebrationDraft(
    draftId: number
  ): Promise<{ draft: CelebrationDraft; post: SocialPost }> {
    return apiFetch<{ draft: CelebrationDraft; post: SocialPost }>(
      `/social/celebration/drafts/${draftId}/approve`,
      { method: "POST" }
    );
  },

  async dismissCelebrationDraft(draftId: number): Promise<CelebrationDraft> {
    return apiFetch<CelebrationDraft>(
      `/social/celebration/drafts/${draftId}/dismiss`,
      { method: "POST" }
    );
  },

  async getCelebrationStatus(): Promise<CelebrationStatus> {
    return apiFetch<CelebrationStatus>("/social/celebration/status");
  },

  // =========================
  // AI Interview (Applicant) - Phase 1: voice foundation
  //
  // The browser never holds a LiveKit secret: it asks SmartHR for a session,
  // and SmartHR returns a short-lived token for one room, microphone + camera (Stage 4A).
  // =========================

  async getAiInterviewStatus(): Promise<AiInterviewStatus> {
    return apiFetch<AiInterviewStatus>("/ai-interview/status");
  },

  async getMyAiInterviews(): Promise<{ interviews: AiInterviewListing[] }> {
    return apiFetch<{ interviews: AiInterviewListing[] }>("/ai-interview/interviews");
  },

  /** The backend resolves the job and checks ownership; language is optional for legacy callers. */
  async startAiInterviewSession(interviewId: number, language?: 'en' | 'ar'): Promise<AiInterviewSession> {
    return apiFetch<AiInterviewSession>("/ai-interview/session", {
      method: "POST",
      body: JSON.stringify({ interview_id: interviewId, ...(language ? { language } : {}) }),
    });
  },

  // --- AI Interview report (Phase 8, Admin / HR) ---------------------------

  /** Built from stored answers and analyses; one session, never merged. */
  async getAiInterviewReport(interviewId: number, sessionId?: number): Promise<AiInterviewReport> {
    const query = sessionId ? `?session_id=${sessionId}` : "";
    return apiFetch<AiInterviewReport>(`/ai-interview/report/${interviewId}${query}`);
  },

  /** The existing Phase 7 re-run: analyses answers with no completed analysis. */
  async reanalyseAiInterview(interviewId: number): Promise<AiReanalyseResult> {
    return apiFetch<AiReanalyseResult>(`/ai-interview/answers/${interviewId}/analyse`, {
      method: "POST",
    });
  },

  /** Phase 11.5.3: counts over recorded AI Interview activity. Admin / HR only. */
  async getAiInterviewAnalytics(): Promise<AiInterviewAnalytics> {
    return apiFetch<AiInterviewAnalytics>("/ai-interview/analytics");
  },
};
