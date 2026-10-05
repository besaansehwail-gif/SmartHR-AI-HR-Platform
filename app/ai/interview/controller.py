"""Drives the interview: its state machine and its Question Bank progression.

LiveKit's `AgentSession` knows, moment to moment, whether the *agent* is
listening, thinking or speaking and whether the *applicant* is speaking,
listening or away. The controller turns those events into the interview's own
states (`state.py`), and owns what is the interview's business:

* **which question is current** - `QuestionProgress`, built from the plan the
  backend sent from the Question Bank. Q1 is spoken verbatim here; every later
  question is appended verbatim by the agent's `llm_node` after GPT-4o's
  one-sentence acknowledgement. GPT-4o never chooses a question;
* **answer association** - each accepted answer is recorded against the
  question that was current when it was given (`on_answer`), and handed to
  `on_commit` (Phase 7: sent to the backend) once it is final - when the reply
  to it starts playing, or when the session ends (`flush_answers`);
* the opening, the silence nudge, the time limit, and ENDING -> COMPLETED
  after the last question;
* Phase 11.1: whether a main question's predefined follow-up is asked -
  `decide_follow_up` puts the interview in FOLLOW_UP_DECISION and asks the
  injected decider (GPT-4o, yes/no only) - the words are the bank's;
* Phase 11.2: when no follow-up is asked, which predefined main question
  comes next - `select_next_question` (ADAPTIVE_SELECTION) asks the injected
  selector for a Question Bank id; `QuestionProgress` accepts it only if it is
  a not-yet-asked main question of this plan, else the bank's own order;
* the turn classifier: `classify_turn` decides ANSWER / SIDE_QUESTION /
  REPEAT_REQUEST / NOISE_OR_INCOMPLETE (noise deterministically first, then
  the injected model classifier, which defaults to ANSWER).
  `non_answer_directive` handles the three non-answers: nothing recorded,
  the CURRENT question again - or, after MAX_NOISE_REASKS noisy turns, the
  next question;
* never silent: `reply_expected` arms a watchdog that speaks a fixed
  fallback plus the question if no reply has started within REPLY_DEADLINE_S;
* publishing state as participant attributes (the page and tests read them).

Published attributes carry the state name, counts and "question N of M" -
never the words said, never question ids or evaluation notes.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from app.ai.interview import diagnostics as diag
from app.ai.interview.adaptive import SELECT_TIMEOUT_S
from app.ai.interview.follow_up import DECISION_TIMEOUT_S

from app.ai.interview.questions import (
    FIXED_LEADS,
    NON_ANSWER_FALLBACKS,
    NON_ANSWER_NOTES,
    AnswerRecord,
    Directive,
    QuestionProgress,
)
from app.ai.interview.turn_policy import noise_reason
from app.ai.interview.utterance import (
    ANSWER,
    CLASSIFY_TIMEOUT_S,
    NOISE_OR_INCOMPLETE,
    REPEAT_REQUEST,
    SIDE_QUESTION,
    effective_label,
)
from app.ai.interview.state import IllegalTransition, InterviewState, InterviewStateMachine
from app.ai.interview.turn_policy import MAX_NUDGES_PER_SILENCE
from app.ai.interview.spoken import spoken_phrase

logger = logging.getLogger("smarthr.interview.controller")

S = InterviewState

#: Participant attributes the agent publishes. Read by AiInterviewPage.tsx
#: and by the scripts/verify_ai_interview_*.py live tests.
STATE_ATTRIBUTE = "smarthr.interview.state"
COUNTERS_ATTRIBUTE = "smarthr.interview.turns"
QUESTION_ATTRIBUTE = "smarthr.interview.question"

#: If no interviewer speech has started this long after a turn was decided,
#: the controller speaks a fixed fallback plus the question itself, so a turn
#: never ends in silence (a stalled model or TTS). Above the agent's own
#: first-sentence fallback (LLM_FIRST_SENTENCE_TIMEOUT_S) plus TTS start.
REPLY_DEADLINE_S = 15.0

#: A practice session ends itself after this long. Ten minutes is ample for
#: five questions, and stops a forgotten tab from holding a room (and
#: spending model time) indefinitely.
DEFAULT_MAX_SECONDS = 600


class InterviewController:
    def __init__(
        self,
        session,
        machine: InterviewStateMachine,
        room_name: str,
        publish: Callable[[dict[str, str]], Awaitable[None]] | None = None,
        progress: QuestionProgress | None = None,
        job_title: str | None = None,
        on_commit: Callable[[list[AnswerRecord]], None] | None = None,
        follow_up_decider: Callable[[str, str, str], Awaitable[bool]] | None = None,
        next_question_selector: Callable[[str, str, list], Awaitable[int | None]] | None = None,
        utterance_classifier: Callable[[str, str, bool], Awaitable[str | None]] | None = None,
        language: str | None = "en",
    ) -> None:
        self.session = session
        #: (current question, effective words, is follow-up) -> a label, or
        #: None. None configured = the model step is skipped (ANSWER unless
        #: the deterministic noise check says otherwise).
        self._utterance_classifier = utterance_classifier
        #: A non-answer reply (nothing to commit) is pending.
        self._non_answer_pending = False
        #: ...its audio has started; the LiveKit speech handle carrying it;
        #: the bank text it must deliver (a re-ask / skip counts as HEARD only
        #: if that text was played - LiveKit records an interrupted reply as
        #: the words actually played); and whether it closes the interview.
        self._non_answer_spoke = False
        self._non_answer_speech = None
        self._non_answer_text: str | None = None
        self._skip_finishing = False
        #: Observability: the current turn's id, when it ended, how long the
        #: applicant's speech in it lasted (VAD), and the reply watchdog.
        self.turn_id = 0
        self._turn_ended_at: float | None = None
        self._speech_ms = 0
        self._speech_since: float | None = None
        self._reply_pending_turn: int | None = None
        self._watchdog: asyncio.Task | None = None
        #: The applicant spoke (VAD) while the uninterruptible welcome played.
        self._spoke_during_welcome = False
        #: Phase 11.1: (main question, answer, follow-up) -> ask it? None means
        #: follow-ups are never asked (every earlier behaviour, unchanged).
        self._follow_up_decider = follow_up_decider
        #: Phase 11.2: (main question, answer, remaining main questions) -> a
        #: Question Bank id, or None. None configured = the bank's own order.
        self._next_question_selector = next_question_selector
        #: Phase 7: receives answers once they are final, numbered in order.
        self._on_commit = on_commit
        #: The role named in the welcome (Phase 4). From the backend's Job
        #: Context - the controller never looks a job up itself.
        self.job_title = job_title
        self.language = language
        self.machine = machine
        self.room_name = room_name
        self._publish = publish
        self.progress = progress or QuestionProgress([])
        self.opening_done = False
        self._tasks: set[asyncio.Task] = set()
        #: When the interviewer's voice last started playing (agent "speaking").
        self._last_spoke_at: float | None = None
        #: An answer has been decided on and its reply not yet heard.
        self._awaiting_reply = False
        #: The answer's reply, "provisional until heard" like a re-ask / skip:
        #: the LiveKit speech handle carrying it, whether its audio started,
        #: and the next question it owes. The answer is COMMITTED (and so
        #: sent to the backend, which cannot take it back) only once that
        #: question has been heard.
        self._answer_speech = None
        self._answer_spoke = False
        self._answer_text: str | None = None
        #: The interview state the NEXT interviewer speech represents: ASKING
        #: when it carries the next bank question, ENDING when it carries the
        #: closing line. None means an ordinary reply (SPEAKING).
        self._next_speech_state: InterviewState | None = None
        #: True while `end()` (time limit) runs its own ENDING -> COMPLETED;
        #: the agent going "listening" after its interrupt() must not end
        #: the session before the closing line is spoken.
        self._ending_via_end = False
        #: Phase 9: the interview ended the way an interview should - the
        #: closing line after the last question, or after the time limit. An
        #: applicant leaving, a closed session or a missing plan leave it False,
        #: and the worker then reports "ended" rather than "completed".
        self.completed_normally = False
        #: Serialises attribute updates, so they reach the room in the order
        #: the states happened (two quick updates must not swap places).
        self._publish_lock: asyncio.Lock | None = None
        #: Phase 11.6.2: the question number last actually SPOKEN (set on
        #: entering ASKING) - what the applicant's page is told.
        self._spoken_number: int | None = None
        #: Phase 11.6.5: a question entered ASKING and its audio has not
        #: started yet - "question_spoken" is emitted when it does.
        self._unspoken_question: int | None = None

    # -- state ---------------------------------------------------------------
    def set_state(self, target: InterviewState) -> bool:
        try:
            changed = self.machine.to(target)
        except IllegalTransition as exc:
            # Refused and logged, never forced: the state stays consistent.
            logger.warning("room=%s illegal transition refused: %s", self.room_name, exc)
            diag.emit("state_error", self.room_name, category="state_error",
                      state=self.machine.state.value)
            return False
        if changed:
            if target == S.ASKING:
                # Phase 11.6.2: the number the applicant sees moves only when
                # a question is actually being SPOKEN - not when the next one
                # was merely decided (the progress index moves at decision time).
                self._spoken_number = self.progress.number
                # Phase 11.6.5: "question_spoken" waits for the audio itself.
                self._unspoken_question = self.progress.number
            q = f" (question {self.progress.number}/{self.progress.total})" if target == S.ASKING else ""
            logger.info("room=%s interview state -> %s%s", self.room_name, target.value, q)
            diag.emit("state_changed", self.room_name, state=target.value,
                      question=self._spoken_number, total=self.progress.total)
            if target == S.ENDING:
                diag.emit("interview_ending", self.room_name, once=True, reason=self._ending_reason())
            elif target == S.COMPLETED:
                diag.emit("interview_finished", self.room_name, once=True,
                          completed_normally=self.completed_normally)
            self.publish()
        return changed

    def _ending_reason(self) -> str:
        if self.machine.end_reason == "time_limit":
            return "time_limit"
        return "no_plan" if self.progress.total == 0 else "last_question"

    def publish(self) -> None:
        if self._publish is None:
            return
        attributes = {
            STATE_ATTRIBUTE: self.machine.state.value,
            COUNTERS_ATTRIBUTE: json.dumps(self.machine.counters.as_dict()),
            QUESTION_ATTRIBUTE: json.dumps({
                "number": self._spoken_number if self._spoken_number is not None else self.progress.number,
                "total": self.progress.total}),
        }
        self._spawn(self._publish_in_order(attributes))

    async def _publish_in_order(self, attributes: dict[str, str]) -> None:
        if self._publish_lock is None:
            self._publish_lock = asyncio.Lock()
        async with self._publish_lock:  # asyncio.Lock wakes waiters FIFO
            await self._publish(attributes)

    def _spawn(self, coro) -> None:
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:  # no running loop (unit tests call synchronously)
            coro.close()
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- progression -------------------------------------------------------------
    def follow_up_candidate(self, kind: str, text: str):
        """(main, follow-up, complete answer) when this turn deserves a
        follow-up decision - or None (no decider, no eligible follow-up)."""
        if self._follow_up_decider is None:
            return None
        return self.progress.follow_up_candidate(kind, text)

    async def decide_follow_up(self, main, follow_up, answer: str) -> bool:
        """FOLLOW_UP_DECISION: ask the decider. Never raises; anything but a
        plain True - including a slow or failing model - is "move on"."""
        self.set_state(S.FOLLOW_UP_DECISION)
        began = time.monotonic()
        diag.emit("followup_decision_started", self.room_name, **self._turn(), question=self.progress.number,
                  question_id=main.id)
        fallback = False
        try:
            ask = await asyncio.wait_for(
                self._follow_up_decider(main.text, answer, follow_up.text), DECISION_TIMEOUT_S + 1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("room=%s follow-up decision failed (%s) - moving on",
                           self.room_name, type(exc).__name__)
            diag.emit("llm_error", self.room_name, operation="follow_up", category="llm_error",
                      code=diag.exception_code(exc), error_type=diag.error_type(exc))
            ask, fallback = False, True
        ask = ask is True
        diag.emit("followup_decision_completed", self.room_name, **self._turn(), question=self.progress.number,
                  question_id=main.id, outcome="ask" if ask else "move_on", fallback=fallback,
                  duration_ms=diag.elapsed_ms(began))
        logger.info("room=%s follow-up decision for question %d (id=%s): %s (follow-up id=%s)",
                    self.room_name, self.progress.number, main.id, "ask" if ask else "move on", follow_up.id)
        return ask

    def adaptive_options(self, kind: str, text: str):
        """(main, complete answer, remaining main questions) when there is a
        next main question to choose - or None (no selector, no real choice)."""
        if self._next_question_selector is None:
            return None
        return self.progress.adaptive_options(kind, text)

    async def select_next_question(self, main, answer: str, options: list) -> int | None:
        """ADAPTIVE_SELECTION: ask the selector for the next main question's
        id. Never raises; returns the id only if it is one of `options`
        (QuestionProgress checks it again), else None = the bank's order."""
        self.set_state(S.ADAPTIVE_SELECTION)
        allowed = {q.id for q in options}
        began = time.monotonic()
        diag.emit("adaptive_selection_started", self.room_name, **self._turn(), question=self.progress.number,
                  question_id=main.id, questions=len(allowed))
        try:
            choice = await asyncio.wait_for(
                self._next_question_selector(main.text, answer, options), SELECT_TIMEOUT_S + 1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("room=%s adaptive choice failed (%s) - Question Bank order",
                           self.room_name, type(exc).__name__)
            diag.emit("llm_error", self.room_name, operation="adaptive", category="llm_error",
                      code=diag.exception_code(exc), error_type=diag.error_type(exc))
            choice = None
        if not isinstance(choice, int) or isinstance(choice, bool) or choice not in allowed:
            choice = None
        diag.emit("adaptive_selection_completed", self.room_name, **self._turn(), question=self.progress.number,
                  outcome="chosen" if choice is not None else "bank_order",
                  question_id=choice, duration_ms=diag.elapsed_ms(began))
        logger.info("room=%s adaptive choice after question %d (id=%s): %s (options %s)",
                    self.room_name, self.progress.number, main.id,
                    choice if choice is not None else "bank order", sorted(allowed))
        return choice

    # -- turns ------------------------------------------------------------------
    def begin_turn(self, turn_id: int) -> int:
        """A completed applicant turn is starting to be processed. Returns
        how long the applicant spoke in it (ms, from VAD), and cancels any
        reply watchdog - a new turn supersedes the old reply."""
        self.turn_id = turn_id
        self._turn_ended_at = time.monotonic()
        if self._speech_since is not None:
            self._speech_ms += int((self._turn_ended_at - self._speech_since) * 1000)
            self._speech_since = None
        speech_ms, self._speech_ms = self._speech_ms, 0
        self._cancel_watchdog()
        return speech_ms

    def _turn(self) -> dict:
        return {"turn": self.turn_id} if self.turn_id else {}

    async def classify_turn(self, kind: str, text: str, confidence: float | None = None,
                            speech_ms: int | None = None) -> str:
        """ANSWER / SIDE_QUESTION / REPEAT_REQUEST / NOISE_OR_INCOMPLETE for
        this turn. Runs FIRST, before any follow-up / adaptive decision.

        1. deterministic noise (`turn_policy.noise_reason`) - no model call;
        2. the injected model classifier - anything invalid, failing or slow
           is ANSWER.
        Never raises. Reads the progress, never changes it."""
        q = self.progress.current
        if q is None:
            return ANSWER
        began = time.monotonic()
        words = self.progress.effective_text(kind, text)
        # A fragment completing an open answer is judged with the whole answer:
        # its own confidence and duration say nothing about the rest.
        open_answer = self.progress.resumed is not None
        reason = noise_reason(words, None if open_answer else confidence, None if open_answer else speech_ms)
        if reason is not None:
            self._classified(NOISE_OR_INCOMPLETE, q, kind, False, began, source_noise=reason)
            return NOISE_OR_INCOMPLETE
        if self._utterance_classifier is None:
            return ANSWER
        fallback = False
        try:
            label = await asyncio.wait_for(self._utterance_classifier(
                q.text, words, self.progress.in_follow_up is not None), CLASSIFY_TIMEOUT_S + 1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("room=%s turn classification failed (%s) - treated as an answer",
                           self.room_name, type(exc).__name__)
            diag.emit("llm_error", self.room_name, operation="classify", category="llm_error",
                      code=diag.exception_code(exc), error_type=diag.error_type(exc), **self._turn())
            label = None
        if effective_label(label) != label:
            fallback = True
        label = effective_label(label)
        self._classified(label, q, kind, fallback, began)
        return label

    def _classified(self, label: str, q, kind: str, fallback: bool, began: float,
                    source_noise: str | None = None) -> None:
        logger.info("room=%s turn %d on question %d (id=%s): %s%s", self.room_name, self.turn_id,
                    self.progress.number, q.id, label,
                    f" ({source_noise})" if source_noise else (" (fallback)" if fallback else ""))
        diag.emit("turn_classified", self.room_name, classification=label.lower(),
                  question=self.progress.number, question_id=q.id, kind=kind, fallback=fallback,
                  noise_reason=source_noise, duration_ms=diag.elapsed_ms(began), **self._turn())

    def non_answer_directive(self, label: str) -> Directive | None:
        """The reply to a non-answer. Nothing is recorded or committed.

        SIDE_QUESTION   one short model sentence + the CURRENT question;
        REPEAT_REQUEST  "Of course." + the CURRENT question (no model call);
        NOISE_OR_INCOMPLETE  "Sorry, I didn't catch that." + the CURRENT
                        question, at most MAX_NOISE_REASKS times per question;
                        after that the interview moves on (`skip`) to the
                        next question - or ends - with nothing recorded.
        """
        q = self.progress.current
        if q is None:
            return None
        if label == SIDE_QUESTION:
            kind, text = "side_reply", q.text
        elif label == REPEAT_REQUEST:
            kind, text = "repeat", q.text
        elif label == NOISE_OR_INCOMPLETE:
            if self.progress.note_noise():
                kind, text = "reask", q.text
            else:
                nxt = self.progress.skip()
                logger.info("room=%s question id=%s skipped after repeated noise", self.room_name, q.id)
                self._arm_non_answer(nxt.text if nxt is not None else self.progress.closing_text)
                if nxt is None:
                    # The interview ends only once the closing is HEARD
                    # (`_settle_non_answer`) - ENDING cannot be undone.
                    self._skip_finishing = True
                    self._next_speech_state = None
                    return Directive("skip", "", self.progress.closing_text, self.progress.total)
                self._next_speech_state = S.ASKING
                return Directive("skip", "", nxt.text, self.progress.number)
        else:
            return None
        self._arm_non_answer(text)
        # The reply carries the current question again: heard = ASKING.
        self._next_speech_state = S.ASKING
        return Directive(kind, NON_ANSWER_NOTES[kind] or "", text, self.progress.number)

    def _arm_non_answer(self, text: str) -> None:
        self._non_answer_pending = True
        self._non_answer_spoke = False
        self._non_answer_speech = None
        self._non_answer_text = text
        self._skip_finishing = False

    def _clear_non_answer(self) -> None:
        self._non_answer_pending = False
        self._non_answer_spoke = False
        self._non_answer_speech = None
        self._non_answer_text = None
        self._skip_finishing = False

    @staticmethod
    def _norm(text: str | None) -> str:
        return " ".join("".join(c.lower() if c.isalnum() else " " for c in (text or "")).split())

    def _played_all(self, handle, owed_text: str | None = None) -> bool:
        """Did the interrupted reply carried by `handle` get as far as playing
        the whole bank text? LiveKit records an interrupted reply's message as
        the words actually played (its transcript synchronizer)."""
        played = " ".join(item.text_content or "" for item in getattr(handle, "chat_items", [])
                          if getattr(item, "role", None) == "assistant")
        owed = self._norm(self._non_answer_text if owed_text is None else owed_text)
        return bool(owed) and owed in self._norm(played)

    def _settle_non_answer(self, heard: bool) -> None:
        """Decide a pending re-ask / skip: keep it (heard) or undo it."""
        if not self._non_answer_pending:
            return
        finishing = self._skip_finishing
        if heard:
            self.progress.confirm_pending()
            self._clear_non_answer()
            if finishing and self.machine.active:
                # The closing after the last question was heard: complete.
                self.completed_normally = True
                self.set_state(S.ENDING)
                self.set_state(S.COMPLETED)
                self.session.shutdown()
        else:
            self._revert_non_answer()
            # What the page shows goes back to the question actually heard.
            if self._spoken_number != self.progress.number and self.progress.current is not None:
                self._spoken_number = self.progress.number
                self.publish()

    async def settle_reply(self, timeout: float = 1.0) -> None:
        """A new turn is starting: LiveKit has just interrupted the reply that
        was playing. Let that reply's speech finish settling (bounded), so a
        re-ask / skip is decided heard-or-not on what was actually played
        BEFORE this turn is classified."""
        if self._non_answer_pending:
            handle = self._non_answer_speech
        elif self._awaiting_reply:
            handle = self._answer_speech
        else:
            handle = None
        if handle is None or handle.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.ensure_future(handle.wait_for_playout())), timeout)
        except Exception:  # timeout or LiveKit refusing the wait: absorb_unheard decides
            pass

    # -- never silent ---------------------------------------------------------
    def reply_expected(self, directive: Directive | None) -> None:
        """A turn was decided: its reply must start within REPLY_DEADLINE_S."""
        self._reply_pending_turn = self.turn_id
        self._cancel_watchdog()
        try:
            self._watchdog = asyncio.ensure_future(self._reply_watchdog(self.turn_id, directive))
        except RuntimeError:  # no running loop (synchronous unit tests)
            self._watchdog = None

    def _cancel_watchdog(self) -> None:
        if self._watchdog is not None and not self._watchdog.done():
            self._watchdog.cancel()
        self._watchdog = None

    async def _reply_watchdog(self, turn_id: int, directive: Directive | None) -> None:
        await asyncio.sleep(REPLY_DEADLINE_S)
        if self._reply_pending_turn != turn_id or not self.machine.active:
            return
        if directive is not None and directive.kind in ("reask", "skip") and self.progress.revert_pending():
            # The re-ask / skip was never heard: do NOT move on silently -
            # stay on the question the applicant heard and ask it again.
            self._clear_non_answer()
            self._next_speech_state = S.ASKING
            current = self.progress.current
            directive = Directive("reask", "", current.text if current else None, self.progress.number)
            diag.emit("reply_not_heard", self.room_name, question=self.progress.number, turn=turn_id)
        if self._awaiting_reply:
            # The answer's reply never started: the fallback below (ack + the
            # same next question) becomes the reply that must be heard before
            # the answer is committed - the stuck speech no longer counts.
            self._answer_speech = None
            self._answer_spoke = False
        lead = (spoken_phrase(f"fixed_{directive.kind}", self.language)
                if directive is not None and directive.kind in FIXED_LEADS else None)
        if directive is not None and lead is None:
            lead = (spoken_phrase("side_reply_fallback", self.language)
                    if directive.kind in NON_ANSWER_FALLBACKS
                    else spoken_phrase("fallback_ack", self.language))
        text = " ".join(t for t in (lead or spoken_phrase("fallback_ack", self.language),
                                     directive.say_after if directive else None) if t)
        logger.warning("room=%s turn %d: no reply after %.0fs - speaking the fallback",
                       self.room_name, turn_id, REPLY_DEADLINE_S)
        diag.emit("pipeline_error", self.room_name, category="unknown_error", code="no_reply", turn=turn_id)
        self._reply_pending_turn = None
        try:
            self.session.interrupt()
            self.session.say(text)
        except Exception as exc:  # the fallback itself must not raise
            logger.warning("room=%s fallback speech failed (%s)", self.room_name, type(exc).__name__)

    def on_answer(self, kind: str, text: str, ask_follow_up: bool = False,
                  next_question_id: int | None = None) -> Directive | None:
        """An accepted applicant turn: associate it, then decide what's next.

        Called by the agent's turn gate, BEFORE GPT-4o is asked anything.
        `ask_follow_up` is the follow-up decision, already made (Phase 11.1).
        """
        answered = self.progress.current
        if self._non_answer_pending:
            # An earlier non-answer reply that was never heard must not decide
            # what THIS reply is. (Only then - otherwise nothing changes here.)
            self._clear_non_answer()
            self._next_speech_state = None
        directive = self.progress.decide(kind, text, ask_follow_up=ask_follow_up,
                                         next_question_id=next_question_id)
        if answered is None or directive is None:
            return None
        self._awaiting_reply = True
        self._answer_speech = None
        self._answer_spoke = False
        # Only a reply carrying a QUESTION must be heard first; the closing
        # line after the last answer commits when it starts, as before.
        self._answer_text = directive.say_after if directive.kind in ("advance", "follow_up") else None
        record = self.progress.answers[-1]
        if record.kind != kind:
            # This turn completed an earlier, reopened answer: count the
            # merged answer, not the fragment.
            self._count(kind, -1)
            self._count(record.kind, +1)

        logger.info(
            "room=%s answer recorded: question %d/%d (id=%s) kind=%s words=%d -> %s",
            self.room_name, record.question_number, self.progress.total,
            answered.id, record.kind, record.words, directive.kind,
        )
        if directive.kind in ("advance", "follow_up"):
            # Both are Question Bank questions, spoken verbatim: ASKING.
            self._next_speech_state = S.ASKING
        elif directive.kind == "finish":
            self._next_speech_state = S.ENDING
        # Nothing is published here: the new question number becomes visible
        # when the reply carrying it is actually heard (ASKING).
        return directive

    def _emit(self, records: list[AnswerRecord]) -> None:
        for record in records:
            # Final in the interview; "answer_persisted" follows only when the
            # backend has stored it (answer_client).
            diag.emit("answer_committed", self.room_name, **self._turn(), sequence=record.sequence,
                      question=record.question_number, kind=record.kind)
        if records and self._on_commit is not None:
            try:
                self._on_commit(records)
            except Exception:  # persistence must never break the interview
                logger.exception("room=%s answer hand-off failed", self.room_name)

    def flush_answers(self) -> None:
        """The session is over: make every remaining accepted answer final."""
        self._clear_answer_reply()
        self._emit(self.progress.flush())

    def absorb_unheard(self) -> bool:
        """Phase 11.6.2: a NEW applicant turn arrived while the previous
        decision's reply has not started playing. The applicant was still
        talking, so that decision was premature: reopen it now, and the new
        turn completes the SAME answer (merged, decided once again) - exactly
        what the "agent went back to listening" path does, without depending
        on that event arriving first. No-op when nothing is pending, so a
        normal turn (whose reply was heard) is unaffected."""
        if self._non_answer_pending:
            # The applicant spoke again before the re-ask / skip reply was
            # (fully) heard. If the whole bank text had already played, it
            # counts; otherwise its effect is undone and this turn is about
            # the question they actually heard.
            handle = self._non_answer_speech
            self._settle_non_answer(heard=self._non_answer_spoke and handle is not None and self._played_all(handle))
        if not self._awaiting_reply:
            return False
        self._reopen_answer()
        return True

    def _revert_non_answer(self) -> None:
        self._clear_non_answer()
        self._next_speech_state = None
        if self.progress.revert_pending():
            diag.emit("reply_not_heard", self.room_name, question=self.progress.number, **self._turn())
            logger.info("room=%s re-ask/skip reply not heard: still on question %d",
                        self.room_name, self.progress.number)

    def has_open_answer(self) -> bool:
        """An answer was reopened and is waiting for the rest of it."""
        return self.progress.resumed is not None

    def _count(self, kind: str, delta: int) -> None:
        counters = self.machine.counters
        if kind == "answer":
            counters.answers = max(0, counters.answers + delta)
        elif kind == "short":
            counters.short = max(0, counters.short + delta)

    def _clear_answer_reply(self) -> None:
        self._awaiting_reply = False
        self._answer_speech = None
        self._answer_spoke = False
        self._answer_text = None

    def _confirm_answer(self) -> None:
        """The answer's reply was heard: the answer is final (sent)."""
        self._clear_answer_reply()
        self._emit(self.progress.commit())

    def _answer_done(self, handle) -> None:
        if handle is not self._answer_speech or not self._awaiting_reply:
            return
        if not handle.interrupted or self._played_all(handle, self._answer_text):
            self._confirm_answer()
        else:
            self._answer_not_heard()

    def _answer_not_heard(self) -> None:
        """The next question was cut off before the applicant heard it. The
        answer is NOT committed (nothing is sent). If no audio played at all,
        the decision is undone (`_reopen_answer`, as before). If the applicant
        is talking over it, their turn reopens the answer and is MERGED into
        it (`absorb_unheard`). Otherwise - playback failed - the same next
        question is spoken again and must be heard before the answer counts."""
        self._answer_speech = None
        if not self._answer_spoke:
            self._reopen_answer()
            return
        if self._speech_since is not None:
            logger.info("room=%s next question cut off by the applicant: answer kept pending", self.room_name)
            return
        self._respeak_answer_question()

    def _respeak_answer_question(self) -> None:
        text = self._answer_text
        if not text or not self.machine.active:
            return
        self._answer_spoke = False
        self._next_speech_state = S.ASKING
        diag.emit("reply_not_heard", self.room_name, question=self.progress.number, **self._turn())
        logger.info("room=%s next question cut off: speaking it again, answer kept pending", self.room_name)
        try:
            self.session.say(f"{spoken_phrase('repeat_after_cut', self.language)} {text}")   # bound in on_speech_created
        except Exception as exc:  # re-speaking must never raise
            logger.warning("room=%s re-speaking failed (%s)", self.room_name, type(exc).__name__)

    def turn_ignored(self) -> None:
        """An applicant turn was ignored (noise / filler). If it had cut off
        the next question, nobody would ever say it again - so say it now."""
        if self._awaiting_reply and self._answer_speech is None and self._answer_spoke:
            self._respeak_answer_question()

    def _reopen_answer(self) -> None:
        record = self.progress.reopen()
        self._clear_answer_reply()
        self._next_speech_state = None
        if record is None:
            return
        self._count(record.kind, -1)
        diag.emit("reply_not_heard", self.room_name, question=record.question_number)
        logger.info(
            "room=%s reply cancelled before it was heard (applicant still talking): "
            "question %d/%d stays open", self.room_name, record.question_number, self.progress.total,
        )

    # -- LiveKit events -> interview states -----------------------------------
    def attach(self) -> None:
        self.session.on("agent_state_changed", lambda ev: self.on_agent_state(ev.new_state))
        self.session.on("user_state_changed", lambda ev: self.on_user_state(ev.new_state))
        self.session.on("speech_created", lambda ev: self.on_speech_created(ev.speech_handle))
        self.session.on("close", lambda ev: self.on_close(str(getattr(ev, "reason", "closed"))))

    def on_agent_state(self, new_state: str) -> None:
        event = {"speaking": "interviewer_speaking", "listening": "interviewer_listening",
                 "thinking": "interviewer_thinking"}.get(new_state)
        if event is not None:
            diag.emit(event, self.room_name, agent_state=new_state, state=self.machine.state.value)
        if new_state == "speaking" and self._reply_pending_turn is not None:
            # The reply to the latest turn has started: never silent.
            turn, self._reply_pending_turn = self._reply_pending_turn, None
            self._cancel_watchdog()
            latency = int((time.monotonic() - self._turn_ended_at) * 1000) if self._turn_ended_at else None
            diag.emit("reply_started", self.room_name, turn=turn, latency_ms=latency)
        self._on_agent_state(new_state)
        if (new_state == "speaking" and self._unspoken_question is not None
                and self.machine.state == S.ASKING):
            # The audio carrying the question has started: now it is spoken.
            number, self._unspoken_question = self._unspoken_question, None
            diag.emit("question_spoken", self.room_name, question=number, total=self.progress.total,
                      **self._turn())

    def _non_answer_done(self, handle) -> None:
        if handle is not self._non_answer_speech:
            return
        self._settle_non_answer(heard=not handle.interrupted or self._played_all(handle))

    def _on_agent_state(self, new_state: str) -> None:
        if new_state == "speaking":
            self._last_spoke_at = time.monotonic()
        # During the opening the controller itself sets INTRO / ASKING.
        if not self.opening_done or not self.machine.active:
            return

        if new_state == "listening" and self.machine.state == S.ENDING and not self._ending_via_end:
            # The closing line has been spoken: the interview is over.
            self.completed_normally = True
            self.set_state(S.COMPLETED)
            self.session.shutdown()
            return
        if self.machine.state == S.ENDING:
            return

        if new_state == "speaking" and self._awaiting_reply:
            if self._answer_speech is None:
                # No speech handle to consult (the closing line, or a session
                # that reports no handles): final when the reply starts.
                self._confirm_answer()
            else:
                # Started - not yet heard: final only once the next question
                # has played (see `_answer_done`).
                self._answer_spoke = True
        elif new_state == "listening" and self._awaiting_reply and not self._answer_spoke:
            # Back to listening without a word of the reply played: the
            # applicant resumed mid-answer and LiveKit cancelled the reply.
            self._reopen_answer()
        elif new_state == "speaking" and self._non_answer_pending:
            # Started - not yet heard: a re-ask / skip is kept only once its
            # bank text has actually played (see `_non_answer_done`).
            self._non_answer_spoke = True
        elif new_state == "listening" and self._non_answer_pending:
            if not self._non_answer_spoke:
                # Dropped before a word was played: undone, so the interview
                # stays on the question the applicant actually heard.
                self._settle_non_answer(heard=False)
            elif self._non_answer_speech is None:
                # Played through with no speech handle to consult: heard.
                self._settle_non_answer(heard=True)
            # else: the speech handle's done callback decides, on what played.

        if new_state == "speaking" and self._next_speech_state is not None:
            target, self._next_speech_state = self._next_speech_state, None
        else:
            target = {"thinking": S.PROCESSING, "speaking": S.SPEAKING,
                      "listening": S.LISTENING}.get(new_state)
        if target is not None and self.machine.can(target):
            self.set_state(target)

    def on_user_state(self, new_state: str) -> None:
        if new_state == "speaking":
            self.machine.nudges_since_speech = 0
            if self.machine.state == S.INTRO and not self._spoke_during_welcome:
                # LiveKit will drop these words (the welcome cannot be
                # interrupted); remember that they were said.
                self._spoke_during_welcome = True
                diag.emit("speech_during_welcome", self.room_name)
            if self._speech_since is None:
                self._speech_since = time.monotonic()
            diag.emit("turn_started", self.room_name, state=self.machine.state.value,
                      question=self._spoken_number)
        elif new_state != "speaking" and self._speech_since is not None:
            self._speech_ms += int((time.monotonic() - self._speech_since) * 1000)
            self._speech_since = None
        if new_state == "away":
            diag.emit("applicant_away", self.room_name, state=self.machine.state.value)
            self.maybe_nudge()

    def on_speech_created(self, handle) -> None:
        created = time.monotonic()
        if self._non_answer_pending and self._non_answer_speech is None:
            # The reply to a re-ask / skip / side reply: decide heard-or-not
            # from what this speech actually played.
            self._non_answer_speech = handle
            handle.add_done_callback(self._non_answer_done)
        elif self._awaiting_reply and self._answer_text and self._answer_speech is None:
            # The reply carrying the next question after an answer: the
            # answer is committed only once that question has been heard.
            self._answer_speech = handle
            handle.add_done_callback(self._answer_done)

        def done(h) -> None:
            # Only speech the applicant actually HEARD counts. LiveKit also
            # creates speculative replies while the applicant is still talking
            # (preemptive generation) and discards them unheard; cancelling
            # those is not the applicant interrupting anybody.
            heard = self._last_spoke_at is not None and self._last_spoke_at >= created
            if h.interrupted and heard:
                self.machine.counters.interruptions += 1
                diag.emit("interruption", self.room_name, state=self.machine.state.value)
                logger.info("room=%s interviewer speech interrupted by the applicant", self.room_name)
                self.publish()

        handle.add_done_callback(done)

    def on_close(self, reason: str) -> None:
        if self.machine.active:
            self.machine.abort(reason)
            logger.info("room=%s interview state -> completed (%s)", self.room_name, reason)
            diag.emit("interview_finished", self.room_name, once=True, completed_normally=False,
                      reason=diag.close_reason(reason))
        self._cancel_watchdog()
        for task in list(self._tasks):
            task.cancel()

    # -- interview behaviour --------------------------------------------------
    def maybe_nudge(self) -> bool:
        """One fixed prompt after a long silence - only while listening."""
        if self.machine.state != S.LISTENING:
            return False
        if self.machine.nudges_since_speech >= MAX_NUDGES_PER_SILENCE:
            return False
        self.machine.nudges_since_speech += 1
        self.machine.counters.nudges += 1
        logger.info("room=%s silence nudge", self.room_name)
        diag.emit("silence_nudge", self.room_name, question=self._spoken_number)
        self.session.say(spoken_phrase("silence_nudge", self.language))
        self.publish()
        return True

    async def run_opening(self) -> None:
        first = self.progress.current
        self.set_state(S.INTRO)

        if first is None:
            # No plan from the Question Bank: stop, rather than improvise.
            logger.warning("room=%s no interview plan - ending without questions", self.room_name)
            self.set_state(S.ENDING)
            await self.session.say(spoken_phrase("plan_unavailable", self.language),
                                   allow_interruptions=False).wait_for_playout()
            self.set_state(S.COMPLETED)
            self.session.shutdown()
            return

        if self.job_title:
            welcome = spoken_phrase("welcome_for_role", self.language,
                                    title=self.job_title, count=self.progress.total)
        else:
            welcome = spoken_phrase("welcome", self.language, count=self.progress.total)
        await self.session.say(welcome, allow_interruptions=False).wait_for_playout()

        # Q1, word for word from the Question Bank - no model involved. If the
        # applicant spoke over the welcome, say why they got no reply first.
        self.set_state(S.ASKING)
        opening = (f"{spoken_phrase('spoke_during_welcome', self.language)} {first.text}"
                   if self._spoke_during_welcome else first.text)
        await self.session.say(opening).wait_for_playout()
        if self._unspoken_question is not None:
            # Phase 11.6.5: LiveKit may not report a fresh "speaking" edge when
            # Q1 follows the welcome directly - its playout has ended, so it
            # has certainly been spoken by now.
            number, self._unspoken_question = self._unspoken_question, None
            diag.emit("question_spoken", self.room_name, question=number, total=self.progress.total)

        self.opening_done = True
        # If the applicant already answered over the question, the state has
        # moved on (PROCESSING/SPEAKING) and must not be pulled back.
        if self.machine.state == S.ASKING:
            self.set_state(S.LISTENING)

    async def end(self, reason: str) -> None:
        if not self.machine.active or self.machine.state == S.ENDING:
            return
        self.machine.end_reason = reason
        self._ending_via_end = True
        self._next_speech_state = None
        self.set_state(S.ENDING)
        self.session.interrupt()
        await self.session.say(spoken_phrase("closing", self.language),
                               allow_interruptions=False).wait_for_playout()
        self.completed_normally = True
        self.set_state(S.COMPLETED)
        self.session.shutdown()

    async def enforce_time_limit(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        logger.info("room=%s time limit reached (%ss)", self.room_name, seconds)
        diag.emit("time_limit_reached", self.room_name, state=self.machine.state.value)
        await self.end("time_limit")
