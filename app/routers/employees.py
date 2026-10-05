from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Employee, Department, Position, User
from app.schemas import CELEBRATION_DATE_FIELDS, EmployeeCreate, EmployeeUpdate
from app.dependencies import require_roles, require_staff
from app.routers.auth import get_current_user
from app.identity import resolve_employee
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ENTITY_EMPLOYEE,
)

router = APIRouter(
    prefix="/employees",
    tags=["Employees"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def employee_to_dict(employee, db, include_celebration_dates: bool = True):
    department = (
        db.query(Department)
        .filter(Department.id == employee.department_id)
        .first()
    )

    position = (
        db.query(Position)
        .filter(Position.id == employee.position_id)
        .first()
    )

    user = None
    if employee.user_id:
        user = (
            db.query(User)
            .filter(User.id == employee.user_id)
            .first()
        )

    manager_name = None

    if employee.manager_id:
        manager = (
            db.query(Employee)
            .filter(Employee.id == employee.manager_id)
            .first()
        )

        if manager:
            manager_name = f"{manager.first_name} {manager.last_name}"

    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": user.email if user else "",
        "phone": employee.phone,
        "department_id": employee.department_id,
        "department_name": department.name if department else None,
        "position_id": employee.position_id,
        "position_title": position.title if position else None,
        "manager_id": employee.manager_id,
        "manager_name": manager_name,
        "hire_date": employee.hire_date,
        "employment_status": employee.employment_status,
        # Birth, wedding and new-baby dates are personal; they are returned
        # only where the caller may manage them (Admin/HR) or to the employee
        # about themselves - never to a Manager browsing another record.
        **(
            {name: getattr(employee, name) for name in CELEBRATION_DATE_FIELDS}
            if include_celebration_dates else {}
        ),
    }


# =========================
# Get Employees
# =========================

@router.get(
    "/",
    dependencies=[Depends(require_roles(1, 2))]
)
def get_employees(db: Session = Depends(get_db)):
    employees = db.query(Employee).all()

    return [
        employee_to_dict(employee, db)
        for employee in employees
    ]


# =========================
# Roster (lightweight picker)
#
# Declared before /{employee_id} so the literal path wins the route match.
# Managers (role 3) need names for the attendance and leave screens but are
# not allowed the full employee record, so this returns only identity.
# =========================

@router.get(
    "/roster",
    dependencies=[Depends(require_roles(1, 2, 3))]
)
def get_employee_roster(db: Session = Depends(get_db)):
    employees = (
        db.query(Employee)
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )

    result = []

    for employee in employees:
        department = None
        position = None

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

        result.append({
            "id": employee.id,
            "name": f"{employee.first_name} {employee.last_name}",
            "department_name": department.name if department else None,
            "position_title": position.title if position else None,
        })

    return result


# =========================
# Get One Employee
# =========================

# Admin, HR and Managers may read any employee. Everyone else may read
# exactly one record: their own. That keeps My Profile working for an
# Employee without letting them enumerate the directory by walking ids.

@router.get("/{employee_id}")
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    if current_user.role_id not in (1, 2, 3):
        own = resolve_employee(current_user, db)

        if own is None or own.id != employee_id:
            raise HTTPException(
                status_code=403,
                detail="You may only view your own employee record"
            )

    own_record = resolve_employee(current_user, db)
    may_see_dates = current_user.role_id in (1, 2) or (
        own_record is not None and own_record.id == employee_id
    )

    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    return employee_to_dict(employee, db, include_celebration_dates=may_see_dates)


# =========================
# Create Employee
# =========================

@router.post(
    "/",
    dependencies=[Depends(require_roles(1, 2))]
)
def create_employee(
    employee_data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = Employee(
        first_name=employee_data.first_name,
        last_name=employee_data.last_name,
        phone=employee_data.phone,
        department_id=employee_data.department_id,
        position_id=employee_data.position_id,
        manager_id=employee_data.manager_id,
        hire_date=employee_data.hire_date,
        employment_status=employee_data.employment_status,
        **{name: getattr(employee_data, name) for name in CELEBRATION_DATE_FIELDS},
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_EMPLOYEE, employee.id)

    return employee_to_dict(employee, db)


# =========================
# Update Employee
# =========================

@router.put(
    "/{employee_id}",
    dependencies=[Depends(require_roles(1, 2))]
)
def update_employee(
    employee_id: int,
    employee_data: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    employee.first_name = employee_data.first_name
    employee.last_name = employee_data.last_name
    employee.phone = employee_data.phone
    employee.department_id = employee_data.department_id
    employee.position_id = employee_data.position_id
    employee.manager_id = employee_data.manager_id
    employee.hire_date = employee_data.hire_date
    employee.employment_status = employee_data.employment_status
    # Only the celebration dates the request actually sent. They were added
    # after this endpoint existed, so a client that does not know them must
    # not wipe them by omission (`null` sent explicitly does clear one).
    for name in CELEBRATION_DATE_FIELDS:
        if name in employee_data.model_fields_set:
            setattr(employee, name, getattr(employee_data, name))

    db.commit()
    db.refresh(employee)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_EMPLOYEE, employee.id)

    return employee_to_dict(employee, db)


# =========================
# Delete Employee
# =========================

@router.delete(
    "/{employee_id}",
    dependencies=[Depends(require_roles(1, 2))]
)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    deleted_id = employee.id

    db.delete(employee)
    db.commit()

    record_audit(db, current_user, ACTION_DELETE, ENTITY_EMPLOYEE, deleted_id)

    return {
        "message": "Employee deleted successfully"
    }