from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Position, Department, Employee, User
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ENTITY_POSITION,
)


router = APIRouter(
    prefix="/positions",
    tags=["Positions"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PositionCreate(BaseModel):
    title: str
    department_id: int


class PositionUpdate(BaseModel):
    title: str
    department_id: int


def position_to_dict(position, db):
    """The positions table holds only (id, title, department_id). The
    department name and headcount are resolved, not stored."""
    department = (
        db.query(Department)
        .filter(Department.id == position.department_id)
        .first()
    )

    employee_count = (
        db.query(Employee)
        .filter(Employee.position_id == position.id)
        .count()
    )

    return {
        "id": position.id,
        "title": position.title,
        "department_id": position.department_id,
        "department_name": department.name if department else None,
        "employee_count": employee_count,
    }


def get_position_or_404(position_id: int, db: Session) -> Position:
    position = (
        db.query(Position)
        .filter(Position.id == position_id)
        .first()
    )

    if position is None:
        raise HTTPException(
            status_code=404,
            detail="Position not found"
        )

    return position


def validate_department(department_id: int, db: Session) -> Department:
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


def assert_title_available(
    title: str,
    department_id: int,
    db: Session,
    exclude_id: int | None = None
):
    """No unique constraint exists on the table, but two identical titles in
    the same department are almost always a mistake, so the router guards it."""
    query = (
        db.query(Position)
        .filter(Position.title == title)
        .filter(Position.department_id == department_id)
    )

    if exclude_id is not None:
        query = query.filter(Position.id != exclude_id)

    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A position titled '{title}' already exists in that department"
            )
        )


# =========================
# Get Positions
# =========================

@router.get("/")
def get_positions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    positions = (
        db.query(Position)
        .order_by(Position.department_id, Position.title)
        .all()
    )

    return [
        position_to_dict(position, db)
        for position in positions
    ]


# =========================
# Get One Position
# =========================

@router.get("/{position_id}")
def get_position(
    position_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    return position_to_dict(get_position_or_404(position_id, db), db)


# =========================
# Create Position
# =========================

@router.post("/")
def create_position(
    position_data: PositionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    title = position_data.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Position title is required"
        )

    validate_department(position_data.department_id, db)
    assert_title_available(title, position_data.department_id, db)

    position = Position(
        title=title,
        department_id=position_data.department_id
    )

    db.add(position)
    db.commit()
    db.refresh(position)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_POSITION, position.id)

    return position_to_dict(position, db)


# =========================
# Update Position
# =========================

@router.put("/{position_id}")
def update_position(
    position_id: int,
    position_data: PositionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    position = get_position_or_404(position_id, db)

    title = position_data.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Position title is required"
        )

    validate_department(position_data.department_id, db)
    assert_title_available(
        title,
        position_data.department_id,
        db,
        exclude_id=position.id
    )

    position.title = title
    position.department_id = position_data.department_id

    db.commit()
    db.refresh(position)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_POSITION, position.id)

    return position_to_dict(position, db)


# =========================
# Delete Position
#
# employees.position_id holds a FK to positions, so a delete that would
# orphan staff records is refused rather than attempted.
# =========================

@router.delete("/{position_id}")
def delete_position(
    position_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    position = get_position_or_404(position_id, db)

    employee_count = (
        db.query(Employee)
        .filter(Employee.position_id == position.id)
        .count()
    )

    if employee_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Position '{position.title}' is still assigned to "
                f"{employee_count} employee(s). Reassign them first."
            )
        )

    db.delete(position)
    db.commit()

    record_audit(db, current_user, ACTION_DELETE, ENTITY_POSITION, position_id)

    return {
        "message": "Position deleted successfully",
        "id": position_id,
    }
