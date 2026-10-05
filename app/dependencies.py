from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.identity import resolve_candidate, resolve_employee
from app.models import Candidate, Employee, User
from app.routers.auth import get_current_user

# Role ids as seeded: 1 Admin, 2 HR, 3 Manager, 4 Employee, 5 Applicant.
#
# 1-4 are *internal* staff. 5 is an external job seeker with an account, and
# the difference matters: a handful of endpoints were guarded with a bare
# `get_current_user`, meaning "any signed-in user", which was a complete
# description of the population until role 5 existed. `require_staff` is that
# same intent written explicitly, so adding an external role did not silently
# widen the internal catalogues (/jobs/, /departments/, /positions/,
# /trainings/, /dashboard/employee, /ai/chat) to people outside the company.
STAFF_ROLES = (1, 2, 3, 4)
ROLE_APPLICANT = 5


def require_roles(*allowed_roles: int):
    def role_checker(
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role_id not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )

        return current_user

    return role_checker


def require_staff(current_user: User = Depends(require_roles(*STAFF_ROLES))) -> User:
    """Any internal SmartHR user: Admin, HR, Manager or Employee.

    Use this wherever "any signed-in user" used to mean "anyone who works
    here". It excludes Applicants, who are external.
    """
    return current_user


def require_applicant(
    current_user: User = Depends(require_roles(ROLE_APPLICANT))
) -> User:
    """An external job seeker's account, and only that.

    Deliberately excludes Admin and HR: these are the applicant's *own*
    self-service routes, scoped through the account, so an HR user calling
    them would resolve to an HR candidate row that does not exist. HR reads
    applicant data through the recruitment endpoints they already have.
    """
    return current_user


def get_db():
    """The request's database session.

    Public on purpose. A router that writes to an object resolved by
    `get_current_candidate` (or `get_current_employee`) must depend on *this*
    generator rather than declaring its own: FastAPI caches a dependency by its
    callable, so sharing this one means the dependency and the handler get the
    same `Session`. With two different sessions the resolved row belongs to the
    dependency's session, and committing it from the handler's raises
    "Instance <...> is not persistent within this Session".
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#: Kept as the original private name so existing dependencies keep working.
#: It must stay the *same object* as `get_db` for the caching above to apply.
_db = get_db


def get_current_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(_db)
) -> Employee:
    """The employees row for the signed-in account.

    Self-service endpoints depend on this rather than taking an employee_id
    from the client, so "my" data can only ever mean the caller's own. A
    caller cannot widen the scope by editing a request.
    """
    employee = resolve_employee(current_user, db)

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"The account {current_user.email} is not linked to an employee "
                f"record, so there is no personal data to return."
            )
        )

    return employee


def get_current_candidate(
    current_user: User = Depends(require_applicant),
    db: Session = Depends(_db)
) -> Candidate:
    """The candidates row for the signed-in applicant.

    The applicant-side twin of `get_current_employee`, and the dependency
    every `/applicant/*` route uses. The candidate id never crosses the wire,
    so "my profile", "my CV" and "my applications" cannot be widened by
    editing a request - there is no parameter to edit.
    """
    candidate = resolve_candidate(current_user, db)

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"The account {current_user.email} is not linked to an applicant "
                f"profile. Register again or ask an administrator to link it."
            )
        )

    return candidate
