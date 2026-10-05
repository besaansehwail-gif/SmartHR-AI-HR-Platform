"""AI Interview - HTTP entry points: voice sessions and the agent's context.

    GET  /ai-interview/status       is the voice service configured? (no secrets)
    GET  /ai-interview/interviews   the applicant's own interviews that can be held
    POST /ai-interview/session      {interview_id} -> a short-lived LiveKit token
    POST /ai-interview/agent/plan   questions + Job Context for a room - AGENT ONLY
    POST /ai-interview/agent/cv     the room candidate's CV Context      - AGENT ONLY
    POST /ai-interview/agent/matching  the existing match result, trimmed - AGENT ONLY
    POST /ai-interview/agent/answers   store one accepted answer          - AGENT ONLY
    POST /ai-interview/agent/progress  started / completed / ended        - AGENT ONLY
    GET  /ai-interview/answers/{interview_id}          answers + analyses  - Admin, HR
    POST /ai-interview/answers/{interview_id}/analyse  (re-)run analysis   - Admin, HR
    GET  /ai-interview/report/{interview_id}[?session_id=]  Interview Report - Admin, HR
    GET  /ai-interview/analytics    counts over stored AI Interview data   - Admin, HR

**Its own prefix, `/ai-interview`.** `/interviews/{interview_id}` is the
recruitment scheduling API and is integer-typed; a literal path under it
would have to be ordered around that route, and the two features have
different audiences. Keeping them apart means neither can shadow the other.

Guards:

* `/interviews` and `/session` are **Applicant only** and go through
  `get_current_candidate`, so the candidate comes from the JWT. `/session`
  takes an `interview_id` and optional `language` (`en` / `ar`): the
  backend resolves interview -> application -> job and checks the application
  is the caller's. Somebody else's interview is a 404, exactly like a missing
  one. The browser never names a job.
* `/status` is Applicant, Admin and HR. It reports which LiveKit variables
  are *present* and which models are in use - never a value.

* `/agent/plan` takes **no user login at all**. It is called by the agent
  worker, which has no SmartHR account and must not read the database. The
  worker signs a 2-minute LiveKit-format token with the project secret
  (`app/ai/interview/agent_auth.py`); an applicant cannot mint one, and an
  applicant's own room token is refused because it is not an agent token.
  The response is the ordered MAIN questions (never `evaluation_focus`) and
  the trimmed Job Context of the interview the ROOM was bound to when the
  applicant's session was issued - resolved here, never taken from the worker.
* `/agent/cv` (Phase 5) is the same token, the same room binding and the same
  re-checks, answering with the trimmed CV Context of the candidate whose
  APPLICATION the interview belongs to - their latest CV, parsed by the one
  CV pipeline. It is a separate call only because parsing takes seconds: the
  worker asks for it in the background while the welcome and Q1 play.
* `/agent/matching` (Phase 6) is the same token, binding and re-checks again,
  answering with three fields of SmartHR's EXISTING matching result for the
  room's candidate and job (`screening_service.screen_candidate`): score,
  matching_skills, skill_gaps - or `unavailable` with no context. The
  worker names only the room; candidate, job and application are resolved
  here, and nothing about matching is ever sent to the browser.

* `/agent/answers` (Phase 7) is the same token and the same binding, with a
  grace period after the join window (an interview outlives it). The body
  names the question (id AND number, which must agree with the bank's plan),
  the answer's order and the accepted transcript - and nothing else: extra
  fields such as `candidate_id` or `interview_id` are a 422. Interview and
  candidate come from the binding; the question's words from the bank.
* `/agent/progress` (Phase 9) is the same token and binding: the agent
  reports `started` when it joins (interview -> in_progress), and at the end
  `completed` (-> completed) or `ended` (-> back to scheduled). Only the
  interview's newest room may report; an older one is a 409. The body is the
  event and nothing else.
* `/session` (Phase 9) also refuses, each with its own code: an application
  not at the interview stage (`not_approved`, 409), outside the start window
  (`too_early` / `too_late`, 409), an already completed interview
  (`completed`, 409), a second start while one is running
  (`session_active`, 409) and - Phase 10 - an interview that has used its
  2 started attempts (`attempts_exhausted`, 409). Every refusal body is
  `{"detail": <English message>, "code": <token>}`: `detail` as before, and
  `code` for the page to translate. The same stage and window rules are re-checked on
  every agent call.
* `/answers/{interview_id}` and `/answers/{interview_id}/analyse` (Phase 7)
  are **Admin and HR only**, like `/candidates/` and `/cvs/`. An applicant
  cannot read answers or analyses - their own or anybody's.
* `/report/{interview_id}` (Phase 8) is the same audience: the Interview
  Report, assembled read-only from the stored answers and analyses
  (`interview_report_service`) for ONE session - no model call, no score,
  no decision.

The Question Bank's HR management API is `app/routers/interview_questions.py`.
"""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.hr_intelligence import orchestrator as hr_intelligence
from app.ai.interview import diagnostics as diag
from app.ai.interview.agent_auth import AgentAuthError, verify_agent_token
from app.ai.interview.config import voice_settings
from app.dependencies import ROLE_APPLICANT, get_current_candidate, get_db, require_roles
from app.models import Candidate
from app.services import (
    ai_interview_analytics_service,
    ai_interview_service,
    interview_analysis_service,
    interview_answer_service,
    interview_context_service,
    interview_cv_service,
    interview_matching_service,
    interview_progress_service,
    interview_report_service,
    question_bank_service,
)
from app.services.ai_interview_service import AiInterviewError
from app.services.interview_answer_service import AnswerError, AnswerSubmission

