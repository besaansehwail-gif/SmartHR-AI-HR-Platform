"""The AI Interview agent worker - a separate process from the backend.

Run from the repository root:

    venv\\Scripts\\python.exe -m app.ai.interview.worker dev     # development
    venv\\Scripts\\python.exe -m app.ai.interview.worker start   # production mode

The worker connects out to LiveKit Cloud and registers as `AGENT_NAME`. It is
never sent to a room on its own: LiveKit dispatches it only when an applicant
joins with a token whose room configuration asks for this agent by name, and
only SmartHR's backend mints those tokens (`POST /ai-interview/session`).

    job start       -> POST /ai-interview/agent/progress started   (Phase 9:
                                                      interview -> in_progress)
                    -> POST /ai-interview/agent/plan   the Question Bank's questions
                                                      + the room's Job Context
                    -> POST /ai-interview/agent/cv     the candidate's CV Context,
                                                      in the background (Phase 5)
    applicant audio -> VAD (local)          speech started / stopped
                    -> turn detector        finished, or only pausing?
                    -> STT                  the words
                    -> on_user_turn_completed   noise/filler? ignore. otherwise the
                                            controller records the answer against the
                                            current question and decides what is next
                    -> openai/gpt-4o        a one-sentence acknowledgement (filtered)
                    -> + next bank question, appended verbatim by code
                    -> TTS                  the interviewer's voice
    answer final    -> POST /ai-interview/agent/answers   stored by the backend
                                            (Phase 7), when its reply is heard
                                            or when the session ends
    job end         -> POST /ai-interview/agent/progress completed | ended
                                            (Phase 9), after the answers

The interview's own phase (WAITING ... COMPLETED) is kept by
`InterviewStateMachine`, driven by `InterviewController` from LiveKit's
events, and published to the room as participant attributes.

STT, GPT-4o and TTS run through LiveKit Inference, authenticated with the same
LiveKit project credentials - no separate OpenAI key in this process.

**This module does not touch the database** and must not start to. Logging
carries room names, states and counts - never what the applicant said.
"""

import asyncio
import logging

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, APIConnectOptions, inference, room_io
from livekit.agents.voice.agent_session import SessionConnectOptions

from app.ai.interview import diagnostics as diag
from app.ai.interview import turn_policy
from app.ai.interview.spoken import spoken_phrase
from app.ai.interview.agent import InterviewerAgent
from app.ai.interview.answer_client import AnswerSink
from app.ai.interview.config import (
    AGENT_NAME,
    camera_vision_enabled,
    export_livekit_environment,
    interview_setting,
    voice_settings,
)
from app.ai.interview.controller import DEFAULT_MAX_SECONDS, InterviewController
from app.ai.interview.adaptive import grounded_selector
from app.ai.interview.follow_up import ask_model
from app.ai.interview.logging_policy import configure_worker_logging
from app.ai.interview.plan_client import PlanUnavailable, fetch_cv, fetch_matching, fetch_plan
from app.ai.interview.progress_client import (
    END_ATTEMPTS,
    END_PAUSE_S,
    STARTED_ATTEMPTS,
    STARTED_PAUSE_S,
    STARTED_TIMEOUT_S,
    report_progress,
)
from app.ai.interview.questions import QuestionProgress
from app.ai.interview.state import InterviewStateMachine
from app.ai.interview.debug_capture import TurnCapture
from app.ai.interview.utterance import classify_with_model

logger = logging.getLogger("smarthr.interview.worker")

# Phase 10: LiveKit's library logs the applicant's words at DEBUG. Pin its
# logger to INFO and drop any record carrying personal data, before the CLI
# sets up logging (see logging_policy.py).
configure_worker_logging()

# LiveKit's own code reads its credentials from os.environ. Export the three
# LiveKit values (and nothing else) before the server is created, so this
# process and any job process it spawns see the same configuration.
export_livekit_environment()

#: STT models whose Arabic support is not confirmed for this deployment.
ARABIC_UNCONFIRMED_MODELS = frozenset({"deepgram/nova-3"})
ARABIC_TTS_MODELS = frozenset({"cartesia/sonic-3", "cartesia/sonic-3.5"})


