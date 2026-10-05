from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import AuditLog, User
from app.dependencies import require_roles
from app.audit import ACTION_EXPORT, ENTITY_AUDIT_LOG
from app.routers.interviews import describe_user


router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# The audit trail is append-only: there is no update or delete endpoint, and
# the only action a client may record for itself is an export of the trail.
CLIENT_RECORDABLE_ACTIONS = {ACTION_EXPORT}


class AuditLogCreate(BaseModel):
    action: str
    entity_type: str | None = None
    entity_id: int | None = None


# =========================
# Derived display helpers
#
# audit_logs stores six columns and nothing else. The sentence a page shows is
# composed from action + entity_type + entity_id at read time - it is a
# rendering of the stored row, not a stored column.
# =========================

VERB_PHRASES = {
    "CREATE": "Created",
    "UPDATE": "Updated",
    "DELETE": "Deleted",
    "APPROVE": "Approved",
    "REJECT": "Rejected",
    "STATUS_CHANGE": "Changed the status of",
    "ASSIGN": "Assigned",
    "ACTIVATE": "Activated",
    "DEACTIVATE": "Deactivated",
    "LOGIN": "Signed in",
    "LOGIN_FAILED": "Failed sign-in attempt",
    "EXPORT": "Exported",
}

ENTITY_LABELS = {
    "Employee": "employee record",
    "Job": "job opening",
    "Candidate": "candidate",
    "CV": "CV",
    "Application": "application",
    "Interview": "interview",
    "InterviewSession": "AI interview",
    "InterviewReport": "AI interview report",
    "Attendance": "attendance record",
    "LeaveRequest": "leave request",
    "Training": "training course",
    "EmployeeTraining": "training assignment",
    "PerformanceReview": "performance review",
    "User": "user account",
    "Department": "department",
    "Position": "position",
    "AuditLog": "audit trail",
    "Session": "session",
}


def describe_event(log: AuditLog) -> str:
    phrase = VERB_PHRASES.get(log.action, log.action.replace("_", " ").capitalize())
    label = ENTITY_LABELS.get(log.entity_type or "", log.entity_type)

    # Sign-in events describe themselves; there is no target record to name.
    if log.action in ("LOGIN", "LOGIN_FAILED"):
        return phrase

    if not label:
        return phrase

    if log.entity_id is None:
        return f"{phrase} {label}"

    return f"{phrase} {label} #{log.entity_id}"


def audit_log_to_dict(log: AuditLog, db: Session):
    """user_id is the only stored reference to a person. users carries just an
    email and a role, so the display name comes from the matching employees
    row via describe_user(), the same resolver interviews and reviews use."""
    actor = None

    if log.user_id is not None:
        actor = db.query(User).filter(User.id == log.user_id).first()

    if actor is not None:
        name, role_name = describe_user(actor, db)
        user_block = {
            "id": actor.id,
            "name": name,
            "email": actor.email,
            "role": role_name,
        }
    else:
        # user_id is nullable, and a deleted account leaves a dangling id.
        user_block = {
            "id": log.user_id,
            "name": "System",
            "email": None,
            "role": None,
        }

    return {
        "id": log.id,
        "user_id": log.user_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        # Derived, never stored:
        "user": user_block,
        "description": describe_event(log),
    }


def get_audit_log_or_404(log_id: int, db: Session) -> AuditLog:
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()

    if log is None:
        raise HTTPException(
            status_code=404,
            detail="Audit log entry not found"
        )

    return log


# =========================
# Get Audit Logs
#
# Newest first. The trail grows without bound, so reads are capped and the
# page asks for a window rather than the whole table.
# =========================

@router.get("/")
def get_audit_logs(
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    entity_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action.strip().upper())

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type.strip())

    logs = (
        query
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [audit_log_to_dict(log, db) for log in logs]


# =========================
# Get One Audit Log
# =========================

@router.get("/{log_id}")
def get_audit_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    return audit_log_to_dict(get_audit_log_or_404(log_id, db), db)


# =========================
# Record Audit Log
#
# Audit rows are generated by the write endpoints themselves, not entered by
# hand - there is no create form anywhere in the UI. The one client-originated
# event the app can observe and the server cannot is an export of the trail,
# so that is the only action this endpoint accepts.
#
# user_id is always taken from the JWT and never from the request body, so a
# caller cannot attribute an event to somebody else.
# =========================

@router.post("/")
def create_audit_log(
    data: AuditLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    action = data.action.strip().upper()

    if action not in CLIENT_RECORDABLE_ACTIONS:
        allowed = ", ".join(sorted(CLIENT_RECORDABLE_ACTIONS))

        raise HTTPException(
            status_code=422,
            detail=(
                f"Action '{action}' cannot be recorded by a client. "
                f"Audit entries are generated by the system action they "
                f"describe. Allowed here: {allowed}."
            )
        )

    log = AuditLog(
        user_id=current_user.id,
        action=action,
        entity_type=data.entity_type or ENTITY_AUDIT_LOG,
        entity_id=data.entity_id,
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return audit_log_to_dict(log, db)
