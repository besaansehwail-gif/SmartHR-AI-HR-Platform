"""Leave business logic.

This is the single implementation of "summarise an employee's own leave". The
REST route `GET /leave-requests/me` and the MCP tool `get_my_leave` both call
it, so there is one behaviour to reason about and one place to change.

It deliberately takes an `Employee`, not an id from a caller: resolving the
employee is an identity decision that belongs to whoever authenticated the
request, and passing the resolved row in makes it impossible for this function
to be handed somebody else's id by accident.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Employee, LeaveRequest

# One definition of the status vocabulary and the derived span, shared with the
# leave router rather than copied.
from app.routers.leave_requests import duration_days, read_status

#: Beyond this the individual rows are omitted; the counts still cover them all.
MAX_DETAIL_ROWS = 20


def _leave_row(leave: LeaveRequest) -> dict[str, Any]:
    """One request, using only columns that exist on leave_requests."""
    return {
        "id": leave.id,
        "leave_type": leave.leave_type,
        "start_date": leave.start_date.isoformat() if leave.start_date else None,
        "end_date": leave.end_date.isoformat() if leave.end_date else None,
        # Derived from the two date columns; there is no duration column.
        "duration_days": duration_days(leave.start_date, leave.end_date),
        "status": read_status(leave.status),
        "reason": leave.reason,
    }


def my_leave_summary(
    employee: Employee,
    db: Session,
    status: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Everything SmartHR can truthfully say about one employee's leave.

    The query is always filtered to `employee.id`. There is no parameter that
    widens it to another person, which is what makes this safe to expose to a
    language model.
    """
    query = db.query(LeaveRequest).filter(LeaveRequest.employee_id == employee.id)

    if isinstance(year, int) and 1900 < year < 2200:
        query = query.filter(
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )

    rows = query.order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc()).all()

    wanted = (status or "").strip()
    if wanted and wanted.lower() != "all":
        rows = [row for row in rows if read_status(row.status).lower() == wanted.lower()]

    requests = [_leave_row(row) for row in rows]

    by_status: dict[str, int] = {}
    days_by_status: dict[str, int] = {}
    days_by_type: dict[str, int] = {}

    for entry in requests:
        entry_status = entry["status"]
        by_status[entry_status] = by_status.get(entry_status, 0) + 1
        days_by_status[entry_status] = (
            days_by_status.get(entry_status, 0) + entry["duration_days"]
        )

        if entry_status in ("Pending", "Approved"):
            leave_type = entry["leave_type"] or "Unspecified"
            days_by_type[leave_type] = days_by_type.get(leave_type, 0) + entry["duration_days"]

    today = date.today().isoformat()
    upcoming = [
        entry
        for entry in requests
        if entry["start_date"]
        and entry["start_date"] >= today
        and entry["status"] in ("Pending", "Approved")
    ]

    return {
        "employee": {
            "id": employee.id,
            "full_name": f"{employee.first_name} {employee.last_name}",
        },
        "filters": {"status": wanted or "all", "year": year if isinstance(year, int) else None},
        "total_requests": len(requests),
        "counts_by_status": by_status,
        "days_by_status": days_by_status,
        "days_taken_by_type": days_by_type,
        "upcoming_count": len(upcoming),
        # `requests` is newest-first, so the soonest upcoming request is last.
        "next_leave": upcoming[-1] if upcoming else None,
        "requests": requests[:MAX_DETAIL_ROWS],
        "truncated": len(requests) > MAX_DETAIL_ROWS,
        # Stated rather than left to be inferred: this schema has no
        # entitlement or allowance table, so a remaining balance does not
        # exist and must not be implied.
        "entitlement_available": False,
        "notes": (
            "SmartHR stores no leave entitlement or allowance table, so only "
            "days requested and days approved can be reported - never a "
            "remaining balance."
        ),
    }
