"""AI Interview - Phase 11.6.5 voice session observability. Deterministic, offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_observability

No LiveKit, no model, no microphone, no real interview. The REAL agent turn
gate, controller, QuestionProgress, state machine, answer sink, progress
client and the worker's own room / pipeline handlers run against fakes that
deliver the events LiveKit would. The backend half (session created, stale
session refused, answers stored, completion accepted) runs the REAL services
and route functions in process against ONE temporary interview on
applicant10's fixture application, deleted at the end - agent tokens are
minted locally, nothing is sent to LiveKit.

Every diagnostic record is captured from the `smarthr.interview.diag` logger
and every log line of the run from the root logger (DEBUG), and fake
transcripts, PII, tokens and error messages are fed into every diagnostic
path. None of them may appear in any line.
"""

import ast
import asyncio
import logging
import secrets
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_ai_interview_turn_taking import LONG, Session, plan, turn  # noqa: E402

passed = 0
failed: list[str] = []
MARK = "OBSERVABILITY TEST"
CREATED: list[int] = []

# The values that must never reach a log line.
SECRET_TRANSCRIPT = "synthetic-transcript-marker"
EMAIL = "candidate@example.com"
PHONE = "+1-202-555-0102"
BEARER = "Bearer SECRET"
CTX_TOKEN = "synthetic-context-marker"
CV_TEXT = "private CV text"
SECRETS = [SECRET_TRANSCRIPT, EMAIL, PHONE, BEARER, CTX_TOKEN, CV_TEXT]
SENSITIVE_ANSWER = (f"{SECRET_TRANSCRIPT} I rebuilt the pipeline, write to {EMAIL} or call {PHONE}, "
                    f"my {CV_TEXT} says so, {BEARER} {CTX_TOKEN}.")
ERROR_MESSAGE = f"provider failed on prompt '{SECRET_TRANSCRIPT}' for {EMAIL} {PHONE} {BEARER} {CTX_TOKEN} {CV_TEXT}"
EXTRA_SECRETS: list[str] = []      # minted tokens, LiveKit key/secret - checked, never printed


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.records: list[dict] = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))
        diag = getattr(record, "smarthr_diag", None)
        if diag is not None:
            self.records.append(dict(diag))


CAP = Capture()


def room_name(tag: str) -> str:
    return f"smarthr-ai-interview-{tag}{secrets.token_hex(5)}"


def recs(room: str) -> list[dict]:
    return [r for r in CAP.records if r.get("room") == room]


def names(room: str) -> list[str]:
    return [r["event"] for r in recs(room)]


def find(room: str, event: str, **match) -> list[int]:
    """Positions (in this room's records) of `event` with the given fields."""
    return [i for i, r in enumerate(recs(room))
            if r["event"] == event and all(r.get(k) == v for k, v in match.items())]


def first(room: str, event: str, **match) -> int:
    hits = find(room, event, **match)
    return hits[0] if hits else -1


def in_order(room: str, *steps) -> bool:
    """Each (event, fields) step occurs, strictly after the previous one."""
    at = -1
    for step in steps:
        event, match = (step, {}) if isinstance(step, str) else step
        later = [i for i in find(room, event, **match) if i > at]
        if not later:
            return False
        at = later[0]
    return True


def two():
    from app.ai.interview.questions import PlannedQuestion as Q
    return [Q(11, 1, "general", "Tell me about yourself."), Q(12, 2, "behavioral", "Describe a challenge you faced.")]


def rig(room, questions=None, decider=None, selector=None, on_commit=None):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine

    m = InterviewStateMachine()
    s = Session()
    committed: list = []

    async def publish(_attrs):
        return None

    c = InterviewController(s, m, room, publish=publish, progress=QuestionProgress(list(two() if questions is None else questions)),
                            on_commit=on_commit or committed.extend, follow_up_decider=decider,
                            next_question_selector=selector)
    a = InterviewerAgent(m, room, set_state=c.set_state, on_answer=c.on_answer, has_open_answer=c.has_open_answer,
                         follow_up_candidate=c.follow_up_candidate, decide_follow_up=c.decide_follow_up,
                         adaptive_options=c.adaptive_options, select_next_question=c.select_next_question,
                         absorb_unheard=c.absorb_unheard)
    return m, s, c, a, committed


class Emitter:
    """A LiveKit-style event emitter: `.on(name)` as decorator or with a callback."""

    def __init__(self):
        self.handlers: dict[str, list] = {}

    def on(self, name, callback=None):
        if callback is None:
            def deco(fn):
                self.handlers.setdefault(name, []).append(fn)
                return fn
            return deco
        self.handlers.setdefault(name, []).append(callback)
        return callback

    def fire(self, name, *args):
        for fn in self.handlers.get(name, []):
            fn(*args)


async def report(room, event, statuses, **kw):
    """The REAL report_progress against a fake transport."""
    from app.ai.interview import progress_client as pc
    queue = list(statuses)

    async def fake_send(_room, _event, _timeout):
        s = queue.pop(0)
        if isinstance(s, BaseException):
            raise s
        return s
    real_send, real_settings = pc._send, pc.voice_settings
    pc._send, pc.voice_settings = fake_send, (lambda: SimpleNamespace(configured=True))
    try:
        return await pc.report_progress(room, event, pause=0, **kw)
    finally:
        pc._send, pc.voice_settings = real_send, real_settings


def sink_for(room, statuses, marks=None):
    """The REAL AnswerSink against a fake POST (and no retry pauses)."""
    import app.ai.interview.answer_client as ac
    from app.ai.interview.answer_client import AnswerSink
    queue = list(statuses)

    async def post(payload):
        if marks is not None:
            marks.append((payload["sequence"], len(recs(room))))
        s = queue.pop(0) if queue else 200
        if isinstance(s, BaseException):
            raise s
        return s
    ac.RETRY_DELAYS_S = (0.0, 0.0)
    return AnswerSink(room, post=post)