logger = logging.getLogger("smarthr.interview")

router = APIRouter(prefix="/ai-interview", tags=["AI Interview"])

#: Admin, HR and the applicant. Named once so the guard and the docstring
#: cannot drift apart.
STATUS_ROLES = (1, 2, ROLE_APPLICANT)
#: Who may read stored answers and their analysis: HR-owned data.
REVIEW_ROLES = (1, 2)

ERROR_STATUS = {
    "not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    "not_found": status.HTTP_404_NOT_FOUND,
    "completed": status.HTTP_409_CONFLICT,
    "not_approved": status.HTTP_409_CONFLICT,
    "too_early": status.HTTP_409_CONFLICT,
    "too_late": status.HTTP_409_CONFLICT,
    "session_active": status.HTTP_409_CONFLICT,
    "attempts_exhausted": status.HTTP_409_CONFLICT,
}


class SessionRequest(BaseModel):
    """Which of the caller's interviews to hold, and its optional STT language.

    No job, room, candidate or application can be named by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    interview_id: int = Field(gt=0)
    language: Literal["en", "ar"] | None = None


class AgentAnswer(BaseModel):
    """One accepted answer, as the worker sends it. Nothing else is accepted -
    in particular no interview, application, candidate or question text."""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(gt=0)
    question_number: int = Field(ge=1, le=20)
    sequence: int = Field(ge=1, le=interview_answer_service.SEQUENCE_MAX)
    kind: str = Field(min_length=1, max_length=10)
    transcript: str = Field(min_length=1, max_length=interview_answer_service.TRANSCRIPT_MAX)
    answered_at: datetime | None = None


class AgentProgress(BaseModel):
    """One lifecycle report from the agent. Nothing but the event."""

    model_config = ConfigDict(extra="forbid")

    event: str = Field(pattern="^(started|completed|ended)$")


ANSWER_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "invalid": 422,
    "question_mismatch": status.HTTP_409_CONFLICT,
    "sequence_conflict": status.HTTP_409_CONFLICT,
    "not_started": status.HTTP_409_CONFLICT,
}


def _fail(error: AiInterviewError) -> JSONResponse:
    """The refusal as `{"detail": <message>, "code": <token>}` - `detail` as
    FastAPI would send it (the page shows it today), plus the code to translate."""
    return JSONResponse(
        status_code=ERROR_STATUS.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        content={"detail": str(error), "code": error.code},
    )


@router.get("/status", dependencies=[Depends(require_roles(*STATUS_ROLES))])
def voice_status():
    """Whether an applicant could start a voice session right now."""
    return {"phase": 1, **voice_settings().public_status()}


@router.get("/interviews")
def my_interviews(
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """The caller's scheduled / in-progress interviews: id, job title, time."""
    return {"interviews": interview_context_service.my_interviews(candidate, db)}


