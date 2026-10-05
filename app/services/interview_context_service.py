"""AI Interview (Phase 4) - which job an AI Interview is for, resolved server-side.

    interviews.application_id -> applications.job_id -> jobs
                              -> applications.candidate_id -> candidates.user_id (the JWT)

SmartHR already models this; nothing here copies job, application or interview
data. Three entry points, one rule each:

* `my_interviews()`  - the applicant's own interviews that can be held now.
  Ownership is IN the query (`applications.candidate_id = caller`).
* `interview_for_candidate()` - one of them by id, or None. Somebody else's id
  and a non-existent id are indistinguishable (the router answers 404 for
  both), the rule `application_for_candidate()` already follows.
* `context_for_room()` - for the agent worker: the room's binding in
  `ai_interview_sessions`, re-checked against the live rows (still the same
  candidate's application? still scheduled?), then the trimmed Job Context.

The browser only ever names an `interview_id`, and only one that ownership
resolves. It never names a job: the job is whatever the application points at.

**The Job Context is built field by field** (the `public_job()` rule): a
projection that starts from the whole row and removes the private parts leaks
the next column somebody adds. Everything in it is already shown to applicants
on the Opportunities page. Not in it, on purpose: `jobs.status`, `created_by`,
`location`, `deadline`, applicant counts, the application's pipeline stage,
`interviews.notes`, the interviewer, and anything about the candidate.

`jobs` has no responsibilities or skills column. `description` is the job's own
summary of the work, and `requirements` is split by the same
`requirement_tokens()` the Opportunities page and matching use - so every item
is a literal phrase from the posting, never an interpretation.

**Phase 9: when an interview may be held** (`ineligibility()`, one rule for
the applicant's start AND every agent call):

* the interview is `scheduled` or `in_progress` (completed / cancelled are
  finished business - a completed AI Interview cannot be started again);
* HR has approved it: the APPLICATION's stage is `interview` - moving a
  candidate on (or back) closes the AI Interview, even mid-way;
* it is inside the start window around `scheduled_at` (`interview_window()`,
  15 min before to 30 min after by default). The applicant's start is checked
  against now; a room is checked against when its session was started, so
  an interview begun inside the window may run past its end.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.ai.interview.config import interview_window as window_settings
from app.ai.interview.config import window_exempt_ids
from app.models import AiInterviewSession, Application, Candidate, Interview, Job
from app.routers.applications import read_stage
from app.services.opportunity_service import (
    _department_name,
    read_employment_type,
    requirement_tokens,
)

logger = logging.getLogger("smarthr.interview")

# Reserved only for the permanent local development interview. The marker is
# ignored in production and survives the ordinary interview-status lifecycle.
DEVELOPMENT_TEST_INTERVIEW_LOCATION = "SmartHR Development AI Interview (TEST)"

#: An AI Interview can be held for an interview that is going to happen or is
#: under way. `completed` and `cancelled` are finished business.
ELIGIBLE_STATUSES = ("scheduled", "in_progress")

#: Phase 9: HR's approval is the application being at this stage.
APPROVED_STAGE = "interview"

#: Why an interview cannot be held (None = it can), in the order checked.
NOT_OPEN = "not_open"          # cancelled, or any other non-eligible status
COMPLETED = "completed"        # already held
NOT_APPROVED = "not_approved"  # the application is not at the interview stage
TOO_EARLY = "too_early"
TOO_LATE = "too_late"

#: Caps on what reaches the model's prompt. The real rows are far shorter;
#: these only stop an unusually long posting from crowding out the interview.
DESCRIPTION_MAX = 2000
REQUIREMENTS_MAX = 20
REQUIREMENT_MAX = 120

#: The fields a Job Context has - asserted by the tests, so adding one is a
#: deliberate change rather than a side effect.
JOB_CONTEXT_FIELDS = (
    "job_id", "title", "department", "employment_type", "description", "requirements",
)


def _status(interview: Interview) -> str:
    return (interview.status or "").strip().lower().replace(" ", "_")


def is_development_test_interview(interview: Interview) -> bool:
    """Whether this is the explicitly marked development fixture.

    The location marker is stable while `status` temporarily tracks a running
    session. Production deliberately never treats a row as a test interview.
    """
    from app.settings import PRODUCTION, environment

    return (
        environment() != PRODUCTION
        and interview.location == DEVELOPMENT_TEST_INTERVIEW_LOCATION
    )


def _owned(db: Session, candidate_id: int):
    """(Interview, Job, Application) rows whose application belongs to this
    candidate."""
    return (
        db.query(Interview, Job, Application)
        .join(Application, Application.id == Interview.application_id)
        .join(Job, Job.id == Application.job_id)
        .filter(Application.candidate_id == candidate_id)
    )


def _clip(text: str | None, limit: int) -> str | None:
    text = " ".join((text or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def job_context(job: Job, db: Session) -> dict[str, Any]:
    """The trimmed, interview-relevant view of one `jobs` row."""
    requirements = [
        _clip(item, REQUIREMENT_MAX) for item in requirement_tokens(job.requirements)
    ][:REQUIREMENTS_MAX]
    return {
        "job_id": job.id,
        "title": job.title,
        "department": _department_name(job.department_id, db),
        "employment_type": read_employment_type(job.employment_type),
        "description": _clip(job.description, DESCRIPTION_MAX),
        "requirements": [item for item in requirements if item],
    }


def interview_summary(interview: Interview, job: Job) -> dict[str, Any]:
    """What the applicant's page needs to pick an interview - and no more."""
    is_test = is_development_test_interview(interview)
    # Phase 10: the start window, from the same `start_window()` the rule uses,
    # so the page can say when Start becomes available instead of guessing.
    # Local wall-clock times, like `scheduled_at`.
    # A window-exempt test interview has no window: no times, which the page
    # already reads as "the backend decides".
    opens, closes = (start_window(interview) if interview.scheduled_at
                     and not window_exempt(interview) and not is_test
                     else (None, None))
    return {
        "interview_id": interview.id,
        "job_title": job.title,
        "scheduled_at": interview.scheduled_at.isoformat()
        if interview.scheduled_at and not is_test else None,
        "status": "test" if is_test else _status(interview) or "scheduled",
        "is_test": is_test,
        "opens_at": opens.isoformat() if opens else None,
        "closes_at": closes.isoformat() if closes else None,
    }


