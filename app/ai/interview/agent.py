"""The interviewer - a structured interview from the Question Bank, for one job.

Who decides what:

    Question Bank  which questions exist, in which order   (the backend)
    Job Context    which role this interview is for        (the backend, Phase 4)
    CV Context     what the applicant's CV says            (the backend, Phase 5)
    Matching       SmartHR's EXISTING match result          (the backend, Phase 6)
                   for this candidate + job: score,
                   matching skills, skill gaps
    controller     which question is current / next        (controller.py)
    turn detector  whether the applicant has finished      (turn_policy.py)
    GPT-4o         the WORDS of a short acknowledgement    (this module, constrained)

The Job, CV and Matching Contexts reach GPT-4o in exactly one place:
delimited DATA blocks of the agent's instructions (`build_instructions`). They
inform the acknowledgement; they cannot change the question, because the
question is not GPT-4o's to write. The CV arrives a few seconds into the
session (it is parsed on demand) and is added with `set_cv`; the matching
result follows it with `set_matching` (it is computed from that same parse).
Until each arrives, the instructions say it is not available. Every sentence
GPT-4o speaks - on the advance path and the elaborate path alike - passes two
code-level guards (`drops_sentence`): `cv_context.unsupported_cv_claim`, which
drops a citation of the CV for something the CV context does not contain, and
`matching_context.decision_or_score_claim`, which drops a stated score,
percentage or match, a hiring verdict, or a claim that the applicant lacks
something. GPT-4o never computes a score: it is only shown the existing one,
and told never to say it.

The first question is spoken verbatim by the controller. After each answer,
`on_user_turn_completed` asks the controller for a `Directive` and attaches it
to the context of the one reply about to be generated. `llm_node` then shapes
that reply in code:

    advance / finish   GPT-4o's text is filtered sentence by sentence - any
                       sentence that asks something is DROPPED - and the next
                       bank question (or the closing line) is appended
                       VERBATIM. So the question the applicant hears is the
                       bank's text, whatever the model wrote.
    elaborate          a short answer: GPT-4o may invite more about the
                       CURRENT bank question (once per question, see
                       questions.py). No new question is appended.

The gate before all of that is unchanged from Phase 2: empty / filler turns
are refused with StopResponse and never reach GPT-4o.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import Agent, StopResponse, llm
from livekit.agents.llm import ImageContent

from app.ai.interview import cv_context as cvmod
from app.ai.interview import diagnostics as diag
from app.ai.interview.cv_context import CvContext
from app.ai.interview.job_context import JobContext, instructions_block
from app.ai.interview import matching_context as matchmod
from app.ai.interview.matching_context import MatchingContext
from app.ai.interview.debug_capture import TurnCapture
from app.ai.interview.questions import (
    FIXED_LEADS,
    MAX_ACK_SENTENCES,
    NON_ANSWER_FALLBACKS,
    NON_ANSWER_MAX_SENTENCES,
    NON_ANSWER_NOTES,
    Directive,
    is_questionlike,
    split_sentences,
)
from app.ai.interview.spoken import spoken_phrase
from app.ai.interview.state import InterviewState, InterviewStateMachine
from app.ai.interview.turn_policy import SHORT_ANSWER_NOTE, classify_utterance
from app.ai.interview.utterance import ANSWER

logger = logging.getLogger("smarthr.interview.agent")

#: The Stage 4A publication name. Only this linked-applicant camera is used.
CAMERA_TRACK_NAME = "ai-interview-camera"
CAMERA_INFERENCE_WIDTH = 512
CAMERA_INFERENCE_HEIGHT = 288


class CameraFrameInput:
    """One optional remote camera stream and a single replace-only frame slot."""

    def __init__(self, room_name: str, enabled: bool = False) -> None:
        self.room_name = room_name
        self.enabled = enabled
        self._room = None
        self._applicant_identity: str | None = None
        self._stream: rtc.VideoStream | None = None
        self._reader: asyncio.Task | None = None
        self._publication_sid: str | None = None
        self._latest_frame: rtc.VideoFrame | None = None

    def start(self, room, applicant_identity: str) -> None:
        """Watch an existing or later track from the linked applicant only."""
        if not self.enabled or self._room is not None:
            return
        self._room = room
        self._applicant_identity = applicant_identity
        room.on("track_subscribed", self._on_track_subscribed)
        room.on("track_unsubscribed", self._on_track_unsubscribed)
        room.on("track_unpublished", self._on_track_unpublished)
        participant = getattr(room, "remote_participants", {}).get(applicant_identity)
        if participant is not None:
            for publication in list(getattr(participant, "track_publications", {}).values()):
                track = getattr(publication, "track", None)
                if track is not None:
                    self._consider(track, publication, participant)

    @staticmethod
    def _name(publication) -> str:
        return str(getattr(publication, "name", getattr(publication, "track_name", "")) or "")

    def _matches(self, track, publication, participant) -> bool:
        return (
            getattr(participant, "identity", None) == self._applicant_identity
            and getattr(track, "kind", None) == rtc.TrackKind.KIND_VIDEO
            and getattr(publication, "source", None) == rtc.TrackSource.SOURCE_CAMERA
            and self._name(publication) == CAMERA_TRACK_NAME
        )

    def _on_track_subscribed(self, track, publication, participant) -> None:
        self._consider(track, publication, participant)

    def _consider(self, track, publication, participant) -> None:
        if not self._matches(track, publication, participant):
            return
        sid = str(getattr(publication, "sid", "") or "")
        if self._stream is not None and self._publication_sid == sid:
            return
        self._stop_stream()
        try:
            stream = rtc.VideoStream(track)
        except Exception as exc:
            self._latest_frame = None
            diag.emit("video_stream_failed", self.room_name, category="unknown_error",
                      error_type=diag.error_type(exc))
            return
        self._stream = stream
        self._publication_sid = sid
        diag.emit("video_track_detected", self.room_name)
        diag.emit("video_stream_started", self.room_name)
        self._reader = asyncio.create_task(self._read(stream))

    async def _read(self, stream: rtc.VideoStream) -> None:
        try:
            async for event in stream:
                if self._stream is stream:
                    self._latest_frame = event.frame
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._stream is stream:
                self._latest_frame = None
                diag.emit("video_stream_failed", self.room_name, category="unknown_error",
                          error_type=diag.error_type(exc))

    def _on_track_unsubscribed(self, track, publication, participant) -> None:
        if self._matches(track, publication, participant) and self._publication_sid == str(getattr(publication, "sid", "") or ""):
            self._stop_stream()
            diag.emit("video_track_disconnected", self.room_name)

    def _on_track_unpublished(self, publication, participant) -> None:
        if (getattr(participant, "identity", None) == self._applicant_identity
                and getattr(publication, "source", None) == rtc.TrackSource.SOURCE_CAMERA
                and self._name(publication) == CAMERA_TRACK_NAME
                and self._publication_sid == str(getattr(publication, "sid", "") or "")):
            self._stop_stream()
            diag.emit("video_track_disconnected", self.room_name)

    def take_latest_image(self) -> ImageContent | None:
        """Consume at most one frame for one accepted applicant answer turn."""
        if not self.enabled:
            self._latest_frame = None
            return None
        frame, self._latest_frame = self._latest_frame, None
        if frame is None:
            return None
        try:
            return ImageContent(image=frame, inference_width=CAMERA_INFERENCE_WIDTH,
                                inference_height=CAMERA_INFERENCE_HEIGHT, inference_detail="low")
        except Exception as exc:
            diag.emit("image_attachment_failed", self.room_name, category="unknown_error",
                      error_type=diag.error_type(exc))
            return None

    def _stop_stream(self) -> None:
        reader, self._reader = self._reader, None
        stream, self._stream = self._stream, None
        self._publication_sid = None
        self._latest_frame = None
        if reader is not None:
            reader.cancel()
        if stream is not None:
            task = asyncio.create_task(stream.aclose())
            task.add_done_callback(lambda _: None)

    async def aclose(self) -> None:
        room, self._room = self._room, None
        if room is not None:
            room.off("track_subscribed", self._on_track_subscribed)
            room.off("track_unsubscribed", self._on_track_unsubscribed)
            room.off("track_unpublished", self._on_track_unpublished)
        reader, self._reader = self._reader, None
        stream, self._stream = self._stream, None
        self._publication_sid = None
        self._latest_frame = None
        if reader is not None:
            reader.cancel()
            try:
                await reader
            except (asyncio.CancelledError, Exception):
                pass
        if stream is not None:
            try:
                await stream.aclose()
            except Exception:
                pass

#: Spoken first, through TTS only (state INTRO), and NOT interruptible:
#: LiveKit discards a user turn that ends while it plays. So it is short, and
#: it ends by telling the applicant exactly when to speak - after the first
#: question, which follows immediately. {count} is the plan length.
WELCOME = ("Hi, welcome to your SmartHR interview. There are {count} questions - "
           "please answer after each one. Here is the first.")
#: The same welcome once the job is known (Phase 4). {title} is jobs.title.
WELCOME_FOR_ROLE = (
    "Hi, welcome to your SmartHR interview for the {title} position. "
    "There are {count} questions - please answer after each one. Here is the first."
)
#: Said before Q1 when the applicant spoke during the welcome (VAD heard
#: them; LiveKit dropped the words): why there was no reply, and that the
#: question is coming now.
SPOKE_DURING_WELCOME = "Sorry, I couldn't hear you while I was speaking."
#: Said once after a long silence (state SPEAKING, no model call).
SILENCE_NUDGE = "Take your time. Whenever you're ready, I'm listening."
#: Said when the session's time limit is reached (state ENDING).
CLOSING = "Thank you for your time today. That's the end of this practice interview. Goodbye."
#: Said when the Question Bank could not be loaded - the interview does not
#: go ahead on improvised questions.
PLAN_UNAVAILABLE = (
    "I'm sorry - the interview questions could not be loaded right now, so we can't "
    "continue this interview. Please try again a little later. Goodbye."
)

#: Marks the controller's per-reply instruction in the chat context, so
#: `llm_node` can find it without any shared mutable state.
DIRECTIVE_KEY = "smarthr_directive"

INSTRUCTIONS = """You are the SmartHR AI interviewer conducting a structured, spoken job interview.

