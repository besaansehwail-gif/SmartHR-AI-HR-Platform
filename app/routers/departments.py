from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Department, Position, Employee, Job, User
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ENTITY_DEPARTMENT,
)


router = APIRouter(
    prefix="/departments",
    tags=["Departments"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DepartmentCreate(BaseModel):
    name: str


class DepartmentUpdate(BaseModel):
    name: str


def department_to_dict(department, db):
    """The departments table holds only (id, name). Every figure below is
    counted from the referencing tables, not stored."""
    employee_count = (
        db.query(Employee)
        .filter(Employee.department_id == department.id)
        .count()
    )

    position_count = (
        db.query(Position)
        .filter(Position.department_id == department.id)
        .count()
    )

    job_count = (
        db.query(Job)
        .filter(Job.department_id == department.id)
        .count()
    )

    open_job_count = (
        db.query(Job)
        .filter(Job.department_id == department.id)
        .filter(Job.status == "open")
        .count()
    )

    return {
        "id": department.id,
        "name": department.name,
        "employee_count": employee_count,
        "position_count": position_count,
        "job_count": job_count,
        "open_job_count": open_job_count,
    }


def get_department_or_404(department_id: int, db: Session) -> Department:
    department = (
        db.query(Department)
        .filter(Department.id == department_id)
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=404,
            detail="Department not found"
        )

    return department


def assert_name_available(name: str, db: Session, exclude_id: int | None = None):
    """departments.name carries a UNIQUE constraint; surface it as a 409
    rather than letting the insert fail with an IntegrityError."""
    query = db.query(Department).filter(Department.name == name)

    if exclude_id is not None:
        query = query.filter(Department.id != exclude_id)

    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A department named '{name}' already exists"
        )


# =========================
# Get Departments
# =========================

@router.get("/")
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    departments = (
        db.query(Department)
        .order_by(Department.name)
        .all()
    )

    return [
        department_to_dict(department, db)
        for department in departments
    ]


# =========================
# Get One Department
# =========================

@router.get("/{department_id}")
def get_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    return department_to_dict(get_department_or_404(department_id, db), db)


# =========================
# Create Department
# =========================

@router.post("/")
def create_department(
    department_data: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    name = department_data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Department name is required"
        )

    assert_name_available(name, db)

    department = Department(name=name)

    db.add(department)
    db.commit()
    db.refresh(department)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_DEPARTMENT, department.id)

    return department_to_dict(department, db)


# =========================
# Update Department
# =========================

@router.put("/{department_id}")
def update_department(
    department_id: int,
    department_data: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    department = get_department_or_404(department_id, db)

    name = department_data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Department name is required"
        )

    assert_name_available(name, db, exclude_id=department.id)

    department.name = name

    db.commit()
    db.refresh(department)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_DEPARTMENT, department.id)

    return department_to_dict(department, db)


# =========================
# Delete Department
#
# positions, employees and jobs all hold a FK to departments, so a delete
# that would orphan them is refused rather than attempted.
# =========================

@router.delete("/{department_id}")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    department = get_department_or_404(department_id, db)

    references = {
        "positions": db.query(Position).filter(Position.department_id == department.id).count(),
        "employees": db.query(Employee).filter(Employee.department_id == department.id).count(),
        "jobs": db.query(Job).filter(Job.department_id == department.id).count(),
    }

    blocking = {table: n for table, n in references.items() if n}

    if blocking:
        detail = ", ".join(f"{table}: {n}" for table, n in blocking.items())

        raise HTTPException(
            status_code=409,
            detail=(
                f"Department '{department.name}' is still referenced by "
                f"{detail}. Reassign or remove those records first."
            )
        )

    db.delete(department)
    db.commit()

    record_audit(db, current_user, ACTION_DELETE, ENTITY_DEPARTMENT, department_id)

    return {
        "message": "Department deleted successfully",
        "id": department_id,
    }
