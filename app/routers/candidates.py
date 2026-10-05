from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import (
    Candidate,
    Application,
    Job,
    Department,
    CV,
    Interview,
    User,
)
from app.dependencies import require_roles
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_CANDIDATE,
)
from app.routers.applications import normalize_stage, read_stage


router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    # Optional: when supplied, the candidate is immediately entered into the
    # pipeline for this requisition by inserting an applications row.
    job_id: int | None = None
    stage: str = "applied"


class CandidateUpdate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    location: str | None = None


def build_timeline(candidate, applications, interview, db):
    """Recruitment audit trail assembled from the rows that actually exist:
    the candidate record, their applications, and any scheduled interview.
    There is no dedicated history table, so nothing here is synthesised."""
    events = []

    events.append({
        "label": "Registered",
        "date": candidate.created_at,
        "note": "Candidate profile created in SmartHR.",
    })

    for application in applications:
        job = (
            db.query(Job)
            .filter(Job.id == application.job_id)
            .first()
        )

        events.append({
            "label": "Applied",
            "date": application.applied_at,
            "note": (
                f"Applied for {job.title}" if job
                else f"Applied for job #{application.job_id}"
            ),
        })

        stage = read_stage(application.status)

        if stage != "applied":
            events.append({
                "label": stage.title(),
                "date": application.applied_at,
                "note": (
                    f"Current stage for {job.title}." if job
                    else "Current pipeline stage."
                ),
            })

    if interview is not None:
        events.append({
            "label": "Interview",
            "date": interview.scheduled_at,
            "note": (
                f"Interview {interview.status}"
                + (f" - {interview.location}" if interview.location else "")
            ),
        })

    events.sort(key=lambda event: (event["date"] is None, event["date"]))

    return events


def candidate_to_dict(candidate, db):
    applications = (
        db.query(Application)
        .filter(Application.candidate_id == candidate.id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    # The most recent application is the one the ATS row represents.
    latest = applications[0] if applications else None

    job = None
    department = None

    if latest is not None:
        job = (
            db.query(Job)
            .filter(Job.id == latest.job_id)
            .first()
        )

        if job is not None:
            department = (
                db.query(Department)
                .filter(Department.id == job.department_id)
                .first()
            )

    # Most recent CV on file, if any.
    cv = (
        db.query(CV)
        .filter(CV.candidate_id == candidate.id)
        .order_by(CV.uploaded_at.desc(), CV.id.desc())
        .first()
    )

    # Most recent interview across every application this candidate has.
    interview = None

    if applications:
        interview = (
            db.query(Interview)
            .filter(
                Interview.application_id.in_(
                    [application.id for application in applications]
                )
            )
            .order_by(Interview.scheduled_at.desc(), Interview.id.desc())
            .first()
        )

    return {
        "id": candidate.id,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "full_name": f"{candidate.first_name} {candidate.last_name}",
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "created_at": candidate.created_at,

        "application_id": latest.id if latest else None,
        "job_id": latest.job_id if latest else None,
        "job_title": job.title if job else None,
        "department_name": department.name if department else None,
        "stage": read_stage(latest.status) if latest else None,
        "applied_at": latest.applied_at if latest else None,
        "applications_count": len(applications),

        "cv_file_name": cv.file_name if cv else None,
        "interview_status": interview.status if interview else None,
        "interview_scheduled_at": interview.scheduled_at if interview else None,

        "timeline": build_timeline(candidate, applications, interview, db),
    }


def get_candidate_or_404(candidate_id: int, db: Session) -> Candidate:
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id)
        .first()
    )

    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found"
        )

    return candidate


# =========================
# Get Candidates
# =========================

@router.get("/")
def get_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    candidates = (
        db.query(Candidate)
        .order_by(Candidate.created_at.desc(), Candidate.id.desc())
        .all()
    )

    return [
        candidate_to_dict(candidate, db)
        for candidate in candidates
    ]


# =========================
# Get One Candidate
# =========================

@router.get("/{candidate_id}")
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    return candidate_to_dict(get_candidate_or_404(candidate_id, db), db)


# =========================
# Create Candidate
# =========================

@router.post("/")
def create_candidate(
    candidate_data: CandidateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    if candidate_data.job_id is not None:
        job = (
            db.query(Job)
            .filter(Job.id == candidate_data.job_id)
            .first()
        )

        if job is None:
            raise HTTPException(
                status_code=400,
                detail=f"Job {candidate_data.job_id} does not exist"
            )

    candidate = Candidate(
        first_name=candidate_data.first_name,
        last_name=candidate_data.last_name,
        email=candidate_data.email,
        phone=candidate_data.phone,
        location=candidate_data.location
    )

    db.add(candidate)
    db.flush()

    if candidate_data.job_id is not None:
        db.add(
            Application(
                candidate_id=candidate.id,
                job_id=candidate_data.job_id,
                status=normalize_stage(candidate_data.stage)
            )
        )

    db.commit()
    db.refresh(candidate)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_CANDIDATE, candidate.id)

    return candidate_to_dict(candidate, db)


# =========================
# Update Candidate
# =========================

@router.put("/{candidate_id}")
def update_candidate(
    candidate_id: int,
    candidate_data: CandidateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    candidate = get_candidate_or_404(candidate_id, db)

    candidate.first_name = candidate_data.first_name
    candidate.last_name = candidate_data.last_name
    candidate.email = candidate_data.email
    candidate.phone = candidate_data.phone
    candidate.location = candidate_data.location

    db.commit()
    db.refresh(candidate)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_CANDIDATE, candidate.id)

    return candidate_to_dict(candidate, db)