# -- 1. The emitter itself -----------------------------------------------------------------------

def test_emitter() -> None:
    section("1. The emitter: allow-listed fields, closed vocabularies, never raises")
    from app.ai.interview import diagnostics as diag
    from app.ai.interview.state import InterviewState

    check("the diagnostic state vocabulary is exactly the interview state machine's",
          diag.STATES == {s.value for s in InterviewState})
    room = room_name("emit")
    rec = diag.emit("state_changed", room, state="listening", question=2, transcript=SENSITIVE_ANSWER,
                    text=CV_TEXT, email=EMAIL, headers={"Authorization": BEARER})
    check("unknown fields (transcript, text, email, headers) are dropped, not logged",
          rec is not None and not {"transcript", "text", "email", "headers"} & set(rec))
    check("known fields kept, with the room, source, counter and timing",
          rec["state"] == "listening" and rec["question"] == 2 and rec["room"] == room
          and rec["source"] == "worker" and rec["n"] == 1 and isinstance(rec["t_ms"], int))
    rec = diag.emit("pipeline_error", room, state=SECRET_TRANSCRIPT, category=EMAIL, code=CTX_TOKEN,
                    error_type=BEARER, reason=PHONE, outcome=CV_TEXT, operation="answer; drop")
    check("a sensitive value in ANY string field is replaced by 'redacted'",
          all(rec[k] == diag.REDACTED for k in ("state", "category", "code", "error_type", "reason",
                                                 "outcome", "operation")), str(rec))
    rec = diag.emit("answer_retry", room, sequence="3", attempt=True, question=-1, words=2.5)
    check("numbers must be plain non-negative ints (no strings, bools, negatives, floats)",
          all(rec[k] == diag.REDACTED for k in ("sequence", "attempt", "question", "words")))
    check("an unknown event name is refused (nothing logged)", diag.emit("said_" + SECRET_TRANSCRIPT, room) is None)
    check("a room that is not a SmartHR interview room is redacted",
          diag.emit("reconnecting", f"room-of-{EMAIL}")["room"] == diag.REDACTED)
    check("'once' events are written once per room",
          diag.emit("interviewer_joined", room, once=True) is not None
          and diag.emit("interviewer_joined", room, once=True) is None)
    ns = [r["n"] for r in recs(room)]
    check("the per-room counter orders every event", ns == list(range(1, len(ns) + 1)), str(ns))
    diag.release(room)
    check("release() forgets the room (a new job starts at n=1)", diag.emit("job_received", room)["n"] == 1)

    exc = RuntimeError(ERROR_MESSAGE)
    check("error_type is the exception CLASS, never its message", diag.error_type(exc) == "RuntimeError")
    check("exception codes come from the type: timeout / network / other",
          diag.exception_code(TimeoutError(ERROR_MESSAGE)) == "timeout"
          and diag.exception_code(asyncio.TimeoutError()) == "timeout"
          and diag.exception_code(ConnectionError(ERROR_MESSAGE)) == "network"
          and diag.exception_code(OSError()) == "network" and diag.exception_code(exc) == "other")
    check("HTTP statuses become http_NNN", diag.http_code(503) == "http_503" and diag._code("http_409"))

    class STT: pass                                    # noqa: E701
    class TTS: pass                                    # noqa: E701
    class LLM: pass                                    # noqa: E701
    check("pipeline errors are categorised by component",
          diag.pipeline_category(STT(), exc) == "stt_error" and diag.pipeline_category(TTS(), exc) == "tts_error"
          and diag.pipeline_category(LLM(), exc) == "llm_error"
          and diag.pipeline_category(object(), exc) == "unknown_error")
    check("close reasons map onto a closed set (anything else is 'other')",
          diag.close_reason("participant_disconnected") == "participant_disconnected"
          and diag.close_reason(SimpleNamespace(value="user_initiated")) == "user_initiated"
          and diag.close_reason(BEARER) == "other")

    real = diag.logger.info

    def broken(*_a, **_k):
        raise RuntimeError("logging is down")
    diag.logger.info = broken
    try:
        m, s, c, a, _ = rig(room_name("broken"))
        survived = diag.emit("job_received", room) is None and c.set_state(InterviewState.INTRO) is True
    except Exception:
        survived = False
    finally:
        diag.logger.info = real
    check("a failing diagnostics log never breaks the interview (emit returns None, the state moves)", survived)


# -- 2. Normal lifecycle -------------------------------------------------------------------------

