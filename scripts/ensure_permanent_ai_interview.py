"""Prepare the permanent development AI Interview for a local test applicant.

Run from the repository root with:
    venv\\Scripts\\python.exe -m scripts.ensure_permanent_ai_interview

Set AI_INTERVIEW_APPLICANT_EMAIL to a local account in the reserved test
domain before running. Never use a production or real applicant account.

This reuses the applicant's interview-stage application and, when available,
its unstarted backup interview. It creates only an Interview row if no safe
existing interview can be reused. The command is idempotent and refuses to
run in production.
"""

from __future__ import annotations

import os
from datetime import datetime

from app.database import SessionLocal
from app.models import AiInterviewSession, Application, Candidate, Interview, User
from app.routers.applications import read_stage
from app.services.interview_context_service import DEVELOPMENT_TEST_INTERVIEW_LOCATION
from app.settings import PRODUCTION, environment

def configured_applicant_email() -> str:
    email = os.environ.get("AI_INTERVIEW_APPLICANT_EMAIL", "")
    if not email.lower().endswith("@smarthr.test"):
        raise RuntimeError(
            "Set AI_INTERVIEW_APPLICANT_EMAIL to a local account in the reserved test domain."
        )
    return email


BACKUP_LOCATION_TOKEN = "backup"


def ensure_permanent_interview() -> tuple[int, bool]:
    if environment() == PRODUCTION:
        raise RuntimeError("The permanent AI Interview fixture is development-only.")
    applicant_email = configured_applicant_email()

    with SessionLocal() as db:
        candidate = (
            db.query(Candidate)
            .join(User, User.id == Candidate.user_id)
            .filter(User.email == applicant_email, User.role_id == 5)
            .one_or_none()
        )
        if candidate is None:
            raise RuntimeError(
                "The configured test account must have a linked Applicant profile before setup."
            )

        applications = (
            db.query(Application)
            .filter(Application.candidate_id == candidate.id)
            .order_by(Application.id)
            .all()
        )
        application = next(
            (row for row in applications if read_stage(row.status) == "interview"),
            None,
        )
        if application is None:
            raise RuntimeError(
                "The selected applicant needs an existing application at the interview stage; "
                "no candidate, job, or application was created."
            )

        marked = (
            db.query(Interview)
            .filter(
                Interview.application_id == application.id,
                Interview.location == DEVELOPMENT_TEST_INTERVIEW_LOCATION,
            )
            .order_by(Interview.id)
            .first()
        )
        if marked is not None:
            if marked.status == "in_progress":
                raise RuntimeError(
                    f"Development interview {marked.id} is currently in progress; "
                    "it was left untouched."
                )
            marked.status = "TEST"
            db.commit()
            return marked.id, False

        existing = (
            db.query(Interview)
            .filter(Interview.application_id == application.id)
            .order_by(Interview.id.desc())
            .all()
        )
        reusable = next(
            (
                row for row in existing
                if BACKUP_LOCATION_TOKEN in (row.location or "").casefold()
                and db.query(AiInterviewSession)
                .filter(AiInterviewSession.interview_id == row.id)
                .count() == 0
            ),
            None,
        )
        if reusable is not None:
            reusable.location = DEVELOPMENT_TEST_INTERVIEW_LOCATION
            reusable.status = "TEST"
            db.commit()
            return reusable.id, False

        interview = Interview(
            application_id=application.id,
            scheduled_at=datetime.now().replace(microsecond=0),
            location=DEVELOPMENT_TEST_INTERVIEW_LOCATION,
            status="TEST",
            notes="Permanent development/testing interview; not a real candidate interview.",
        )
        db.add(interview)
        db.commit()
        return interview.id, True


def main() -> None:
    interview_id, created = ensure_permanent_interview()
    applicant_email = configured_applicant_email()
    print(
        f"{'Created' if created else 'Reused'} permanent development AI Interview "
        f"{interview_id} for {applicant_email}."
    )
    print("No candidate, job, or application rows were created.")


if __name__ == "__main__":
    main()
