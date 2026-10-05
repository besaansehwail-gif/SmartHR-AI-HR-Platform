from datetime import date, time, datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Attendance, Employee, Department, Position, User
from app.dependencies import require_roles
from app.dependencies import get_current_employee
from app.routers.auth import get_current_user
from app.models import Employee as EmployeeModel  # noqa: F401
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_STATUS_CHANGE,
    ENTITY_ATTENDANCE,
)


router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Attendance status
#
# attendance.status is a plain varchar(30) defaulting to 'present', but the
# rows already in this database are Title Case ('Present', 'Late'), so that
# is the canonical form written back - existing rows are never rewritten.
# =========================

ATTENDANCE_STATUSES = ("Present", "Late", "Absent", "On Leave", "Half Day")

STATUS_ALIASES = {status.lower(): status for status in ATTENDANCE_STATUSES}
STATUS_ALIASES.update({
    "on_leave": "On Leave",
    "onleave": "On Leave",
    "half_day": "Half Day",
    "halfday": "Half Day",
    "leave": "On Leave",
})


def normalize_status(value: str | None) -> str:
    """Strict: used on write. Rejects anything outside the five states."""
    if value is None:
        return "Present"

    normalized = STATUS_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid attendance status '{value}'. "
                f"Allowed values: {', '.join(ATTENDANCE_STATUSES)}"
            )
        )

    return normalized


def read_status(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STATUS_ALIASES.get((value or "").strip().lower(), "Present")


class AttendanceCreate(BaseModel):
    employee_id: int
    date: date
    check_in: time | None = None
    check_out: time | None = None
    status: str = "Present"


class AttendanceUpdate(BaseModel):
    employee_id: int
    date: date
    check_in: time | None = None
    check_out: time | None = None
    status: str = "Present"


class AttendanceStatusUpdate(BaseModel):
    status: str


def worked_hours(check_in: time | None, check_out: time | None) -> float | None:
    """Derived from the two real time columns - not a stored value."""
    if check_in is None or check_out is None:
        return None

    anchor = date(2000, 1, 1)
    delta = datetime.combine(anchor, check_out) - datetime.combine(anchor, check_in)
    hours = delta.total_seconds() / 3600

    if hours < 0:
        return None

    return round(hours, 2)


def attendance_to_dict(record, db):
    employee = (
        db.query(Employee)
        .filter(Employee.id == record.employee_id)
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

    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee else None
        ),
        "department_name": department.name if department else None,
        "position_title": position.title if position else None,
        "date": record.date,
        "check_in": record.check_in,
        "check_out": record.check_out,
        "worked_hours": worked_hours(record.check_in, record.check_out),
        "status": read_status(record.status),
        "created_at": record.created_at,
    }


def get_attendance_or_404(attendance_id: int, db: Session) -> Attendance:
    record = (
        db.query(Attendance)
        .filter(Attendance.id == attendance_id)
        .first()
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found"
        )

    return record


def validate_employee(employee_id: int, db: Session):
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


# =========================
# Get Attendance
# =========================

# =========================
# My Attendance
#
# Scoped to the caller: the employee comes from the JWT via
# get_current_employee, never from a query parameter, so this cannot be
# pointed at somebody else.
#
# Declared before /{attendance_id} so the literal path wins the route match.
# =========================

@router.get("/me")
def get_my_attendance(
    db: Session = Depends(get_db),
    employee=Depends(get_current_employee)
):
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee.id)
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .all()
    )

    return [attendance_to_dict(record, db) for record in records]


# =========================
# Get Attendance (whole organisation)
#
# Admin, HR and Managers only. Employees read /attendance/me instead, so one
# person cannot enumerate everybody else's check-in times.
# =========================

@router.get("/")
def get_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    records = (
        db.query(Attendance)
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .all()
    )

    return [
        attendance_to_dict(record, db)
        for record in records
    ]


# =========================
# Get One Attendance Record
# =========================

@router.get("/{attendance_id}")
def get_attendance_record(
    attendance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    return attendance_to_dict(get_attendance_or_404(attendance_id, db), db)


# =========================
# Create Attendance
# =========================

@router.post("/")
def create_attendance(
    attendance_data: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    validate_employee(attendance_data.employee_id, db)

    record = Attendance(
        employee_id=attendance_data.employee_id,
        date=attendance_data.date,
        check_in=attendance_data.check_in,
        check_out=attendance_data.check_out,
        status=normalize_status(attendance_data.status)
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_ATTENDANCE, record.id)

    return attendance_to_dict(record, db)


# =========================
# Update Attendance
# =========================

@router.put("/{attendance_id}")
def update_attendance(
    attendance_id: int,
    attendance_data: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    record = get_attendance_or_404(attendance_id, db)

    validate_employee(attendance_data.employee_id, db)

    record.employee_id = attendance_data.employee_id
    record.date = attendance_data.date
    record.check_in = attendance_data.check_in
    record.check_out = attendance_data.check_out
    record.status = normalize_status(attendance_data.status)

    db.commit()
    db.refresh(record)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_ATTENDANCE, record.id)

    return attendance_to_dict(record, db)


# =========================
# Update Attendance Status
# =========================

@router.patch("/{attendance_id}/status")
def update_attendance_status(
    attendance_id: int,
    status_data: AttendanceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    record = get_attendance_or_404(attendance_id, db)

    record.status = normalize_status(status_data.status)

    db.commit()
    db.refresh(record)

    record_audit(db, current_user, ACTION_STATUS_CHANGE, ENTITY_ATTENDANCE, record.id)

    return attendance_to_dict(record, db)