def test_lifecycle() -> None:
    section("2. A normal interview: every event in the order it happened")
    room = room_name("life")
    marks: list = []

    async def run():
        sink = sink_for(room, [], marks)
        m, s, c, a, _ = rig(room, two(), on_commit=sink.submit)
        await c.run_opening()
        c.on_user_state("speaking")
        await turn(a, LONG)
        c.on_agent_state("thinking")
        snapshot = names(room)
        c.on_agent_state("speaking")                      # the reply (ack + Q2) starts playing
        await sink.drain(2)
        c.on_agent_state("listening")
        c.on_user_state("speaking")
        await turn(a, "I paired with a colleague and we traced the failing job together.")
        c.on_agent_state("speaking")                      # the closing line starts playing
        c.on_agent_state("listening")                     # ...and has been spoken
        c.flush_answers()
        await sink.drain(2)
        ok = await report(room, "completed", [200], attempts=2)
        return snapshot, c, ok
    snapshot, c, ok = asyncio.run(run())

    check("the opening: intro, Q1 asked, Q1 spoken - in that order",
          in_order(room, ("state_changed", {"state": "intro"}), ("state_changed", {"state": "asking"}),
                   ("question_spoken", {"question": 1})))
    check("an applicant turn: started -> finalized -> processing -> decided",
          in_order(room, ("question_spoken", {"question": 1}), "turn_started", ("turn_finalized", {"kind": "answer"}),
                   "processing_started", ("turn_decided", {"directive": "advance", "question": 2})))
    check("Q2 is NOT reported spoken while its reply has only been decided",
          "question_spoken" in snapshot and snapshot.count("question_spoken") == 1)
    check("the answer is final when the reply is heard, then Q2 is spoken",
          in_order(room, ("turn_decided", {"directive": "advance"}), ("interviewer_speaking", {}),
                   ("answer_committed", {"sequence": 1, "question": 1}), ("question_spoken", {"question": 2})))
    check("each question is reported spoken exactly once",
          len(find(room, "question_spoken", question=1)) == 1 and len(find(room, "question_spoken", question=2)) == 1)
    persisted = {r["sequence"]: i for i, r in enumerate(recs(room)) if r["event"] == "answer_persisted"}
    committed = {r["sequence"]: i for i, r in enumerate(recs(room)) if r["event"] == "answer_committed"}
    check("both answers persisted, each after it was committed",
          set(persisted) == {1, 2} and all(persisted[s] > committed[s] for s in (1, 2)))
    check("'answer_persisted' is written only AFTER the backend call returned",
          all(persisted[seq] >= at for seq, at in marks), str(marks))
    check("the end: ENDING (last question) -> finished normally -> completion accepted -> completed",
          ok and in_order(room, ("interview_ending", {"reason": "last_question"}),
                          ("interview_finished", {"completed_normally": True}),
                          ("progress_accepted", {"operation": "progress_completed", "attempt": 1}),
                          ("interview_completed", {"progress_event": "completed"})))
    check("no 'ended' for an interview that completed", not find(room, "interview_ended"))
    ns = [r["n"] for r in recs(room)]
    ts = [r["t_ms"] for r in recs(room)]
    check("the room's events are numbered 1..N with non-decreasing time",
          ns == list(range(1, len(ns) + 1)) and ts == sorted(ts))
    check("every worker event carries the room (the correlation key)",
          all(r.get("room") == room and r["source"] == "worker" for r in recs(room)))


# -- 3. Applicant turns --------------------------------------------------------------------------

def test_turns() -> None:
    section("3. Applicant turns: ignored, STT-empty, merged")
    room = room_name("turn")

    async def run():
        m, s, c, a, committed = rig(room)
        await c.run_opening()
        c.on_user_state("speaking")
        await turn(a, "um")
        after_filler = names(room)
        await turn(a, "")                                  # STT delivered nothing
        await turn(a, "At my last job I rebuilt the forecasting pipeline")
        await turn(a, "after it failed, and I documented every step for the team.")   # reply not heard yet
        c.on_agent_state("speaking")
        return after_filler, committed
    after_filler, committed = asyncio.run(run())
    check("a filler turn: finalized, then ignored - never 'processing'",
          in_order(room, ("turn_finalized", {"kind": "filler"}), ("turn_ignored", {"kind": "filler"}))
          and after_filler[-1] == "turn_ignored" and after_filler.count("processing_started") == 0)
    check("an empty STT result: finalized as 'empty', ignored, nothing decided",
          in_order(room, ("turn_finalized", {"kind": "empty", "words": 0}), ("turn_ignored", {"kind": "empty"})))
    check("a turn that continues an unheard answer is reported merged",
          len(find(room, "turn_merged")) == 1 and in_order(room, "turn_decided", "turn_merged", "turn_decided"))
    check("...and the two halves become ONE committed answer",
          len(find(room, "answer_committed")) == 1 and len(committed) == 1)
    check("turn events carry kind and word counts only (plus the turn id and its duration)",
          all(set(r) <= {"event", "source", "room", "n", "t_ms", "kind", "words", "state", "directive", "question",
                         "turn", "duration_ms"}
              for r in recs(room) if r["event"].startswith("turn_")))


# -- 4. Answer persistence -----------------------------------------------------------------------

def test_answers() -> None:
    section("4. Answer persistence: retries, refusals, failure, drain")
    from app.ai.interview.questions import AnswerRecord

    def record(seq):
        r = AnswerRecord(11, 1, SENSITIVE_ANSWER, "answer", len(SENSITIVE_ANSWER.split()))
        r.sequence = seq
        return r

    async def deliver(room, statuses, drain=2.0):
        sink = sink_for(room, statuses)
        sink.submit([record(1)])
        await sink.drain(drain)
        return sink

    room = room_name("ans")
    asyncio.run(deliver(room, [503, ConnectionError(ERROR_MESSAGE), 200]))
    check("503 then a network error: two retries, then persisted on attempt 3",
          in_order(room, ("answer_retry", {"attempt": 1, "code": "http_503", "category": "answer_persistence_error"}),
                   ("answer_retry", {"attempt": 2, "code": "network"}),
                   ("answer_persisted", {"attempt": 3, "sequence": 1, "outcome": "delivered"})))
    check("...operation named, and never the body", all(r.get("operation") == "answer" for r in recs(room)))
    room = room_name("ans")
    asyncio.run(deliver(room, [409]))
    check("a refusal is reported once, not retried, not persisted",
          names(room) == ["answer_refused"] and recs(room)[0]["code"] == "http_409")
    room = room_name("ans")
    asyncio.run(deliver(room, [TimeoutError(ERROR_MESSAGE)] * 3))
    check("still failing: retry, retry, then 'answer_failed' - never 'answer_persisted'",
          names(room) == ["answer_retry", "answer_retry", "answer_failed"]
          and recs(room)[-1]["attempts"] == 3 and recs(room)[-1]["code"] == "timeout")
    room = room_name("ans")

    async def slow_drain():
        from app.ai.interview.answer_client import AnswerSink

        async def post(_payload):
            await asyncio.sleep(1)
            return 200
        sink = AnswerSink(room, post=post)
        sink.submit([record(1)])
        await sink.drain(0.01)
    asyncio.run(slow_drain())
    check("a drain that runs out of time is reported, with the count left",
          find(room, "answer_drain_timeout", pending=1, code="timeout") != [] and not find(room, "answer_persisted"))


