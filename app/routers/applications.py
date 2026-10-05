from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Application, Candidate, Job, Department, User
from app.dependencies import require_roles
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_STATUS_CHANGE,
    ENTITY_APPLICATION,
)


router = APIRouter(
    prefix="/applications",
    tags=["Applications"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Recruitment stages
#
# applications.status is a plain varchar(30) defaulting to 'applied'.
# These are the stages the ATS board works with; everything is stored
# lowercase so the column stays comparable in SQL.
# =========================

APPLICATION_STAGES = (
    "applied",
    "screening",
    "shortlisted",
    "interview",
    "assessment",
    "offer",
    "hired",
    "rejected",
)

STAGE_ALIASES = {stage: stage for stage in APPLICATION_STAGES}
STAGE_ALIASES.update({
    "short listed": "shortlisted",
    "short-listed": "shortlisted",
    "screen": "screening",
    "interviewing": "interview",
    "offered": "offer",
    "reject": "rejected",
    "declined": "rejected",
})


def normalize_stage(value: str | None) -> str:
    """Strict: used on write. Rejects anything outside the known stages."""
    if value is None:
        return "applied"

    normalized = STAGE_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid application stage '{value}'. "
                f"Allowed values: {', '.join(APPLICATION_STAGES)}"
            )
        )

    return normalized


def read_stage(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STAGE_ALIASES.get((value or "").strip().lower(), "applied")


class ApplicationCreate(BaseModel):
    candidate_id: int
    job_id: int
    status: str = "applied"


class ApplicationStatusUpdate(BaseModel):
    status: str


def application_to_dict(application, db):
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

    department = None
    if job is not None:
        department = (
            db.query(Department)
            .filter(Department.id == job.department_id)
            .first()
        )

    return {
        "id": application.id,
        "candidate_id": application.candidate_id,
        "candidate_name": (
            f"{candidate.first_name} {candidate.last_name}"
            if candidate else None
        ),
        "job_id": application.job_id,
        "job_title": job.title if job else None,
        "department_name": department.name if department else None,
        "status": read_stage(application.status),
        "applied_at": application.applied_at,
    }


def get_application_or_404(application_id: int, db: Session) -> Application:
    application = (
        db.query(Application)
        .filter(Application.id == application_id)
        .first()
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found"
        )

    return application


@router.get("/")
def get_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    applications = (
        db.query(Application)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    return [
        application_to_dict(application, db)
        for application in applications
    ]


@router.post("/")
def create_application(
    application_data: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == application_data.candidate_id)
        .first()
    )

    if candidate is None:
        raise HTTPException(
            status_code=400,
            detail=f"Candidate {application_data.candidate_id} does not exist"
        )

    job = (
        db.query(Job)
        .filter(Job.id == application_data.job_id)
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=400,
            detail=f"Job {application_data.job_id} does not exist"
        )

    application = Application(
        candidate_id=application_data.candidate_id,
        job_id=application_data.job_id,
        status=normalize_stage(application_data.status)
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_APPLICATION, application.id)

    return application_to_dict(application, db)


# =========================
# Update Application Stage
# =========================

@router.patch("/{application_id}/status")
def update_application_status(
    application_id: int,
    status_data: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    application = get_application_or_404(application_id, db)

    application.status = normalize_stage(status_data.status)

    db.commit()
    db.refresh(application)

    record_audit(db, current_user, ACTION_STATUS_CHANGE, ENTITY_APPLICATION, application.id)

    return application_to_dict(application, db)
