"""A real LiveKit AgentSession for offline interview simulations.

No microphone, no LiveKit server, no model. What is REAL: livekit-agents'
AgentSession / AgentActivity (turn scheduling, the chat context, speech
handles, interruptions, agent-state events, the TTS/audio pipeline), and all
of SmartHR's interview code (InterviewerAgent, InterviewController,
QuestionProgress, the turn classifier hook, diagnostics). What is FAKE:

* ScriptLLM   - an llm.LLM whose replies are scripted (text, tool calls,
                errors, hangs), including the classifier / follow-up / adaptive
                tool calls the controller makes through the SAME session.llm;
* SilentTTS   - a tts.TTS producing silent 16 kHz PCM (~25 ms per word), or
                hanging forever ("TTS never starts audio");
* PacedAudio  - an io.AudioOutput that "plays" frames at a scaled real-time
                rate and reports playback started / finished / interrupted,
                exactly the events a room audio track would produce.

A finished applicant turn is injected through LiveKit's own entry point,
`AgentActivity.on_end_of_turn` (what STT + the turn detector call), so
`on_user_turn_completed` and the reply run on LiveKit's scheduler. This uses
two private names (`_activity`, `_EndOfTurnInfo`) - pinned to
livekit-agents 1.8.3.
"""

import asyncio
import json
import time
from typing import Any, Callable

from livekit import rtc
from livekit.agents import APIConnectionError, APIConnectOptions, AgentSession, llm, tts
from livekit.agents.voice import io
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.agents.voice.audio_recognition import _EndOfTurnInfo, _EndOfTurnMetrics

SAMPLE_RATE = 16000
SECONDS_PER_WORD = 0.025


class ScriptLLM(llm.LLM):
    """`script(chat_ctx, tool_names) -> action`:
    ("text", str) | ("tool", name, dict) | ("raise",) | ("hang",) | ("midway", str)."""

    def __init__(self, script: Callable[[llm.ChatContext, list[str]], tuple]):
        super().__init__()
        self.script = script
        self.calls: list[list[str]] = []

    def chat(self, *, chat_ctx, tools=None, conn_options=APIConnectOptions(), parallel_tool_calls=None,
             tool_choice=None, extra_kwargs=None, **_kw):
        return _ScriptStream(self, chat_ctx=chat_ctx, tools=list(tools or []), conn_options=conn_options)


class _ScriptStream(llm.LLMStream):
    async def _run(self) -> None:
        names = [getattr(t, "id", None) or getattr(getattr(t, "info", None), "name", None) or str(t) for t in self._tools]
        self._llm.calls.append(names)
        action = self._llm.script(self._chat_ctx, names)
        kind = action[0]
        if kind == "raise":
            raise APIConnectionError("scripted failure")
        if kind == "hang":
            await asyncio.sleep(3600)
        if kind == "tool":
            _, name, args = action
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=llm.ChoiceDelta(
                role="assistant", tool_calls=[llm.FunctionToolCall(name=name, arguments=json.dumps(args), call_id="t1")])))
            return
        text = action[1]
        if kind == "midway":
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=llm.ChoiceDelta(role="assistant", content=text)))
            await asyncio.sleep(0.05)
            raise APIConnectionError("stream broke")
        for piece in text.split(" "):
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=llm.ChoiceDelta(role="assistant", content=piece + " ")))
            await asyncio.sleep(0)


class SilentTTS(tts.TTS):
    def __init__(self):
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=SAMPLE_RATE, num_channels=1)
        self.hang = False
        self.texts: list[str] = []

    def synthesize(self, text, *, conn_options=APIConnectOptions()):
        self.texts.append(text)
        return _SilentStream(tts=self, input_text=text, conn_options=conn_options)


class _SilentStream(tts.ChunkedStream):
    async def _run(self, output_emitter) -> None:
        if self._tts.hang:
            await asyncio.sleep(3600)
        output_emitter.initialize(request_id="r", sample_rate=SAMPLE_RATE, num_channels=1, mime_type="audio/pcm")
        seconds = max(0.05, SECONDS_PER_WORD * len(self.input_text.split()))
        output_emitter.push(b"\x00\x00" * int(SAMPLE_RATE * seconds))
        output_emitter.flush()


class PacedAudio(io.AudioOutput):
    """Plays at `speed` x real time; reports started / finished / interrupted."""

    def __init__(self, speed: float = 1.0):
        super().__init__(label="paced", capabilities=io.AudioOutputCapabilities(pause=False), sample_rate=SAMPLE_RATE)
        self.speed = speed
        self._pushed = 0.0
        self._started_at: float | None = None
        self._finish: asyncio.Task | None = None

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        await super().capture_frame(frame)
        if self._started_at is None:
            self._started_at = time.monotonic()
            self.on_playback_started(created_at=time.time())
        self._pushed += frame.duration

    def flush(self) -> None:
        super().flush()
        if self._started_at is None:
            return
        remaining = max(0.0, self._pushed / self.speed - (time.monotonic() - self._started_at))
        self._finish = asyncio.ensure_future(self._finished_after(remaining))

    async def _finished_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        position, self._pushed, self._started_at = self._pushed, 0.0, None
        self.on_playback_finished(playback_position=position, interrupted=False)

    def clear_buffer(self) -> None:
        if self._started_at is None:
            return
        if self._finish is not None:
            self._finish.cancel()
        played = min(self._pushed, (time.monotonic() - self._started_at) * self.speed)
        self._pushed, self._started_at = 0.0, None
        self.on_playback_finished(playback_position=played, interrupted=True)