# -- 5 / 6. Model decisions ----------------------------------------------------------------------

class _Empty:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def aclose(self):
        return None


class _Slow(_Empty):
    async def __anext__(self):
        await asyncio.sleep(5)
        raise StopAsyncIteration


class _Model:
    def __init__(self, mode):
        self.mode = mode

    def chat(self, **_kw):
        if self.mode == "raise":
            raise RuntimeError(ERROR_MESSAGE)
        return _Slow() if self.mode == "slow" else _Empty()


def test_follow_up() -> None:
    section("5. Follow-up decisions: started -> completed -> decided -> spoken")
    room = room_name("fu")

    async def yes(*_a):
        return True

    async def run(decider):
        m, s, c, a, _ = rig(room, plan(), decider=decider)
        await c.run_opening()
        await turn(a, LONG)
        c.on_agent_state("speaking")
    asyncio.run(run(yes))
    check("decision started -> completed (ask) -> turn decided (follow_up) -> the follow-up is spoken",
          in_order(room, ("state_changed", {"state": "follow_up_decision"}),
                   ("followup_decision_started", {"question": 1, "question_id": 11}),
                   ("followup_decision_completed", {"outcome": "ask", "fallback": False}),
                   ("turn_decided", {"directive": "follow_up"}), ("question_spoken", {"question": 1})))
    check("the decision's duration is recorded", isinstance(recs(room)[first(room, "followup_decision_completed")]
                                                            .get("duration_ms"), int))

    room = room_name("fu")

    async def boom(*_a):
        raise RuntimeError(ERROR_MESSAGE)
    asyncio.run(run(boom))
    check("a failing model: llm_error (class, code) -> completed as a fallback 'move on'",
          in_order(room, "followup_decision_started",
                   ("llm_error", {"operation": "follow_up", "category": "llm_error", "error_type": "RuntimeError",
                                  "code": "other"}),
                   ("followup_decision_completed", {"outcome": "move_on", "fallback": True})))

    from app.ai.interview import diagnostics as diag
    from app.ai.interview.follow_up import ask_model
    room = room_name("fu")

    def on_error(code, exc):     # exactly what the worker's llm_failed("follow_up") emits
        diag.emit("llm_error", room, operation="follow_up", category="llm_error", code=code,
                  error_type=diag.error_type(exc))

    async def model_paths():
        return [await ask_model(_Model(mode), "Tell me about yourself.", SENSITIVE_ANSWER, "And then?",
                                timeout=0.05, on_error=on_error) for mode in ("raise", "slow", "empty")]
    results = asyncio.run(model_paths())
    check("inside ask_model: provider error / timeout / unusable reply each reported by code",
          results == [False, False, False]
          and [r.get("code") for r in recs(room)] == ["model_error", "timeout", "unusable"])

    async def hook_raises():
        def bad(*_a):
            raise RuntimeError("diagnostics down")
        return await ask_model(_Model("raise"), "Q", "A", "F", timeout=0.05, on_error=bad)
    check("a failing diagnostics hook never changes the decision", asyncio.run(hook_raises()) is False)


