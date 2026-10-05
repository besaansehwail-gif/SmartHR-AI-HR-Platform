"""Resolving an authenticated user to the person they are.

`users` stores only (id, email, password_hash, role_id, is_active, created_at)
- no name, no department, no position. The person is the `employees` row whose
`user_id` points back at the account, and that column is **nullable**, so an
account with no employee record is a legitimate state rather than an error.

This module deliberately imports nothing from `app/routers/` or
`app/dependencies.py`: `dependencies.py` imports `get_current_user` from
`routers/auth.py`, so anything the auth router needs has to live outside that
chain or it becomes an import cycle.
"""

from app.models import Candidate, Employee, Department, Position, Role, User


def resolve_employee(user: User | None, db) -> Employee | None:
    """The employees row linked to this account, or None when unlinked."""
    if user is None:
        return None

    return (
        db.query(Employee)
        .filter(Employee.user_id == user.id)
        .first()
    )


def resolve_candidate(user: User | None, db) -> Candidate | None:
    """The candidates row linked to this account, or None when unlinked.

    The applicant-side twin of `resolve_employee`. An Applicant is a `users`
    row whose `candidates.user_id` points back at it, so every applicant
    self-service path resolves the candidate here from the verified JWT rather
    than accepting a candidate_id from the request. There is no parameter to
    tamper with, which is what makes "my applications" mean only the caller's.

    Returns None for a staff account, and for the candidates HR keyed in by
    hand - `candidates.user_id` is nullable and most rows have none.
    """
    if user is None:
        return None

    return (
        db.query(Candidate)
        .filter(Candidate.user_id == user.id)
        .first()
    )


def employee_identity(employee: Employee, db) -> dict:
    """The employee plus the names hanging off its foreign keys.

    department_name, position_title and manager_name are all resolved on read;
    employees stores only the ids.
    """
    department = None
    position = None
    manager = None

    if employee.department_id is not None:
        department = (
            db.query(Department)
            .filter(Department.id == employee.department_id)
            .first()
        )

    if employee.position_id is not None:
        position = (
            db.query(Position)
            .filter(Position.id == employee.position_id)
            .first()
        )

    if employee.manager_id is not None:
        manager = (
            db.query(Employee)
            .filter(Employee.id == employee.manager_id)
            .first()
        )

    account = None
    role = None

    if employee.user_id is not None:
        account = db.query(User).filter(User.id == employee.user_id).first()

        if account is not None:
            role = db.query(Role).filter(Role.id == account.role_id).first()

    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "full_name": f"{employee.first_name} {employee.last_name}",
        "phone": employee.phone,
        "department_id": employee.department_id,
        "department_name": department.name if department else None,
        "position_id": employee.position_id,
        "position_title": position.title if position else None,
        "manager_id": employee.manager_id,
        "manager_name": (
            f"{manager.first_name} {manager.last_name}" if manager else None
        ),
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "employment_status": employee.employment_status,
        # From the linked account, never from employees - there is no email
        # or role column on employees.
        "email": account.email if account else None,
        "role_id": account.role_id if account else None,
        "role_name": role.name if role else None,
    }
