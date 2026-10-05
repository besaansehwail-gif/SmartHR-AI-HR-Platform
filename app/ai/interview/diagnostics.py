"""Safe structured diagnostics for one AI Interview session (Phase 11.6.5).

One line per lifecycle event, on the `smarthr.interview.diag` logger:

    diag {"event":"answer_persisted","n":14,"question":2,"room":"smarthr-ai-interview-...",
          "sequence":3,"source":"worker","t_ms":48211}

**Correlation.** The room name is the key. The worker only knows the room (it
never reads the database); the backend's events carry the same room plus the
`session_id` (the `ai_interview_sessions` row) and `interview_id`, so
`grep <room>` over both processes' logs follows one session end to end. `n`
is the worker's per-room event counter and `t_ms` the time since the room's
first event - enough to order events and to time a turn.

**What can be logged is decided here, not at the call site.** `emit()` keeps
only the fields in `FIELDS`, and each field has a validator: numbers must be
plain ints, and every string field is a closed vocabulary (states, outcomes,
categories, codes) or a strict pattern (the room name, an exception CLASS
name). Anything else - a transcript passed by mistake, an email, a token, an
exception message - is replaced by "redacted" before the line is written.
There is no free-text field, so there is nowhere for speech, PII, prompts,
model output or credentials to go.

Nothing here decides anything: it observes the existing state machine and
clients. `emit()` never raises.
"""

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger("smarthr.interview.diag")

#: The record is also attached to the log record under this attribute, so a
#: handler (or a test) can read it without parsing the line.
RECORD_ATTRIBUTE = "smarthr_diag"
REDACTED = "redacted"

EVENTS = frozenset({
    # worker - session lifecycle
    "job_received", "session_started", "session_start_refused", "plan_received",
    "plan_unavailable", "context_received", "interviewer_joined", "applicant_joined",
    "applicant_left", "microphone_ready", "microphone_lost", "reconnecting", "reconnected",
    "room_disconnected",
    # worker - optional sampled camera context (Stage 5)
    "video_track_detected", "video_stream_started", "video_stream_failed",
    "video_track_disconnected", "image_attachment_failed",
    # worker - the conversation
    "state_changed", "state_error", "interviewer_speaking", "interviewer_listening",
    "interviewer_thinking", "turn_started", "applicant_away", "stt_final", "turn_finalized",
    "turn_ignored", "turn_merged", "processing_started", "turn_decided",
    "followup_decision_started", "followup_decision_completed", "adaptive_selection_started",
    "adaptive_selection_completed", "question_spoken", "reply_not_heard", "interruption",
    "silence_nudge", "time_limit_reached", "pipeline_error", "llm_error", "turn_classified",
    "stt_turn", "llm_reply", "reply_started", "speech_during_welcome",
    # worker - answers and progress
    "answer_committed", "answer_persisted", "answer_retry", "answer_refused", "answer_failed",
    "answer_drain_timeout", "answers_summary", "progress_accepted", "progress_retry",
    "progress_refused", "progress_failed",
    # worker - the end
    "interview_ending", "interview_finished", "session_closed", "interview_completed",
    "interview_ended",
    # backend
    "backend_session_created", "backend_session_refused", "backend_progress_accepted",
    "backend_progress_refused", "backend_answer_stored", "backend_answer_refused",
})

CATEGORIES = frozenset({
    "connection_error", "microphone_error", "stt_error", "llm_error", "tts_error",
    "backend_error", "state_error", "answer_persistence_error", "progress_report_error",
    "unknown_error",
})

STATES = frozenset({"waiting", "intro", "asking", "listening", "processing", "follow_up_decision",
                    "adaptive_selection", "speaking", "ending", "completed"})
AGENT_STATES = frozenset({"initializing", "idle", "listening", "thinking", "speaking"})
OUTCOMES = frozenset({"accepted", "refused", "failed", "delivered", "unchanged", "ask", "move_on",
                      "chosen", "bank_order", "available", "none", "unavailable"})
OPERATIONS = frozenset({"answer", "progress_started", "progress_completed", "progress_ended",
                        "plan", "cv", "matching", "follow_up", "adaptive", "classify"})
REASONS = frozenset({"last_question", "time_limit", "no_plan", "start_refused", "error",
                     "job_shutdown", "participant_disconnected", "user_initiated",
                     "task_completed", "closed", "other"})
KINDS = frozenset({"answer", "short", "filler", "empty"})
DIRECTIVES = frozenset({"advance", "elaborate", "finish", "follow_up", "free_reply",
                        "side_reply", "repeat", "reask", "skip"})
#: The utterance classifier's labels, as logged (lowercase).
CLASSIFICATIONS = frozenset({"answer", "side_question", "repeat_request", "noise_or_incomplete"})
#: Why a turn was judged noise without asking a model (turn_policy.noise_reason).
NOISE_REASONS = frozenset({"empty", "filler", "low_confidence", "too_short", "dangling"})
INTERVIEW_STATUSES = frozenset({"scheduled", "in_progress", "completed", "cancelled"})
PROGRESS_EVENTS = frozenset({"started", "completed", "ended"})
CODES = frozenset({
    # transport
    "timeout", "network", "not_configured", "model_error", "unusable", "other", "no_reply",
    # backend refusals (progress, answers, session start)
    "not_found", "superseded", "attempts_exhausted", "attempt_finished", "not_started",
    "invalid_transition", "invalid", "question_mismatch", "sequence_conflict",
    "session_active", "completed", "not_approved", "too_early", "too_late",
})
SOURCES = frozenset({"worker", "backend"})