def local_now() -> datetime:
    """`interviews.scheduled_at` is a local wall-clock time (as HR typed it,
    compared with `datetime.now()` like the dashboards do)."""
    return datetime.now()


def utc_to_local(value: datetime) -> datetime:
    """A naive UTC timestamp (`ai_interview_sessions`) on the local clock."""
    return value + (datetime.now() - datetime.utcnow())


def start_window(interview: Interview) -> tuple[datetime, datetime]:
    """(opens, closes) for starting this interview, local time."""
    window = window_settings()
    return (interview.scheduled_at - timedelta(minutes=window.early_minutes),
            interview.scheduled_at + timedelta(minutes=window.late_minutes))


def window_exempt(interview: Interview) -> bool:
    """A development test interview that may start at any time
    (`SMARTHR_INTERVIEW_WINDOW_EXEMPT_IDS`; never in production)."""
    return interview.id in window_exempt_ids()


def ineligibility(interview: Interview, application: Application, at: datetime) -> str | None:
    """Why this interview cannot be held at local time `at` - or None."""
    status = _status(interview)
    if is_development_test_interview(interview):
        if status == "completed":
            return COMPLETED
        return None if status in {"test", *ELIGIBLE_STATUSES} else NOT_OPEN
    if status == "completed":
        return COMPLETED
    if status not in ELIGIBLE_STATUSES:
        return NOT_OPEN
    if read_stage(application.status) != APPROVED_STAGE:
        return NOT_APPROVED
    if window_exempt(interview):
        return None
    opens, closes = start_window(interview)
    if at < opens:
        return TOO_EARLY
    if at > closes:
        return TOO_LATE
    return None


def my_interviews(candidate: Candidate, db: Session) -> list[dict[str, Any]]:
    """Open, HR-approved interviews. Not filtered by the start window: an
    upcoming interview is listed, and starting it early is refused with the
    time it opens."""
    # Phase 11.6.4: whether the interview's started attempts are used up - the
    # backend's own count (Phase 10), so a refreshed page never offers a Start
    # the backend would refuse. Informational; the limit is enforced at Start.
    # (Lazy import: interview_progress_service imports this module.)
    from app.services.interview_progress_service import MAX_STARTED_ATTEMPTS, started_attempts

    rows = _owned(db, candidate.id).order_by(Interview.scheduled_at, Interview.id).all()
    listings = []
    for interview, job, application in rows:
        is_test = is_development_test_interview(interview)
        test_status = _status(interview) in {"test", *ELIGIBLE_STATUSES, "completed"}
        eligible = (
            test_status
            if is_test
            else _status(interview) in ELIGIBLE_STATUSES
            and read_stage(application.status) == APPROVED_STAGE
        )
        if not eligible:
            continue
        listings.append({
            **interview_summary(interview, job),
            "attempts_exhausted": (
                False if is_test
                else started_attempts(db, interview.id) >= MAX_STARTED_ATTEMPTS
            ),
        })
    return listings


