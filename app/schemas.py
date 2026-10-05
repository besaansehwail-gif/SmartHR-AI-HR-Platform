from datetime import date

from pydantic import BaseModel, field_validator

#: The optional celebration dates on `employees`
#: (migrations/2026-09-27_employee_celebration_dates.sql), read by the AI
#: Employee Celebration workflow. Named once for the router and the tests.
CELEBRATION_DATE_FIELDS = (
    "birth_date", "promotion_date", "graduation_date", "wedding_date", "new_baby_date",
)


class _CelebrationDates(BaseModel):
    birth_date: date | None = None
    promotion_date: date | None = None
    graduation_date: date | None = None
    wedding_date: date | None = None
    new_baby_date: date | None = None

    @field_validator("birth_date")
    @classmethod
    def _birth_date_in_past(cls, value: date | None) -> date | None:
        # A birthday is celebrated from this date every year; one that has not
        # happened yet is a typing mistake, and would be silently never found.
        if value is not None and value >= date.today():
            raise ValueError("birth_date must be in the past")
        return value


class EmployeeCreate(_CelebrationDates):
    first_name: str
    last_name: str
    phone: str | None = None
    department_id: int | None = None
    position_id: int | None = None
    manager_id: int | None = None
    hire_date: date | None = None
    employment_status: str = "active"


class EmployeeUpdate(_CelebrationDates):
    first_name: str
    last_name: str
    phone: str | None = None
    department_id: int | None = None
    position_id: int | None = None
    manager_id: int | None = None
    hire_date: date | None = None
    employment_status: str = "active"