def test_adaptive() -> None:
    section("6. Adaptive selection: started -> completed -> decided -> spoken")
    mains = [q for q in plan()[1:]]                        # 12, 13, 14 - no follow-ups

    async def run(room, selector):
        m, s, c, a, _ = rig(room, mains, selector=selector)
        await c.run_opening()
        await turn(a, LONG)
        c.on_agent_state("speaking")
        return c

    async def pick14(*_a):
        return 14
    room = room_name("ad")
    asyncio.run(run(room, pick14))
    check("chosen: started (2 options) -> completed (chosen id 14) -> decided -> Q2 spoken",
          in_order(room, ("state_changed", {"state": "adaptive_selection"}),
                   ("adaptive_selection_started", {"question": 1, "questions": 2}),
                   ("adaptive_selection_completed", {"outcome": "chosen", "question_id": 14}),
                   ("turn_decided", {"directive": "advance"}), ("question_spoken", {"question": 2})))

    async def bogus(*_a):
        return 999
    room = room_name("ad")
    asyncio.run(run(room, bogus))
    check("an id outside the plan: completed as 'bank_order', no id claimed",
          find(room, "adaptive_selection_completed", outcome="bank_order") != []
          and "question_id" not in recs(room)[first(room, "adaptive_selection_completed")])

    async def boom(*_a):
        raise RuntimeError(ERROR_MESSAGE)
    room = room_name("ad")
    asyncio.run(run(room, boom))
    check("a failing model: llm_error -> bank order",
          in_order(room, "adaptive_selection_started", ("llm_error", {"operation": "adaptive"}),
                   ("adaptive_selection_completed", {"outcome": "bank_order"})))

    from app.ai.interview import diagnostics as diag
    from app.ai.interview.adaptive import choose_with_model
    room = room_name("ad")

    async def model_paths():
        cb = (lambda code, exc: diag.emit("llm_error", room, operation="adaptive", category="llm_error",
                                          code=code, error_type=diag.error_type(exc)))
        return [await choose_with_model(_Model(mode), "Q", SENSITIVE_ANSWER, mains, timeout=0.05, on_error=cb)
                for mode in ("raise", "slow", "empty")]
    check("inside choose_with_model: error / timeout / unusable reported by code",
          asyncio.run(model_paths()) == [None, None, None]
          and [r.get("code") for r in recs(room)] == ["model_error", "timeout", "unusable"])
    src = (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    check("the worker wires both model hooks to llm_error diagnostics",
          'on_error=llm_failed("follow_up")' in src and 'on_error=llm_failed("adaptive")' in src)


# -- 7. Question spoken / TTS failure -------------------------------------------------------------

def test_spoken() -> None:
    section("7. 'Question spoken' only when its audio starts; a reply that never plays")
    room = room_name("tts")

    async def run():
        m, s, c, a, committed = rig(room)
        await c.run_opening()
        await turn(a, LONG)
        c.on_agent_state("thinking")
        c.on_agent_state("listening")          # TTS never played the reply - LiveKit dropped it
        cancelled = names(room)
        await turn(a, "and I documented every step for the team afterwards.")
        c.on_agent_state("speaking")
        c.on_agent_state("speaking")           # a duplicate event
        return cancelled, committed
    cancelled, committed = asyncio.run(run())
    check("a reply that never plays: 'reply_not_heard', no answer committed, Q2 not spoken",
          "reply_not_heard" in cancelled and "answer_committed" not in cancelled
          and cancelled.count("question_spoken") == 1)
    check("when a reply does play: committed once, Q2 spoken once (duplicate event ignored)",
          len(find(room, "answer_committed")) == 1 and len(find(room, "question_spoken", question=2)) == 1
          and len(committed) == 1)
    check("Q1 spoken even when LiveKit reports no fresh 'speaking' edge (after its playout)",
          find(room, "question_spoken", question=1) != [])


# -- 8. Room: reconnect, microphone, applicant ---------------------------------------------------

def test_room() -> None:
    section("8. Room events: reconnect, microphone, applicant (worker handlers)")
    from livekit import rtc

    from app.ai.interview import worker
    room = room_name("rtc")
    r = Emitter()
    worker.attach_room_diagnostics(r, room)
    applicant = SimpleNamespace(identity=f"applicant-{EMAIL}")
    agent = SimpleNamespace(identity="smarthr-interviewer")
    audio = SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO)
    video = SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO)

    r.fire("participant_connected", applicant)
    r.fire("participant_connected", agent)
    r.fire("track_subscribed", video, None, applicant)
    before_mic = names(room)
    r.fire("track_subscribed", audio, None, applicant)
    r.fire("reconnecting")
    during = names(room)
    r.fire("reconnected")
    r.fire("track_unsubscribed", audio, None, applicant)
    r.fire("participant_disconnected", applicant)
    r.fire("disconnected", "CLIENT_INITIATED")
    check("applicant joined once (the agent itself is not reported)", names(room).count("applicant_joined") == 1)
    check("'microphone_ready' only when the applicant's AUDIO track arrives (not video)",
          "microphone_ready" not in before_mic and find(room, "microphone_ready") != [])
    check("'reconnected' only after LiveKit reports it - reconnecting first",
          "reconnected" not in during and in_order(room, ("reconnecting", {"category": "connection_error"}),
                                                   "reconnected"))
    check("a lost microphone track is a microphone_error",
          find(room, "microphone_lost", category="microphone_error") != [])
    check("the applicant leaving and the room closing are reported, in order",
          in_order(room, "microphone_ready", "reconnected", "microphone_lost", "applicant_left", "room_disconnected"))
    check("no identity is logged", all(set(x) <= {"event", "source", "room", "n", "t_ms", "category"}
                                       for x in recs(room)))


# -- 9. Pipeline: STT / LLM / TTS errors --------------------------------------------------------

def test_pipeline() -> None:
    section("9. Pipeline errors: STT, LLM, TTS as categories - never their messages")
    from app.ai.interview import worker
    room = room_name("pipe")
    s = Emitter()
    worker._attach_logging(s, room)

    class STT: pass                                    # noqa: E701
    class LLM: pass                                    # noqa: E701
    class TTS: pass                                    # noqa: E701

    class APIConnectionError(Exception):
        recoverable = True

    class APIStatusError(Exception):
        recoverable = False

    s.fire("user_input_transcribed", SimpleNamespace(is_final=False, transcript=SENSITIVE_ANSWER))
    s.fire("user_input_transcribed", SimpleNamespace(is_final=True, transcript=SENSITIVE_ANSWER))
    s.fire("error", SimpleNamespace(source=STT(), error=APIConnectionError(ERROR_MESSAGE)))
    s.fire("error", SimpleNamespace(source=LLM(), error=APIStatusError(ERROR_MESSAGE)))
    s.fire("error", SimpleNamespace(source=TTS(), error=APIConnectionError(ERROR_MESSAGE)))
    s.fire("error", SimpleNamespace(source=object(), error=ValueError(ERROR_MESSAGE)))
    s.fire("close", SimpleNamespace(reason="participant_disconnected"))
    s.fire("close", SimpleNamespace(reason="participant_disconnected"))
    check("a final STT result reports its word count only (interim results nothing)",
          find(room, "stt_final", words=len(SENSITIVE_ANSWER.split())) != [] and len(find(room, "stt_final")) == 1)
    check("STT failure -> stt_error (class, recoverable)",
          find(room, "pipeline_error", category="stt_error", error_type="APIConnectionError", recoverable=True) != [])
    check("LLM failure -> llm_error", find(room, "pipeline_error", category="llm_error", recoverable=False) != [])
    check("TTS failure -> tts_error", find(room, "pipeline_error", category="tts_error") != [])
    check("an unknown source -> unknown_error", find(room, "pipeline_error", category="unknown_error") != [])
    check("the session closing is reported once (duplicate close ignored)",
          len(find(room, "session_closed", reason="participant_disconnected")) == 1)