The interview questions come from SmartHR's Question Bank and are asked by the
interview system, not by you. Your job between questions is small:
- follow the [Interview controller] instruction attached to each reply exactly;
- keep what you say brief and natural - this is spoken aloud;
- never invent interview questions of your own and never change the topic.

Rules:
- Do not evaluate, score or judge the applicant, and never discuss hiring decisions.
- Do not invent facts about the job, the company or the applicant.
- Plain spoken sentences only - no lists, markdown, emojis or symbols.
- When no session language is specified, answer in the language the applicant uses."""

SESSION_LANGUAGE_INSTRUCTIONS = {
    "en": "For this interview, answer in English, regardless of the language used in the applicant's replies.",
    "ar": "For this interview, answer in Arabic, regardless of the language used in the applicant's replies.",
}


def build_instructions(
    job: JobContext | None,
    cv: CvContext | None = None,
    *,
    cv_block: bool = False,
    matching: MatchingContext | None = None,
    matching_block: bool = False,
    language: str | None = None,
) -> str:
    """The base rules, plus the role (Phase 4), the CV (Phase 5) and the
    existing matching result (Phase 6).

    `cv_block=False` reproduces the Phase 4 instructions exactly, and
    `matching_block=False` the Phase 5 ones. The worker passes True for both,
    so a session with no (or not yet loaded) CV or match is told so
    explicitly rather than left to guess.
    """
    text = INSTRUCTIONS
    prompt_language = (
        "ar" if isinstance(language, str) and language.casefold().startswith("ar")
        else "en" if isinstance(language, str) and language.casefold().startswith("en")
        else None
    )
    if prompt_language is not None:
        text += "\n\n" + SESSION_LANGUAGE_INSTRUCTIONS[prompt_language]
    if job is not None:
        text += "\n\n" + instructions_block(job)
    if cv_block:
        text += "\n\n" + cvmod.instructions_block(cv)
    if matching_block:
        text += "\n\n" + matchmod.instructions_block(matching)
    return text


#: Every directive kind a reply can carry. The last four are the turn
#: classifier's non-answer replies (nothing recorded).
DIRECTIVE_KINDS = ("advance", "elaborate", "finish", "follow_up", *NON_ANSWER_NOTES)

#: GPT-4o's first spoken sentence must arrive within this long; otherwise (or
#: on any model error) the reply is a fixed fallback plus the bank text, so a
#: turn never ends in silence. The whole acknowledgement is one or two
#: sentences, normally well under two seconds.
LLM_FIRST_SENTENCE_TIMEOUT_S = 6.0


def find_directive(chat_ctx: llm.ChatContext) -> Directive | None:
    """The controller's directive for THIS reply: a system message after the
    applicant's latest turn. Anything older belongs to a previous reply."""
    for item in reversed(chat_ctx.items):
        role = getattr(item, "role", None)
        if role == "user":
            return None
        if role == "system":
            data = (getattr(item, "extra", None) or {}).get(DIRECTIVE_KEY)
            if isinstance(data, dict) and data.get("kind") in DIRECTIVE_KINDS:
                return Directive(data["kind"], "", data.get("say_after"),
                                 int(data.get("question_number", 0)))
    return None


