"""Sending final answers to the backend (Phase 7) - the worker never stores them.

    controller.on_commit([AnswerRecord, ...])     numbered, final answers
      -> AnswerSink.submit()                      queued, never blocks a turn
      -> POST /ai-interview/agent/answers         agent token for THIS room
         {question_id, question_number, sequence, kind, transcript, answered_at}

The body carries no interview, application or candidate id and no question
text: the backend resolves those from the room binding and the Question Bank.
The worker names the room only inside its signed token, as for the plan.

Delivery is sequential (one request at a time, in answer order) and retried
on network errors and 5xx. A retry is safe because `sequence` makes the
request idempotent: the backend answers a repeat with the row it already has.
A 4xx is not retried - it is a refusal, not a hiccup. At the end of the
session `drain()` waits (bounded) for everything queued.

Logs carry sequence numbers and status codes - never a transcript.
"""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from app.ai.interview import diagnostics as diag
from app.ai.interview.agent_auth import mint_agent_token
from app.ai.interview.config import backend_url, voice_settings
from app.ai.interview.questions import AnswerRecord

logger = logging.getLogger("smarthr.interview.answers")

TIMEOUT_S = 10
#: Pauses before the 2nd and 3rd attempt.
RETRY_DELAYS_S = (1.0, 3.0)
#: Inside livekit-agents' 10 s graceful job shutdown (shutdown_process_timeout).
#: Phase 11.6.3: 6.5 s (was 8 s), leaving room after the drain for the END
#: progress report and its one retry (progress_client: 2 x 1.2 s + 0.2 s), so
#: the whole shutdown stays under 10 s. Answers are normally delivered while
#: the interview runs; the drain only covers the last one or two.
DRAIN_TIMEOUT_S = 6.5


def answer_payload(record: AnswerRecord) -> dict:
    """The request body for one final answer. Exactly these six keys."""
    if record.sequence is None:
        raise ValueError("answer is not final")
    return {
        "question_id": record.question_id,
        "question_number": record.question_number,
        "sequence": record.sequence,
        "kind": record.kind,
        "transcript": record.text,
        "answered_at": datetime.fromtimestamp(record.wall, timezone.utc).isoformat(),
    }


class AnswerSink:
    def __init__(self, room_name: str, post=None) -> None:
        self.room_name = room_name
        #: Injectable for tests: async (payload) -> HTTP status.
        self._post = post or self._http_post
        self._queue: list[AnswerRecord] = []
        self._task: asyncio.Task | None = None
        self.delivered: list[int] = []
        self.refused: list[tuple[int, int]] = []
        self.undelivered: list[int] = []

    def submit(self, records: list[AnswerRecord]) -> None:
        """Queue final answers. Never raises, never waits."""
        self._queue.extend(r for r in records if r.sequence is not None)
        if self._task is None or self._task.done():
            try:
                self._task = asyncio.ensure_future(self._deliver())
            except RuntimeError:  # no running loop
                logger.warning("room=%s answers queued without an event loop", self.room_name)

    async def _deliver(self) -> None:
        while self._queue:
            record = self._queue.pop(0)
            await self._send(record)

    async def _send(self, record: AnswerRecord) -> None:
        payload = answer_payload(record)
        # Phase 11.6.5: sequence, question number, attempt and a code - never
        # the body (it carries the transcript).
        ids = {"sequence": record.sequence, "question": record.question_number,
               "operation": "answer"}
        category = "answer_persistence_error"
        for attempt in range(len(RETRY_DELAYS_S) + 1):
            try:
                status = await self._post(payload)
            except Exception as exc:
                status, reason = None, type(exc).__name__
                code = diag.exception_code(exc)
            else:
                reason = f"HTTP {status}"
                code = diag.http_code(status)
            if status == 200:
                self.delivered.append(record.sequence)
                logger.info("room=%s answer seq=%s delivered (question %s)", self.room_name,
                            record.sequence, record.question_number)
                diag.emit("answer_persisted", self.room_name, attempt=attempt + 1,
                          outcome="delivered", **ids)
                return
            if status is not None and 400 <= status < 500:
                self.refused.append((record.sequence, status))
                logger.warning("room=%s answer seq=%s refused: %s", self.room_name, record.sequence, reason)
                diag.emit("answer_refused", self.room_name, attempt=attempt + 1, category=category,
                          code=code, outcome="refused", **ids)
                return
            if attempt < len(RETRY_DELAYS_S):
                diag.emit("answer_retry", self.room_name, attempt=attempt + 1, category=category,
                          code=code, **ids)
                await asyncio.sleep(RETRY_DELAYS_S[attempt])
        self.undelivered.append(record.sequence)
        logger.warning("room=%s answer seq=%s NOT delivered after %d attempts (%s)", self.room_name,
                       record.sequence, len(RETRY_DELAYS_S) + 1, reason)
        diag.emit("answer_failed", self.room_name, attempts=len(RETRY_DELAYS_S) + 1,
                  category=category, code=code, outcome="failed", **ids)

    async def drain(self, timeout: float = DRAIN_TIMEOUT_S) -> None:
        """Wait for every queued answer to be delivered or given up on."""
        if self._task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
        except asyncio.TimeoutError:
            logger.warning("room=%s %d answer(s) still queued at shutdown", self.room_name,
                           len(self._queue) + 1)
            diag.emit("answer_drain_timeout", self.room_name, pending=len(self._queue) + 1,
                      category="answer_persistence_error", code="timeout")

    async def _http_post(self, payload: dict) -> int:
        settings = voice_settings()
        token = mint_agent_token(settings.api_key, settings.api_secret, self.room_name)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as http:
            async with http.post(f"{backend_url()}/ai-interview/agent/answers", json=payload,
                                 headers={"Authorization": f"Bearer {token}"}) as resp:
                return resp.status
