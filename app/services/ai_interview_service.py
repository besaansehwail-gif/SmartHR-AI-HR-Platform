"""AI Interview - the backend half: who may join, and with what token.

The browser never holds a LiveKit secret. It asks SmartHR for a session; SmartHR
checks the JWT (role 5, linked applicant profile), then mints a **LiveKit
access token** signed with the project secret. That token is the only
credential the browser gets, and it is narrow on purpose:

* **one room** - `room_join` for a single, randomly named room;
* **microphone + camera (Stage 4A)** - `can_publish_sources=["microphone", "camera"]`, so screen
  share is refused by LiveKit itself, not just hidden in the UI;
* **no data publishing** - the page only needs to receive the transcript;
* **short-lived** - usable to join for `token_ttl_minutes` (default 10);
* **dispatches the interviewer** - the token's room configuration names
  `AGENT_NAME`, so LiveKit sends the worker into exactly this room.

**Nothing personal goes into LiveKit.** The identity is `applicant-<id>`,
the display name is the word "Applicant", and neither the token nor the room
carries metadata. No name, email, CV or job reaches LiveKit's servers.

**Phase 4: a session is for ONE interview.** The browser names an
`interview_id` - never a job. `interview_context_service` resolves it through
`applications` to the caller's own candidate row (somebody else's id is a
404, like a missing one), and the random room is bound to that interview in
`ai_interview_sessions`. The worker later asks the backend for the room's
Job Context; it is never carried by LiveKit.

**Phase 9: whether it may start now.** The interview must be open, approved
by HR (the application at the `interview` stage) and inside its start window,
no other session of it may be running, and it may not have used its
`MAX_STARTED_ATTEMPTS` started attempts (`interview_progress_service`).
Each refusal has its own code and a message the page shows as it is. Nothing
here changes the interview's status - the agent reports that once it has
actually joined.
"""

import logging
import secrets
from datetime import timedelta

from livekit import api

from app.audit import ACTION_STATUS_CHANGE, ENTITY_INTERVIEW, record_audit
from app.ai.interview import diagnostics as diag
from app.ai.interview.agent_auth import ROOM_PREFIX as _ROOM_PREFIX
from app.ai.interview.config import VoiceSettings, voice_settings
from sqlalchemy.orm import Session

from app.models import Candidate
from app.services import interview_context_service, interview_progress_service

logger = logging.getLogger("smarthr.interview")

#: One definition, shared with the agent-token check (`agent_auth.py`).
ROOM_PREFIX = _ROOM_PREFIX
PUBLISH_SOURCES = ["microphone", "camera"]