def tts_language_for(settings, language: str | None = None) -> str | None:
    """Resolve an explicit TTS language, refusing unverified Arabic models."""
    effective = language if language is not None else settings.language
    if not isinstance(effective, str):
        return None
    lowered = effective.casefold()
    if lowered == "multi":
        return None
    selected = "ar" if lowered == "ar" or lowered.startswith("ar-") else (
        "en" if lowered == "en" or lowered.startswith("en-") else None
    )
    if selected == "ar":
        model = settings.tts_model.split(":", 1)[0].casefold()
        if model not in ARABIC_TTS_MODELS:
            raise ValueError(
                f"Arabic TTS is not verified for configured model {settings.tts_model!r}; "
                "use cartesia/sonic-3 or cartesia/sonic-3.5."
            )
    return selected


def log_stt_configuration(settings=None, language: str | None = None) -> str | None:
    """One metadata line with the effective STT language and model (never a
    credential), and a warning when Arabic is expected on a model whose
    Arabic support is unconfirmed. Returns the warning text, if any."""
    from app.ai.interview.debug_capture import capture_enabled

    settings = settings or voice_settings()
    language = settings.language if language is None else language
    logger.info("stt configuration: language=%s stt=%s tts=%s debug_capture=%s", language,
                settings.stt_model, settings.tts_model, "on" if capture_enabled() else "off")
    if language in ("ar", "multi") and settings.stt_model in ARABIC_UNCONFIRMED_MODELS:
        # Measured with scripts/check_stt_arabic.py (synthetic Arabic clip):
        # nova-3 + multi returned English words / Latin transliteration, nova-3
        # + ar ~77-85% of words, speechmatics/enhanced + ar 100%.
        if language == "multi":
            warning = (f"language=multi on {settings.stt_model} transcribed Arabic speech as English / Latin "
                       "letters when measured - use language=ar, and set SMARTHR_INTERVIEW_STT_MODEL "
                       "(for example speechmatics/enhanced) for Arabic answers.")
        else:
            warning = (f"Arabic on {settings.stt_model} is only partly reliable (measured ~80% of words); "
                       "set SMARTHR_INTERVIEW_STT_MODEL (for example speechmatics/enhanced) for Arabic answers.")
        logger.warning("stt configuration: %s", warning)
        return warning
    return None


# Once per worker process (each job process re-imports this module).
log_stt_configuration()

server = AgentServer()


def max_session_seconds() -> int:
    raw = interview_setting("SMARTHR_INTERVIEW_MAX_SECONDS")
    try:
        value = int(raw) if raw else DEFAULT_MAX_SECONDS
    except ValueError:
        return DEFAULT_MAX_SECONDS
    return value if value > 0 else DEFAULT_MAX_SECONDS


#: The session's GPT-4o calls fail fast instead of LiveKit's default 10 s x 4
#: attempts (~44 s of silence on a failing call - measured as a 51 s gap in a
#: live test). One retry, 6 s each. The agent's own first-sentence fallback
#: (agent.LLM_FIRST_SENTENCE_TIMEOUT_S) and the controller's reply watchdog
#: sit on top of this.
LLM_CONNECT = APIConnectOptions(max_retry=1, retry_interval=0.5, timeout=6.0)


def build_session(language: str | None = None) -> AgentSession:
    """The voice pipeline and its turn-taking, in one place.

    Every number used here is defined and justified in `turn_policy.py`.
    """
    settings = voice_settings()
    if language is not None and language not in {"en", "ar"}:
        raise ValueError("session language must be 'en' or 'ar'")
    stt_language = language or settings.language
    tts_language = tts_language_for(settings, language)
    tts_options = {"language": tts_language} if tts_language is not None else {}

    return AgentSession(
        stt=inference.STT(model=settings.stt_model, language=stt_language),
        llm=inference.LLM(model=settings.llm_model),
        tts=inference.TTS(model=settings.tts_model, **tts_options),
        vad=turn_policy.vad(),
        turn_handling=turn_policy.turn_handling(),
        user_away_timeout=turn_policy.SILENCE_NUDGE_AFTER_S,
        conn_options=SessionConnectOptions(llm_conn_options=LLM_CONNECT),
    )