def check_interview(
    db: Session, candidate_id: int, interview_id: int, at: datetime
) -> tuple[Interview | None, Job | None, str | None]:
    """(interview, job, reason): reason None = it can be held at `at`.
    Somebody else's interview and a missing one are both (None, None,
    "not_found") - ownership is in the query."""
    row = _owned(db, candidate_id).filter(Interview.id == interview_id).first()
    if row is None:
        return None, None, "not_found"
    interview, job, application = row
    return interview, job, ineligibility(interview, application, at)


def interview_for_candidate(
    candidate: Candidate, interview_id: int, db: Session
) -> tuple[Interview, Job] | None:
    interview, job, reason = check_interview(db, candidate.id, interview_id, local_now())
    return None if reason else (interview, job)


def bind_room(
    db: Session,
    room_name: str,
    interview: Interview,
    candidate: Candidate,
    ttl_minutes: int,
    language: str | None = None,
) -> AiInterviewSession:
    now = datetime.utcnow()
    binding = AiInterviewSession(
        room_name=room_name,
        interview_id=interview.id,
        candidate_id=candidate.id,
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        language=language,
    )
    db.add(binding)
    db.commit()
    return binding


def resolve_binding(
    db: Session, room_name: str, grace: timedelta = timedelta(0)
) -> tuple[AiInterviewSession, Interview, Job] | None:
    """The room's binding row, its interview and its job, or None.

    The one validation every agent call goes through. None for: no binding,
    an expired binding, an interview no longer scheduled/in progress, an
    application that no longer belongs to the candidate the room was issued
    to, an application no longer at the interview stage (Phase 9), or a
    session that was not started inside the interview's window (Phase 9 -
    so rescheduling the interview closes its open room). Each is re-read from
    the live rows, not remembered.

    `grace` extends the expiry, and only Phase 7's answer recording passes
    one: the binding expires when the applicant's JOIN window closes, but an
    interview that started inside that window runs on after it, and its
    answers arrive until it ends. Context (plan / CV / matching) is fetched at
    the start and gets no grace.
    """
    binding = (
        db.query(AiInterviewSession)
        .filter(AiInterviewSession.room_name == room_name)
        .first()
    )
    if binding is None:
        logger.warning("agent context refused: room=%s has no interview binding", room_name)
        return None
    if binding.expires_at + grace <= datetime.utcnow():
        logger.warning("agent context refused: room=%s binding expired", room_name)
        return None

    interview, job, reason = check_interview(
        db, binding.candidate_id, binding.interview_id, utc_to_local(binding.created_at))
    if reason:
        logger.warning(
            "agent context refused: room=%s interview=%s no longer eligible (%s)",
            room_name, binding.interview_id, reason,
        )
        return None

    return binding, interview, job


def resolve_room(db: Session, room_name: str) -> tuple[Interview, Job, int] | None:
    """The interview, its job and its candidate id for a bound room, or None.

    Job Context (Phase 4), CV Context (Phase 5) and Matching Context (Phase 6)
    all go through this; see `resolve_binding` for what is re-checked. The
    candidate id returned is the APPLICATION's candidate - the same row the
    binding named, re-proved by the join rather than trusted.
    """
    resolved = resolve_binding(db, room_name)
    if resolved is None:
        return None
    binding, interview, job = resolved
    return interview, job, binding.candidate_id


def context_for_room(db: Session, room_name: str) -> dict[str, Any] | None:
    """The Job Context for the interview this room was created for, or None."""
    resolved = resolve_room(db, room_name)
    if resolved is None:
        return None
    _, job, _ = resolved
    return job_context(job, db)


def plan_context_for_room(
    db: Session, room_name: str
) -> tuple[dict[str, Any], str | None] | None:
    """The job context and stored language for a valid agent room."""
    resolved = resolve_binding(db, room_name)
    if resolved is None:
        return None
    binding, _, job = resolved
    return job_context(job, db), binding.language
