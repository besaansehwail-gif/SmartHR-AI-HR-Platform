from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import (
    User,
    Role,
    Candidate,
    Employee,
    Department,
    Position,
    Notification,
    Job,
    Interview,
    LeaveRequest,
    PerformanceReview,
    AuditLog,
)
from app.routers.auth import password_hash
from app.dependencies import require_roles
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ACTION_ACTIVATE,
    ACTION_DEACTIVATE,
    ENTITY_USER,
)
from app.routers.auth import get_current_user
from app.services.applicant_service import (
    ROLE_APPLICANT,
    ApplicantError,
    link_candidate_profile,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ADMIN_ROLE_ID = 1


class UserCreate(BaseModel):
    email: str
    password: str
    role_id: int
    is_active: bool = True
    # Only meaningful for role 5. `users` stores no name, but an applicant's
    # profile row does and both name columns are NOT NULL, so an Admin
    # creating a job-seeker account may supply the real one here instead of
    # leaving it derived from the email address. Ignored for staff roles,
    # whose name lives on their employees row.
    full_name: str | None = None


class UserUpdate(BaseModel):
    email: str
    role_id: int
    is_active: bool = True
    # Optional: only re-hashed when a non-empty value is supplied. The
    # existing hash is left untouched otherwise.
    password: str | None = None


class UserStatusUpdate(BaseModel):
    is_active: bool


def user_to_dict(user, db):
    """Never includes password_hash - the hash must not leave the backend."""
    role = (
        db.query(Role)
        .filter(Role.id == user.role_id)
        .first()
    )

    # users carry no name; the profile comes from the linked employee row.
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == user.id)
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
        "id": user.id,
        "email": user.email,
        "role_id": user.role_id,
        "role_name": role.name if role else None,
        "is_active": user.is_active,
        "created_at": user.created_at,

        "employee_id": employee.id if employee else None,
        "first_name": employee.first_name if employee else None,
        "last_name": employee.last_name if employee else None,
        "full_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee else None
        ),
        "phone": employee.phone if employee else None,
        "department_name": department.name if department else None,
        "position_title": position.title if position else None,
    }


def get_user_or_404(user_id: int, db: Session) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user


def validate_role(role_id: int, db: Session) -> Role:
    role = (
        db.query(Role)
        .filter(Role.id == role_id)
        .first()
    )

    if role is None:
        raise HTTPException(
            status_code=400,
            detail=f"Role {role_id} does not exist"
        )

    return role


def assert_email_available(email: str, db: Session, exclude_id: int | None = None):
    """users.email carries a UNIQUE constraint; surface it as a 409 rather
    than letting the insert fail with an IntegrityError."""
    query = db.query(User).filter(User.email == email)

    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)

    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A user with email {email} already exists"
        )


def count_other_active_admins(db: Session, user_id: int) -> int:
    return (
        db.query(User)
        .filter(User.id != user_id)
        .filter(User.role_id == ADMIN_ROLE_ID)
        .filter(User.is_active.is_(True))
        .count()
    )


def assert_not_self_lockout(user: User, current_user: User, action: str):
    if user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail=f"You cannot {action} your own account"
        )


def assert_admin_access_preserved(
    user: User,
    db: Session,
    action: str,
    still_active_admin: bool = False
):
    """Refuse anything that would leave the platform with no active Admin -
    this is what protects the bootstrap admin account."""
    if user.role_id != ADMIN_ROLE_ID or not user.is_active:
        return

    if still_active_admin:
        return

    if count_other_active_admins(db, user.id) == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot {action} the last active Admin account "
                f"({user.email}). Promote another user to Admin first."
            )
        )


def count_references(user_id: int, db: Session) -> dict:
    """Eight tables hold a FK to users; a delete must not orphan them.

    `candidates` is the eighth, added with the Applicant feature: deleting a
    job seeker's account would otherwise fail on candidates_user_id_fkey as a
    raw IntegrityError instead of the 409 this guard exists to return.
    """
    return {
        "employees": db.query(Employee).filter(Employee.user_id == user_id).count(),
        "candidates": db.query(Candidate).filter(Candidate.user_id == user_id).count(),
        "notifications": db.query(Notification).filter(Notification.user_id == user_id).count(),
        "jobs": db.query(Job).filter(Job.created_by == user_id).count(),
        "interviews": db.query(Interview).filter(Interview.interviewer_id == user_id).count(),
        "leave_requests": db.query(LeaveRequest).filter(LeaveRequest.approved_by == user_id).count(),
        "performance_reviews": db.query(PerformanceReview).filter(PerformanceReview.reviewer_id == user_id).count(),
        "audit_logs": db.query(AuditLog).filter(AuditLog.user_id == user_id).count(),
    }


# =========================
# Roles
#
# Declared before /{user_id} so the literal path wins the route match.
# =========================