def _attach_logging(session: AgentSession, room_name: str) -> None:
    """States and counts only - enough to see where a turn stopped."""

    @session.on("agent_state_changed")
    def _agent_state(event) -> None:
        logger.info("room=%s agent %s -> %s", room_name, event.old_state, event.new_state)

    @session.on("user_state_changed")
    def _user_state(event) -> None:
        logger.info("room=%s applicant %s -> %s", room_name, event.old_state, event.new_state)

    @session.on("user_input_transcribed")
    def _transcribed(event) -> None:
        if event.is_final:
            words = len(event.transcript.split())
            logger.info("room=%s STT final transcript: %d words", room_name, words)
            diag.emit("stt_final", room_name, words=words)

    @session.on("agent_false_interruption")
    def _false_interruption(event) -> None:
        logger.info("room=%s false interruption - interviewer resumes", room_name)

    @session.on("error")
    def _error(event) -> None:
        # The error's type and source class name; its message can quote input.
        logger.warning(
            "room=%s pipeline error from %s: %s",
            room_name,
            type(event.source).__name__,
            type(event.error).__name__,
        )
        pipeline_error_diagnostic(room_name, event.source, event.error)

    @session.on("close")
    def _close(event) -> None:
        logger.info("room=%s session closed: %s", room_name, event.reason)
        diag.emit("session_closed", room_name, once=True, reason=diag.close_reason(event.reason))


def pipeline_error_diagnostic(room_name: str, source, error) -> None:
    """Phase 11.6.5: an STT / LLM / TTS failure as a category, the error's
    CLASS name and whether LiveKit will retry it - never its message, which
    can quote what the applicant said or what was sent to the model."""
    recoverable = getattr(error, "recoverable", None)
    diag.emit("pipeline_error", room_name, category=diag.pipeline_category(source, error),
              error_type=diag.error_type(error) if isinstance(error, BaseException) else None,
              recoverable=recoverable if isinstance(recoverable, bool) else None)


def _is_applicant(participant) -> bool:
    return str(getattr(participant, "identity", "")).startswith("applicant-")


def attach_room_diagnostics(room, room_name: str) -> None:
    """Phase 11.6.5: what LiveKit ACTUALLY reports about the room - the
    applicant arriving and leaving, their microphone track being received or
    lost, and this agent's own connection dropping and coming back. No
    identity, name or track name is logged."""

    def audio(track) -> bool:
        return getattr(track, "kind", None) == rtc.TrackKind.KIND_AUDIO

    @room.on("participant_connected")
    def _joined(participant) -> None:
        if _is_applicant(participant):
            diag.emit("applicant_joined", room_name)

    @room.on("participant_disconnected")
    def _left(participant) -> None:
        if _is_applicant(participant):
            diag.emit("applicant_left", room_name)

    @room.on("track_subscribed")
    def _mic_ready(track, publication, participant) -> None:
        if audio(track) and _is_applicant(participant):
            diag.emit("microphone_ready", room_name)

    @room.on("track_unsubscribed")
    def _mic_lost(track, publication, participant) -> None:
        if audio(track) and _is_applicant(participant):
            diag.emit("microphone_lost", room_name, category="microphone_error")

    @room.on("reconnecting")
    def _reconnecting() -> None:
        diag.emit("reconnecting", room_name, category="connection_error")

    @room.on("reconnected")
    def _reconnected() -> None:
        diag.emit("reconnected", room_name)

    @room.on("disconnected")
    def _disconnected(*_args) -> None:
        diag.emit("room_disconnected", room_name)


