"""Explicit post-interview orchestration (Phase 12).

    stored answers
      -> 1. Analysis Agent     interview_analysis_service.analyse_interview
                               (answers with no completed analysis only;
                               failures stored as failed, as before)
      -> 2. Report Agent       interview_report_service.interview_report
                               -> report_agent.build_brief  (no model)
      -> 3. Recruitment Agent  interview_matching_service.matching_for_candidate
                               -> matching_agent.explain    (no model)

The steps are plain Python calls in a fixed order - no role calls another,
none chooses what runs next. Each step reads its data through the existing
service and is isolated: a failure is reported with a code and the next step
still runs. None of them writes `interviews`, the sessions or the answers
(only step 1 writes, to the analyses table, through its existing service),
and that is re-checked after the run: the interview's status and every
stored answer are compared with a snapshot taken before it.

The interviewer is not part of this: it runs in the worker process during
the interview and nothing here imports it.
"""

import hashlib
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.ai.hr_intelligence import matching_agent, report_agent
from app.ai.hr_intelligence.contracts import AgentInputError
from app.ai.hr_intelligence.roles import POST_INTERVIEW_ORDER
from app.models import AiInterviewAnswer, Application, Interview, Job
from app.services import (
    interview_analysis_service,
    interview_context_service,
    interview_matching_service,
    interview_report_service,
)

logger = logging.getLogger("smarthr.hr_intelligence")

DISCLAIMER = ("Produced by SmartHR's post-interview AI roles from stored interview data. "
              "Nothing here is a score, a ranking, a recommendation or a hiring decision.")


class IntelligenceError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _snapshot(db: Session, interview_id: int) -> tuple[str | None, str]:
    """The interview's status and a digest of its stored answers."""
    db.expire_all()
    interview = db.get(Interview, interview_id)
    rows = (db.query(AiInterviewAnswer.id, AiInterviewAnswer.sequence, AiInterviewAnswer.question_id,
                     AiInterviewAnswer.transcript)
            .filter(AiInterviewAnswer.interview_id == interview_id)
            .order_by(AiInterviewAnswer.id).all())
    digest = hashlib.sha256(repr([tuple(r) for r in rows]).encode("utf-8")).hexdigest()
    return (interview.status if interview else None), digest


def _analysis_step(db: Session, interview_id: int, analyse: bool) -> dict[str, Any]:
    if not analyse:
        return {"status": "skipped", "attempted": 0}
    attempted = interview_analysis_service.analyse_interview(db, interview_id)
    return {"status": "completed", "attempted": attempted}


def _report_step(db: Session, interview_id: int, session_id: int | None) -> dict[str, Any]:
    report = interview_report_service.interview_report(db, interview_id, session_id)
    brief = report_agent.build_brief(report)
    counts = report["summary"]["analysis_status_counts"]
    return {"status": "completed", "analysis_status_counts": counts, "brief": brief}


def _matching_step(db: Session, interview_id: int) -> dict[str, Any]:
    interview = db.get(Interview, interview_id)
    application = db.get(Application, interview.application_id) if interview else None
    job = db.get(Job, application.job_id) if application else None
    if job is None:
        return {"status": "completed", "explanation": matching_agent.explain(
            matching_agent.MatchingInput(job_title=None, status=matching_agent.STATUS_UNAVAILABLE))}
    result = interview_matching_service.matching_for_candidate(db, application.candidate_id, job)
    data = matching_agent.input_from(interview_context_service.job_context(job, db), result.status,
                                     result.context)
    return {"status": "completed", "explanation": matching_agent.explain(data)}


def run_post_interview(db: Session, interview_id: int, *, analyse: bool = True,
                       session_id: int | None = None) -> dict[str, Any]:
    """Run the post-interview roles for one interview. Raises
    IntelligenceError("not_found") only for an unknown interview; every
    step's own failure is reported in its result instead."""
    if db.get(Interview, interview_id) is None:
        raise IntelligenceError("Interview not found.", "not_found")
    before = _snapshot(db, interview_id)

    steps = {
        "analysis": lambda: _analysis_step(db, interview_id, analyse),
        "report": lambda: _report_step(db, interview_id, session_id),
        "recruitment": lambda: _matching_step(db, interview_id),
    }
    results: dict[str, Any] = {}
    for name in POST_INTERVIEW_ORDER:
        try:
            results[name] = steps[name]()
        except interview_report_service.ReportError as exc:
            db.rollback()
            results[name] = {"status": "failed", "error_code": exc.code}
        except AgentInputError:
            db.rollback()
            results[name] = {"status": "failed", "error_code": "unsafe_input"}
        except Exception as exc:   # one role failing never stops or alters the rest
            db.rollback()
            logger.warning("hr intelligence: interview=%s role=%s failed (%s)",
                           interview_id, name, type(exc).__name__)
            results[name] = {"status": "failed", "error_code": "internal_error"}

    after = _snapshot(db, interview_id)
    intact = after == before
    if not intact:  # cannot happen through these services; said loudly if it ever does
        logger.error("hr intelligence: interview=%s status or answers changed during the run", interview_id)
    logger.info("hr intelligence: interview=%s %s", interview_id,
                " ".join(f"{n}={results[n]['status']}" for n in POST_INTERVIEW_ORDER))
    return {
        "interview_id": interview_id,
        "order": list(POST_INTERVIEW_ORDER),
        "agents": results,
        "interview_unchanged": intact,
        "disclaimer": DISCLAIMER,
        "is_hiring_decision": False,
    }
