from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import LeaveRequest, Employee, Department, Position, User
from app.dependencies import require_roles
from app.dependencies import get_current_employee
from app.routers.auth import get_current_user
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_STATUS_CHANGE,
    ENTITY_LEAVE_REQUEST,
)


router = APIRouter(
    prefix="/leave-requests",
    tags=["Leave Requests"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Leave status
#
# leave_requests.status is a plain varchar(30) defaulting to 'pending', but
# the rows already in this database are Title Case ('Pending', 'Approved'),
# so that is the canonical form written back.
# =========================

LEAVE_STATUSES = ("Pending", "Approved", "Rejected", "Cancelled")

STATUS_ALIASES = {status.lower(): status for status in LEAVE_STATUSES}
STATUS_ALIASES.update({
    "approve": "Approved",
    "reject": "Rejected",
    "declined": "Rejected",
    "canceled": "Cancelled",
})

# A decision on a leave request is a distinct audit event from an ordinary
# edit, so the trail records which way it went.
DECISION_ACTIONS = {
    "Approved": ACTION_APPROVE,
    "Rejected": ACTION_REJECT,
}


def normalize_status(value: str | None) -> str:
    """Strict: used on write."""
    if value is None:
        return "Pending"

    normalized = STATUS_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid leave status '{value}'. "
                f"Allowed values: {', '.join(LEAVE_STATUSES)}"
            )
        )

    return normalized


def read_status(value: str | None) -> str:
    """Lenient: used on read so legacy rows never break the listing."""
    return STATUS_ALIASES.get((value or "").strip().lower(), "Pending")


class MyLeaveRequestCreate(BaseModel):
    """The self-service payload. Deliberately has no employee_id - the
    employee is taken from the JWT so a caller cannot file leave for
    somebody else - and no status, because a request always starts Pending."""
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveRequestCreate(BaseModel):
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = None
    status: str = "Pending"


class LeaveRequestUpdate(BaseModel):
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = None
    status: str = "Pending"


class LeaveStatusUpdate(BaseModel):
    status: str


def duration_days(start: date, end: date) -> int:
    """Inclusive calendar span - derived from the two real date columns."""
    if start is None or end is None:
        return 0

    return max((end - start).days + 1, 0)


def overlapping_count(leave, db) -> int:
    """How many OTHER approved/pending requests overlap this date range.
    Computed on the fly; there is no stored overlap column."""
    others = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id != leave.id)
        .filter(LeaveRequest.start_date <= leave.end_date)
        .filter(LeaveRequest.end_date >= leave.start_date)
        .all()
    )

    return len([
        other for other in others
        if read_status(other.status) in ("Pending", "Approved")
    ])


def leave_to_dict(leave, db):
    employee = (
        db.query(Employee)
        .filter(Employee.id == leave.employee_id)
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

    approver = None
    if leave.approved_by:
        approver = (
            db.query(User)
            .filter(User.id == leave.approved_by)
            .first()
        )

    return {
        "id": leave.id,
        "employee_id": leave.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee else None
        ),
        "department_name": department.name if department else None,
        "position_title": position.title if position else None,

        "leave_type": leave.leave_type,
        "start_date": leave.start_date,
        "end_date": leave.end_date,
        "duration_days": duration_days(leave.start_date, leave.end_date),
        "reason": leave.reason,
        "status": read_status(leave.status),

        "approved_by": leave.approved_by,
        "approved_by_email": approver.email if approver else None,

        "overlapping_count": overlapping_count(leave, db),
        "created_at": leave.created_at,
    }


def get_leave_or_404(leave_id: int, db: Session) -> LeaveRequest:
    leave = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == leave_id)
        .first()
    )

    if leave is None:
        raise HTTPException(
            status_code=404,
            detail="Leave request not found"
        )

    return leave


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


