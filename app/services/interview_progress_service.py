"""AI Interview (Phase 9) - the interview's status follows the AI Interview.

    applicant presses Start  -> POST /ai-interview/session
                                (refused while another session is running)
    agent joins the room     -> POST /ai-interview/agent/progress {started}
                                interviews.status: scheduled -> in_progress
    closing line spoken      -> {completed}   in_progress -> completed
    (all questions, or the time limit)
    anything else ends it    -> {ended}       in_progress -> scheduled
    (applicant left, error)

The existing `interviews.status` column is the only state: no column or table
was added. `in_progress` therefore means "an AI Interview is running now", and
an attempt that ends early puts the interview back to `scheduled`, so it can
be started again inside its window. Its answers are kept either way.

**A completed interview cannot be started again** - `completed` is not an
eligible status (`interview_context_service.ineligibility`).

**One running session per interview.** Only the interview's NEWEST binding
may report `started`, so a second Start before the first agent has joined
supersedes the first room (its agent is refused and says it cannot start),
and a Start while an agent is running is refused (`active_session`). An agent
that never reports its end (a crashed worker) stops counting as running once
its binding is past the answer grace period.

Opening the page, listing interviews or a failed session creation changes no
status: only the agent's own reports do, and only through the room binding
every agent call is re-checked against.

**At most `MAX_STARTED_ATTEMPTS` (2) started attempts per interview** (Phase
10). An attempt is a session of the interview whose agent's `started` report
was ACCEPTED - the moment the interview went to in_progress. A session that
was created and never joined, or whose agent was refused (superseded, not
eligible), is not an attempt. `ai_interview_sessions` has no column for that,
so acceptance is recorded as one `audit_logs` row (STATUS_CHANGE /
AiInterviewSession / the session id, no user), written in the SAME
transaction as the status change and never through the best-effort
`record_audit`. `started_attempts()` counts this interview's session rows that
have that row. The limit is checked on Start (`attempts_exhausted`, 409) and
again on the agent's `started` report, so refreshing, a second room or a
session created earlier cannot get a third attempt going. A session that
already started may repeat `started` only while its interview is still
in_progress (a retry); once that attempt has ended, re-joining its room is
refused (`attempt_finished`) rather than becoming a free extra run.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from app.ai.interview import diagnostics as diag
from app.audit import ACTION_STATUS_CHANGE, ENTITY_AI_INTERVIEW_SESSION, ENTITY_INTERVIEW, record_audit
from app.models import AiInterviewSession, AuditLog, Interview
from app.services import interview_context_service
from app.services.interview_answer_service import answer_grace

logger = logging.getLogger("smarthr.interview")

STARTED = "started"
COMPLETED = "completed"
ENDED = "ended"
EVENTS = (STARTED, COMPLETED, ENDED)

#: Started AI Interview attempts allowed per interview.
MAX_STARTED_ATTEMPTS = 2


class ProgressError(Exception):
    """`not_found` (no usable binding), `superseded` (not the newest room),
    `attempts_exhausted` (the interview has used its started attempts),
    `attempt_finished` (this session already started and ended),
    `not_started` (an end report from a session that never started) or
    `invalid_transition` (completed from anything but in_progress)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def newest_binding(db: Session, interview_id: int) -> AiInterviewSession | None:
    return (
        db.query(AiInterviewSession)
        .filter(AiInterviewSession.interview_id == interview_id)
        .order_by(AiInterviewSession.id.desc())
        .first()
    )


def _start_record(session_id_column):
    return exists().where(
        AuditLog.action == ACTION_STATUS_CHANGE,
        AuditLog.entity_type == ENTITY_AI_INTERVIEW_SESSION,
        AuditLog.entity_id == session_id_column,
    )


def started_attempts(db: Session, interview_id: int) -> int:
    """How many of this interview's sessions actually started."""
    return db.query(func.count(AiInterviewSession.id)).filter(
        AiInterviewSession.interview_id == interview_id,
        _start_record(AiInterviewSession.id),
    ).scalar() or 0


def session_started(db: Session, session_id: int) -> bool:
    return bool(db.query(_start_record(session_id)).scalar())


def active_session(db: Session, interview: Interview) -> AiInterviewSession | None:
    """The session whose agent is running this interview now, or None."""
    if (interview.status or "").strip().lower() != "in_progress":
        return None
    newest = newest_binding(db, interview.id)
    if newest is None or newest.expires_at + answer_grace() <= datetime.utcnow():
        return None
    return newest


def lock_interview(db: Session, interview_id: int) -> Interview | None:
    """The interview row, locked until the caller commits - so a Start and an
    agent's report for the same interview cannot interleave."""
    return db.query(Interview).filter(Interview.id == interview_id).with_for_update().first()


