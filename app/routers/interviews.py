from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import (
    Interview,
    Application,
    Candidate,
    Job,
    Department,
    Employee,
    Role,
    User,
)
from app.dependencies import require_roles
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_STATUS_CHANGE,
    ENTITY_INTERVIEW,
)


router = APIRouter(
    prefix="/interviews",
    tags=["Interviews"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Interview status
#
# interviews.status is a plain varchar(30) defaulting to 'scheduled'.
# These are the states the panel board works with; everything is stored
# lowercase/underscored so the column stays comparable in SQL.
# =========================

INTERVIEW_STATUSES = ("scheduled", "in_progress", "completed", "cancelled")

STATUS_ALIASES = {status: status for status in INTERVIEW_STATUSES}
STATUS_ALIASES.update({
    "in progress": "in_progress",
    "in-progress": "in_progress",
    "inprogress": "in_progress",
    "complete": "completed",
    "done": "completed",
    "canceled": "cancelled",
    "cancel": "cancelled",
})


def normalize_status(value: str | None) -> str:
    """Strict: used on write. Rejects anything outside the four states."""
    if value is None:
        return "scheduled"

    normalized = STATUS_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid interview status '{value}'. "
                f"Allowed values: {', '.join(INTERVIEW_STATUSES)}"
            )
        )

    return normalized


def read_status(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STATUS_ALIASES.get((value or "").strip().lower(), "scheduled")


class InterviewCreate(BaseModel):
    application_id: int
    interviewer_id: int | None = None
    scheduled_at: datetime
    location: str | None = None
    status: str = "scheduled"
    notes: str | None = None


class InterviewUpdate(BaseModel):
    application_id: int
    interviewer_id: int | None = None
    scheduled_at: datetime
    location: str | None = None
    status: str = "scheduled"
    notes: str | None = None


class InterviewStatusUpdate(BaseModel):
    status: str
    notes: str | None = None


def describe_user(user, db):
    """Users only carry an email and a role, so the display name comes from
    the linked employee row when one exists."""
    if user is None:
        return None, None

    employee = (
        db.query(Employee)
        .filter(Employee.user_id == user.id)
        .first()
    )

    name = (
        f"{employee.first_name} {employee.last_name}"
        if employee else user.email
    )

    role = (
        db.query(Role)
        .filter(Role.id == user.role_id)
        .first()
    )

    return name, (role.name if role else None)


def interview_to_dict(interview, db):
    application = (
        db.query(Application)
        .filter(Application.id == interview.application_id)
        .first()
    )

    candidate = None
    job = None
    department = None

    if application is not None:
        candidate = (
            db.query(Candidate)
            .filter(Candidate.id == application.candidate_id)
            .first()
        )

        job = (
            db.query(Job)
            .filter(Job.id == application.job_id)
            .first()
        )

        if job is not None:
            department = (
                db.query(Department)
                .filter(Department.id == job.department_id)
                .first()
            )

    interviewer = None
    if interview.interviewer_id:
        interviewer = (
            db.query(User)
            .filter(User.id == interview.interviewer_id)
            .first()
        )

    interviewer_name, interviewer_role = describe_user(interviewer, db)

    return {
        "id": interview.id,
        "application_id": interview.application_id,

        "candidate_id": candidate.id if candidate else None,
        "candidate_name": (
            f"{candidate.first_name} {candidate.last_name}"
            if candidate else None
        ),
        "candidate_email": candidate.email if candidate else None,

        "job_id": job.id if job else None,
        "job_title": job.title if job else None,
        "department_name": department.name if department else None,
        "application_stage": application.status if application else None,

        "interviewer_id": interview.interviewer_id,
        "interviewer_name": interviewer_name,
        "interviewer_role": interviewer_role,

        "scheduled_at": interview.scheduled_at,
        "location": interview.location,
        "status": read_status(interview.status),
        "notes": interview.notes,
        "created_at": interview.created_at,
    }


def get_interview_or_404(interview_id: int, db: Session) -> Interview:
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id)
        .first()
    )

    if interview is None:
        raise HTTPException(
            status_code=404,
            detail="Interview not found"
        )

    return interview


def validate_relations(application_id: int, interviewer_id: int | None, db: Session):
    application = (
        db.query(Application)
        .filter(Application.id == application_id)
        .first()
    )

    if application is None:
        raise HTTPException(
            status_code=400,
            detail=f"Application {application_id} does not exist"
        )

    if interviewer_id is not None:
        interviewer = (
            db.query(User)
            .filter(User.id == interviewer_id)
            .first()
        )

        if interviewer is None:
            raise HTTPException(
                status_code=400,
                detail=f"Interviewer (user) {interviewer_id} does not exist"
            )


# =========================
# Interviewer picker
#
# Declared before /{interview_id} so the literal path wins the match.
# The /users/ endpoint is Admin-only, so HR gets this narrow view instead.
# =========================

@router.get("/interviewers")
def get_interviewers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )

    result = []

    for user in users:
        name, role = describe_user(user, db)

        result.append({
            "id": user.id,
            "email": user.email,
            "name": name,
            "role": role,
        })

    return result


# =========================
# Get Interviews
# =========================

@router.get("/")
def get_interviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    interviews = (
        db.query(Interview)
        .order_by(Interview.scheduled_at.desc(), Interview.id.desc())
        .all()
    )

    return [
        interview_to_dict(interview, db)
        for interview in interviews
    ]


# =========================
# Get One Interview
# =========================

@router.get("/{interview_id}")
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    return interview_to_dict(get_interview_or_404(interview_id, db), db)


# =========================
# Create Interview
# =========================

@router.post("/")
def create_interview(
    interview_data: InterviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    validate_relations(
        interview_data.application_id,
        interview_data.interviewer_id,
        db
    )

    interview = Interview(
        application_id=interview_data.application_id,
        interviewer_id=interview_data.interviewer_id,
        scheduled_at=interview_data.scheduled_at,
        location=interview_data.location,
        status=normalize_status(interview_data.status),
        notes=interview_data.notes
    )

    db.add(interview)
    db.commit()
    db.refresh(interview)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_INTERVIEW, interview.id)

    return interview_to_dict(interview, db)


# =========================
# Update Interview
# =========================

@router.put("/{interview_id}")
def update_interview(
    interview_id: int,
    interview_data: InterviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    interview = get_interview_or_404(interview_id, db)

    validate_relations(
        interview_data.application_id,
        interview_data.interviewer_id,
        db
    )

    interview.application_id = interview_data.application_id
    interview.interviewer_id = interview_data.interviewer_id
    interview.scheduled_at = interview_data.scheduled_at
    interview.location = interview_data.location
    interview.status = normalize_status(interview_data.status)
    interview.notes = interview_data.notes

    db.commit()
    db.refresh(interview)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_INTERVIEW, interview.id)

    return interview_to_dict(interview, db)


# =========================
# Update Interview Status
#
# Notes are optional here so the "Complete & Review" flow can record the
# outcome and the status in a single call.
# =========================

@router.patch("/{interview_id}/status")
def update_interview_status(
    interview_id: int,
    status_data: InterviewStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    interview = get_interview_or_404(interview_id, db)

    interview.status = normalize_status(status_data.status)

    if status_data.notes is not None:
        interview.notes = status_data.notes

    db.commit()
    db.refresh(interview)

    record_audit(db, current_user, ACTION_STATUS_CHANGE, ENTITY_INTERVIEW, interview.id)

    return interview_to_dict(interview, db)
