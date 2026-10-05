"""Applying to an opportunity, and tracking what happened next.

Shared by three callers, which is the reason it is a service and not router
code:

    POST /applicant/applications          the Apply button
    the `submit_application` MCP tool     the Career Agent, when asked to apply
    GET  /applicant/applications          the applicant's tracker

`submit()` takes a `Candidate` object, never a candidate id. The only way to
obtain that object is `dependencies.get_current_candidate`, which resolves it
from the verified JWT. So "Applicant A cannot create an application for
Applicant B" is not a check that could be forgotten somewhere - there is no
argument through which B could be named. The Career Agent is bound by the same
thing: its tool has a `job_id` parameter and no candidate parameter at all.

Applications are ordinary `applications` rows with the ordinary stage
vocabulary from `app/routers/applications.py`, which is imported rather than
restated. An application an applicant files and one HR keys in are the same
row, on the same recruitment board, moving through the same eight stages.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Application, Candidate, Interview, Job
from app.routers.applications import read_stage
from app.services.applicant_service import latest_cv
from app.services.opportunity_service import public_job

logger = logging.getLogger("smarthr.applicant")


class ApplicationError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# What an applicant is told about their own application
#
# `applications.status` is the same eight-token column HR moves through. These
# are the applicant-facing words for those tokens - a presentation map, not a
# second vocabulary, so nothing has to stay in sync in the database.
#
# Note `screening` -> "Under Review". The stage names recruiters use describe
# what the *team* is doing; these describe what the applicant can know.
# ---------------------------------------------------------------------------

APPLICANT_STAGE_LABELS = {
    "applied": "Applied",
    "screening": "Under Review",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "assessment": "Assessment",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Not selected",
}

#: Ordered, for the tracker's progress indicator. `rejected` is deliberately
#: outside it: it is an outcome, not a step on the way to one.
STAGE_ORDER = (
    "applied", "screening", "shortlisted", "interview", "assessment", "offer", "hired",
)

CLOSED_STAGES = ("hired", "rejected")

#: Re-applying is refused while an application is still live. Once it has been
#: decided, a fresh application to the same opportunity is allowed - people
#: reapply, and the schema has no unique constraint to argue with.
OPEN_STAGES = tuple(s for s in STAGE_ORDER)


def stage_view(raw_status: str | None) -> dict[str, Any]:
    stage = read_stage(raw_status)
    in_order = stage in STAGE_ORDER

    return {
        "status": stage,
        "status_label": APPLICANT_STAGE_LABELS.get(stage, stage.title()),
        "step": STAGE_ORDER.index(stage) + 1 if in_order else None,
        "total_steps": len(STAGE_ORDER),
        "is_closed": stage in CLOSED_STAGES,
        "is_successful": stage == "hired",
    }


def application_view(
    application: Application, db: Session, *, include_interviews: bool = True
) -> dict[str, Any]:
    """One application as its owner may see it.

    What is **not** here is the design: no `interviews.notes` (the interviewer's
    private write-up), no interviewer identity, no other candidate, no pipeline
    position, no recruiter, no AI match score. An applicant learns their own
    stage and, when an interview is actually booked, when and where to turn up.
    """
    job = db.query(Job).filter(Job.id == application.job_id).first()

    scheduled: list[dict[str, Any]] = []

    if include_interviews:
        interviews = (
            db.query(Interview)
            .filter(Interview.application_id == application.id)
            .order_by(Interview.scheduled_at)
            .all()
        )

        for interview in interviews:
            status = (interview.status or "").strip().lower()

            # Only interviews that are actually going to happen. A cancelled
            # one is internal churn the applicant was never told about.
            if status in ("cancelled", "canceled"):
                continue

            scheduled.append({
                "id": interview.id,
                "scheduled_at": (
                    interview.scheduled_at.isoformat()
                    if interview.scheduled_at else None
                ),
                "location": interview.location,
                "status": status or "scheduled",
            })

    return {
        "id": application.id,
        "applied_at": application.applied_at.isoformat() if application.applied_at else None,
        **stage_view(application.status),
        "opportunity": public_job(job, db) if job else None,
        "job_id": application.job_id,
        "job_title": job.title if job else None,
        "interviews": scheduled,
    }


def my_applications(candidate: Candidate, db: Session) -> list[dict[str, Any]]:
    """Every application belonging to this candidate, newest first.

    The filter is `candidate_id == candidate.id` and the candidate came from
    the JWT, so this returns the caller's applications and can return no
    others.
    """
    rows = (
        db.query(Application)
        .filter(Application.candidate_id == candidate.id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    return [application_view(row, db) for row in rows]


def application_for_candidate(
    candidate: Candidate, application_id: int, db: Session
) -> dict[str, Any] | None:
    """One application, only if it belongs to this candidate.

    Ownership is part of the query rather than a check after it, so a
    mismatched id is indistinguishable from a non-existent one - it returns
    None either way, and the router turns that into a 404. An applicant cannot
    learn that somebody else's application exists by probing ids.
    """
    application = (
        db.query(Application)
        .filter(Application.id == application_id)
        .filter(Application.candidate_id == candidate.id)
        .first()
    )

    if application is None:
        return None

    return application_view(application, db)


@dataclass
class SubmissionResult:
    application: dict[str, Any]
    created: bool
    cv_id: int | None
    warnings: list[str]


def existing_open_application(
    candidate: Candidate, job_id: int, db: Session
) -> Application | None:
    """A live application by this candidate to this job, if there is one."""
    rows = (
        db.query(Application)
        .filter(Application.candidate_id == candidate.id)
        .filter(Application.job_id == job_id)
        .all()
    )

    for row in rows:
        if read_stage(row.status) not in CLOSED_STAGES:
            return row

    return None


def submit(
    candidate: Candidate,
    job_id: int,
    db: Session,
    *,
    require_cv: bool = True,
) -> SubmissionResult:
    """File one application for this candidate.

    Everything that could make the application invalid is checked before the
    row is written: the job exists, it is open, its deadline has not passed,
    the applicant has not already applied, and there is a CV on file. Each
    refusal carries a code the router maps to a status and the Career Agent can
    explain.
    """
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise ApplicationError("That opportunity does not exist.", code="not_found")

    if job.status != "open":
        raise ApplicationError(
            f"'{job.title}' is not accepting applications.", code="not_open"
        )

    if job.deadline and job.deadline < date.today():
        raise ApplicationError(
            f"The deadline for '{job.title}' passed on {job.deadline.isoformat()}.",
            code="deadline_passed",
        )

    duplicate = existing_open_application(candidate, job_id, db)

    if duplicate is not None:
        raise ApplicationError(
            f"You have already applied to '{job.title}'. Your application is "
            f"currently at: {APPLICANT_STAGE_LABELS.get(read_stage(duplicate.status))}.",
            code="already_applied",
        )

    cv = latest_cv(candidate, db)

    if cv is None and require_cv:
        raise ApplicationError(
            "Upload your CV before applying, so the recruiter can read it.",
            code="no_cv",
        )

    warnings: list[str] = []

    if not candidate.skills:
        warnings.append(
            "Your profile lists no skills yet. Adding them improves the "
            "opportunity suggestions you are shown."
        )

    application = Application(
        candidate_id=candidate.id,
        job_id=job_id,
        status="applied",
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    logger.info(
        "Application submitted | candidate_id=%s job_id=%s application_id=%s cv=%s",
        candidate.id, job_id, application.id, cv.id if cv else None,
    )

    return SubmissionResult(
        application=application_view(application, db),
        created=True,
        cv_id=cv.id if cv else None,
        warnings=warnings,
    )


def application_summary(candidate: Candidate, db: Session) -> dict[str, Any]:
    """Counts for the applicant's dashboard, from their own rows."""
    rows = (
        db.query(Application)
        .filter(Application.candidate_id == candidate.id)
        .all()
    )

    by_stage: dict[str, int] = {}

    for row in rows:
        stage = read_stage(row.status)
        by_stage[stage] = by_stage.get(stage, 0) + 1

    return {
        "total": len(rows),
        "active": sum(
            1 for row in rows if read_stage(row.status) not in CLOSED_STAGES
        ),
        "by_stage": by_stage,
        "by_stage_label": {
            APPLICANT_STAGE_LABELS.get(stage, stage): count
            for stage, count in by_stage.items()
        },
    }