@router.post("/session")
def start_session(
    payload: SessionRequest,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Mint the applicant's LiveKit token for one of their interviews.

    The response carries the LiveKit server URL and the token - both needed by
    the browser to connect, and neither usable beyond this one room for more
    than a few minutes - plus the job title the page shows.
    """
    try:
        session = ai_interview_service.start_voice_session(
            candidate, payload.interview_id, db, language=payload.language
        )
    except AiInterviewError as error:
        # Phase 11.6.5: which interview, and the refusal code - nothing else.
        diag.emit("backend_session_refused", None, source="backend",
                  interview_id=payload.interview_id, code=error.code, outcome="refused")
        return _fail(error)
    # Start reading the candidate's CV now (off this request), so the
    # interviewer usually has it by the first answer. Nothing CV-related is
    # returned to the browser.
    interview_cv_service.prewarm(db, candidate.id)
    return session


def _agent_room(authorization: str | None) -> str:
    """The room named by a valid agent token - the only way either agent
    endpoint learns which interview it is being asked about."""
    settings = voice_settings()
    if not settings.configured:
        raise HTTPException(status_code=503, detail="The AI Interview voice service is not configured.")

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Agent token required.")
    try:
        return verify_agent_token(token.strip(), settings.api_key, settings.api_secret)
    except AgentAuthError as error:
        logger.warning("agent context refused: %s", error)
        raise HTTPException(status_code=403, detail="Not a valid agent token.") from None


@router.post("/agent/plan")
def agent_plan(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """The questions and Job Context for one interview room - for the agent only.

    Questions: deterministic from the Question Bank, active main questions by
    (position, id). Job: resolved from the room's binding (room -> interview
    -> application -> job), re-checked now; an unbound, expired or no longer
    eligible room is a 404 and the interview does not go ahead. The room is
    echoed back so the agent can see the answer is for the room it asked about.
    """
    room_name = _agent_room(authorization)
    plan_context = interview_context_service.plan_context_for_room(db, room_name)
    if plan_context is None:
        raise HTTPException(status_code=404, detail="No interview is bound to this room.")
    job, language = plan_context

    try:
        questions = question_bank_service.interview_plan(
            db, language=question_bank_service.question_language(language)
        )
    except question_bank_service.QuestionBankError as error:
        if error.code == "translation_missing":
            raise HTTPException(
                status_code=503,
                detail="Interview questions are not available in the selected language.",
            ) from None
        raise
    logger.info("agent plan issued: room=%s job=%s questions=%d",
                room_name, job["job_id"], len(questions))
    return {
        "room_name": room_name,
        "questions": questions,
        "total": len(questions),
        "job": job,
        "language": language,
    }


@router.post("/agent/cv")
def agent_cv(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """The CV Context for one interview room - for the agent only.

    The candidate is the one the room's interview -> application points at,
    re-proved on every call (`resolve_room`); the worker names only the room.
    `status` is `available` (with `context`), `none` (no CV on file) or
    `unavailable` (a CV exists but could not be read or analysed) - the
    interview goes ahead in the last two cases, without CV facts.
    """
    room_name = _agent_room(authorization)
    resolved = interview_context_service.resolve_room(db, room_name)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No interview is bound to this room.")
    _, _, candidate_id = resolved

    result = interview_cv_service.cv_for_candidate(db, candidate_id)
    logger.info(
        "agent CV context: room=%s status=%s code=%s sections=%d",
        room_name, result.status, result.code, len(result.context or {}),
    )
    return {"room_name": room_name, "cv": {"status": result.status, "context": result.context}}


@router.post("/agent/matching")
def agent_matching(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """The Matching Context for one interview room - for the agent only.

    Candidate and job are the ones the room's interview -> application points
    at, re-proved on every call (`resolve_room`). The result is SmartHR's
    existing HR matching for that pair, not a new calculation; `status` is
    `available` (with `context`: score, matching_skills, skill_gaps) or
    `unavailable` (no context - the interview goes ahead without it).
    """
    room_name = _agent_room(authorization)
    resolved = interview_context_service.resolve_room(db, room_name)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No interview is bound to this room.")
    _, job, candidate_id = resolved

    result = interview_matching_service.matching_for_candidate(db, candidate_id, job)
    context = result.context or {}
    logger.info(
        "agent matching context: room=%s status=%s code=%s matching=%d gaps=%d",
        room_name, result.status, result.code,
        len(context.get("matching_skills", [])), len(context.get("skill_gaps", [])),
    )
    return {"room_name": room_name, "matching": {"status": result.status, "context": result.context}}


@router.post("/agent/answers")
def agent_answer(
    payload: AgentAnswer,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Store one accepted applicant answer for the room's interview - agent only.

    The room comes from the agent token; interview and candidate from its
    binding (re-checked, with a grace period after the join window). The
    question must be the Question Bank plan's question at that number, and
    its stored text is the bank's. A retry of the same answer is 200 with
    `created: false`; a different answer under a used `sequence` is 409.
    A new answer is analysed in the background.
    """
    room_name = _agent_room(authorization)
    try:
        row, created = interview_answer_service.record_answer(db, room_name, AnswerSubmission(
            question_id=payload.question_id,
            question_number=payload.question_number,
            sequence=payload.sequence,
            kind=payload.kind,
            transcript=payload.transcript,
            answered_at=payload.answered_at,
        ))
    except AnswerError as error:
        # Phase 11.6.5: the code and the numbers - never the transcript.
        diag.emit("backend_answer_refused", room_name, source="backend", code=error.code,
                  sequence=payload.sequence, question=payload.question_number, outcome="refused")
        raise HTTPException(status_code=ANSWER_ERROR_STATUS.get(error.code, 422), detail=str(error)) from None
    diag.emit("backend_answer_stored", room_name, source="backend", session_id=row.session_id,
              interview_id=row.interview_id, sequence=row.sequence, question=row.question_number,
              created=created, outcome="accepted" if created else "unchanged")
    if created:
        interview_analysis_service.schedule(row.id)
    return {"room_name": room_name, "answer_id": row.id, "sequence": row.sequence, "created": created}


