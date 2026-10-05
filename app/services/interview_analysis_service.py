"""AI Interview (Phase 7) - analysing a stored answer, and keeping the result.

    ai_interview_answers row
      -> the question it was stored against (bank text, copied at write time)
      -> its transcript, plus earlier parts of the answer to the same question
      -> Job Context       interview_context_service.job_context()      (Phase 4)
      -> CV Context        interview_cv_service.cv_for_candidate()     (Phase 5)
      -> Matching Context  interview_matching_service.matching_for_candidate() (Phase 6)
      -> app/ai/interview_analysis.analyse()   one GPT-4o call, validated
      -> ai_interview_answer_analyses          completed | failed (with a code)

Every context comes from the builder its phase already uses - nothing is
re-derived here, and no second matching or CV pipeline exists. The candidate
and job are those of the answer's own session and interview, and the two are
re-checked against each other (the application must still be that session's
candidate's) before anything is sent to the model.

**When it runs.** Once, in the background, right after a new answer is stored
(`schedule`), so HR normally finds it ready; and again only when HR asks
(`POST /ai-interview/answers/{interview_id}/analyse`), which re-runs failed or
missing analyses, or every one with `force`. A completed analysis is not
silently replaced, so a stored reading stays stable.

**Failure is recorded, not hidden.** No model, an unreachable model, or output
that does not validate is stored as `failed` with its code. The answer itself
is never affected: analysis is derived, the answer is the record.

Nothing here logs a transcript or an analysis: ids, statuses and codes only.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.hr_intelligence.contracts import AgentInputError, assert_safe_input
from app.ai.interview_analysis import AnalysisError, AnalysisInput, analyse
from app.models import (
    AiInterviewAnswer,
    AiInterviewAnswerAnalysis,
    AiInterviewSession,
    Application,
    Interview,
    Job,
)
from app.services import interview_context_service, interview_cv_service, interview_matching_service

logger = logging.getLogger("smarthr.interview.analysis")

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="interview-analysis")


def build_input(db: Session, answer: AiInterviewAnswer) -> AnalysisInput:
    """Everything the model is shown for this answer - from the stored rows."""
    session = db.get(AiInterviewSession, answer.session_id)
    interview = db.get(Interview, answer.interview_id)
    application = db.get(Application, interview.application_id) if interview else None
    if session is None or application is None or application.candidate_id != session.candidate_id:
        raise AnalysisError("The answer's interview no longer belongs to its session's candidate.",
                            "binding_mismatch")
    job = db.get(Job, application.job_id)
    if job is None:
        raise AnalysisError("The interview's job no longer exists.", "binding_mismatch")

    earlier = (db.query(AiInterviewAnswer.transcript)
               .filter(AiInterviewAnswer.session_id == answer.session_id,
                       AiInterviewAnswer.question_id == answer.question_id,
                       AiInterviewAnswer.sequence < answer.sequence)
               .order_by(AiInterviewAnswer.sequence)
               .all())

    cv = interview_cv_service.cv_for_candidate(db, session.candidate_id)
    matching = interview_matching_service.matching_for_candidate(db, session.candidate_id, job)
    context = matching.context or {}
    data = AnalysisInput(
        question=answer.question_text,
        transcript=answer.transcript,
        earlier_parts=[row[0] for row in earlier],
        job=interview_context_service.job_context(job, db),
        cv=cv.context if cv.status == interview_cv_service.STATUS_AVAILABLE else None,
        # The score is deliberately NOT passed on: the analysis has nothing to
        # restate and nothing to recalculate.
        matching_skills=list(context.get("matching_skills") or []),
        skill_gaps=list(context.get("skill_gaps") or []),
        matching_available=matching.status == interview_matching_service.STATUS_AVAILABLE,
    )
    # Phase 12: the Analysis Agent's input contract - plain data, no credential
    # or contact-PII key, no token-shaped value. Refused = a stored failure.
    try:
        assert_safe_input(data, "analysis")
    except AgentInputError:
        raise AnalysisError("The analysis input was refused by its contract.", "unsafe_input") from None
    return data


def _existing(db: Session, answer_id: int) -> AiInterviewAnswerAnalysis | None:
    return (db.query(AiInterviewAnswerAnalysis)
            .filter(AiInterviewAnswerAnalysis.answer_id == answer_id)
            .first())


def _store(db: Session, answer_id: int, status: str, analysis: dict | None,
           code: str | None, model: str | None) -> AiInterviewAnswerAnalysis:
    values = {"status": status, "analysis": analysis, "error_code": code, "model": model,
              "analysed_at": datetime.utcnow()}
    for _ in range(2):
        row = _existing(db, answer_id)
        if row is None:
            row = AiInterviewAnswerAnalysis(answer_id=answer_id, **values)
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        try:
            db.commit()
            db.refresh(row)
            return row
        except IntegrityError as exc:
            # The background run and an HR request raced on the first insert;
            # the second pass finds the other one's row and updates it.
            db.rollback()
            last = exc
    raise RuntimeError(f"could not store the analysis ({type(last.orig).__name__})")


def analyse_answer(db: Session, answer_id: int, force: bool = False,
                   provider=None) -> AiInterviewAnswerAnalysis | None:
    """Analyse one stored answer and store the result. None if no such answer.

    A completed analysis is returned as it is unless `force`."""
    answer = db.get(AiInterviewAnswer, answer_id)
    if answer is None:
        return None
    current = _existing(db, answer_id)
    if current is not None and current.status == STATUS_COMPLETED and not force:
        return current

    try:
        result = analyse(build_input(db, answer), provider=provider)
    except AnalysisError as exc:
        logger.info("answer analysis failed: answer=%s code=%s", answer_id, exc.code)
        return _store(db, answer_id, STATUS_FAILED, None, exc.code, None)
    except Exception:
        logger.exception("answer analysis crashed: answer=%s", answer_id)
        db.rollback()
        return _store(db, answer_id, STATUS_FAILED, None, "internal_error", None)

    guards = result.analysis["meta"]["guards"]
    logger.info("answer analysed: answer=%s evidence=%d skills=%d dropped=%d",
                answer_id, len(result.analysis["evidence"]), len(result.analysis["skills_mentioned"]),
                sum(guards.values()))
    return _store(db, answer_id, STATUS_COMPLETED, result.analysis, None, result.model)


def analyse_interview(db: Session, interview_id: int, force: bool = False) -> int:
    """(Re-)analyse every answer of an interview that has no completed
    analysis, or all of them with `force`. Returns how many were attempted."""
    ids = [row[0] for row in (db.query(AiInterviewAnswer.id)
                              .filter(AiInterviewAnswer.interview_id == interview_id)
                              .order_by(AiInterviewAnswer.session_id, AiInterviewAnswer.sequence)
                              .all())]
    attempted = 0
    for answer_id in ids:
        current = _existing(db, answer_id)
        if force or current is None or current.status != STATUS_COMPLETED:
            analyse_answer(db, answer_id, force=True)
            attempted += 1
    return attempted


def _run(answer_id: int) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        analyse_answer(db, answer_id)
    except Exception:
        logger.exception("background answer analysis failed: answer=%s", answer_id)
    finally:
        db.close()


def schedule(answer_id: int) -> None:
    """Analyse a newly stored answer off the request thread. Never raises."""
    try:
        _executor.submit(_run, answer_id)
    except Exception:
        logger.exception("could not schedule answer analysis: answer=%s", answer_id)