class NullText(io.TextOutput):
    """The end of the transcription chain (the room would publish it)."""

    def __init__(self):
        super().__init__(label="null-text", next_in_chain=None)

    async def capture_text(self, text: str) -> None:
        return None

    def flush(self) -> None:
        return None


def llm_connect():
    """The worker's own GPT-call options (6 s, one retry)."""
    from app.ai.interview.worker import LLM_CONNECT

    return LLM_CONNECT


async def start_interview(questions, script, *, room="smarthr-ai-interview-sim0001", speed=4.0,
                          labels: dict[str, str] | None = None, decider=None, selector=None, synced: bool = False):
    """A started session + the worker's wiring. Returns a namespace."""
    from types import SimpleNamespace

    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine
    from app.ai.interview.utterance import classify_with_model

    model = ScriptLLM(script)
    voice = SilentTTS()
    session = AgentSession(llm=model, tts=voice, conn_options=SessionConnectOptions(llm_conn_options=llm_connect()))
    audio = PacedAudio(speed)
    if synced:
        # As in a room: LiveKit's own transcript synchronizer between the
        # reply and the audio, so an interrupted reply is recorded as only
        # the words actually played.
        from livekit.agents.voice.transcription.synchronizer import TranscriptSynchronizer

        sync = TranscriptSynchronizer(next_in_chain_audio=audio, next_in_chain_text=NullText())
        session.output.audio = sync.audio_output
        session.output.transcription = sync.text_output
    else:
        session.output.audio = audio
    machine = InterviewStateMachine()
    committed: list = []
    published: list = []
    events: list[tuple[float, str, Any]] = []

    async def publish(attrs):
        published.append(attrs)

    controller = InterviewController(
        session, machine, room, publish=publish, progress=QuestionProgress(list(questions)),
        on_commit=committed.extend, follow_up_decider=decider, next_question_selector=selector,
        utterance_classifier=lambda q, w, f: classify_with_model(session.llm, q, w, f))
    controller.attach()
    agent = InterviewerAgent(machine, room, set_state=controller.set_state, on_answer=controller.on_answer,
                             has_open_answer=controller.has_open_answer,
                             follow_up_candidate=controller.follow_up_candidate,
                             decide_follow_up=controller.decide_follow_up,
                             adaptive_options=controller.adaptive_options,
                             select_next_question=controller.select_next_question,
                             absorb_unheard=controller.absorb_unheard, classify_turn=controller.classify_turn,
                             non_answer_directive=controller.non_answer_directive,
                             begin_turn=controller.begin_turn, reply_expected=controller.reply_expected,
                             settle_reply=controller.settle_reply, on_turn_ignored=controller.turn_ignored)
    t0 = time.monotonic()
    session.on("agent_state_changed", lambda ev: events.append((time.monotonic() - t0, "agent", ev.new_state)))
    session.on("conversation_item_added", lambda ev: events.append(
        (time.monotonic() - t0, "item", (ev.item.role, ev.item.text_content, getattr(ev.item, "interrupted", False))))
        if getattr(ev.item, "type", None) == "message" else None)
    await session.start(agent)
    return SimpleNamespace(session=session, agent=agent, controller=controller, machine=machine, model=model,
                           tts=voice, audio=audio, committed=committed, published=published, events=events, t0=t0)


def end_turn(sim, text: str, confidence: float = 0.95) -> bool:
    """Commit one applicant turn through LiveKit's own end-of-turn entry point."""
    now = time.time()
    info = _EndOfTurnInfo(skip_reply=False, new_transcript=text, transcript_confidence=confidence,
                          metrics=_EndOfTurnMetrics(started_speaking_at=now - 2.0, stopped_speaking_at=now - 0.4,
                                                    transcription_delay=0.2, end_of_turn_delay=0.4))
    return sim.session._activity.on_end_of_turn(info)


async def turn_and_reply(sim, text: str, timeout: float = 15.0, confidence: float = 0.95) -> str | None:
    """Commit a turn and wait until its reply has finished playing (a new
    assistant item, then listening). Returns the reply text, or None."""
    before = len(spoken(sim))
    end_turn(sim, text, confidence)
    ok = await wait_for(lambda: len(spoken(sim)) > before and sim.session.agent_state == "listening", timeout)
    return spoken(sim)[-1] if ok else None


async def cut_reply(sim, after: float, *, barge_in: bool, timeout: float = 10.0) -> bool:
    """Wait for the interviewer's reply to START, let it play `after`
    seconds, then cut it off: as a barge-in (VAD reports the applicant
    speaking, then LiveKit interrupts - what a real barge-in does) or as a
    playback failure (interrupted with nobody talking). The applicant stays
    "speaking" after a barge-in until `stop_talking`."""
    if not await wait_for(lambda: sim.session.agent_state == "speaking", timeout):
        return False
    await asyncio.sleep(after)
    if barge_in:
        sim.session._update_user_state("speaking")
    sim.session.interrupt()
    return True


def stop_talking(sim) -> None:
    sim.session._update_user_state("listening")


def IS_HEARD(played: str, owed: str) -> bool:
    """The controller's own heard-rule, for tests: the whole owed text is in
    what LiveKit recorded as played."""
    from app.ai.interview.controller import InterviewController
    return InterviewController._norm(owed) in InterviewController._norm(played)


def sent(sim) -> list[tuple[int, str]]:
    """Answers handed to the backend (question id, words), in order."""
    return [(r.question_id, r.text) for r in sim.committed]


def spoken(sim) -> list[str]:
    """What the interviewer said (assistant items, as LiveKit recorded them)."""
    return [e[2][1] for e in sim.events if e[1] == "item" and e[2][0] == "assistant"]


async def wait_for(predicate, timeout: float = 10.0, step: float = 0.02) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        await asyncio.sleep(step)
    return predicate()
