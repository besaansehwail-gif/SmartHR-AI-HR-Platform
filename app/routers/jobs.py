from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Job, Department, User, Application
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_STATUS_CHANGE,
    ENTITY_JOB,
)


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Status handling
#
# The jobs.status column is a plain varchar(30) defaulting to 'open'.
# These are the four values the recruitment UI works with; everything is
# stored lowercase/underscored so the column stays comparable in SQL.
# =========================

JOB_STATUSES = ("open", "on_hold", "closed", "draft")

STATUS_ALIASES = {
    "open": "open",
    "active": "open",
    "on hold": "on_hold",
    "on-hold": "on_hold",
    "on_hold": "on_hold",
    "onhold": "on_hold",
    "hold": "on_hold",
    "paused": "on_hold",
    "closed": "closed",
    "close": "closed",
    "draft": "draft",
}


def normalize_status(value: str | None) -> str:
    """Strict: used on write. Rejects anything outside the four states."""
    if value is None:
        return "open"

    normalized = STATUS_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid job status '{value}'. "
                f"Allowed values: {', '.join(JOB_STATUSES)}"
            )
        )

    return normalized


def read_status(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STATUS_ALIASES.get((value or "").strip().lower(), "draft")


# =========================
# Pipeline counts
#
# Sourced from the applications table (applications.job_id / .status),
# so the counters on each job card reflect real rows.
# =========================

PIPELINE_STAGES = (
    "applied",
    "screening",
    "shortlisted",
    "interview",
    "assessment",
    "offer",
    "hired",
    "rejected",
)


class JobCreate(BaseModel):
    title: str
    department_id: int
    description: str | None = None
    requirements: str | None = None
    status: str = "open"
    created_by: int | None = None


class JobUpdate(BaseModel):
    title: str
    department_id: int
    description: str | None = None
    requirements: str | None = None
    status: str = "open"


class JobStatusUpdate(BaseModel):
    status: str


def job_to_dict(job, db):
    department = (
        db.query(Department)
        .filter(Department.id == job.department_id)
        .first()
    )

    created_by_user = None
    if job.created_by:
        created_by_user = (
            db.query(User)
            .filter(User.id == job.created_by)
            .first()
        )

    applications = (
        db.query(Application)
        .filter(Application.job_id == job.id)
        .all()
    )

    pipeline_counts = {stage: 0 for stage in PIPELINE_STAGES}

    for application in applications:
        stage = (application.status or "").strip().lower()

        if stage in pipeline_counts:
            pipeline_counts[stage] += 1

    return {
        "id": job.id,
        "title": job.title,
        "department_id": job.department_id,
        "department_name": department.name if department else None,
        "description": job.description,
        "requirements": job.requirements,
        "status": read_status(job.status),
        "created_by": job.created_by,
        "created_by_email": created_by_user.email if created_by_user else None,
        "created_at": job.created_at,
        "applications_count": len(applications),
        "pipeline_counts": pipeline_counts,
    }


def get_job_or_404(job_id: int, db: Session) -> Job:
    job = (
        db.query(Job)
        .filter(Job.id == job_id)
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return job


def validate_department(department_id: int, db: Session):
    department = (
        db.query(Department)
        .filter(Department.id == department_id)
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=400,
            detail=f"Department {department_id} does not exist"
        )

    return department


# =========================
# Get Jobs
# =========================

@router.get("/")
def get_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    jobs = (
        db.query(Job)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .all()
    )

    return [
        job_to_dict(job, db)
        for job in jobs
    ]


# =========================
# Get One Job
# =========================

@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    return job_to_dict(get_job_or_404(job_id, db), db)


# =========================
# Create Job
# =========================

@router.post("/")
def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    validate_department(job_data.department_id, db)

    job = Job(
        title=job_data.title,
        department_id=job_data.department_id,
        description=job_data.description,
        requirements=job_data.requirements,
        status=normalize_status(job_data.status),
        created_by=job_data.created_by or current_user.id
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_JOB, job.id)

    return job_to_dict(job, db)


# =========================
# Update Job
# =========================

@router.put("/{job_id}")
def update_job(
    job_id: int,
    job_data: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    job = get_job_or_404(job_id, db)

    validate_department(job_data.department_id, db)

    job.title = job_data.title
    job.department_id = job_data.department_id
    job.description = job_data.description
    job.requirements = job_data.requirements
    job.status = normalize_status(job_data.status)

    db.commit()
    db.refresh(job)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_JOB, job.id)

    return job_to_dict(job, db)


# =========================
# Update Job Status
# =========================

@router.patch("/{job_id}/status")
def update_job_status(
    job_id: int,
    status_data: JobStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    job = get_job_or_404(job_id, db)

    job.status = normalize_status(status_data.status)

    db.commit()
    db.refresh(job)

    record_audit(db, current_user, ACTION_STATUS_CHANGE, ENTITY_JOB, job.id)

    return job_to_dict(job, db)
