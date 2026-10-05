"""AI Employee Celebration.

    GET  /social/celebration/drafts              HR's queue
    POST /social/celebration/drafts/{id}/approve HR posts it
    POST /social/celebration/drafts/{id}/dismiss HR does not
    POST /social/celebration/run                 run the sweep now
    POST /social/celebration                     one employee, on demand
    GET  /social/celebration/status              what it can do, and cannot

**The workflow starts by itself.** `scripts/run_daily_celebrations.py` runs
once a day, finds who is celebrating today from the employee's dates
(`hire_date`, `birth_date`, `promotion_date`, `graduation_date`,
`wedding_date`, `new_baby_date`), and prepares one celebration each; nobody has to pick a name from a list. `/run`
is the same sweep on demand, so a recruiter (or a test) need not wait a day
to see it work.

Both are `require_roles(1, 2)` - Admin and HR. The workflow reads an
employee's hire date and job title for anybody in the company, which is
`/employees/`-grade data, and `/employees/` is Admin+HR. An AI surface must
not widen who may read something, so this is guarded exactly as the data it
reads is guarded. Manager, Employee and Applicant get 403.

**Its own prefix, not a route inside `app/routers/social.py`.** That file is
the Social Hub's HTTP layer and is guarded with `require_staff` (roles 1-4)
at the router; adding a stricter route inside it would put two different
access rules in one file, which is how one of them eventually gets forgotten.
The path still sits under `/social/` because this is a Social Hub feature.

**No agent publishes anything.** The sweep's most consequential act is to
write a `pending` draft. It becomes a post only through
`/drafts/{id}/approve`, which takes the signed-in recruiter and calls
`social_service.create_post()` - the same function the composer calls, with
its moderation and its audit row. The scheduler has no `User`, so it cannot
reach that path even if it tried, and a draft the Review Agent rejected is
refused there as well.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.celebration.graph import run_celebration
from app.ai.celebration.state import MAX_RETRIES, OCCASIONS
from app.ai.config import llm_settings
from app.audit import ACTION_CREATE, ENTITY_SOCIAL_POST, record_audit
from app.dependencies import get_db, require_roles
from app.models import User
from app.services import celebration_service

logger = logging.getLogger("smarthr.ai.celebration")

router = APIRouter(prefix="/social/celebration", tags=["AI Employee Celebration"])

#: Admin and HR. Named once so the guard and this module's docstring cannot
#: drift apart.
CELEBRATION_ROLES = (1, 2)


#: Service error code -> HTTP status. Everything else is 422, the rule
#: `app/routers/social.py` already follows.
ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "already_decided": status.HTTP_409_CONFLICT,
    "not_approved": status.HTTP_409_CONFLICT,
}


def _fail(error: celebration_service.CelebrationError):
    raise HTTPException(
        status_code=ERROR_STATUS.get(
            error.code, status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        detail=str(error),
    )


class SweepRequest(BaseModel):
    """Nothing required. `dry_run` reports what would be prepared."""

    dry_run: bool = False


@router.post("/run")
def run_sweep(
    payload: SweepRequest | None = None,
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """Run today's sweep now - the same function the daily job calls.

    Here so a recruiter does not have to wait until tomorrow to see the
    feature work, and so the scheduled path and the on-demand path cannot
    drift into two behaviours. It is **idempotent**: a second call finds the
    drafts the first one wrote and prepares nothing, spending no model calls.
    """
    dry_run = bool(payload.dry_run) if payload else False

    try:
        summary = celebration_service.run_daily(db, dry_run=dry_run)
    except Exception:
        logger.exception("Celebration sweep failed | user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The celebration sweep could not be completed. Nothing has "
                "been posted."
            ),
        )

    logger.info(
        "Celebration sweep requested | user_id=%s prepared=%s skipped=%s",
        current_user.id, summary["prepared"], summary["skipped_existing"],
    )
    return summary


@router.get("/drafts")
def list_drafts(
    status_filter: str | None = None,
    limit: int = 50,
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """HR's queue: celebrations the AI prepared and nobody has decided on yet.

    `status_filter=all` returns every draft including posted and dismissed
    ones, so a recruiter can see what was done rather than only what is left.
    """
    wanted = None if status_filter == "all" else (
        status_filter or celebration_service.STATUS_PENDING
    )
    return {
        "drafts": celebration_service.list_drafts(db, status=wanted, limit=limit),
        "status": wanted or "all",
    }


@router.post("/drafts/{draft_id}/approve")
def approve_draft(
    draft_id: int,
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """HR posts a prepared celebration. This is the human approval step.

    The post is created by `social_service.create_post()` under **this
    recruiter's** account, so it is moderated, audited and attributed exactly
    as a post they typed. A draft the Review Agent did not approve is refused
    with 409.
    """
    try:
        result = celebration_service.approve_draft(draft_id, current_user, db)
    except celebration_service.CelebrationError as error:
        _fail(error)

    # The audit row for a post is written by the router, not by
    # `social_service.create_post()` - `app/routers/social.py` does the same
    # after its own commit. Without this line a celebration would be the one
    # post in SmartHR that reached the feed unaudited, which is exactly the
    # post that most needs the trail: a person published words a model wrote.
    record_audit(
        db, current_user, ACTION_CREATE, ENTITY_SOCIAL_POST, result["post"]["id"]
    )

    return result


@router.post("/drafts/{draft_id}/dismiss")
def dismiss_draft(
    draft_id: int,
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """HR decides not to post it. The draft is kept, marked dismissed."""
    try:
        return celebration_service.dismiss_draft(draft_id, current_user, db)
    except celebration_service.CelebrationError as error:
        _fail(error)


class CelebrationRequest(BaseModel):
    """One employee id, and nothing else.

    No occasion, no message, no years - everything the workflow decides, it
    decides from SmartHR's own rows. A request that could name the occasion
    would let the browser assert a fact about a person, which is the whole
    thing this feature must not do.
    """

    employee_id: int = Field(gt=0)


@router.post("")
def generate_celebration(
    payload: CelebrationRequest,
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """Run the three agents over one employee and return what came out.

    The response carries the review as well as the result, because "approved"
    and "written but rejected" are different things and a person about to
    post one of them should be able to tell which they have.
    """
    try:
        employee = celebration_service.get_employee(payload.employee_id, db)
        events = celebration_service.get_employee_events(payload.employee_id, db)
    except celebration_service.CelebrationError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if error.code == "not_found"
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(error),
        ) from error

    try:
        final = run_celebration(employee, events)
    except Exception:
        # The graph catches its own agent failures; reaching here means a bug
        # in the wiring. Nothing was written either way - no node in this
        # workflow can write - so the message says so rather than leaving a
        # recruiter wondering what it did to the record.
        logger.exception(
            "Celebration workflow failed | employee_id=%s | user_id=%s",
            payload.employee_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The celebration workflow could not be completed. Nothing has "
                "been posted and no employee record has been changed."
            ),
        )

    logger.info(
        "Celebration run | employee_id=%s | occasion=%s | approved=%s | "
        "retries=%s | error=%s | user_id=%s",
        payload.employee_id,
        final.get("occasion"),
        final.get("review_approved"),
        final.get("retry_count"),
        final.get("error_code"),
        current_user.id,
    )

    return {
        "employee": {
            "employee_id": employee["employee_id"],
            "name": employee["name"],
            "position_title": employee["position_title"],
            "department_name": employee["department_name"],
        },
        "occasion": final.get("occasion") or "none",
        "years": final.get("years"),
        "occasion_reason": final.get("occasion_reason") or "",
        "message": final.get("message") or None,
        "review": {
            "approved": bool(final.get("review_approved")),
            "reason": final.get("review_reason") or "",
            "suggestions": final.get("review_suggestions"),
        },
        # Null unless the Review Agent approved it. This is the field the UI
        # offers to post, so an unapproved run offers nothing.
        "final_celebration": final.get("final_celebration"),
        "retry_count": int(final.get("retry_count") or 0),
        "max_retries": MAX_RETRIES,
        "error_code": final.get("error_code"),
        # One line per node, in the order they ran, so a recruiter can see
        # which agent decided what instead of taking the result on trust -
        # the same reasoning behind the HR Agent's tool trace.
        "trace": final.get("trace") or [],
        "published": False,
    }


@router.get("/status")
def celebration_status(
    current_user: User = Depends(require_roles(*CELEBRATION_ROLES)),
    db: Session = Depends(get_db),
):
    """What this workflow can evidence, stated rather than implied.

    Every occasion is detected from one employee date column
    (`occasion_fields`); an employee with that column empty simply has no such
    occasion - that is reported per person in the events payload, not here.
    """
    settings = llm_settings()

    return {
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model or None,
        "workflow": "langgraph",
        "agents": ["occasion", "message", "review"],
        "max_retries": MAX_RETRIES,
        "occasions": list(OCCASIONS),
        "occasions_available": [*celebration_service.OCCASION_FIELDS, "none"],
        "occasions_unavailable": celebration_service.NOT_RECORDED,
        # occasion -> the employees column it is detected from, and whether
        # it recurs every year (birthday, anniversary) or happens once.
        "occasion_fields": {
            occasion: {"column": column, "yearly": yearly}
            for occasion, (column, yearly) in celebration_service.OCCASION_FIELDS.items()
        },
        "anniversary_window_days": celebration_service.ANNIVERSARY_WINDOW_DAYS,
        # Said outright: this endpoint generates, it does not publish.
        "publishes": False,
        "writes": False,
    }