def _chunk_text(chunk) -> str | None:
    return chunk if isinstance(chunk, str) else (
        chunk.delta.content if getattr(chunk, "delta", None) else None)


async def _sentences(stream):
    """GPT-4o's streamed reply, one complete sentence at a time."""
    buffer = ""
    async for chunk in stream:
        text = _chunk_text(chunk)
        if not text:
            continue
        buffer += text
        sentences, buffer = split_sentences(buffer)
        for sentence in sentences:
            yield sentence
    if buffer.strip():
        yield buffer.strip()


async def shape_reply(
    stream,
    directive: Directive,
    drop: Callable[[str], bool] | None = None,
    *,
    language: str | None = "en",
):
    """GPT-4o's words, minus any question (and any sentence `drop` rejects),
    plus the bank's text verbatim. A non-answer reply keeps at most ONE
    sentence and has its own fallback; the bank text is then the CURRENT
    question."""
    non_answer = directive.kind in NON_ANSWER_NOTES
    limit = NON_ANSWER_MAX_SENTENCES if non_answer else MAX_ACK_SENTENCES
    kept = 0
    async for sentence in _sentences(stream):
        if is_questionlike(sentence):
            logger.info("dropped a question-like sentence from GPT-4o's acknowledgement")
        elif drop is not None and drop(sentence):
            logger.info("dropped a sentence rejected by the context guards")
        elif kept < limit:
            kept += 1
            yield sentence + " "

    if kept == 0:
        fallback = ("side_reply_fallback" if directive.kind in NON_ANSWER_FALLBACKS else "fallback_ack")
        yield spoken_phrase(fallback, language) + " "
    if directive.say_after:
        yield directive.say_after