# -- 10. Progress reports ------------------------------------------------------------------------

def test_progress() -> None:
    section("10. Progress reports: retries, refusals, failures - 'completed' only when accepted")
    room = room_name("prog")
    ok = asyncio.run(report(room, "started", [ConnectionError(ERROR_MESSAGE), 200], attempts=2))
    check("'started' retried once, then accepted -> session_started",
          ok and in_order(room, ("progress_retry", {"operation": "progress_started", "attempt": 1, "code": "network",
                                                    "category": "progress_report_error"}),
                          ("progress_accepted", {"attempt": 2}), ("session_started", {"progress_event": "started"})))
    room = room_name("prog")
    ok = asyncio.run(report(room, "completed", [503, 200], attempts=2))
    check("completion retry: retry (http_503) -> accepted -> interview_completed",
          ok and names(room) == ["progress_retry", "progress_accepted", "interview_completed"])
    ok2 = asyncio.run(report(room, "completed", [200], attempts=2))
    check("a repeated completion report does not repeat 'interview_completed'",
          ok2 and len(find(room, "interview_completed")) == 1 and len(find(room, "progress_accepted")) == 2)
    room = room_name("prog")
    ok = asyncio.run(report(room, "completed", [TimeoutError(), TimeoutError()], attempts=2))
    check("completion never accepted: retry -> failed (attempts 2, timeout) - NO interview_completed",
          not ok and names(room) == ["progress_retry", "progress_failed"]
          and recs(room)[-1]["attempts"] == 2 and recs(room)[-1]["code"] == "timeout")
    room = room_name("prog")
    ok = asyncio.run(report(room, "completed", [409], attempts=2))
    check("completion refused (409): progress_refused, not retried, NO interview_completed",
          not ok and names(room) == ["progress_refused"] and recs(room)[0]["code"] == "http_409")
    room = room_name("prog")
    ok = asyncio.run(report(room, "started", [409], attempts=2))
    check("start refused: progress_refused, no session_started", not ok and "session_started" not in names(room))

    from app.ai.interview import progress_client as pc
    room = room_name("prog")
    real = pc.voice_settings
    pc.voice_settings = lambda: SimpleNamespace(configured=False)
    try:
        asyncio.run(pc.report_progress(room, "ended"))
    finally:
        pc.voice_settings = real
    check("not configured: progress_failed (not_configured), nothing claimed",
          names(room) == ["progress_failed"] and recs(room)[0]["code"] == "not_configured")


# -- 11. Endings ---------------------------------------------------------------------------------

