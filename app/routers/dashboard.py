"""Read-only aggregation endpoints for the dashboards and the reports page.

Nothing here writes. Every figure is counted or averaged from the tables that
already exist - no column was added for reporting, and no value is invented.

Where the schema simply cannot answer a question the payload says so with an
explicit null plus an `*_available: false` flag, rather than returning a
plausible-looking number. Two such gaps exist today:

  * work mode (remote / hybrid / onsite) - employees has no such column;
  * turnover / exits / retention - there is no termination or exit date
    anywhere, and employment_status only ever holds 'active' in this database,
    so an exit count cannot be derived from what is stored.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Employee,
    Department,
    Position,
    Job,
    Application,
    Candidate,
    Interview,
    Attendance,
    LeaveRequest,
    Training,
    EmployeeTraining,
    PerformanceReview,
    User,
    AuditLog,
)
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.routers.interviews import describe_user, read_status as read_interview_status
from app.routers.applications import read_stage
from app.routers.performance_reviews import rating_label


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Shared helpers
# =========================

# Chart colours are presentation, not data. The palette is cycled by index so
# a department added tomorrow still gets a colour without a stored column.
PALETTE = [
    "#7C3AED", "#6366F1", "#0284C7", "#059669", "#D97706",
    "#DB2777", "#4F46E5", "#0891B2", "#65A30D", "#64748B",
]


def color_at(index: int) -> str:
    return PALETTE[index % len(PALETTE)]


def pct(part: int | float, whole: int | float, digits: int = 1) -> float:
    """Percentage that is safe on an empty dataset."""
    if not whole:
        return 0.0
    return round((part / whole) * 100, digits)


def day_span(start: date | None, end: date | None) -> int:
    """Inclusive day count, matching duration_days() in leave_requests.py."""
    if start is None or end is None:
        return 0
    if end < start:
        return 0
    return (end - start).days + 1


def employee_name(employee: Employee | None) -> str | None:
    if employee is None:
        return None
    return f"{employee.first_name} {employee.last_name}"


def resolve_employee(user: User, db: Session) -> Employee | None:
    """users stores no name and no department - the person is the employees
    row whose user_id matches. An account with no such row is legitimate, so
    callers must handle None rather than 404."""
    return db.query(Employee).filter(Employee.user_id == user.id).first()


def department_distribution(db: Session, employee_ids: list[int] | None = None):
    """Headcount per department, counted from employees.department_id."""
    query = db.query(
        Employee.department_id,
        func.count(Employee.id)
    )

    if employee_ids is not None:
        if not employee_ids:
            return []
        query = query.filter(Employee.id.in_(employee_ids))

    rows = query.group_by(Employee.department_id).all()

    names = {d.id: d.name for d in db.query(Department).all()}
    total = sum(count for _, count in rows)

    result = [
        {
            "department": names.get(dept_id, "Unassigned"),
            "department_id": dept_id,
            "count": count,
            "percentage": pct(count, total, 0),
        }
        for dept_id, count in rows
    ]

    result.sort(key=lambda row: row["count"], reverse=True)

    for index, row in enumerate(result):
        row["color"] = color_at(index)

    return result


# The funnel the UI draws, in pipeline order. applications.status owns the
# vocabulary (see app/routers/applications.py); rejected sits outside the
# funnel because it is an exit, not a stage.
FUNNEL_STAGES = [
    "applied", "screening", "shortlisted", "interview",
    "assessment", "offer", "hired",
]

STAGE_LABELS = {
    "applied": "Applied",
    "screening": "Screening",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "assessment": "Assessment",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Rejected",
}


def recruitment_pipeline(db: Session):
    """Counts each application at the stage it currently sits in. Rates are
    expressed against the total number of applications, so they read as the
    share of the funnel still at or past that point."""
    applications = db.query(Application).all()

    counts: dict[str, int] = {stage: 0 for stage in FUNNEL_STAGES}
    rejected = 0

    for application in applications:
        stage = read_stage(application.status)
        if stage == "rejected":
            rejected += 1
        else:
            counts[stage] = counts.get(stage, 0) + 1

    total = len(applications)

    pipeline = [
        {
            "stage": STAGE_LABELS[stage],
            "token": stage,
            "count": counts.get(stage, 0),
            "rate": f"{pct(counts.get(stage, 0), total, 1)}%",
            "color": color_at(index),
        }
        for index, stage in enumerate(FUNNEL_STAGES)
    ]

    return {
        "stages": pipeline,
        "total_applications": total,
        "rejected": rejected,
    }


def attendance_summary(db: Session, on_date: date | None = None, employee_ids: list[int] | None = None):
    """attendance.status holds Title Case values in this database."""
    query = db.query(Attendance)

    if on_date is not None:
        query = query.filter(Attendance.date == on_date)

    if employee_ids is not None:
        if not employee_ids:
            records = []
        else:
            records = query.filter(Attendance.employee_id.in_(employee_ids)).all()
    else:
        records = query.all()

    buckets: dict[str, int] = {}
    worked = []

    for record in records:
        status = record.status or "Unknown"
        buckets[status] = buckets.get(status, 0) + 1

        if record.check_in and record.check_out:
            start = record.check_in.hour * 60 + record.check_in.minute
            end = record.check_out.hour * 60 + record.check_out.minute
            if end > start:
                worked.append((end - start) / 60)

    total = len(records)
    present = buckets.get("Present", 0)
    late = buckets.get("Late", 0)

    return {
        "date": on_date.isoformat() if on_date else None,
        "total_records": total,
        "by_status": [
            {"status": status, "count": count, "percentage": pct(count, total, 1)}
            for status, count in sorted(buckets.items(), key=lambda kv: -kv[1])
        ],
        "present": present,
        "late": late,
        "absent": buckets.get("Absent", 0),
        "on_leave": buckets.get("On Leave", 0),
        "half_day": buckets.get("Half Day", 0),
        # On-time share of every logged record.
        "punctuality_rate": pct(present, total, 1),
        # Anyone who turned up at all, on time or late.
        "attendance_rate": pct(present + late, total, 1),
        "avg_worked_hours": round(sum(worked) / len(worked), 2) if worked else None,
    }


def interview_brief(interview: Interview, db: Session):
    application = (
        db.query(Application)
        .filter(Application.id == interview.application_id)
        .first()
    )

    candidate = None
    job = None

    if application is not None:
        candidate = (
            db.query(Candidate)
            .filter(Candidate.id == application.candidate_id)
            .first()
        )
        job = db.query(Job).filter(Job.id == application.job_id).first()

    interviewer = None
    if interview.interviewer_id is not None:
        user = db.query(User).filter(User.id == interview.interviewer_id).first()
        interviewer, _ = describe_user(user, db) if user else (None, None)

    return {
        "id": interview.id,
        "candidate_name": (
            f"{candidate.first_name} {candidate.last_name}" if candidate else None
        ),
        "job_title": job.title if job else None,
        "scheduled_at": (
            interview.scheduled_at.isoformat() if interview.scheduled_at else None
        ),
        "location": interview.location,
        "status": read_interview_status(interview.status),
        "interviewer_name": interviewer,
    }


def leave_brief(leave: LeaveRequest, db: Session):
    employee = db.query(Employee).filter(Employee.id == leave.employee_id).first()

    department = None
    if employee is not None and employee.department_id is not None:
        department = (
            db.query(Department)
            .filter(Department.id == employee.department_id)
            .first()
        )

    return {
        "id": leave.id,
        "employee_id": leave.employee_id,
        "employee_name": employee_name(employee),
        "department_name": department.name if department else None,
        "leave_type": leave.leave_type,
        "start_date": leave.start_date.isoformat() if leave.start_date else None,
        "end_date": leave.end_date.isoformat() if leave.end_date else None,
        "duration_days": day_span(leave.start_date, leave.end_date),
        "status": leave.status,
        "reason": leave.reason,
    }


def employee_brief(employee: Employee, db: Session):
    department = None
    position = None

    if employee.department_id is not None:
        department = (
            db.query(Department)
            .filter(Department.id == employee.department_id)
            .first()
        )

    if employee.position_id is not None:
        position = (
            db.query(Position)
            .filter(Position.id == employee.position_id)
            .first()
        )

    return {
        "id": employee.id,
        "name": employee_name(employee),
        "department_id": employee.department_id,
        "department_name": department.name if department else None,
        "position_id": employee.position_id,
        "position_title": position.title if position else None,
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "employment_status": employee.employment_status,
        "user_id": employee.user_id,
    }


# =========================
# Attention items
#
# Every item below is a count of real rows. Nothing is emitted unless the
# records that justify it exist, so an empty database yields an empty list
# rather than a set of invented alerts.
# =========================

def build_attention_items(db: Session, today: date):
    items = []

    # 1. Leave requests still waiting on a decision.
    pending_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "Pending")
        .all()
    )

    if pending_leaves:
        starting_soon = [
            leave for leave in pending_leaves
            if leave.start_date and 0 <= (leave.start_date - today).days <= 7
        ]
        items.append({
            "id": "pending-leave",
            "type": "leave",
            "severity": "high" if starting_soon else "medium",
            "title": (
                f"{len(pending_leaves)} leave request"
                f"{'s' if len(pending_leaves) != 1 else ''} awaiting a decision"
            ),
            "description": (
                f"{len(starting_soon)} of them start within the next 7 days."
                if starting_soon
                else "None of them start within the next 7 days."
            ),
            "context": "Leave Requests",
            "due_label": "Starts this week" if starting_soon else "No immediate deadline",
            "action_label": "Review Leave",
            "target_page": "manager-leave",
            "count": len(pending_leaves),
        })

    # 2. Interviews on the calendar in the week ahead.
    horizon = datetime.combine(today + timedelta(days=7), datetime.min.time())
    now = datetime.now()

    upcoming_interviews = (
        db.query(Interview)
        .filter(Interview.scheduled_at >= now)
        .filter(Interview.scheduled_at <= horizon)
        .all()
    )

    if upcoming_interviews:
        items.append({
            "id": "upcoming-interviews",
            "type": "recruitment",
            "severity": "medium",
            "title": (
                f"{len(upcoming_interviews)} interview"
                f"{'s' if len(upcoming_interviews) != 1 else ''} scheduled this week"
            ),
            "description": "Confirm interviewers, times and locations before they run.",
            "context": "Interviews",
            "due_label": "Next 7 days",
            "action_label": "View Interviews",
            "target_page": "hr-interviews",
            "count": len(upcoming_interviews),
        })

    # 3. Applications nobody has moved out of the intake stages yet.
    unreviewed = (
        db.query(Application)
        .filter(func.lower(Application.status).in_(["applied", "screening"]))
        .count()
    )

    if unreviewed:
        items.append({
            "id": "unreviewed-applications",
            "type": "recruitment",
            "severity": "medium",
            "title": f"{unreviewed} application{'s' if unreviewed != 1 else ''} still at intake",
            "description": "Applications sitting at Applied or Screening have not been advanced.",
            "context": "Candidates",
            "due_label": "Pipeline backlog",
            "action_label": "Open Pipeline",
            "target_page": "hr-candidates",
            "count": unreviewed,
        })

    # 4. Open requisitions that have attracted nobody.
    open_jobs = db.query(Job).filter(func.lower(Job.status) == "open").all()
    empty_jobs = [
        job for job in open_jobs
        if db.query(Application).filter(Application.job_id == job.id).count() == 0
    ]

    if empty_jobs:
        items.append({
            "id": "jobs-without-applicants",
            "type": "recruitment",
            "severity": "medium",
            "title": f"{len(empty_jobs)} open job{'s' if len(empty_jobs) != 1 else ''} with no applicants",
            "description": ", ".join(job.title for job in empty_jobs[:3]) + (
                f" and {len(empty_jobs) - 3} more" if len(empty_jobs) > 3 else ""
            ),
            "context": "Recruitment",
            "due_label": "No applications yet",
            "action_label": "Review Postings",
            "target_page": "hr-jobs",
            "count": len(empty_jobs),
        })

    # 5. Staff with no way to sign in - employees.user_id is nullable.
    unlinked = db.query(Employee).filter(Employee.user_id.is_(None)).count()

    if unlinked:
        items.append({
            "id": "employees-without-accounts",
            "type": "security",
            "severity": "medium",
            "title": f"{unlinked} employee{'s' if unlinked != 1 else ''} without a user account",
            "description": "These records have no linked login, so those people cannot access SmartHR.",
            "context": "Users",
            "due_label": "Access gap",
            "action_label": "Manage Users",
            "target_page": "users",
            "count": unlinked,
        })

    # 6. Failed sign-ins recorded by the audit trail in the past week.
    week_ago = datetime.combine(today - timedelta(days=7), datetime.min.time())
    failed_logins = (
        db.query(AuditLog)
        .filter(AuditLog.action == "LOGIN_FAILED")
        .filter(AuditLog.timestamp >= week_ago)
        .count()
    )

    if failed_logins:
        items.append({
            "id": "failed-logins",
            "type": "security",
            "severity": "high" if failed_logins >= 5 else "medium",
            "title": f"{failed_logins} failed sign-in attempt{'s' if failed_logins != 1 else ''}",
            "description": "Recorded in the audit trail over the past 7 days.",
            "context": "Audit Logs",
            "due_label": "Past 7 days",
            "action_label": "Inspect Trail",
            "target_page": "audit",
            "count": failed_logins,
        })

    # 7. Training assignments that were started but never finished.
    stalled = (
        db.query(EmployeeTraining)
        .filter(func.lower(EmployeeTraining.status) == "in_progress")
        .count()
    )

    if stalled:
        items.append({
            "id": "training-in-progress",
            "type": "compliance",
            "severity": "medium",
            "title": f"{stalled} training assignment{'s' if stalled != 1 else ''} in progress",
            "description": "Started but not yet marked complete.",
            "context": "Training",
            "due_label": "Incomplete",
            "action_label": "View Training",
            "target_page": "hr-training",
            "count": stalled,
        })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: severity_order.get(item["severity"], 3))

    return items


# =========================
# Admin dashboard
# =========================

@router.get("/admin")
def admin_dashboard(
    db: Session = Depends(get_db),
    # Admin only. This backs the Admin Command Center, which is the one
    # workspace `access.ts` reserves for role 1, and it reports account and
    # audit figures that the HR dashboard deliberately does not carry. HR has
    # its own endpoint at /dashboard/hr.
    current_user: User = Depends(require_roles(1))
):
    today = date.today()

    total_employees = db.query(Employee).count()
    active_employees = (
        db.query(Employee)
        .filter(func.lower(Employee.employment_status) == "active")
        .count()
    )

    total_users = db.query(User).count()
    active_user_accounts = db.query(User).filter(User.is_active.is_(True)).count()

    # "Active in the last 30 days" is answerable now that auth writes LOGIN
    # rows into audit_logs - it is a count of distinct signed-in accounts.
    thirty_days_ago = datetime.now() - timedelta(days=30)
    signed_in_30d = (
        db.query(func.count(func.distinct(AuditLog.user_id)))
        .filter(AuditLog.action == "LOGIN")
        .filter(AuditLog.timestamp >= thirty_days_ago)
        .scalar()
    ) or 0

    open_jobs = db.query(Job).filter(func.lower(Job.status) == "open").count()
    total_jobs = db.query(Job).count()

    new_hires_30d = (
        db.query(Employee)
        .filter(Employee.hire_date.isnot(None))
        .filter(Employee.hire_date >= today - timedelta(days=30))
        .count()
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "kpis": {
            "total_employees": total_employees,
            "active_employees": active_employees,
            "new_hires_30d": new_hires_30d,
            "total_users": total_users,
            "active_user_accounts": active_user_accounts,
            "signed_in_30d": signed_in_30d,
            "departments": db.query(Department).count(),
            "positions": db.query(Position).count(),
            "open_jobs": open_jobs,
            "total_jobs": total_jobs,
        },
        "department_distribution": department_distribution(db),
        "recruitment": recruitment_pipeline(db),
        "attendance_today": attendance_summary(db, today),
        "attention_items": build_attention_items(db, today),
        # employees has no work-mode column, so there is nothing to report.
        "work_mode_available": False,
        "work_mode": None,
    }


# =========================
# HR dashboard
# =========================

@router.get("/hr")
def hr_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    today = date.today()
    now = datetime.now()

    total_employees = db.query(Employee).count()

    new_hires_30d = (
        db.query(Employee)
        .filter(Employee.hire_date.isnot(None))
        .filter(Employee.hire_date >= today - timedelta(days=30))
        .count()
    )
    new_hires_90d = (
        db.query(Employee)
        .filter(Employee.hire_date.isnot(None))
        .filter(Employee.hire_date >= today - timedelta(days=90))
        .count()
    )

    open_positions = db.query(Job).filter(func.lower(Job.status) == "open").count()

    upcoming = (
        db.query(Interview)
        .filter(Interview.scheduled_at >= now)
        .order_by(Interview.scheduled_at)
        .all()
    )

    # A candidate is "active" while at least one of their applications is
    # still live - neither hired nor rejected.
    live_candidate_ids = {
        application.candidate_id
        for application in db.query(Application).all()
        if read_stage(application.status) not in ("hired", "rejected")
    }

    pending_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "Pending")
        .order_by(LeaveRequest.start_date)
        .all()
    )

    assignments = db.query(EmployeeTraining).all()
    completed_assignments = [
        a for a in assignments if (a.status or "").lower() == "completed"
    ]

    recent_hires = (
        db.query(Employee)
        .filter(Employee.hire_date.isnot(None))
        .order_by(Employee.hire_date.desc())
        .limit(5)
        .all()
    )

    return {
        "generated_at": now.isoformat(),
        "kpis": {
            "total_employees": total_employees,
            "new_hires_30d": new_hires_30d,
            "new_hires_90d": new_hires_90d,
            "open_positions": open_positions,
            "interviews_upcoming": len(upcoming),
            "interviews_total": db.query(Interview).count(),
            "active_candidates": len(live_candidate_ids),
            "total_candidates": db.query(Candidate).count(),
            "pending_leave_requests": len(pending_leaves),
            "training_courses": db.query(Training).count(),
            "training_assignments": len(assignments),
            "training_completed": len(completed_assignments),
            "training_completion_rate": pct(len(completed_assignments), len(assignments), 1),
        },
        "attendance_today": attendance_summary(db, today),
        "department_distribution": department_distribution(db),
        "recruitment": recruitment_pipeline(db),
        "upcoming_interviews": [interview_brief(i, db) for i in upcoming[:6]],
        "pending_leave": [leave_brief(leave, db) for leave in pending_leaves[:6]],
        "recent_hires": [employee_brief(e, db) for e in recent_hires],
        "attention_items": build_attention_items(db, today),
        "work_mode_available": False,
        "work_mode": None,
    }


# =========================
# Manager dashboard
#
# A manager's team is employees.manager_id pointing at the manager's own
# employees row, so the caller has to be linked to one. When they are not -
# or when nobody reports to them - the payload says so and every figure is a
# truthful zero rather than a stand-in.
# =========================

@router.get("/manager")
def manager_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    today = date.today()
    now = datetime.now()

    me = resolve_employee(current_user, db)

    team = []
    if me is not None:
        team = db.query(Employee).filter(Employee.manager_id == me.id).all()

    team_ids = [member.id for member in team]

    today_attendance = {
        record.employee_id: record
        for record in (
            db.query(Attendance)
            .filter(Attendance.date == today)
            .filter(Attendance.employee_id.in_(team_ids))
            .all()
            if team_ids else []
        )
    }

    pending_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "Pending")
        .filter(LeaveRequest.employee_id.in_(team_ids))
        .order_by(LeaveRequest.start_date)
        .all()
        if team_ids else []
    )

    approved_today = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "Approved")
        .filter(LeaveRequest.employee_id.in_(team_ids))
        .filter(LeaveRequest.start_date <= today)
        .filter(LeaveRequest.end_date >= today)
        .all()
        if team_ids else []
    )
    on_leave_ids = {leave.employee_id for leave in approved_today}

    reviews = (
        db.query(PerformanceReview)
        .filter(PerformanceReview.employee_id.in_(team_ids))
        .all()
        if team_ids else []
    )
    rated = [r.rating for r in reviews if r.rating is not None]

    assignments = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.employee_id.in_(team_ids))
        .all()
        if team_ids else []
    )

    # Interviews the manager is personally down to run (interviewer_id is a
    # FK to users, not employees).
    my_interviews = (
        db.query(Interview)
        .filter(Interview.interviewer_id == current_user.id)
        .filter(Interview.scheduled_at >= now)
        .order_by(Interview.scheduled_at)
        .all()
    )

    members = []
    for member in team:
        record = today_attendance.get(member.id)
        brief = employee_brief(member, db)
        brief["today_status"] = record.status if record else None
        brief["check_in"] = record.check_in.isoformat() if record and record.check_in else None
        brief["check_out"] = record.check_out.isoformat() if record and record.check_out else None
        brief["on_leave_today"] = member.id in on_leave_ids
        members.append(brief)

    present = sum(1 for r in today_attendance.values() if r.status == "Present")
    late = sum(1 for r in today_attendance.values() if r.status == "Late")

    return {
        "generated_at": now.isoformat(),
        "linked_employee": employee_brief(me, db) if me else None,
        "is_linked": me is not None,
        "has_team": bool(team),
        "kpis": {
            "team_size": len(team),
            "present_today": present,
            "late_today": late,
            "on_leave_today": len(on_leave_ids),
            "not_logged_today": len(team) - len(today_attendance),
            "pending_leave_requests": len(pending_leaves),
            "performance_reviews": len(reviews),
            "average_rating": round(sum(rated) / len(rated), 2) if rated else None,
            "training_assignments": len(assignments),
            "training_completed": sum(
                1 for a in assignments if (a.status or "").lower() == "completed"
            ),
            "interviews_upcoming": len(my_interviews),
        },
        "team": members,
        "attendance_today": attendance_summary(db, today, team_ids),
        "department_distribution": department_distribution(db, team_ids),
        "pending_leave": [leave_brief(leave, db) for leave in pending_leaves],
        "upcoming_interviews": [interview_brief(i, db) for i in my_interviews[:5]],
    }


# =========================
# Employee dashboard
#
# Scoped to the caller and nobody else: every query below is filtered by the
# employees row linked to the JWT user.
# =========================

@router.get("/employee")
def employee_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    today = date.today()
    now = datetime.now()

    me = resolve_employee(current_user, db)

    if me is None:
        return {
            "generated_at": now.isoformat(),
            "is_linked": False,
            "employee": None,
            "attendance_today": None,
            "attendance_30d": None,
            "leave": None,
            "training": None,
            "performance": None,
            "upcoming_leave": [],
        }

    today_record = (
        db.query(Attendance)
        .filter(Attendance.employee_id == me.id)
        .filter(Attendance.date == today)
        .first()
    )

    recent_records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == me.id)
        .filter(Attendance.date >= today - timedelta(days=30))
        .all()
    )

    buckets: dict[str, int] = {}
    for record in recent_records:
        buckets[record.status or "Unknown"] = buckets.get(record.status or "Unknown", 0) + 1

    my_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == me.id)
        .all()
    )

    days_by_type: dict[str, int] = {}
    for leave in my_leaves:
        if leave.status == "Approved":
            key = leave.leave_type or "Unspecified"
            days_by_type[key] = days_by_type.get(key, 0) + day_span(leave.start_date, leave.end_date)

    upcoming_leave = [
        leave for leave in my_leaves
        if leave.start_date and leave.start_date >= today and leave.status in ("Pending", "Approved")
    ]
    upcoming_leave.sort(key=lambda leave: leave.start_date)

    assignments = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.employee_id == me.id)
        .all()
    )

    training_items = []
    for assignment in assignments:
        course = (
            db.query(Training)
            .filter(Training.id == assignment.training_id)
            .first()
        )
        training_items.append({
            "id": assignment.id,
            "training_id": assignment.training_id,
            "title": course.title if course else None,
            "provider": course.provider if course else None,
            "duration_hours": course.duration_hours if course else None,
            "status": assignment.status,
            "started_at": assignment.started_at.isoformat() if assignment.started_at else None,
            "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        })

    my_reviews = (
        db.query(PerformanceReview)
        .filter(PerformanceReview.employee_id == me.id)
        .order_by(PerformanceReview.review_date.desc())
        .all()
    )
    rated = [r.rating for r in my_reviews if r.rating is not None]
    latest = my_reviews[0] if my_reviews else None

    total_30d = len(recent_records)

    return {
        "generated_at": now.isoformat(),
        "is_linked": True,
        "employee": employee_brief(me, db),
        "attendance_today": {
            "status": today_record.status if today_record else None,
            "check_in": today_record.check_in.isoformat() if today_record and today_record.check_in else None,
            "check_out": today_record.check_out.isoformat() if today_record and today_record.check_out else None,
            "logged": today_record is not None,
        },
        "attendance_30d": {
            "total_records": total_30d,
            "present": buckets.get("Present", 0),
            "late": buckets.get("Late", 0),
            "absent": buckets.get("Absent", 0),
            "punctuality_rate": pct(buckets.get("Present", 0), total_30d, 1),
            "by_status": [
                {"status": status, "count": count, "percentage": pct(count, total_30d, 1)}
                for status, count in sorted(buckets.items(), key=lambda kv: -kv[1])
            ],
        },
        "leave": {
            "total_requests": len(my_leaves),
            "pending": sum(1 for l in my_leaves if l.status == "Pending"),
            "approved": sum(1 for l in my_leaves if l.status == "Approved"),
            "rejected": sum(1 for l in my_leaves if l.status == "Rejected"),
            "approved_days_taken": sum(days_by_type.values()),
            # There is no leave_balances table, so entitlement and remaining
            # days cannot be reported - only what has actually been taken.
            "entitlement_available": False,
            "days_by_type": [
                {"leave_type": key, "days": value}
                for key, value in sorted(days_by_type.items(), key=lambda kv: -kv[1])
            ],
        },
        "upcoming_leave": [leave_brief(leave, db) for leave in upcoming_leave[:5]],
        "training": {
            "total": len(assignments),
            "assigned": sum(1 for a in assignments if (a.status or "").lower() == "assigned"),
            "in_progress": sum(1 for a in assignments if (a.status or "").lower() == "in_progress"),
            "completed": sum(1 for a in assignments if (a.status or "").lower() == "completed"),
            "completion_rate": pct(
                sum(1 for a in assignments if (a.status or "").lower() == "completed"),
                len(assignments),
                1,
            ),
            "items": training_items,
        },
        "performance": {
            "reviews": len(my_reviews),
            "average_rating": round(sum(rated) / len(rated), 2) if rated else None,
            "latest_rating": latest.rating if latest else None,
            "latest_label": rating_label(latest.rating) if latest else None,
            "latest_review_date": (
                latest.review_date.isoformat() if latest and latest.review_date else None
            ),
            "latest_feedback": latest.feedback if latest else None,
        },
    }


# =========================
# Reports and analytics
# =========================

@router.get("/reports")
def reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    today = date.today()

    employees = db.query(Employee).all()
    total_employees = len(employees)

    status_buckets: dict[str, int] = {}
    tenures = []

    for employee in employees:
        key = employee.employment_status or "unknown"
        status_buckets[key] = status_buckets.get(key, 0) + 1
        if employee.hire_date:
            tenures.append((today - employee.hire_date).days / 365.25)

    # --- headcount history -------------------------------------------------
    # Built by bucketing hire_date. There is no termination or exit date in
    # the schema, so this is a cumulative hire curve, not a true headcount
    # series - exits_tracked says as much rather than implying otherwise.
    months = []
    cursor = date(today.year, today.month, 1)
    for _ in range(12):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()

    headcount_history = []
    for month_start in months:
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        hires = sum(
            1 for e in employees
            if e.hire_date and month_start <= e.hire_date < next_month
        )
        cumulative = sum(
            1 for e in employees
            if e.hire_date and e.hire_date < next_month
        )

        headcount_history.append({
            "month": month_start.isoformat(),
            "label": month_start.strftime("%b %y"),
            "hires": hires,
            "cumulative": cumulative,
        })

    # --- leave -------------------------------------------------------------
    leaves = db.query(LeaveRequest).all()

    leave_type_days: dict[str, int] = {}
    leave_type_requests: dict[str, int] = {}
    leave_status: dict[str, int] = {}

    for leave in leaves:
        key = leave.leave_type or "Unspecified"
        days = day_span(leave.start_date, leave.end_date)
        leave_type_days[key] = leave_type_days.get(key, 0) + days
        leave_type_requests[key] = leave_type_requests.get(key, 0) + 1
        leave_status[leave.status or "Unknown"] = leave_status.get(leave.status or "Unknown", 0) + 1

    total_leave_days = sum(leave_type_days.values())

    # --- training ----------------------------------------------------------
    assignments = db.query(EmployeeTraining).all()
    employee_departments = {e.id: e.department_id for e in employees}
    department_names = {d.id: d.name for d in db.query(Department).all()}

    training_by_dept: dict[int | None, dict[str, int]] = {}
    training_status: dict[str, int] = {}

    for assignment in assignments:
        status = (assignment.status or "unknown").lower()
        training_status[status] = training_status.get(status, 0) + 1

        dept_id = employee_departments.get(assignment.employee_id)
        bucket = training_by_dept.setdefault(dept_id, {"assigned": 0, "completed": 0})
        bucket["assigned"] += 1
        if status == "completed":
            bucket["completed"] += 1

    training_completed = training_status.get("completed", 0)

    # --- performance -------------------------------------------------------
    reviews = db.query(PerformanceReview).all()
    rating_counts: dict[int, int] = {}
    for review in reviews:
        if review.rating is not None:
            rating_counts[review.rating] = rating_counts.get(review.rating, 0) + 1

    rated_total = sum(rating_counts.values())
    all_ratings = [r.rating for r in reviews if r.rating is not None]

    # --- recruitment -------------------------------------------------------
    pipeline = recruitment_pipeline(db)
    hired = next(
        (s["count"] for s in pipeline["stages"] if s["token"] == "hired"), 0
    )

    interview_status: dict[str, int] = {}
    for interview in db.query(Interview).all():
        token = read_interview_status(interview.status)
        interview_status[token] = interview_status.get(token, 0) + 1

    job_status: dict[str, int] = {}
    for job in db.query(Job).all():
        token = (job.status or "draft").lower()
        job_status[token] = job_status.get(token, 0) + 1

    return {
        "generated_at": datetime.now().isoformat(),
        "headcount": {
            "total": total_employees,
            "active": status_buckets.get("active", 0),
            "by_status": [
                {"status": key, "count": value, "percentage": pct(value, total_employees, 1)}
                for key, value in sorted(status_buckets.items(), key=lambda kv: -kv[1])
            ],
            "avg_tenure_years": round(sum(tenures) / len(tenures), 2) if tenures else None,
            "with_hire_date": len(tenures),
            "history": headcount_history,
            # No exit/termination column exists anywhere in the schema.
            "exits_tracked": False,
        },
        "department_breakdown": department_distribution(db),
        "attendance": attendance_summary(db),
        "leave": {
            "total_requests": len(leaves),
            "total_days": total_leave_days,
            "by_type": [
                {
                    "leave_type": key,
                    "requests": leave_type_requests.get(key, 0),
                    "days": value,
                    "percentage": pct(value, total_leave_days, 0),
                    "color": color_at(index),
                }
                for index, (key, value) in enumerate(
                    sorted(leave_type_days.items(), key=lambda kv: -kv[1])
                )
            ],
            "by_status": [
                {"status": key, "count": value, "percentage": pct(value, len(leaves), 1)}
                for key, value in sorted(leave_status.items(), key=lambda kv: -kv[1])
            ],
        },
        "recruitment": {
            "total_candidates": db.query(Candidate).count(),
            "total_applications": pipeline["total_applications"],
            "rejected_applications": pipeline["rejected"],
            "hired": hired,
            "conversion_rate": pct(hired, pipeline["total_applications"], 1),
            "stages": pipeline["stages"],
            "jobs_by_status": [
                {"status": key, "count": value}
                for key, value in sorted(job_status.items(), key=lambda kv: -kv[1])
            ],
            "interviews_by_status": [
                {"status": key, "count": value}
                for key, value in sorted(interview_status.items(), key=lambda kv: -kv[1])
            ],
        },
        "training": {
            "courses": db.query(Training).count(),
            "assignments": len(assignments),
            "completed": training_completed,
            "completion_rate": pct(training_completed, len(assignments), 1),
            "by_status": [
                {"status": key, "count": value, "percentage": pct(value, len(assignments), 1)}
                for key, value in sorted(training_status.items(), key=lambda kv: -kv[1])
            ],
            "by_department": [
                {
                    "department": department_names.get(dept_id, "Unassigned"),
                    "assigned": bucket["assigned"],
                    "completed": bucket["completed"],
                    "rate": pct(bucket["completed"], bucket["assigned"], 0),
                }
                for dept_id, bucket in sorted(
                    training_by_dept.items(), key=lambda kv: -kv[1]["assigned"]
                )
            ],
        },
        "performance": {
            "reviews": len(reviews),
            "rated": rated_total,
            "average_rating": (
                round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None
            ),
            # performance_reviews.rating is an INTEGER with a CHECK of 1..5,
            # so the distribution has exactly five possible buckets.
            "by_rating": [
                {
                    "rating": value,
                    "label": rating_label(value),
                    "count": rating_counts.get(value, 0),
                    "percentage": pct(rating_counts.get(value, 0), rated_total, 0),
                    "color": color_at(5 - value),
                }
                for value in (5, 4, 3, 2, 1)
            ],
        },
        # Declared gaps. The UI keeps its panels but renders them as untracked
        # rather than showing a number the database cannot support.
        "work_mode_available": False,
        "work_mode": None,
        "turnover_available": False,
        "turnover": None,
    }