_ROOM = re.compile(r"smarthr-ai-interview-[A-Za-z0-9-]{1,48}")
_HTTP = re.compile(r"http_[1-5][0-9]{2}")
#: An exception CLASS name - CamelCase, no spaces, digits or underscores - so
#: a message can never be passed off as one.
_ERROR_TYPE = re.compile(r"[A-Z][A-Za-z]{1,59}")


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10 ** 12


def _bool(value: Any) -> bool:
    return isinstance(value, bool)


def _one_of(allowed: frozenset):
    return lambda value: isinstance(value, str) and value in allowed


def _code(value: Any) -> bool:
    return isinstance(value, str) and (value in CODES or _HTTP.fullmatch(value) is not None)


def _pattern(regex: re.Pattern):
    return lambda value: isinstance(value, str) and regex.fullmatch(value) is not None


#: Every field a diagnostic line may carry, and what its value must be.
FIELDS = {
    "event": _one_of(EVENTS),
    "source": _one_of(SOURCES),
    "room": _pattern(_ROOM),
    "n": _int, "t_ms": _int, "duration_ms": _int, "turn": _int, "latency_ms": _int,
    "confidence_pct": _int, "speech_ms": _int, "pieces": _int,
    "session_id": _int, "interview_id": _int,
    "question": _int, "total": _int, "question_id": _int, "sequence": _int,
    "attempt": _int, "attempts": _int, "words": _int, "questions": _int, "follow_ups": _int,
    "delivered": _int, "refused": _int, "undelivered": _int, "pending": _int,
    "state": _one_of(STATES), "agent_state": _one_of(AGENT_STATES),
    "category": _one_of(CATEGORIES), "code": _code, "error_type": _pattern(_ERROR_TYPE),
    "outcome": _one_of(OUTCOMES), "operation": _one_of(OPERATIONS), "reason": _one_of(REASONS),
    "kind": _one_of(KINDS), "directive": _one_of(DIRECTIVES), "noise_reason": _one_of(NOISE_REASONS),
    "classification": _one_of(CLASSIFICATIONS),
    "from_status": _one_of(INTERVIEW_STATUSES), "to_status": _one_of(INTERVIEW_STATUSES),
    "progress_event": _one_of(PROGRESS_EVENTS),
    "recoverable": _bool, "fallback": _bool, "created": _bool, "completed_normally": _bool,
}


class _Room:
    __slots__ = ("started", "n", "once")

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.n = 0
        self.once: set[str] = set()


#: Per-room ordering state for the worker (one job process = one room).
_rooms: dict[str, _Room] = {}


def sanitize(fields: dict[str, Any]) -> dict[str, Any]:
    """Only known fields; each value valid for its field, else "redacted"."""
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        check = FIELDS.get(key)
        if check is None or value is None:
            continue                       # unknown field: dropped, never logged
        clean[key] = value if check(value) else REDACTED
    return clean


def emit(event: str, room: str | None = None, *, once: bool = False, source: str = "worker",
         **fields: Any) -> dict | None:
    """Log one diagnostic event. Returns the record written (None if a
    `once` event was already emitted for this room). Never raises."""
    try:
        if event not in EVENTS:
            logger.warning("diag rejected an unknown event name")
            return None
        record: dict[str, Any] = {"event": event, "source": source, "room": room, **fields}
        if source == "worker" and isinstance(room, str):
            state = _rooms.get(room)
            if state is None:
                state = _rooms[room] = _Room()
            if once:
                if event in state.once:
                    return None
                state.once.add(event)
            state.n += 1
            record["n"] = state.n
            record["t_ms"] = int((time.monotonic() - state.started) * 1000)
        record = sanitize(record)
        logger.info("diag %s", json.dumps(record, sort_keys=True, separators=(",", ":")),
                    extra={RECORD_ATTRIBUTE: record})
        return record
    except Exception:  # diagnostics must never break an interview
        return None


def release(room: str) -> None:
    """Forget a room's ordering state (end of the job)."""
    _rooms.pop(room, None)


def reset() -> None:
    """Tests only."""
    _rooms.clear()


def elapsed_ms(since: float) -> int:
    return max(0, int((time.monotonic() - since) * 1000))


def http_code(status: int) -> str:
    return f"http_{status}"


def exception_code(exc: BaseException) -> str:
    """timeout / network / other - from the exception's TYPE, never its message."""
    names = [cls.__name__ for cls in type(exc).__mro__]
    if any("Timeout" in name for name in names):
        return "timeout"
    if any(name in ("OSError", "ClientError", "ConnectionError") or "Connect" in name for name in names):
        return "network"
    return "other"


def error_type(exc: BaseException | None) -> str | None:
    return type(exc).__name__ if exc is not None else None


def pipeline_category(source: Any, error: Any) -> str:
    """The voice pipeline component an `error` event came from."""
    names = f"{type(source).__name__} {type(error).__name__}".upper()
    if "STT" in names:
        return "stt_error"
    if "TTS" in names:
        return "tts_error"
    if "LLM" in names:
        return "llm_error"
    return "unknown_error"


def close_reason(reason: Any) -> str:
    """LiveKit's CloseReason (enum or string) as one of REASONS."""
    value = getattr(reason, "value", reason)
    value = str(value).rsplit(".", 1)[-1].lower() if value is not None else "closed"
    return value if value in REASONS else "other"