def test_endings() -> None:
    section("11. Endings: early / retriable, time limit")
    room = room_name("end")

    async def early():
        m, s, c, a, _ = rig(room)
        await c.run_opening()
        await turn(a, LONG)
        c.on_close("participant_disconnected")
        c.on_close("participant_disconnected")
        c.flush_answers()
        return await report(room, "completed" if c.completed_normally else "ended", [200], attempts=2)
    ok = asyncio.run(early())
    check("applicant left: finished (not normally, reason) -> 'ended' accepted -> interview_ended",
          ok and in_order(room, ("interview_finished", {"completed_normally": False,
                                                        "reason": "participant_disconnected"}),
                          ("progress_accepted", {"operation": "progress_ended"}), "interview_ended"))
    check("...no ENDING, no 'interview_completed', finished reported once",
          not find(room, "interview_ending") and not find(room, "interview_completed")
          and len(find(room, "interview_finished")) == 1)
    check("...the unheard answer was still committed at shutdown", find(room, "answer_committed", sequence=1) != [])

    room = room_name("end")

    async def time_limit():
        m, s, c, a, _ = rig(room)
        await c.run_opening()
        await c.enforce_time_limit(0)
    asyncio.run(time_limit())
    check("time limit: reached -> ENDING (time_limit) -> finished normally",
          in_order(room, "time_limit_reached", ("interview_ending", {"reason": "time_limit"}),
                   ("interview_finished", {"completed_normally": True})))

    room = room_name("end")

    async def no_plan():
        m, s, c, a, _ = rig(room, [])
        await c.run_opening()
    asyncio.run(no_plan())
    check("no plan: ENDING (no_plan) -> finished, not normally",
          in_order(room, ("interview_ending", {"reason": "no_plan"}), ("interview_finished",
                                                                      {"completed_normally": False})))
    src = (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    body = src[src.index("async def interview_session"):src.index("async def _load_candidate_context")]
    check("worker order: start report -> session.start -> interviewer_joined",
          body.index('report_progress(room_name, "started"') < body.index("await session.start(")
          < body.index('diag.emit("interviewer_joined"'))
    check("worker: 'session_start_refused' only on the not-started branch",
          body.index("if not started:") < body.index('"session_start_refused"') < body.index("else:"))
    deliver = body[body.index("async def _deliver_answers"):]
    check("worker shutdown: drain -> answers_summary -> end report -> release",
          deliver.index("await answers.drain()") < deliver.index('"answers_summary"')
          < deliver.index("report_progress(") < deliver.index("diag.release(room_name)"))


# -- 12. Backend, in process -------------------------------------------------------------------------

def test_backend() -> None:
    section("12. Backend events: session created, stale session refused, answers, completion")
    from fastapi import HTTPException

    from app.ai.interview.agent_auth import mint_agent_token
    from app.ai.interview.config import voice_settings
    from app.database import SessionLocal
    from app.models import Application, Candidate, Interview, User
    from app.routers import ai_interview as r
    from app.services import ai_interview_service, interview_analysis_service, question_bank_service as qb
    from scripts.test_ai_interview_cv_context import APPLICANT_MANY_CVS

    settings = voice_settings()
    if not settings.configured:
        check("LiveKit credentials configured (needed to mint agent tokens locally)", False)
        return
    EXTRA_SECRETS.extend(v for v in (settings.api_key, settings.api_secret) if v)
    interview_analysis_service.schedule = lambda _answer_id: None        # no background model call

    def bearer(room):
        token = mint_agent_token(settings.api_key, settings.api_secret, room)
        EXTRA_SECRETS.append(token)
        return f"Bearer {token}"

    def progress(room, event):
        try:
            return r.agent_progress(r.AgentProgress(event=event), authorization=bearer(room), db=db)
        except HTTPException as e:
            return e.status_code

    def answer(room, seq, transcript):
        try:
            return r.agent_answer(r.AgentAnswer(question_id=q1, question_number=1, sequence=seq, kind="answer",
                                                transcript=transcript, answered_at=datetime.utcnow()),
                                  authorization=bearer(room), db=db)
        except HTTPException as e:
            return e.status_code

    db = SessionLocal()
    try:
        candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                     .filter(User.email == APPLICANT_MANY_CVS).one())
        application = (db.query(Application).filter(Application.candidate_id == candidate.id)
                       .order_by(Application.id).first())
        application.status = "interview"
        interview = Interview(application_id=application.id, scheduled_at=datetime.now().replace(microsecond=0),
                              status="scheduled", location=MARK, notes=MARK)
        db.add(interview)
        db.commit()
        CREATED.append(interview.id)
        iid = interview.id
        q1 = qb.interview_plan(db)[0]["id"]

        old = ai_interview_service.start_voice_session(candidate, iid, db)
        new = ai_interview_service.start_voice_session(candidate, iid, db)
        EXTRA_SECRETS.extend(v for d in (old, new) for v in d.values() if isinstance(v, str) and len(v) > 40)
        old_room, new_room = old["room_name"], new["room_name"]
        created = find(new_room, "backend_session_created", interview_id=iid)
        check("session created: room, session id and interview id together (the correlation point)",
              created != [] and isinstance(recs(new_room)[created[0]].get("session_id"), int)
              and find(old_room, "backend_session_created", interview_id=iid) != [])
        new_sid = recs(new_room)[created[0]]["session_id"]

        check("stale session: the older room's start is refused (409)", progress(old_room, "started") == 409)
        check("...diagnosed as backend_progress_refused / superseded, with ITS session and interview",
              find(old_room, "backend_progress_refused", code="superseded", interview_id=iid,
                   progress_event="started") != [])
        check("an answer from a session that never started is refused - diagnosed not_started",
              answer(new_room, 1, SENSITIVE_ANSWER) == 409
              and find(new_room, "backend_answer_refused", code="not_started", sequence=1) != [])
        check("an end report before the start is refused - diagnosed not_started",
              progress(new_room, "ended") == 409
              and find(new_room, "backend_progress_refused", code="not_started", session_id=new_sid) != [])
        check("start accepted: scheduled -> in_progress",
              progress(new_room, "started")["interview_status"] == "in_progress"
              and find(new_room, "backend_progress_accepted", progress_event="started", from_status="scheduled",
                       to_status="in_progress", session_id=new_sid, interview_id=iid) != [])
        stored = answer(new_room, 1, SENSITIVE_ANSWER)
        again = answer(new_room, 1, SENSITIVE_ANSWER)
        check("answer stored, then its retry is the same row (created true, then false)",
              stored["created"] is True and again["created"] is False
              and find(new_room, "backend_answer_stored", created=True, sequence=1, session_id=new_sid) != []
              and find(new_room, "backend_answer_stored", created=False, outcome="unchanged") != [])
        check("completion accepted: in_progress -> completed",
              progress(new_room, "completed")["interview_status"] == "completed"
              and find(new_room, "backend_progress_accepted", progress_event="completed",
                       from_status="in_progress", to_status="completed") != [])
        check("a repeated completion is accepted as 'unchanged' (idempotent)",
              progress(new_room, "completed")["interview_status"] == "completed"
              and find(new_room, "backend_progress_accepted", outcome="unchanged") != [])
        response = r.start_session(r.SessionRequest(interview_id=iid), candidate=candidate, db=db)
        check("starting the completed interview again: refused, diagnosed with its code",
              getattr(response, "status_code", None) == 409
              and any(x["event"] == "backend_session_refused" and x.get("code") == "completed"
                      and x.get("interview_id") == iid for x in CAP.records))
        backend = [x for x in recs(new_room) if x["source"] == "backend"]
        check("every backend event for the room carries its session id and interview id",
              backend and all(x.get("session_id") == new_sid and x.get("interview_id") == iid
                              for x in backend if x["event"] != "backend_answer_refused"))
        check("backend event order for the session: created -> refused(not_started) -> started -> stored -> completed",
              in_order(new_room, "backend_session_created", "backend_answer_refused",
                       ("backend_progress_accepted", {"progress_event": "started"}), "backend_answer_stored",
                       ("backend_progress_accepted", {"progress_event": "completed"})))
    finally:
        db.close()


# -- 13. Source-level guarantees ------------------------------------------------------------------