@server.rtc_session(agent_name=AGENT_NAME)
async def interview_session(ctx: agents.JobContext) -> None:
    """One job = one room = one applicant."""
    room_name = ctx.room.name
    settings = voice_settings()
    limit = max_session_seconds()
    diag.emit("job_received", room_name, once=True)
    logger.info(
        "room=%s job received: stt=%s llm=%s tts=%s limit=%ss",
        room_name,
        settings.stt_model,
        settings.llm_model,
        settings.tts_model,
        limit,
    )

    # Phase 9: tell the backend the interview is starting (-> in_progress).
    # Refused when the room is no longer eligible or a newer session of the
    # same interview exists - and then the interview does not go ahead, the
    # same way as when there is no plan.
    # Phase 11.6.3: a transient failure is retried once; a refusal is final.
    started = await report_progress(room_name, "started", timeout=STARTED_TIMEOUT_S,
                                    attempts=STARTED_ATTEMPTS, pause=STARTED_PAUSE_S)

    # The interview's questions (Question Bank) and the job it is for (room ->
    # interview -> application -> job), both resolved by the backend. The
    # worker never chooses either and never reads the database. Without them
    # the interview does not go ahead: an empty plan makes the controller end.
    questions, job, session_language = [], None, None
    if not started:
        logger.warning("room=%s interview start refused by the backend", room_name)
        diag.emit("session_start_refused", room_name, once=True, category="state_error")
    else:
        try:
            plan = await fetch_plan(room_name)
            questions, job, session_language = plan.questions, plan.job, plan.language
            diag.emit("plan_received", room_name, questions=len(questions),
                      follow_ups=sum(1 for q in questions if getattr(q, "follow_up", None)))
        except PlanUnavailable as exc:
            logger.warning("room=%s interview plan unavailable: %s", room_name, exc)
            diag.emit("plan_unavailable", room_name, operation="plan", category="backend_error",
                      error_type=diag.error_type(exc))

    effective_language = session_language or settings.language
    log_stt_configuration(settings, effective_language)
    machine = InterviewStateMachine()
    session = build_session(effective_language if effective_language in {"en", "ar"} else None)
    # Phase 7: final answers go to the backend, which stores them. Delivery
    # runs beside the conversation and never holds up a turn.
    answers = AnswerSink(room_name)
    _attach_logging(session, room_name)
    attach_room_diagnostics(ctx.room, room_name)

    def llm_failed(operation: str):
        # Phase 11.6.5: why a follow-up / adaptive decision fell back - a code
        # and the exception's class, never the prompt or the model's output.
        return lambda code, exc: diag.emit("llm_error", room_name, operation=operation,
                                           category="llm_error", code=code,
                                           error_type=diag.error_type(exc))

    # `local_participant` exists only once session.start() has connected the
    # room, so it is looked up when publishing, not here.
    controller = InterviewController(
        session,
        machine,
        room_name,
        publish=lambda attributes: ctx.room.local_participant.set_attributes(attributes),
        progress=QuestionProgress(
            questions, closing_text=spoken_phrase("closing_after_last", effective_language)
        ),
        job_title=job.title if job else None,
        on_commit=answers.submit,
        # Phase 11.1: GPT-4o (the session's own model) says only whether a
        # main question's predefined follow-up is asked - never its words.
        follow_up_decider=lambda main, answer, follow_up: ask_model(
            session.llm, main, answer, follow_up, on_error=llm_failed("follow_up")),
        # Phase 11.2: with no follow-up, GPT-4o may pick WHICH remaining main
        # question is next - by Question Bank id only; invalid = bank order.
        # Phase 11.3: grounded in the Job / CV / Matching context the agent
        # already holds (no score, no PII), read at the moment of each choice.
        next_question_selector=lambda main, answer, options: grounded_selector(
            session.llm, agent, on_error=llm_failed("adaptive"))(main, answer, options),
        # Is the turn an answer at all? Asked FIRST; only the label comes back,
        # and anything invalid is ANSWER (the behaviour before this existed).
        utterance_classifier=lambda question, words, is_follow_up: classify_with_model(
            session.llm, question, words, is_follow_up, on_error=llm_failed("classify")),
        language=effective_language,
    )
    controller.attach()

    agent = InterviewerAgent(machine, room_name, set_state=controller.set_state,
                             on_answer=controller.on_answer, job=job,
                             language=effective_language,
                             has_open_answer=controller.has_open_answer, cv_enabled=True,
                             matching_enabled=True,
                             follow_up_candidate=controller.follow_up_candidate,
                             decide_follow_up=controller.decide_follow_up,
                             adaptive_options=controller.adaptive_options,
                             select_next_question=controller.select_next_question,
                             absorb_unheard=controller.absorb_unheard,
                             classify_turn=controller.classify_turn,
                             non_answer_directive=controller.non_answer_directive,
                             begin_turn=controller.begin_turn,
                             reply_expected=controller.reply_expected,
                             settle_reply=controller.settle_reply,
                             on_turn_ignored=controller.turn_ignored,
                             capture=TurnCapture(room_name))
    # The CV is parsed on demand by the backend (seconds), so it is fetched
    # while the welcome and Q1 play, and added to GPT-4o's instructions when
    # it arrives. The existing matching result is computed from that same
    # parse, so it is asked for next. Until each arrives - and if it never
    # does - the instructions say it is not available, so nothing is claimed.
    cv_task = asyncio.ensure_future(_load_candidate_context(agent, room_name)) if questions else None

    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(
            # Voice only. Camera comes after voice is verified.
            video_input=False,
        ),
    )

    # Stage 5 reads the Stage 4A camera publication manually. Do not enable
    # RoomOptions.video_input: that automatic path only forwards frames to a
    # realtime model, while this remains the existing STT -> GPT-4o -> TTS
    # pipeline.
    linked = session.room_io.linked_participant
    if _is_applicant(linked) and camera_vision_enabled():
        agent.start_camera_input(ctx.room, str(linked.identity), enabled=True)
        ctx.add_shutdown_callback(agent.close_camera_input)

    # The agent is in the room now. The applicant is normally there first, so
    # their arrival is reported here as well as by the room events.
    diag.emit("interviewer_joined", room_name, once=True)
    for participant in list(getattr(ctx.room, "remote_participants", {}).values()):
        if _is_applicant(participant):
            diag.emit("applicant_joined", room_name)

    controller.publish()  # WAITING, until the opening starts
    limit_task = asyncio.ensure_future(controller.enforce_time_limit(limit))
    ctx.add_shutdown_callback(lambda: _cancel(limit_task))
    if cv_task is not None:
        ctx.add_shutdown_callback(lambda: _cancel(cv_task))

    async def _deliver_answers() -> None:
        controller.flush_answers()
        await answers.drain()
        logger.info("room=%s answers delivered=%d refused=%d undelivered=%d", room_name,
                    len(answers.delivered), len(answers.refused), len(answers.undelivered))
        diag.emit("answers_summary", room_name, delivered=len(answers.delivered),
                  refused=len(answers.refused), undelivered=len(answers.undelivered))
        # Phase 9: after the answers (a completed interview takes no more),
        # report how it ended - only if this job's start was accepted.
        if started:
            # Phase 11.6.3: retried on a transient failure (bounded to fit the
            # shutdown budget) - a lost "completed" must not leave a finished
            # interview in_progress and, once stale, startable again.
            # Phase 11.6.5: interview_completed / interview_ended are emitted
            # by report_progress only once the backend has accepted the report.
            await report_progress(room_name, "completed" if controller.completed_normally else "ended",
                                  attempts=END_ATTEMPTS, pause=END_PAUSE_S)
        diag.release(room_name)

    ctx.add_shutdown_callback(_deliver_answers)

    await controller.run_opening()


