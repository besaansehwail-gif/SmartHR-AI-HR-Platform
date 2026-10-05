from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Training, EmployeeTraining, User
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_TRAINING,
)


router = APIRouter(
    prefix="/trainings",
    tags=["Trainings"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TrainingCreate(BaseModel):
    title: str
    description: str | None = None
    provider: str | None = None
    duration_hours: int | None = None


class TrainingUpdate(BaseModel):
    title: str
    description: str | None = None
    provider: str | None = None
    duration_hours: int | None = None


def training_to_dict(training, db):
    """enrolled_count / completed_count / completion_rate are derived from
    the employee_trainings rows - the trainings table stores no counters."""
    assignments = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.training_id == training.id)
        .all()
    )

    enrolled_count = len(assignments)

    completed_count = len([
        assignment for assignment in assignments
        if (assignment.status or "").strip().lower() == "completed"
    ])

    completion_rate = (
        round(completed_count / enrolled_count * 100)
        if enrolled_count else 0
    )

    return {
        "id": training.id,
        "title": training.title,
        "description": training.description,
        "provider": training.provider,
        "duration_hours": training.duration_hours,
        "created_at": training.created_at,
        "enrolled_count": enrolled_count,
        "completed_count": completed_count,
        "completion_rate": completion_rate,
    }


def get_training_or_404(training_id: int, db: Session) -> Training:
    training = (
        db.query(Training)
        .filter(Training.id == training_id)
        .first()
    )

    if training is None:
        raise HTTPException(
            status_code=404,
            detail="Training not found"
        )

    return training


# =========================
# Get Trainings
# =========================

@router.get("/")
def get_trainings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    trainings = (
        db.query(Training)
        .order_by(Training.created_at.desc(), Training.id.desc())
        .all()
    )

    return [
        training_to_dict(training, db)
        for training in trainings
    ]


# =========================
# Get One Training
# =========================

@router.get("/{training_id}")
def get_training(
    training_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    return training_to_dict(get_training_or_404(training_id, db), db)


# =========================
# Create Training
# =========================

@router.post("/")
def create_training(
    training_data: TrainingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    if not training_data.title.strip():
        raise HTTPException(
            status_code=400,
            detail="Training title is required"
        )

    if training_data.duration_hours is not None and training_data.duration_hours < 0:
        raise HTTPException(
            status_code=400,
            detail="Duration hours cannot be negative"
        )

    training = Training(
        title=training_data.title.strip(),
        description=training_data.description,
        provider=training_data.provider,
        duration_hours=training_data.duration_hours
    )

    db.add(training)
    db.commit()
    db.refresh(training)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_TRAINING, training.id)

    return training_to_dict(training, db)


# =========================
# Update Training
# =========================

@router.put("/{training_id}")
def update_training(
    training_id: int,
    training_data: TrainingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    training = get_training_or_404(training_id, db)

    if not training_data.title.strip():
        raise HTTPException(
            status_code=400,
            detail="Training title is required"
        )

    if training_data.duration_hours is not None and training_data.duration_hours < 0:
        raise HTTPException(
            status_code=400,
            detail="Duration hours cannot be negative"
        )

    training.title = training_data.title.strip()
    training.description = training_data.description
    training.provider = training_data.provider
    training.duration_hours = training_data.duration_hours

    db.commit()
    db.refresh(training)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_TRAINING, training.id)

    return training_to_dict(training, db)
