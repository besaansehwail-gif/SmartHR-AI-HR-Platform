"""AI Interview (Phase 7) - storing the applicant's accepted answers.

    worker --(agent token for ONE room)--> POST /ai-interview/agent/answers
        {question_id, question_number, sequence, kind, transcript, answered_at}
    -> resolve_binding(room)        the session row, its interview and job,
                                    re-checked exactly like every agent call
    -> the Question Bank plan       question_number -> question_id must agree,
                                    and question_text is taken from the BANK
    -> ai_interview_answers         one row per (session, sequence), never updated

What the worker may say is deliberately small: which question (as the id AND
its 1-based number, which must agree with the plan the backend itself issued),
the answer's order, and the transcript it accepted. It cannot name an
interview, an application or a candidate - those come from the room binding -
and it cannot supply the question's words: `question_text` is copied from the
bank row, so a question GPT-4o might have phrased differently can never be
stored as the question that was answered.

**Duplicates.** The worker numbers answers in the order they were committed
(`sequence`). UNIQUE (session_id, sequence) means a retried request cannot
create a second row: the same content again is answered 200 with the stored
row (`created: false`); DIFFERENT content under a sequence already used is a
409, so a late or partial turn can never overwrite a valid answer.

**Timing.** `answered_at` is the worker's UTC time of acceptance; one that is
missing or implausible (before the session existed, or in the future) is
replaced by the server's clock rather than trusted. `created_at` is always the
server's. Both are `datetime.utcnow()` - Postgres `now()` is local time here.

Nothing here logs a transcript: ids, numbers and word counts only.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.interview.config import interview_setting
from app.models import (
    AiInterviewAnswer,
    AiInterviewAnswerAnalysis,
    AiInterviewSession,
    Interview,
    InterviewQuestion,
)
from app.services import interview_context_service, question_bank_service

logger = logging.getLogger("smarthr.interview.answers")

ANSWER_KINDS = ("answer", "short", "filler")
TRANSCRIPT_MAX = 20000
SEQUENCE_MAX = 200

#: The worker's own session limit (SMARTHR_INTERVIEW_MAX_SECONDS, default
#: 600 - `controller.DEFAULT_MAX_SECONDS`, not imported because that module
#: pulls in livekit-agents), plus time for the closing line and the final
#: flush. Answers are accepted this long after the JOIN window closes.
DEFAULT_MAX_SECONDS = 600
FLUSH_MARGIN_S = 300
#: A worker clock this far out is not believed.
CLOCK_SKEW_S = 120


class AnswerError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnswerSubmission:
    question_id: int
    question_number: int
    sequence: int
    kind: str
    transcript: str
    answered_at: datetime | None = None


def answer_grace() -> timedelta:
    raw = interview_setting("SMARTHR_INTERVIEW_MAX_SECONDS")
    try:
        seconds = int(raw) if raw else DEFAULT_MAX_SECONDS
    except ValueError:
        seconds = DEFAULT_MAX_SECONDS
    return timedelta(seconds=max(seconds, 1) + FLUSH_MARGIN_S)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _answered_at(sub: AnswerSubmission, binding: AiInterviewSession, now: datetime) -> datetime:
    at = _utc_naive(sub.answered_at)
    skew = timedelta(seconds=CLOCK_SKEW_S)
    if at is None or at < binding.created_at - skew or at > now + skew:
        return now
    return at


def _same(row: AiInterviewAnswer, sub: AnswerSubmission) -> bool:
    return (row.question_id == sub.question_id and row.question_number == sub.question_number
            and row.transcript == sub.transcript)


def record_answer(db: Session, room_name: str, sub: AnswerSubmission) -> tuple[AiInterviewAnswer, bool]:
    """Store one accepted answer for the room's interview.

    Returns (row, created). Raises AnswerError: `not_found` (no usable binding
    - unbound, expired, or the interview is no longer held), `invalid`
    (kind / transcript / sequence), `question_mismatch` (not the plan's
    question at that number), `sequence_conflict` (that sequence already
    holds a different answer).
    """
    if sub.kind not in ANSWER_KINDS:
        raise AnswerError("Unknown answer kind.", "invalid")
    if not sub.transcript.strip() or len(sub.transcript) > TRANSCRIPT_MAX:
        raise AnswerError("The transcript is empty or too long.", "invalid")
    if not 1 <= sub.sequence <= SEQUENCE_MAX:
        raise AnswerError("Sequence out of range.", "invalid")

    resolved = interview_context_service.resolve_binding(db, room_name, grace=answer_grace())
    if resolved is None:
        raise AnswerError("No interview is bound to this room.", "not_found")
    binding, interview, _job = resolved

    # Phase 11.6.4: only a session whose agent actually STARTED can hold
    # answers - a superseded room that never started cannot. (Lazy import:
    # interview_progress_service imports this module.)
    from app.services.interview_progress_service import session_started
    if not session_started(db, binding.id):
        logger.warning("answer refused: room=%s session never started", room_name)
        raise AnswerError("This AI Interview session never started.", "not_started")

    question_text = _plan_question_text(
        db, binding.id, sub, language=question_bank_service.question_language(binding.language)
    )
    if question_text is None:
        logger.warning("answer refused: room=%s question %s/%s is not the plan's", room_name,
                       sub.question_number, sub.question_id)
        raise AnswerError("That is not the interview's question at that number.", "question_mismatch")

    existing = _by_sequence(db, binding.id, sub.sequence)
    if existing is not None:
        return _existing(existing, sub, room_name)

    now = datetime.utcnow()
    row = AiInterviewAnswer(
        session_id=binding.id,
        interview_id=interview.id,
        question_id=sub.question_id,
        question_number=sub.question_number,
        question_text=question_text,
        sequence=sub.sequence,
        answer_kind=sub.kind,
        transcript=sub.transcript,
        word_count=len(sub.transcript.split()),
        answered_at=_answered_at(sub, binding, now),
        created_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Two copies of one request raced past the lookup; the constraint
        # let exactly one in.
        db.rollback()
        existing = _by_sequence(db, binding.id, sub.sequence)
        if existing is None:
            raise
        return _existing(existing, sub, room_name)

    db.refresh(row)
    logger.info("answer stored: room=%s interview=%s seq=%s question %s (id=%s) kind=%s words=%s",
                room_name, interview.id, row.sequence, row.question_number, row.question_id,
                row.answer_kind, row.word_count)
    return row, True


def _plan_question_text(
    db: Session, session_id: int, sub: AnswerSubmission, *, language: str = "en"
) -> str | None:
    """The bank text of the question this answer names - or None when the
    question does not belong at that number in THIS session.

    `question_number` is the order the applicant heard ("Question N of M").
    Up to Phase 11.1 that was always the plan position; since Phase 11.2 the
    next main question may be chosen adaptively, so the rule is consistency,
    not position:

    * the id is a MAIN question of the current plan, or the plan's
      predefined follow-up of one (Phase 11.1);
    * the number is within the plan (1..its length);
    * within this session a main question keeps ONE number and a number holds
      ONE main question - so a main question is never answered under two
      numbers (never revisited) and two main questions never share one;
    * a follow-up sits under the number of its own main question.

    Without an adaptive choice the worker sends plan order, so what is
    stored is exactly what it was; the backend itself no longer insists that
    number N is the plan's Nth question - only on the consistency above.
    """
    plan = question_bank_service.interview_plan(db, language=language)
    if not 1 <= sub.question_number <= len(plan):
        return None
    mains = {p["id"]: p for p in plan}
    parents = {p["follow_up"]["id"]: p["id"] for p in plan if p.get("follow_up")}
    if sub.question_id in mains:
        main_id, text = sub.question_id, mains[sub.question_id]["question_text"]
    elif sub.question_id in parents:
        main_id = parents[sub.question_id]
        text = mains[main_id]["follow_up"]["question_text"]
    else:
        return None

    number_of: dict[int, int] = {}
    main_at: dict[int, int] = {}
    for qid, number in (db.query(AiInterviewAnswer.question_id, AiInterviewAnswer.question_number)
                        .filter(AiInterviewAnswer.session_id == session_id,
                                AiInterviewAnswer.sequence != sub.sequence).all()):
        owner = qid if qid in mains else parents.get(qid)
        if owner is not None:
            number_of.setdefault(owner, number)
            main_at.setdefault(number, owner)
    if number_of.get(main_id, sub.question_number) != sub.question_number:
        return None      # this main question already has another number
    if main_at.get(sub.question_number, main_id) != main_id:
        return None      # that number already belongs to another main question
    return text


def _by_sequence(db: Session, session_id: int, sequence: int) -> AiInterviewAnswer | None:
    return (db.query(AiInterviewAnswer)
            .filter(AiInterviewAnswer.session_id == session_id, AiInterviewAnswer.sequence == sequence)
            .first())


def _existing(row: AiInterviewAnswer, sub: AnswerSubmission, room_name: str):
    if _same(row, sub):
        logger.info("answer already stored: room=%s seq=%s (retry)", room_name, row.sequence)
        return row, False
    logger.warning("answer refused: room=%s seq=%s already holds a different answer",
                   room_name, row.sequence)
    raise AnswerError("That answer number is already recorded.", "sequence_conflict")


# --- reading (HR) ---------------------------------------------------------------------

def answer_view(row: AiInterviewAnswer, analysis: AiInterviewAnswerAnalysis | None,
                question_type: str | None = None) -> dict[str, Any]:
    return {
        "answer_id": row.id,
        "sequence": row.sequence,
        "question_id": row.question_id,
        "question_number": row.question_number,
        "question_text": row.question_text,
        # Phase 11.1: "main" or "follow_up", read from the Question Bank row
        # the answer's question_id points at (no column was added for it).
        "question_type": question_type or "main",
        "answer_kind": row.answer_kind,
        "transcript": row.transcript,
        "word_count": row.word_count,
        "answered_at": row.answered_at.isoformat(),
        "analysis": analysis_view(analysis),
    }


def analysis_view(analysis: AiInterviewAnswerAnalysis | None) -> dict[str, Any] | None:
    if analysis is None:
        return {"status": "pending"}
    return {
        "status": analysis.status,
        "error_code": analysis.error_code,
        "model": analysis.model,
        "analysed_at": analysis.analysed_at.isoformat(),
        "result": analysis.analysis,
    }


def answers_for_interview(db: Session, interview_id: int) -> dict[str, Any] | None:
    """Every AI Interview session held for an interview, with its answers in
    order and each answer's analysis. None when the interview does not exist."""
    if db.get(Interview, interview_id) is None:
        return None
    sessions = (db.query(AiInterviewSession)
                .filter(AiInterviewSession.interview_id == interview_id)
                .order_by(AiInterviewSession.created_at, AiInterviewSession.id)
                .all())
    rows = (db.query(AiInterviewAnswer, AiInterviewAnswerAnalysis)
            .outerjoin(AiInterviewAnswerAnalysis, AiInterviewAnswerAnalysis.answer_id == AiInterviewAnswer.id)
            .filter(AiInterviewAnswer.interview_id == interview_id)
            .order_by(AiInterviewAnswer.session_id, AiInterviewAnswer.sequence)
            .all())
    ids = {answer.question_id for answer, _ in rows}
    types = dict(db.query(InterviewQuestion.id, InterviewQuestion.question_type)
                 .filter(InterviewQuestion.id.in_(ids)).all()) if ids else {}
    by_session: dict[int, list] = {}
    for answer, analysis in rows:
        by_session.setdefault(answer.session_id, []).append(
            answer_view(answer, analysis, types.get(answer.question_id)))
    return {
        "interview_id": interview_id,
        "label": "AI Interview answers - for review",
        "is_hiring_decision": False,
        "sessions": [
            {"session_id": s.id, "started_at": s.created_at.isoformat(),
             "answers": by_session.get(s.id, [])}
            for s in sessions
            if s.id in by_session
        ],
    }