class AiInterviewError(Exception):
    """A refusal with a machine-readable `code` the router maps to a status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def new_room_name() -> str:
    """Random and unguessable: a room name is not a secret, but there is no
    reason to make one predictable from an id."""
    return f"{ROOM_PREFIX}{secrets.token_hex(8)}"


def participant_identity(candidate: Candidate) -> str:
    return f"applicant-{candidate.id}"


def mint_applicant_token(
    settings: VoiceSettings,
    room_name: str,
    identity: str,
) -> str:
    """The LiveKit JWT for one applicant in one room."""
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_publish_sources=PUBLISH_SOURCES,
        can_subscribe=True,
        can_publish_data=False,
    )

    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)],
    )

    return (
        api.AccessToken(settings.api_key, settings.api_secret)
        .with_identity(identity)
        .with_name("Applicant")
        .with_grants(grants)
        .with_room_config(room_config)
        .with_ttl(timedelta(minutes=settings.token_ttl_minutes))
        .to_jwt()
    )


def _require_configured(settings: VoiceSettings) -> None:
    if not settings.configured:
        raise AiInterviewError(
            "not_configured",
            "The AI Interview voice service is not configured on this server. "
            "Missing: " + ", ".join(settings.missing) + ".",
        )


def start_voice_session(
    candidate: Candidate,
    interview_id: int,
    db: Session,
    settings: VoiceSettings | None = None,
    language: str | None = None,
) -> dict:
    """A voice room for one of the caller's own interviews.

    Ownership first (404 for anything not theirs or not scheduled), then a
    fresh room, then the room -> interview binding the agent's context lookup
    reads. The response names the job title - the only job field the page
    shows - and nothing else about the application.
    """
    settings = settings or voice_settings()
    _require_configured(settings)

    ctx = interview_context_service
    now = ctx.local_now()
    interview, job, reason = ctx.check_interview(db, candidate.id, interview_id, now)
    if reason == ctx.COMPLETED and interview is not None and ctx.is_development_test_interview(interview):
        interview = interview_progress_service.lock_interview(db, interview.id)
        if interview is not None:
            interview.status = "TEST"
            db.commit()
            record_audit(db, None, ACTION_STATUS_CHANGE, ENTITY_INTERVIEW, interview.id)
        interview, job, reason = ctx.check_interview(db, candidate.id, interview_id, now)
    if reason:
        raise _refusal(reason, interview)

    # Locked until bind_room commits, so two Starts - or a Start and the
    # running agent's report - cannot both see "nothing running".
    interview = interview_progress_service.lock_interview(db, interview.id)
    if interview_progress_service.active_session(db, interview) is not None:
        db.rollback()
        raise AiInterviewError(
            "session_active",
            "An AI Interview session for this interview is already running. "
            "Close it before starting another.",
        )
    # Phase 10: only STARTED attempts count, and the agent's start is checked
    # against the same limit - so extra rooms made here cannot exceed it.
    used = interview_progress_service.started_attempts(db, interview.id)
    is_test = ctx.is_development_test_interview(interview)
    if not is_test and used >= interview_progress_service.MAX_STARTED_ATTEMPTS:
        db.rollback()
        raise AiInterviewError(
            "attempts_exhausted",
            f"You have used all {interview_progress_service.MAX_STARTED_ATTEMPTS} attempts for this "
            "AI Interview, so it cannot be started again. Please contact HR if you need help.",
        )

    session = issue_room(candidate, settings)
    binding = interview_context_service.bind_room(
        db, session["room_name"], interview, candidate, settings.token_ttl_minutes,
        language=language,
    )
    logger.info("voice session bound: room=%s interview=%s job=%s",
                session["room_name"], interview.id, job.id)
    # Phase 11.6.5: the correlation point - room <-> session <-> interview.
    diag.emit("backend_session_created", session["room_name"], source="backend",
              session_id=binding.id, interview_id=interview.id, attempts=used)
    return {
        **session,
        "interview": {"interview_id": interview.id, "job_title": job.title},
    }


def _refusal(reason: str, interview) -> AiInterviewError:
    """A clear, applicant-facing refusal for one `ineligibility()` reason."""
    ctx = interview_context_service
    if reason in ("not_found", ctx.NOT_OPEN):
        return AiInterviewError(
            "not_found", "No interview of yours with that id is ready for an AI Interview.")
    if reason == ctx.COMPLETED:
        return AiInterviewError(
            "completed", "This AI Interview has already been completed and cannot be started again.")
    if reason == ctx.NOT_APPROVED:
        return AiInterviewError(
            "not_approved",
            "This interview is not open for an AI Interview: your application is not at "
            "the interview stage.")
    opens, closes = ctx.start_window(interview)
    if reason == ctx.TOO_EARLY:
        return AiInterviewError(
            "too_early",
            f"This AI Interview opens at {opens:%Y-%m-%d %H:%M} "
            f"(scheduled for {interview.scheduled_at:%Y-%m-%d %H:%M}). Please come back then.")
    return AiInterviewError(
        "too_late",
        f"The time to start this AI Interview ended at {closes:%Y-%m-%d %H:%M} "
        f"(scheduled for {interview.scheduled_at:%Y-%m-%d %H:%M}). Please contact HR to reschedule.")


def issue_room(
    candidate: Candidate,
    settings: VoiceSettings | None = None,
) -> dict:
    """Connection details for the applicant's browser: a new room and a token
    for it. Pure - it writes nothing; `start_voice_session` binds the room."""
    settings = settings or voice_settings()
    _require_configured(settings)

    room_name = new_room_name()
    identity = participant_identity(candidate)
    token = mint_applicant_token(settings, room_name, identity)

    logger.info(
        "voice session issued: candidate_id=%s room=%s ttl_min=%s",
        candidate.id,
        room_name,
        settings.token_ttl_minutes,
    )

    return {
        "server_url": settings.livekit_url,
        "participant_token": token,
        "room_name": room_name,
        "participant_identity": identity,
        "agent_name": settings.agent_name,
        "expires_in_seconds": settings.token_ttl_minutes * 60,
        "models": settings.public_status()["models"],
        "camera": False,
    }