@router.get(
    "/roles",
    dependencies=[Depends(require_roles(1, 2))]
)
def get_roles(db: Session = Depends(get_db)):
    roles = (
        db.query(Role)
        .order_by(Role.id)
        .all()
    )

    result = []

    for role in roles:
        user_count = (
            db.query(User)
            .filter(User.role_id == role.id)
            .count()
        )

        active_count = (
            db.query(User)
            .filter(User.role_id == role.id)
            .filter(User.is_active.is_(True))
            .count()
        )

        result.append({
            "id": role.id,
            "name": role.name,
            "user_count": user_count,
            "active_user_count": active_count,
        })

    return result


# =========================
# Get Users
# =========================

@router.get(
    "/",
    dependencies=[Depends(require_roles(1))]
)
def get_users(db: Session = Depends(get_db)):
    users = (
        db.query(User)
        .order_by(User.id)
        .all()
    )

    return [
        user_to_dict(user, db)
        for user in users
    ]


# =========================
# Get One User
# =========================

@router.get(
    "/{user_id}",
    dependencies=[Depends(require_roles(1))]
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    return user_to_dict(get_user_or_404(user_id, db), db)


def ensure_applicant_profile(user: User, db: Session, full_name: str | None = None):
    """An Applicant account is only usable once it has a candidates row.

    Admin user management can create a role 5 account and can promote an
    existing one, and neither path knew anything about `candidates` - so an
    account made here signed in successfully and then failed on every
    `/applicant/*` route, because `get_current_candidate` had nothing to
    resolve. This closes that gap by calling the same
    `link_candidate_profile()` registration uses, rather than growing a second
    definition of what "linked" means.

    Does nothing for staff roles, and is idempotent: promoting an account that
    already has a profile re-uses it and never creates a duplicate.
    """
    if user.role_id != ROLE_APPLICANT:
        return None

    try:
        candidate, outcome = link_candidate_profile(user, db, full_name=full_name)
    except ApplicantError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()

    return candidate, outcome


# =========================
# Create User
# =========================

@router.post(
    "/",
    dependencies=[Depends(require_roles(1))]
)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    email = data.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required"
        )

    if not data.password or len(data.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters"
        )

    validate_role(data.role_id, db)
    assert_email_available(email, db)

    user = User(
        email=email,
        # Hashed with the same pwdlib PasswordHash the login flow verifies.
        password_hash=password_hash.hash(data.password),
        role_id=data.role_id,
        is_active=data.is_active
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    ensure_applicant_profile(user, db, full_name=data.full_name)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_USER, user.id)

    return user_to_dict(user, db)


# =========================
# Update User
# =========================

@router.put(
    "/{user_id}",
    dependencies=[Depends(require_roles(1))]
)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = get_user_or_404(user_id, db)

    email = data.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required"
        )

    validate_role(data.role_id, db)
    assert_email_available(email, db, exclude_id=user.id)

    # Guard both the demotion and the deactivation paths.
    stays_admin_and_active = (
        data.role_id == ADMIN_ROLE_ID and data.is_active
    )

    if not stays_admin_and_active:
        assert_admin_access_preserved(user, db, "demote or deactivate")

    if not data.is_active and user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account"
        )

    user.email = email
    user.role_id = data.role_id
    user.is_active = data.is_active

    if data.password:
        if len(data.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters"
            )

        user.password_hash = password_hash.hash(data.password)

    db.commit()
    db.refresh(user)

    # Promoting an account to Applicant gives it the profile it now needs. A
    # role change *away* from 5 deliberately leaves the candidates row linked:
    # unlinking it would orphan their applications, CVs and interviews, and
    # RBAC already stops a non-applicant reaching /applicant/*.
    ensure_applicant_profile(user, db)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_USER, user.id)

    return user_to_dict(user, db)


# =========================
# Activate / Deactivate
# =========================

@router.patch(
    "/{user_id}/status",
    dependencies=[Depends(require_roles(1))]
)
def set_user_status(
    user_id: int,
    data: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = get_user_or_404(user_id, db)

    if not data.is_active:
        assert_not_self_lockout(user, current_user, "deactivate")
        assert_admin_access_preserved(user, db, "deactivate")

    user.is_active = data.is_active

    db.commit()
    db.refresh(user)

    # Activation state is a security event, not a routine field edit.
    record_audit(
        db,
        current_user,
        ACTION_ACTIVATE if user.is_active else ACTION_DEACTIVATE,
        ENTITY_USER,
        user.id
    )

    return user_to_dict(user, db)


# =========================
# Delete User
# =========================

@router.delete(
    "/{user_id}",
    dependencies=[Depends(require_roles(1))]
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = get_user_or_404(user_id, db)

    assert_not_self_lockout(user, current_user, "delete")
    assert_admin_access_preserved(user, db, "delete")

    references = count_references(user.id, db)
    blocking = {table: n for table, n in references.items() if n}

    if blocking:
        detail = ", ".join(f"{table}: {n}" for table, n in blocking.items())

        raise HTTPException(
            status_code=409,
            detail=(
                f"User {user.email} is still referenced by other records "
                f"({detail}). Deactivate the account instead of deleting it."
            )
        )

    db.delete(user)
    db.commit()

    record_audit(db, current_user, ACTION_DELETE, ENTITY_USER, user_id)

    return {
        "message": "User deleted successfully",
        "id": user_id,
    }
