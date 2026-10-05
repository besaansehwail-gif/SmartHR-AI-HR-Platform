"""Leave tools.

`get_my_leave` is SmartHR's first real MCP tool. Read its signature closely:
it takes `status` and `year` and **nothing that identifies a person**. That is
the security design, not an omission. The employee is resolved from the
principal FastAPI bound from the verified JWT, so the set of leave rows this
tool can reach is decided before the model is ever consulted.
"""

import logging
from typing import Annotated, Any

from pydantic import Field

from app.database import SessionLocal
from app.identity import resolve_employee
from app.mcp.identity import NoPrincipalBound, current_principal
from app.mcp.permissions import ToolNotPermitted, authorise
from app.mcp.server import smarthr_mcp
from app.services.leave_service import my_leave_summary

logger = logging.getLogger("smarthr.mcp.tools")


def _error(code: str, message: str) -> dict[str, Any]:
    """A refusal the model can act on.

    Returned rather than raised so the model receives a structured explanation
    it can relay ("you do not have access to that") instead of a protocol
    error it can only apologise for.
    """
    return {"ok": False, "error_code": code, "error": message}


@smarthr_mcp.tool(
    name="get_my_leave",
    title="My leave requests",
    description=(
        "Return the signed-in employee's own leave requests from the SmartHR "
        "database: how many they have filed, the status of each, the days "
        "requested and approved per leave type, and anything upcoming. Use it "
        "for any question about the user's own leave, holiday, time off, "
        "vacation or absence, in any language. It always answers for the "
        "signed-in user and cannot return anyone else's leave. SmartHR stores "
        "no entitlement table, so it reports days taken, never a remaining "
        "balance."
    ),
)
def get_my_leave(
    status: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Restrict to one status: Pending, Approved, Rejected or "
                "Cancelled. Omit, or pass 'all', for every request."
            ),
        ),
    ] = None,
    year: Annotated[
        int | None,
        Field(
            default=None,
            description="Only requests whose start date falls in this year.",
        ),
    ] = None,
) -> dict[str, Any]:
    """The signed-in employee's own leave. Takes no employee identifier."""
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
        logger.warning("get_my_leave called with no principal bound")
        return _error("no_principal", str(exc))

    logger.info(
        "MCP tool get_my_leave invoked | user_id=%s status=%s year=%s",
        principal.user_id,
        status or "all",
        year,
    )

    db = SessionLocal()
    try:
        # Authorisation first, and from the database - not from the principal's
        # cached role and not from anything the browser sent.
        try:
            account = authorise("get_my_leave", principal.user_id, db)
        except ToolNotPermitted as exc:
            logger.info(
                "MCP tool get_my_leave refused | user_id=%s code=%s",
                principal.user_id,
                exc.code,
            )
            return _error(exc.code, str(exc))

        employee = resolve_employee(account, db)

        if employee is None:
            # users has no name and the employees link is nullable, so this is
            # a legitimate state rather than a failure.
            logger.info(
                "MCP tool get_my_leave: no employee linked | user_id=%s",
                principal.user_id,
            )
            return _error(
                "no_employee_link",
                "This account is not linked to an employee record, so it has "
                "no personal leave to report.",
            )

        summary = my_leave_summary(employee, db, status=status, year=year)

        # Counts only - never the leave reasons, which are personal.
        logger.info(
            "MCP tool get_my_leave ok | user_id=%s employee_id=%s requests=%s upcoming=%s",
            principal.user_id,
            employee.id,
            summary["total_requests"],
            summary["upcoming_count"],
        )

        return {"ok": True, **summary}

    except Exception:
        logger.exception(
            "MCP tool get_my_leave failed | user_id=%s", principal.user_id
        )
        return _error(
            "database_error", "The SmartHR database could not be read just now."
        )
    finally:
        db.close()