def apply_decision(leave, status: str, current_user: User):
    """approved_by is the only decision-maker column on the table, so it
    records whoever actioned the request and is cleared when the request
    goes back to Pending."""
    leave.status = status

    if status in ("Approved", "Rejected"):
        leave.approved_by = current_user.id
    else:
        leave.approved_by = None


# =========================
# Get Leave Requests
# =========================

# =========================
# My Leave
#
# Both routes are scoped to the caller through get_current_employee and are
# declared before /{leave_id} so the literal path wins the route match.
# =========================

@router.get("/me")
def get_my_leave_requests(
    db: Session = Depends(get_db),
    employee=Depends(get_current_employee)
):
    leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == employee.id)
        .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .all()
    )

    return [leave_to_dict(leave, db) for leave in leaves]


@router.post("/me")
def create_my_leave_request(
    leave_data: MyLeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee=Depends(get_current_employee)
):
    """Submit leave for yourself. employee_id is forced to the caller and the
    status is always Pending - an employee cannot self-approve."""
    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be earlier than start date"
        )

    leave = LeaveRequest(
        employee_id=employee.id,
        leave_type=leave_data.leave_type,
        start_date=leave_data.start_date,
        end_date=leave_data.end_date,
        reason=leave_data.reason,
        status="Pending",
        approved_by=None,
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_LEAVE_REQUEST, leave.id)

    return leave_to_dict(leave, db)


# =========================
# Get Leave Requests (whole organisation)
#
# Admin, HR and Managers only. Employees read /leave-requests/me instead.
# =========================

@router.get("/")
def get_leave_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    leaves = (
        db.query(LeaveRequest)
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
        .all()
    )

    return [
        leave_to_dict(leave, db)
        for leave in leaves
    ]


# =========================
# Get One Leave Request
# =========================

@router.get("/{leave_id}")
def get_leave_request(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    return leave_to_dict(get_leave_or_404(leave_id, db), db)


# =========================
# Create Leave Request
# =========================

@router.post("/")
def create_leave_request(
    leave_data: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    validate_employee(leave_data.employee_id, db)

    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be earlier than start date"
        )

    leave = LeaveRequest(
        employee_id=leave_data.employee_id,
        leave_type=leave_data.leave_type,
        start_date=leave_data.start_date,
        end_date=leave_data.end_date,
        reason=leave_data.reason
    )

    apply_decision(leave, normalize_status(leave_data.status), current_user)

    db.add(leave)
    db.commit()
    db.refresh(leave)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_LEAVE_REQUEST, leave.id)

    return leave_to_dict(leave, db)


# =========================
# Update Leave Request
# =========================

@router.put("/{leave_id}")
def update_leave_request(
    leave_id: int,
    leave_data: LeaveRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    leave = get_leave_or_404(leave_id, db)

    validate_employee(leave_data.employee_id, db)

    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be earlier than start date"
        )

    leave.employee_id = leave_data.employee_id
    leave.leave_type = leave_data.leave_type
    leave.start_date = leave_data.start_date
    leave.end_date = leave_data.end_date
    leave.reason = leave_data.reason

    apply_decision(leave, normalize_status(leave_data.status), current_user)

    db.commit()
    db.refresh(leave)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_LEAVE_REQUEST, leave.id)

    return leave_to_dict(leave, db)


# =========================
# Approve / Reject
# =========================

@router.patch("/{leave_id}/status")
def update_leave_status(
    leave_id: int,
    status_data: LeaveStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    leave = get_leave_or_404(leave_id, db)

    apply_decision(leave, normalize_status(status_data.status), current_user)

    db.commit()
    db.refresh(leave)

    # The decision itself is the audit-worthy event, so it is recorded as
    # an approval or a rejection rather than a generic status change.
    record_audit(
        db,
        current_user,
        DECISION_ACTIONS.get(leave.status, ACTION_STATUS_CHANGE),
        ENTITY_LEAVE_REQUEST,
        leave.id
    )

    return leave_to_dict(leave, db)
