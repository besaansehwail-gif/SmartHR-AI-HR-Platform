from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import (
    EmployeeTraining,
    Employee,
    Department,
    Position,
    Training,
    User,
)
from app.dependencies import require_roles
from app.dependencies import get_current_employee
from app.audit import (
    record_audit,
    ACTION_ASSIGN,
    ACTION_UPDATE,
    ACTION_STATUS_CHANGE,
    ENTITY_EMPLOYEE_TRAINING,
)


router = APIRouter(
    prefix="/employee-trainings",
    tags=["Employee Trainings"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Assignment status
#
# employee_trainings.status is a varchar(30) whose column default is the
# lowercase 'assigned', and the table starts empty, so lowercase tokens are
# the canonical form - consistent with jobs / applications / interviews.
# =========================

ASSIGNMENT_STATUSES = ("assigned", "in_progress", "completed", "cancelled")

STATUS_ALIASES = {status: status for status in ASSIGNMENT_STATUSES}
STATUS_ALIASES.update({
    "not started": "assigned",
    "not_started": "assigned",
    "in progress": "in_progress",
    "in-progress": "in_progress",
    "inprogress": "in_progress",
    "started": "in_progress",
    "complete": "completed",
    "done": "completed",
    "canceled": "cancelled",
})


def normalize_status(value: str | None) -> str:
    """Strict: used on write."""
    if value is None:
        return "assigned"

    normalized = STATUS_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid assignment status '{value}'. "
                f"Allowed values: {', '.join(ASSIGNMENT_STATUSES)}"
            )
        )

    return normalized


def read_status(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STATUS_ALIASES.get((value or "").strip().lower(), "assigned")


class EmployeeTrainingCreate(BaseModel):
    employee_id: int
    training_id: int
    status: str = "assigned"


class EmployeeTrainingUpdate(BaseModel):
    employee_id: int
    training_id: int
    status: str = "assigned"


class EmployeeTrainingStatusUpdate(BaseModel):
    status: str


def apply_status(assignment, status: str):
    """started_at / completed_at are the only progress columns on this table,
    so they are maintained from the status transition rather than sent by the
    client."""
    assignment.status = status

    now = datetime.utcnow()

    if status == "in_progress":
        if assignment.started_at is None:
            assignment.started_at = now
        assignment.completed_at = None

    elif status == "completed":
        if assignment.started_at is None:
            assignment.started_at = now
        if assignment.completed_at is None:
            assignment.completed_at = now

    else:
        # assigned / cancelled: the assignment is not in flight.
        assignment.started_at = None
        assignment.completed_at = None


def employee_training_to_dict(assignment, db):
    employee = (
        db.query(Employee)
        .filter(Employee.id == assignment.employee_id)
        .first()
    )

    department = None
    position = None

    if employee is not None:
        if employee.department_id:
            department = (
                db.query(Department)
                .filter(Department.id == employee.department_id)
                .first()
            )

        if employee.position_id:
            position = (
                db.query(Position)
                .filter(Position.id == employee.position_id)
                .first()
            )

    training = (
        db.query(Training)
        .filter(Training.id == assignment.training_id)
        .first()
    )

    return {
        "id": assignment.id,

        "employee_id": assignment.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee else None
        ),
        "department_name": department.name if department else None,
        "position_title": position.title if position else None,

        "training_id": assignment.training_id,
        "training_title": training.title if training else None,
        "training_provider": training.provider if training else None,
        "training_duration_hours": training.duration_hours if training else None,

        "status": read_status(assignment.status),
        "started_at": assignment.started_at,
        "completed_at": assignment.completed_at,
    }


def get_assignment_or_404(assignment_id: int, db: Session) -> EmployeeTraining:
    assignment = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.id == assignment_id)
        .first()
    )

    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail="Training assignment not found"
        )

    return assignment


def validate_relations(employee_id: int, training_id: int, db: Session):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {employee_id} does not exist"
        )

    training = (
        db.query(Training)
        .filter(Training.id == training_id)
        .first()
    )

    if training is None:
        raise HTTPException(
            status_code=400,
            detail=f"Training {training_id} does not exist"
        )


def ensure_not_duplicate(
    employee_id: int,
    training_id: int,
    db: Session,
    exclude_id: int | None = None
):
    query = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.employee_id == employee_id)
        .filter(EmployeeTraining.training_id == training_id)
    )

    if exclude_id is not None:
        query = query.filter(EmployeeTraining.id != exclude_id)

    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail="This employee is already enrolled in that training"
        )


# =========================
# Get Employee Trainings
# =========================

# =========================
# My Training
#
# Scoped to the caller and declared before /{assignment_id}.
# =========================

@router.get("/me")
def get_my_employee_trainings(
    db: Session = Depends(get_db),
    employee=Depends(get_current_employee)
):
    assignments = (
        db.query(EmployeeTraining)
        .filter(EmployeeTraining.employee_id == employee.id)
        .order_by(EmployeeTraining.id.desc())
        .all()
    )

    return [employee_training_to_dict(a, db) for a in assignments]


# =========================
# Get Assignments (whole organisation)
#
# Admin, HR and Managers only. Employees read /employee-trainings/me.
# =========================

@router.get("/")
def get_employee_trainings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    assignments = (
        db.query(EmployeeTraining)
        .order_by(EmployeeTraining.id.desc())
        .all()
    )

    return [
        employee_training_to_dict(assignment, db)
        for assignment in assignments
    ]


# =========================
# Get One Assignment
# =========================

@router.get("/{assignment_id}")
def get_employee_training(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    return employee_training_to_dict(
        get_assignment_or_404(assignment_id, db),
        db
    )


# =========================
# Assign Training to Employee
# =========================

@router.post("/")
def create_employee_training(
    data: EmployeeTrainingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    validate_relations(data.employee_id, data.training_id, db)
    ensure_not_duplicate(data.employee_id, data.training_id, db)

    assignment = EmployeeTraining(
        employee_id=data.employee_id,
        training_id=data.training_id
    )

    apply_status(assignment, normalize_status(data.status))

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    record_audit(db, current_user, ACTION_ASSIGN, ENTITY_EMPLOYEE_TRAINING, assignment.id)

    return employee_training_to_dict(assignment, db)


# =========================
# Update Assignment
# =========================

@router.put("/{assignment_id}")
def update_employee_training(
    assignment_id: int,
    data: EmployeeTrainingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    assignment = get_assignment_or_404(assignment_id, db)

    validate_relations(data.employee_id, data.training_id, db)
    ensure_not_duplicate(
        data.employee_id,
        data.training_id,
        db,
        exclude_id=assignment.id
    )

    assignment.employee_id = data.employee_id
    assignment.training_id = data.training_id

    apply_status(assignment, normalize_status(data.status))

    db.commit()
    db.refresh(assignment)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_EMPLOYEE_TRAINING, assignment.id)

    return employee_training_to_dict(assignment, db)


# =========================
# Update Assignment Status
# =========================

@router.patch("/{assignment_id}/status")
def update_employee_training_status(
    assignment_id: int,
    status_data: EmployeeTrainingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    assignment = get_assignment_or_404(assignment_id, db)

    apply_status(assignment, normalize_status(status_data.status))

    db.commit()
    db.refresh(assignment)

    record_audit(db, current_user, ACTION_STATUS_CHANGE, ENTITY_EMPLOYEE_TRAINING, assignment.id)

    return employee_training_to_dict(assignment, db)