def test_sources() -> None:
    section("13. Every emit call: a known event, allowed fields, no raw text")
    from app.ai.interview import diagnostics as diag
    from app.ai.interview import progress_client as pc

    allowed_kw = set(diag.FIELDS) | {"once", "source"}
    forbidden = {"text", "transcript", "payload", "message", "prompt", "content", "answer", "body", "headers",
                 "token", "identity", "email", "phone"}
    calls, bad = 0, []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "emit" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "diag"):
                continue
            calls += 1
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            name = node.args[0] if node.args else None
            if isinstance(name, ast.Constant):
                if name.value not in diag.EVENTS:
                    bad.append(f"{where} unknown event {name.value}")
            else:
                strings = {n.value for n in ast.walk(name) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
                if not strings <= diag.EVENTS | diag.AGENT_STATES:
                    bad.append(f"{where} computed event {strings}")
            for kw in node.keywords:
                if kw.arg is not None and kw.arg not in allowed_kw:
                    bad.append(f"{where} field {kw.arg}")
                if isinstance(kw.value, ast.Name) and kw.value.id in forbidden | {"exc", "error"}:
                    bad.append(f"{where} raw value {kw.value.id}")
                for sub in ast.walk(kw.value):
                    if isinstance(sub, ast.Attribute) and sub.attr in forbidden:
                        bad.append(f"{where} {kw.arg} reads .{sub.attr}")
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in ("str", "repr", "format"):
                        bad.append(f"{where} {kw.arg} formats a value")
    check(f"{calls} emit calls in app/: every event known, every field allow-listed, no raw text/exception",
          calls > 50 and not bad, "; ".join(bad[:5]))
    check("the accepted-report events are known events", set(pc.ACCEPTED_EVENT.values()) <= diag.EVENTS)
    src = (ROOT / "app/ai/interview/diagnostics.py").read_text(encoding="utf-8")
    check("diagnostics.py imports no database module",
          not any(x in src for x in ("app.models", "app.database", "sqlalchemy")))
    check("diagnostics.py has no free-text field (every string field is a vocabulary or a strict pattern)",
          not any(v is str for v in diag.FIELDS.values()))
    fe = [ROOT / "frontend/src/pages/applicant/AiInterviewPage.tsx",
          ROOT / "frontend/src/pages/applicant/aiInterviewRules.ts"]
    check("frontend: no console logging added to the interview page",
          all("console." not in p.read_text(encoding="utf-8") for p in fe))


# -- 14. Unchanged behaviour -----------------------------------------------------------------------

def test_unchanged() -> None:
    section("14. Observability only: timing, retries and limits unchanged")
    from app.ai.interview import answer_client as ac, progress_client as pc, turn_policy as tp
    from app.ai.interview.adaptive import SELECT_TIMEOUT_S
    from app.ai.interview.follow_up import DECISION_TIMEOUT_S
    from app.services.interview_progress_service import MAX_STARTED_ATTEMPTS

    h = tp.turn_handling()
    check("VAD / endpointing / interruption unchanged (0.1 s, 1.2 / 4.0 s, 1 word)",
          tp.VAD_MIN_SPEECH_S == 0.1 and h["endpointing"] == {"mode": "fixed", "min_delay": 1.2, "max_delay": 4.0}
          and tp.MIN_INTERRUPTION_WORDS == 1 and tp.PREEMPTIVE_GENERATION is False)
    src = (ROOT / "app/ai/interview/answer_client.py").read_text(encoding="utf-8")
    check("answer retries unchanged (1 s, 3 s; drain 6.5 s)",
          "RETRY_DELAYS_S = (1.0, 3.0)" in src and ac.DRAIN_TIMEOUT_S == 6.5)
    check("progress retries unchanged (started x2 / 1.0 s, end x2 / 0.2 s, 1.2 s timeout)",
          (pc.STARTED_ATTEMPTS, pc.STARTED_PAUSE_S, pc.END_ATTEMPTS, pc.END_PAUSE_S, pc.TIMEOUT_S)
          == (2, 1.0, 2, 0.2, 1.2))
    check("decision timeouts and the attempt limit unchanged",
          DECISION_TIMEOUT_S == 4 and SELECT_TIMEOUT_S == 4 and MAX_STARTED_ATTEMPTS == 2)


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    if not CREATED:
        return 0
    with engine.begin() as conn:
        conn.execute(text("delete from ai_interview_answers where interview_id = any(:i)"), {"i": CREATED})
        conn.execute(text("delete from ai_interview_sessions where interview_id = any(:i)"), {"i": CREATED})
        return conn.execute(text("delete from interviews where id = any(:i) and notes = :m"),
                            {"i": CREATED, "m": MARK}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 11.6.5 observability tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider
    from app.ai.interview import diagnostics as diag

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model

    diag.reset()
    root = logging.getLogger()
    root.addHandler(CAP)
    saved_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        test_emitter()
        test_lifecycle()
        test_turns()
        test_answers()
        test_follow_up()
        test_adaptive()
        test_spoken()
        test_room()
        test_pipeline()
        test_progress()
        test_endings()
        test_backend()
        test_sources()
        test_unchanged()
    finally:
        root.removeHandler(CAP)
        root.setLevel(saved_level)
        removed = cleanup()
        print(f"\n  cleanup: removed {removed} temporary interview(s) with their sessions and answers")

    section("15. Privacy: nothing sensitive in ANY log line")
    for value in SECRETS:
        hits = [line for line in CAP.lines if value in line]
        check(f"'{value}' appears in no log line ({len(CAP.lines)} lines)", not hits, hits[0][:120] if hits else "")
    leaked = [line for line in CAP.lines for v in EXTRA_SECRETS if v and len(v) > 8 and v in line]
    check("no minted token and no LiveKit key/secret in any log line", not leaked)
    check("the sensitive answer never appears, even in part",
          not any(SENSITIVE_ANSWER[:30] in line or LONG[:30] in line for line in CAP.lines))
    from app.ai.interview.diagnostics import sanitize
    check(f"all {len(CAP.records)} diagnostic records are already clean (re-sanitising changes nothing)",
          all(sanitize(x) == x for x in CAP.records))
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
