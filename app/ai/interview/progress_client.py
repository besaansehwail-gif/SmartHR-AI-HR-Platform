"""The worker's lifecycle reports to the backend (Phase 9).

    job start  -> POST /ai-interview/agent/progress {"event": "started"}
                  the backend marks the interview in_progress - or refuses
                  (another session is newer, the room is no longer eligible),
                  and then the interview does not go ahead
    job end    -> {"event": "completed"}  the closing line was spoken
                  {"event": "ended"}      it ended any other way

Same agent token and room binding as every other agent call. The worker
never names an interview or a status - only the room (in the token) and
the event. It does not read the database.

Phase 11.6.3: a TRANSIENT failure (network error, timeout, HTTP 5xx) is
retried a bounded number of times - the same rule answer delivery follows -
because a lost "completed" would leave a finished interview in_progress and,
once stale, startable again. A refusal (4xx) is final and never retried.
Repeating a report is safe: "started" is idempotent for the room that holds
the interview, and a repeated "completed"/"ended" changes nothing.
"""

import asyncio
import logging

import aiohttp

from app.ai.interview import diagnostics as diag
from app.ai.interview.agent_auth import mint_agent_token
from app.ai.interview.config import backend_url, voice_settings

logger = logging.getLogger("smarthr.interview.progress")

#: Short: the end report runs inside the job's shutdown budget, after the
#: answers have been drained (see END_ATTEMPTS / END_PAUSE_S).
TIMEOUT_S = 1.2
STARTED_TIMEOUT_S = 10
#: Attempts per report, for transient failures only.
STARTED_ATTEMPTS = 2
STARTED_PAUSE_S = 1.0
END_ATTEMPTS = 2
END_PAUSE_S = 0.2


async def _send(room_name: str, event: str, timeout: float) -> int:
    """One POST; the HTTP status. Raises on a network failure or timeout."""
    settings = voice_settings()
    token = mint_agent_token(settings.api_key, settings.api_secret, room_name)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
        async with http.post(f"{backend_url()}/ai-interview/agent/progress", json={"event": event},
                             headers={"Authorization": f"Bearer {token}"}) as resp:
            return resp.status


#: Phase 11.6.5: the lifecycle event a report proves - emitted only once the
#: backend has ACCEPTED it (so "completed" is never claimed before it is).
ACCEPTED_EVENT = {"started": "session_started", "completed": "interview_completed",
                  "ended": "interview_ended"}


async def report_progress(room_name: str, event: str, timeout: float = TIMEOUT_S,
                          attempts: int = 1, pause: float = 0.0) -> bool:
    """True when the backend accepted the report. Never raises."""
    operation = f"progress_{event}"
    category = "progress_report_error"
    if not voice_settings().configured:
        diag.emit("progress_failed", room_name, operation=operation, category=category,
                  code="not_configured", attempts=0)
        return False
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            status = await _send(room_name, event, timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status, reason = None, type(exc).__name__
            code = diag.exception_code(exc)
        else:
            reason = f"HTTP {status}"
            code = diag.http_code(status)
        if status == 200:
            logger.info("room=%s progress %s -> HTTP 200", room_name, event)
            diag.emit("progress_accepted", room_name, operation=operation, attempt=attempt,
                      outcome="accepted")
            diag.emit(ACCEPTED_EVENT[event], room_name, once=True, progress_event=event)
            return True
        if status is not None and 400 <= status < 500:
            # A refusal: this room may not report (superseded, not eligible).
            logger.info("room=%s progress %s refused (%s)", room_name, event, reason)
            diag.emit("progress_refused", room_name, operation=operation, attempt=attempt,
                      category=category, code=code, outcome="refused")
            return False
        if attempt < attempts:
            logger.warning("room=%s progress %s failed (%s) - retrying", room_name, event, reason)
            diag.emit("progress_retry", room_name, operation=operation, attempt=attempt,
                      category=category, code=code)
            await asyncio.sleep(pause)
        else:
            logger.warning("room=%s progress %s not delivered after %d attempt(s) (%s)",
                           room_name, event, attempts, reason)
            diag.emit("progress_failed", room_name, operation=operation, attempts=attempts,
                      category=category, code=code, outcome="failed")
    return False