def _completed_repeat(db: Session, room_name: str, event: str) -> dict | None:
    """Phase 11.6.4: an end report arriving AFTER this room's session already
    completed the interview (a retry whose first attempt got through, a
    duplicate). `completed` is terminal, so nothing changes - but the answer is
    the truth ("completed"), not a 404 that reads like a failure. Only for the
    session that actually started and is still the newest."""
    if event == STARTED:
        return None
    binding = db.query(AiInterviewSession).filter(AiInterviewSession.room_name == room_name).first()
    if binding is None:
        return None
    interview = db.get(Interview, binding.interview_id)
    newest = newest_binding(db, binding.interview_id)
    if (interview is None or (interview.status or "").strip().lower() != "completed"
            or newest is None or newest.id != binding.id or not session_started(db, binding.id)):
        return None
    logger.info("agent progress: room=%s interview=%s event=%s - already completed, unchanged",
                room_name, binding.interview_id, event)
    diag.emit("backend_progress_accepted", room_name, source="backend", progress_event=event,
              session_id=binding.id, interview_id=binding.interview_id, outcome="unchanged",
              from_status="completed", to_status="completed")
    return {"room_name": room_name, "event": event, "interview_status": "completed", "unchanged": True}


def agent_event(db: Session, room_name: str, event: str) -> dict:
    """Apply one lifecycle report - and, Phase 11.6.5, record the outcome as
    a safe diagnostic (room, session, interview, event, status, code)."""
    ids: dict = {}
    try:
        result = _agent_event(db, room_name, event, ids)
    except ProgressError as error:
        diag.emit("backend_progress_refused", room_name, source="backend", progress_event=event,
                  code=error.code, outcome="refused", **ids)
        raise
    if not result.get("unchanged"):
        diag.emit("backend_progress_accepted", room_name, source="backend", progress_event=event,
                  outcome="accepted", **ids)
    return result


def _agent_event(db: Session, room_name: str, event: str, ids: dict) -> dict:
    """Apply one lifecycle report from the room's agent.

    Phase 11.6.4 transition rules (the interview's status is the only state):
    scheduled -> in_progress (started, newest session, attempt available);
    in_progress -> completed (completed, by the session that started it);
    in_progress -> scheduled (ended early - retriable); completed is terminal.
    A report from a session that never started cannot end or complete
    anything, and "completed" from any status but in_progress is refused.
    """
    # `started` arrives as the agent joins, inside the join window; the end
    # reports arrive when the interview is over, so they get the answers' grace.
    grace = answer_grace() if event != STARTED else timedelta(0)
    resolved = interview_context_service.resolve_binding(db, room_name, grace=grace)
    if resolved is None:
        repeat = _completed_repeat(db, room_name, event)
        if repeat is not None:
            return repeat
        raise ProgressError("not_found", "No interview is bound to this room.")
    binding, _, _ = resolved
    ids.update(session_id=binding.id, interview_id=binding.interview_id)

    interview = lock_interview(db, binding.interview_id)
    newest = newest_binding(db, binding.interview_id)
    if newest is None or newest.id != binding.id:
        db.rollback()
        logger.warning("agent progress refused: room=%s interview=%s superseded",
                       room_name, binding.interview_id)
        raise ProgressError("superseded", "A newer session exists for this interview.")

    current = (interview.status or "").strip().lower()
    is_test = interview_context_service.is_development_test_interview(interview)
    if event != STARTED and not session_started(db, binding.id):
        # A session whose agent never started cannot end or complete anything.
        db.rollback()
        logger.warning("agent progress refused: room=%s interview=%s event=%s from a session that never started",
                       room_name, binding.interview_id, event)
        raise ProgressError("not_started", "This session never started.")
    if event == COMPLETED and current != "in_progress":
        # Only a running interview can complete (scheduled -> completed would
        # skip the run; completed is terminal and handled above).
        db.rollback()
        logger.warning("agent progress refused: room=%s interview=%s completed from %s",
                       room_name, binding.interview_id, current)
        raise ProgressError("invalid_transition", f"Cannot complete an interview that is {current}.")

    already_started = event == STARTED and session_started(db, binding.id)
    if already_started and (interview.status or "").strip().lower() != "in_progress":
        # This attempt ran and ended. Re-joining its room (its join token may
        # still be valid) would dispatch a new agent - a third run for free.
        db.rollback()
        logger.warning("agent progress refused: room=%s interview=%s attempt already finished",
                       room_name, binding.interview_id)
        raise ProgressError("attempt_finished", "This AI Interview attempt has already ended.")
    if event == STARTED and not already_started:
        if not is_test and started_attempts(db, binding.interview_id) >= MAX_STARTED_ATTEMPTS:
            db.rollback()
            logger.warning("agent progress refused: room=%s interview=%s attempts exhausted",
                           room_name, binding.interview_id)
            raise ProgressError("attempts_exhausted",
                                "This interview has used all of its AI Interview attempts.")
        # The attempt's record - in this transaction, so it cannot be lost
        # while the status change survives (see the module docstring).
        db.add(AuditLog(user_id=None, action=ACTION_STATUS_CHANGE,
                        entity_type=ENTITY_AI_INTERVIEW_SESSION, entity_id=binding.id))

    before = (interview.status or "").strip().lower()
    after = {STARTED: "in_progress", COMPLETED: "completed",
             ENDED: "scheduled" if before == "in_progress" else before}[event]
    if is_test and event == ENDED and before == "in_progress":
        after = "TEST"
    ids.update(from_status=before, to_status=after)
    changed = after != before
    if changed:
        interview.status = after
    db.commit()
    if changed:
        record_audit(db, None, ACTION_STATUS_CHANGE, ENTITY_INTERVIEW, binding.interview_id)
    logger.info("agent progress: room=%s interview=%s event=%s status %s -> %s",
                room_name, binding.interview_id, event, before, after)
    return {"room_name": room_name, "event": event, "interview_status": after}