@router.post("/agent/progress")
def agent_progress(
    payload: AgentProgress,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """The room's agent reports that its interview started, completed, or
    ended early - the only way `interviews.status` follows an AI Interview."""
    room_name = _agent_room(authorization)
    try:
        return interview_progress_service.agent_event(db, room_name, payload.event)
    except interview_progress_service.ProgressError as error:
        code = 404 if error.code == "not_found" else 409
        raise HTTPException(status_code=code, detail=str(error)) from None


@router.get("/answers/{interview_id}", dependencies=[Depends(require_roles(*REVIEW_ROLES))])
def interview_answers(interview_id: int, db: Session = Depends(get_db)):
    """The stored AI Interview answers of one interview, in order, with each
    answer's analysis - for review. Not a decision and not a score."""
    result = interview_answer_service.answers_for_interview(db, interview_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Interview not found.")
    return result


@router.post("/answers/{interview_id}/analyse", dependencies=[Depends(require_roles(*REVIEW_ROLES))])
def analyse_interview_answers(interview_id: int, force: bool = False, db: Session = Depends(get_db)):
    """(Re-)run the analysis of an interview's answers: those with no completed
    analysis, or every one with `force=true`. Returns the updated answers."""
    if interview_answer_service.answers_for_interview(db, interview_id) is None:
        raise HTTPException(status_code=404, detail="Interview not found.")
    attempted = interview_analysis_service.analyse_interview(db, interview_id, force=force)
    logger.info("answer analysis requested: interview=%s attempted=%d force=%s",
                interview_id, attempted, force)
    return {"attempted": attempted, **interview_answer_service.answers_for_interview(db, interview_id)}


@router.get("/analytics", dependencies=[Depends(require_roles(*REVIEW_ROLES))])
def interview_analytics(db: Session = Depends(get_db)):
    """AI Interview analytics (Phase 11.5.3) - counts over the stored
    sessions, answers and analyses. Read-only, no model call; no transcript,
    no candidate data, no score, rating or decision."""
    return ai_interview_analytics_service.interview_analytics(db)


@router.post("/intelligence/{interview_id}", dependencies=[Depends(require_roles(*REVIEW_ROLES))])
def interview_intelligence(interview_id: int, analyse: bool = True, session_id: int | None = None,
                           db: Session = Depends(get_db)):
    """Phase 12 - run the post-interview HR-intelligence roles, in order:
    Analysis (answers not yet analysed; `analyse=false` skips it), Report
    (a readable brief of the stored report, no model) and Recruitment (an
    explanation of the existing matching result, no score, no model). Admin
    and HR only. Never changes the interview's status or its answers; a
    failing role is reported with a code and the others still run."""
    try:
        return hr_intelligence.run_post_interview(db, interview_id, analyse=analyse, session_id=session_id)
    except hr_intelligence.IntelligenceError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.get("/report/{interview_id}", dependencies=[Depends(require_roles(*REVIEW_ROLES))])
def interview_report(interview_id: int, session_id: int | None = None, db: Session = Depends(get_db)):
    """The Interview Report for one AI Interview session of an interview.

    Without `session_id`: the latest session that has answers; an interview
    with none is a valid report with `meta.state = "no_answers"`. A
    `session_id` that is not one of THIS interview's answered sessions is a
    404, like an unknown interview. Read-only: built from what Phase 7
    stored, with no model call. Never a score or a decision.
    """
    try:
        return interview_report_service.interview_report(db, interview_id, session_id)
    except interview_report_service.ReportError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