async def filter_sentences(
    stream, drop: Callable[[str], bool], *, language: str | None = "en"
):
    """A free reply (elaborate / no directive), sentence by sentence, minus
    the sentences `drop` rejects. Questions are allowed here - an elaboration
    invites more about the current question."""
    for_nothing = True
    async for sentence in _sentences(stream):
        if drop(sentence):
            logger.info("dropped a sentence rejected by the context guards")
            continue
        for_nothing = False
        yield sentence + " "
    if for_nothing:
        yield spoken_phrase("elaboration_fallback", language) + " "


class InterviewerAgent(Agent):
    def __init__(
        self,
        machine: InterviewStateMachine,
        room_name: str = "",
        set_state: Callable[[InterviewState], bool] | None = None,
        on_answer: Callable[[str, str], Directive | None] | None = None,
        job: JobContext | None = None,
        has_open_answer: Callable[[], bool] | None = None,
        cv_enabled: bool = False,
        matching_enabled: bool = False,
        follow_up_candidate: Callable[[str, str], Any] | None = None,
        decide_follow_up: Callable[..., Awaitable[bool]] | None = None,
        adaptive_options: Callable[[str, str], Any] | None = None,
        select_next_question: Callable[..., Awaitable[int | None]] | None = None,
        absorb_unheard: Callable[[], bool] | None = None,
        classify_turn: Callable[..., Awaitable[str]] | None = None,
        non_answer_directive: Callable[[str], Directive | None] | None = None,
        begin_turn: Callable[[int], int] | None = None,
        reply_expected: Callable[[Directive | None], None] | None = None,
        capture: TurnCapture | None = None,
        settle_reply: Callable[[], Awaitable[None]] | None = None,
        on_turn_ignored: Callable[[], None] | None = None,
        language: str | None = None,
    ) -> None:
        super().__init__(instructions=build_instructions(
            job, None, cv_block=cv_enabled, matching_block=matching_enabled, language=language))
        self.job = job
        self.language = language
        #: Phase 5: the CV Context, once the backend has supplied it.
        self.cv: CvContext | None = None
        self.cv_enabled = cv_enabled
        #: Phase 6: SmartHR's existing matching result, once supplied.
        self.matching: MatchingContext | None = None
        self.matching_enabled = matching_enabled
        self.machine = machine
        self.room_name = room_name
        # The controller's set_state, so a transition made here is logged and
        # published like any other. Falls back to the bare machine in tests.
        self.set_state = set_state or machine.to
        # The controller's progression decision for an accepted turn.
        self.on_answer = on_answer
        # True when an answer was cut by a mid-answer pause and reopened: then
        # even a filler-only turn ("uh") is the END of that answer, not noise,
        # and dropping it would leave the interview waiting.
        self.has_open_answer = has_open_answer or (lambda: False)
        # Phase 11.1: the controller's follow-up hooks. Without them no
        # follow-up is ever asked and every turn behaves as before.
        self.follow_up_candidate = follow_up_candidate
        self.decide_follow_up = decide_follow_up
        # Phase 11.2: the controller's adaptive-order hooks. Without them the
        # next main question is always the Question Bank's next one.
        self.adaptive_options = adaptive_options
        self.select_next_question = select_next_question
        # Phase 11.6.2: one turn is decided at a time. A turn that arrives
        # while another is being decided waits, then - if the earlier
        # decision's reply has not started - reopens it (`absorb_unheard`) so
        # both halves become ONE answer with ONE decision.
        self.absorb_unheard = absorb_unheard
        # The utterance classifier's hooks. Without them every turn is an
        # ANSWER, exactly as before.
        self.classify_turn = classify_turn
        self.non_answer_directive = non_answer_directive
        # Observability: a turn id per completed applicant turn, the
        # controller's turn start (returns the VAD speech duration) and its
        # reply watchdog, and the debug-only audio/transcript capture.
        self.begin_turn = begin_turn
        self.reply_expected = reply_expected
        # The controller's wait for a just-interrupted reply to settle, so a
        # re-ask / skip is decided on what actually played before this turn.
        self.settle_reply = settle_reply
        # The controller's re-speak when an ignored turn had cut off the next
        # question (otherwise nobody would say it again).
        self.on_turn_ignored = on_turn_ignored
        self.capture = capture or TurnCapture(room_name, enabled=False)
        self.camera_frames = CameraFrameInput(room_name)
        self._last_decision_was_answer = False
        self.turn_id = 0
        self._turn_meta: dict[str, Any] = {}
        self._turn_lock = asyncio.Lock()

    def start_camera_input(self, room, applicant_identity: str, enabled: bool = False) -> None:
        """Start optional Stage 5 remote-camera receipt after room startup."""
        self.camera_frames.enabled = enabled
        self.camera_frames.start(room, applicant_identity)

    async def close_camera_input(self) -> None:
        await self.camera_frames.aclose()

    async def stt_node(self, audio, model_settings):
        """The default STT, unchanged - with the microphone frames copied to
        the debug capture when (and only when) it is enabled."""
        capture = self.capture

        async def frames():
            async for frame in audio:
                capture.add_frame(frame)
                yield frame

        async for event in Agent.default.stt_node(self, frames() if capture.enabled else audio, model_settings):
            yield event

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        text = new_message.text_content or ""
        kind = classify_utterance(text)
        words = len(text.split())
        self.turn_id += 1
        turn = self.turn_id
        speech_ms = self.begin_turn(turn) if self.begin_turn is not None else None
        confidence = getattr(new_message, "transcript_confidence", None)
        confidence = confidence if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None
        self._turn_meta = {"confidence": confidence, "speech_ms": speech_ms, "started": time.monotonic()}
        # Phase 11.6.5: LiveKit has ended the applicant's turn. Kind and word
        # count only - never the words. The STT stage: confidence, duration.
        diag.emit("turn_finalized", self.room_name, turn=turn, kind=kind, words=words,
                  state=self.machine.state.value)
        diag.emit("stt_turn", self.room_name, turn=turn, words=words,
                  confidence_pct=int(round(confidence * 100)) if confidence is not None else None,
                  speech_ms=speech_ms)
        metrics = getattr(new_message, "metrics", None) or {}
        self.capture.end_turn(turn, start=metrics.get("started_speaking_at"),
                              stop=metrics.get("stopped_speaking_at"), transcript=text,
                              stt_confidence=confidence, speech_ms=speech_ms, word_count=words,
                              utterance_kind=kind)

        if not self.machine.active or self.machine.state == InterviewState.ENDING:
            raise StopResponse()

        if kind in ("empty", "filler") and not self.has_open_answer():
            # Not an answer: GPT-4o is not asked, the interview does not move.
            self.machine.counters.ignored += 1
            logger.info("room=%s turn ignored: %s (%d words)", self.room_name, kind, words)
            diag.emit("turn_ignored", self.room_name, turn=turn, kind=kind, words=words)
            self.capture.update(turn, outcome="ignored (empty or filler only)")
            if self.on_turn_ignored is not None:
                self.on_turn_ignored()
            if self.machine.state == InterviewState.PROCESSING:
                self.set_state(InterviewState.LISTENING)
            raise StopResponse()

        self.machine.nudges_since_speech = 0
        if self.machine.can(InterviewState.PROCESSING):
            self.set_state(InterviewState.PROCESSING)
        diag.emit("processing_started", self.room_name, turn=turn, kind=kind, words=words)

        directive = None
        eligible_for_camera = kind in ("answer", "short")
        if not self.on_answer:
            self._count_answer_turn(kind)
        else:
            async with self._turn_lock:
                if self.settle_reply is not None:
                    await self.settle_reply()
                if self.absorb_unheard is not None and self.absorb_unheard():
                    logger.info("room=%s turn continues an answer whose reply was not heard - merged",
                                self.room_name)
                    diag.emit("turn_merged", self.room_name, turn=turn, kind=kind, words=words)
                directive = await self._decide(kind, text)
                eligible_for_camera = self._last_decision_was_answer
        if directive is not None:
            # Temporary context: seen for this one reply, not kept in history.
            # Plain JSON-safe values only: LiveKit may serialise the context.
            turn_ctx.add_message(role="system", content=directive.note, extra={DIRECTIVE_KEY: {
                "kind": directive.kind,
                "say_after": directive.say_after,
                "question_number": directive.question_number,
            }})
        elif kind == "short":
            turn_ctx.add_message(role="system", content=SHORT_ANSWER_NOTE)

        # Additional context only: one accepted answer can consume one latest
        # frame. A missing or unusable image leaves the normal text turn intact.
        if eligible_for_camera and self.camera_frames.enabled:
            image = self.camera_frames.take_latest_image()
            if image is not None:
                try:
                    new_message.content.append(image)
                except Exception as exc:
                    diag.emit("image_attachment_failed", self.room_name, category="unknown_error",
                              error_type=diag.error_type(exc))

        logger.info("room=%s turn %d accepted: %s (%d words) -> %s", self.room_name, turn, kind, words,
                    directive.kind if directive else "free reply")
        diag.emit("turn_decided", self.room_name, turn=turn, kind=kind, words=words,
                  directive=directive.kind if directive else "free_reply",
                  question=directive.question_number if directive else None,
                  duration_ms=diag.elapsed_ms(self._turn_meta["started"]))
        self.capture.update(turn, directive=directive.kind if directive else "free_reply",
                            question_number=directive.question_number if directive else None,
                            decision_ms=diag.elapsed_ms(self._turn_meta["started"]))
        if self.reply_expected is not None:
            # The reply to this turn must start soon - or a fallback is spoken.
            self.reply_expected(directive)

    def _count_answer_turn(self, kind: str) -> None:
        # A filler reaching this point only completes an open answer; the
        # controller counts the merged answer, so it is not counted here.
        if kind == "short":
            self.machine.counters.short += 1
        elif kind == "answer":
            self.machine.counters.answers += 1

    async def _decide(self, kind: str, text: str) -> Directive | None:
        """The controller's decision for this turn.

        FIRST: is it an answer at all (utterance classifier)? A QUESTION,
        OFF_TOPIC or UNCLEAR turn gets the non-answer directive - the current
        question again - and nothing below runs: no counters, no follow-up or
        adaptive call, no `on_answer`, nothing recorded. An ANSWER (or no
        classifier, or any classifier failure) continues exactly as before:
        the follow-up decision when the main question just answered has an
        eligible follow-up (Phase 11.1), the adaptive choice (11.2), then
        `on_answer`."""
        self._last_decision_was_answer = False
        label = ANSWER
        if self.classify_turn is not None:
            try:
                label = await self.classify_turn(kind, text, self._turn_meta.get("confidence"),
                                                 self._turn_meta.get("speech_ms"))
                self.capture.update(self.turn_id, classification=label)
            except asyncio.CancelledError:
                # As for the decisions below: record it, so a dropped reply is
                # reopened and merged like any other.
                self._count_answer_turn(kind)
                self.on_answer(kind, text)
                raise
        if label != ANSWER and self.non_answer_directive is not None:
            directive = self.non_answer_directive(label)
            if directive is not None:
                return directive
        self._last_decision_was_answer = True
        self._count_answer_turn(kind)

        candidate = (self.follow_up_candidate(kind, text)
                     if self.follow_up_candidate and self.decide_follow_up else None)
        options = None
        try:
            ask = False
            if candidate is not None:
                main, follow_up, answer = candidate
                ask = await self.decide_follow_up(main, follow_up, answer)
            # Phase 11.2: only once the follow-up path has been ruled out.
            choice = None
            if not ask and self.adaptive_options and self.select_next_question:
                options = self.adaptive_options(kind, text)
                if options is not None:
                    main, answer, remaining = options
                    choice = await self.select_next_question(main, answer, remaining)
        except asyncio.CancelledError:
            # The applicant spoke again while it was decided: record the
            # answer anyway, so the controller can reopen and merge it when
            # LiveKit drops this reply, exactly as for any other turn.
            self.on_answer(kind, text)
            raise
        if candidate is None and options is None:
            return self.on_answer(kind, text)
        return self.on_answer(kind, text, ask_follow_up=ask, next_question_id=choice)

    def _current_instructions(self) -> str:
        return build_instructions(self.job, self.cv, cv_block=self.cv_enabled,
                                  matching=self.matching, matching_block=self.matching_enabled,
                                  language=self.language)

    async def set_cv(self, cv: CvContext | None) -> None:
        """Add the CV Context to GPT-4o's instructions (Phase 5)."""
        self.cv = cv
        self.cv_enabled = True
        await self.update_instructions(self._current_instructions())

    async def set_matching(self, matching: MatchingContext | None) -> None:
        """Add SmartHR's existing matching result to GPT-4o's instructions (Phase 6)."""
        self.matching = matching
        self.matching_enabled = True
        await self.update_instructions(self._current_instructions())

    def cites_cv_wrongly(self, sentence: str) -> bool:
        """The code-level guard: a CV citation the CV context does not support.
        The job's own words count as known, so "relevant to the AI Engineering
        Intern role" in the same sentence is not mistaken for a CV claim."""
        job = self.job
        job_words = " ".join([job.title, job.department or "", job.description or "",
                              *job.requirements]) if job else ""
        return cvmod.unsupported_cv_claim(sentence, self.cv, job_words)

    def drops_sentence(self, sentence: str) -> bool:
        """Every code-level guard on GPT-4o's spoken words, in one place."""
        return self.cites_cv_wrongly(sentence) or matchmod.decision_or_score_claim(sentence)

    async def llm_node(self, chat_ctx, tools, model_settings):
        """The reply to a decided turn. Never silent:

        * a FIXED-lead directive (repeat / re-ask / skip) is spoken by code with
          no model call at all;
        * otherwise GPT-4o's words, shaped as before - and if its first
          sentence does not arrive within LLM_FIRST_SENTENCE_TIMEOUT_S, or the
          model fails at any point, the reply is completed with a fixed
          fallback plus the bank text the directive still owes."""
        directive = find_directive(chat_ctx)
        began, turn = time.monotonic(), self.turn_id
        if directive is not None and directive.kind in FIXED_LEADS:
            text = " ".join(t for t in (spoken_phrase(f"fixed_{directive.kind}", self.language),
                                         directive.say_after) if t)
            diag.emit("llm_reply", self.room_name, turn=turn, directive=directive.kind, pieces=1,
                      fallback=False, duration_ms=0)
            self.capture.update(turn, reply=text, reply_source="fixed")
            yield text
            return

        stream = Agent.default.llm_node(self, chat_ctx, tools, model_settings)
        if directive is None or directive.kind == "elaborate":
            shaped = filter_sentences(stream, self.drops_sentence, language=self.language)
        else:
            shaped = shape_reply(stream, directive, drop=self.drops_sentence, language=self.language)
        spoken: list[str] = []
        owed = directive.say_after if directive is not None else None
        code = None
        try:
            while True:
                try:
                    if spoken:
                        piece = await shaped.__anext__()
                    else:
                        piece = await asyncio.wait_for(shaped.__anext__(), LLM_FIRST_SENTENCE_TIMEOUT_S)
                except StopAsyncIteration:
                    break
                spoken.append(piece)
                if owed is not None and piece == owed:
                    owed = None
                yield piece
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # timeout or model error: finish the turn anyway
            code = "timeout" if isinstance(exc, asyncio.TimeoutError) else "model_error"
            logger.warning("room=%s turn %d: GPT reply failed (%s) - fallback spoken",
                           self.room_name, turn, type(exc).__name__)
            try:
                await shaped.aclose()
            except Exception:
                pass
            lead = None
            if not spoken:
                key = ("side_reply_fallback" if directive is not None
                       and directive.kind in NON_ANSWER_NOTES
                       and directive.kind in NON_ANSWER_FALLBACKS else "fallback_ack")
                lead = spoken_phrase(key, self.language)
            text = " ".join(t for t in (lead, owed) if t)
            if text:
                spoken.append(text)
                yield text
        finally:
            diag.emit("llm_reply", self.room_name, turn=turn,
                      directive=directive.kind if directive is not None else "free_reply",
                      pieces=len(spoken), fallback=code is not None, code=code,
                      duration_ms=diag.elapsed_ms(began))
            self.capture.update(turn, reply="".join(spoken).strip(),
                                reply_source="fallback" if code else "gpt", llm_ms=diag.elapsed_ms(began))