async def _load_candidate_context(agent: InterviewerAgent, room_name: str) -> None:
    await _load_cv(agent, room_name)
    await _load_matching(agent, room_name)


async def _load_cv(agent: InterviewerAgent, room_name: str) -> None:
    try:
        cv = await fetch_cv(room_name)
    except PlanUnavailable as exc:
        logger.warning("room=%s CV context unavailable: %s", room_name, exc)
        diag.emit("context_received", room_name, operation="cv", outcome="unavailable",
                  category="backend_error", error_type=diag.error_type(exc))
        return
    diag.emit("context_received", room_name, operation="cv",
              outcome="available" if cv is not None else "none")
    await agent.set_cv(cv)


async def _load_matching(agent: InterviewerAgent, room_name: str) -> None:
    try:
        matching = await fetch_matching(room_name)
    except PlanUnavailable as exc:
        logger.warning("room=%s matching context unavailable: %s", room_name, exc)
        diag.emit("context_received", room_name, operation="matching", outcome="unavailable",
                  category="backend_error", error_type=diag.error_type(exc))
        return
    diag.emit("context_received", room_name, operation="matching",
              outcome="available" if matching is not None else "unavailable")
    await agent.set_matching(matching)


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()


if __name__ == "__main__":
    # Phase 10: with SMARTHR_ENV=production, refuse dev-only commands, DEBUG
    # logging and command-line credentials (production.py). No-op otherwise.
    import sys

    from app.ai.interview.production import guard_cli

    guard_cli(sys.argv[1:])
    agents.cli.run_app(server)
