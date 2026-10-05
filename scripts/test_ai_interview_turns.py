"""AI Interview - Phase 2 (turn-taking) offline tests. No network, no LiveKit room.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_turns

Covers the parts of turn-taking that are SmartHR's own code, deterministically:

1. the state machine - every legal path, illegal transitions refused, nothing
   after COMPLETED;
2. `classify_utterance` - empty / filler / short / answer;
3. the turn gate (`InterviewerAgent.on_user_turn_completed`) - filler and
   empty turns never reach GPT-4o, short turns get the note, answers pass;
4. the controller - LiveKit agent/user states mapped onto interview states,
   the opening sequence, the silence nudge limit, interruption counting and
   the ENDING -> COMPLETED path - against a fake session;
5. the turn policy - the configured values are the ones documented.

What the audio actually does (does VAD fire, does a pause keep the turn, does
barge-in stop the voice) needs a real room: `scripts/verify_ai_interview_turns.py`.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from livekit.agents import StopResponse, llm  # noqa: E402

from app.ai.interview import turn_policy  # noqa: E402
from app.ai.interview.agent import (  # noqa: E402
    CLOSING, SILENCE_NUDGE, WELCOME, InterviewerAgent,
)
from app.ai.interview.questions import PlannedQuestion, QuestionProgress  # noqa: E402

#: Phase 3: the opening question comes from the Question Bank plan.
PLAN = [PlannedQuestion(1, 10, "general", "Tell me about yourself."),
        PlannedQuestion(2, 20, "behavioral", "How do you work within a team?")]
OPENING_QUESTION = PLAN[0].text
from app.ai.interview.controller import (  # noqa: E402
    COUNTERS_ATTRIBUTE, STATE_ATTRIBUTE, InterviewController,
)
from app.ai.interview.state import (  # noqa: E402
    IllegalTransition, InterviewState as S, InterviewStateMachine, TRANSITIONS,
)

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  FAIL  {name}{f' - {detail}' if detail else ''}")
    return bool(ok)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# ---------------------------------------------------------------------------
def test_state_machine() -> None:
    section("1. State machine")
    m = InterviewStateMachine()
    check("starts in WAITING", m.state == S.WAITING)

    for target in (S.INTRO, S.ASKING, S.LISTENING, S.PROCESSING, S.SPEAKING,
                   S.LISTENING, S.PROCESSING, S.SPEAKING, S.ENDING, S.COMPLETED):
        m.to(target)
    check("full interview path is legal",
          m.path() == ["waiting", "intro", "asking", "listening", "processing", "speaking",
                       "listening", "processing", "speaking", "ending", "completed"], str(m.path()))
    check("not active once COMPLETED", m.active is False)
    for target in S:
        if target == S.COMPLETED:
            continue
        try:
            m.to(target)
            check(f"nothing after COMPLETED ({target.value})", False)
        except IllegalTransition:
            pass
    check("no transition leaves COMPLETED", TRANSITIONS[S.COMPLETED] == frozenset())

    for src, dst in ((S.WAITING, S.LISTENING), (S.LISTENING, S.ASKING),
                     (S.PROCESSING, S.INTRO), (S.WAITING, S.COMPLETED)):
        m = InterviewStateMachine(state=src)
        try:
            m.to(dst)
            check(f"illegal {src.value} -> {dst.value} refused", False)
        except IllegalTransition:
            check(f"illegal {src.value} -> {dst.value} refused", m.state == src)

    m = InterviewStateMachine(state=S.LISTENING)
    check("same-state transition is a no-op", m.to(S.LISTENING) is False and m.state == S.LISTENING)
    m = InterviewStateMachine(state=S.ASKING)
    check("barge-in during the question: ASKING -> PROCESSING", m.to(S.PROCESSING))
    m = InterviewStateMachine(state=S.PROCESSING)
    check("Phase 3: next bank question: PROCESSING -> ASKING", m.to(S.ASKING))
    m = InterviewStateMachine(state=S.SPEAKING)
    check("interrupted reply: SPEAKING -> LISTENING", m.to(S.LISTENING))
    check("every active state can reach ENDING",
          all(S.ENDING in TRANSITIONS[s] for s in S if s not in (S.ENDING, S.COMPLETED)))
    m = InterviewStateMachine(state=S.SPEAKING)
    m.abort("participant_disconnected")
    check("abort() completes from anywhere", m.state == S.COMPLETED and m.end_reason == "participant_disconnected")


def test_classify() -> None:
    section("2. What counts as an answer")
    cases = {
        None: "empty", "": "empty", "   ": "empty", "...": "empty",
        "uh": "filler", "Uh.": "filler", "um, uh": "filler", "Hmm...": "filler", "mm-hm": "filler", "Mm-hmm.": "filler",
        "yes": "short", "Okay.": "short", "Yes, sure.": "short",
        "I worked at a bank for three years": "answer",
        "My name is Sam and I build web applications.": "answer",
    }
    for text, expected in cases.items():
        got = turn_policy.classify_utterance(text)
        check(f"{text!r} -> {expected}", got == expected, got)


def run(coro):
    return asyncio.run(coro)


def test_gate() -> None:
    section("3. The turn gate - what reaches GPT-4o")

    def attempt(text: str, state: S = S.PROCESSING):
        m = InterviewStateMachine(state=state)
        agent = InterviewerAgent(m, "test-room")
        ctx = llm.ChatContext.empty()
        msg = llm.ChatMessage(role="user", content=[text])
        try:
            run(agent.on_user_turn_completed(ctx, msg))
            stopped = False
        except StopResponse:
            stopped = True
        return m, ctx, msg, stopped

    for text in ("uh", "um, uh", "", "Hmm."):
        m, ctx, _, stopped = attempt(text)
        check(f"{text!r}: GPT-4o not asked (StopResponse)", stopped)
        check(f"{text!r}: counted as ignored, not as an answer",
              m.counters.ignored == 1 and m.counters.answers == 0)
        check(f"{text!r}: interview goes back to LISTENING", m.state == S.LISTENING)

    m, ctx, msg, stopped = attempt("Yes.", state=S.LISTENING)
    check("'Yes.': GPT-4o IS asked", not stopped)
    check("'Yes.': counted as short", m.counters.short == 1 and m.counters.answers == 0)
    notes = [i for i in ctx.items if getattr(i, "role", None) == "system"]
    check("'Yes.': the short-answer note is in this reply's context",
          len(notes) == 1 and "very short" in notes[0].text_content)
    check("'Yes.': the applicant's own message is not altered", msg.text_content == "Yes.")
    check("'Yes.': state -> PROCESSING", m.state == S.PROCESSING)

    m, ctx, _, stopped = attempt("I worked at a bank and then moved into software.", state=S.LISTENING)
    check("answer: GPT-4o is asked, no note", not stopped and not [i for i in ctx.items if getattr(i, "role", None) == "system"])
    check("answer: counted as an answer", m.counters.answers == 1)

    m, _, _, stopped = attempt("I worked at a bank for years.", state=S.SPEAKING)
    check("answer after barge-in: SPEAKING -> PROCESSING", not stopped and m.state == S.PROCESSING)

    # Regression (live run): the gate must go through the controller's
    # set_state, or PROCESSING is never logged or published.
    m = InterviewStateMachine(state=S.LISTENING)
    calls = []
    agent = InterviewerAgent(m, "test-room", set_state=lambda st: calls.append(st) or m.to(st))
    run(agent.on_user_turn_completed(llm.ChatContext.empty(),
                                     llm.ChatMessage(role="user", content=["I built payment systems for banks."])))
    check("gate uses the injected set_state (so PROCESSING is published)", calls == [S.PROCESSING], str(calls))

    m = InterviewStateMachine()
    m.abort("gone")
    agent = InterviewerAgent(m, "test-room")
    try:
        run(agent.on_user_turn_completed(llm.ChatContext.empty(),
                                         llm.ChatMessage(role="user", content=["a long real answer here"])))
        check("after COMPLETED: nothing reaches GPT-4o", False)
    except StopResponse:
        check("after COMPLETED: nothing reaches GPT-4o", True)


class FakeHandle:
    def __init__(self, interrupted: bool = False):
        self.interrupted = interrupted
        self._callbacks = []

    async def _playout(self):
        return None

    def wait_for_playout(self):
        return self._playout()

    def add_done_callback(self, cb):
        self._callbacks.append(cb)

    def finish(self):
        for cb in self._callbacks:
            cb(self)


class FakeSession:
    def __init__(self):
        self.said: list[tuple[str, object]] = []
        self.handlers: dict[str, list] = {}
        self.interrupted = 0
        self.shut_down = False

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def say(self, text, allow_interruptions=None):
        self.said.append((text, allow_interruptions))
        return FakeHandle()

    def interrupt(self, force=False):
        self.interrupted += 1

    def shutdown(self, drain=True):
        self.shut_down = True


def test_controller() -> None:
    section("4. Controller: LiveKit events -> interview states")
    published: list[dict] = []

    async def publish(attrs):
        published.append(attrs)

    async def scenario():
        m = InterviewStateMachine()
        session = FakeSession()
        c = InterviewController(session, m, "test-room", publish=publish,
                                progress=QuestionProgress(list(PLAN)))
        c.attach()
        check("controller subscribes to the four session events",
              {"agent_state_changed", "user_state_changed", "speech_created", "close"} <= set(session.handlers))

        c.on_agent_state("speaking")
        check("agent events ignored before the opening", m.state == S.WAITING)

        await c.run_opening()
        check("opening says the welcome, then the question",
              [t for t, _ in session.said] == [WELCOME.format(count=2), OPENING_QUESTION])
        check("the welcome cannot be interrupted, the question can",
              session.said[0][1] is False and session.said[1][1] is None)
        check("after the question: LISTENING (hand-off to the applicant)", m.state == S.LISTENING)
        check("path WAITING -> INTRO -> ASKING -> LISTENING",
              m.path() == ["waiting", "intro", "asking", "listening"], str(m.path()))

        c.on_agent_state("thinking")
        check("agent thinking -> PROCESSING", m.state == S.PROCESSING)
        c.on_agent_state("speaking")
        check("agent speaking -> SPEAKING", m.state == S.SPEAKING)
        c.on_agent_state("listening")
        check("agent listening -> LISTENING", m.state == S.LISTENING)

        # Silence: one nudge per stretch of silence, never more.
        c.on_user_state("away")
        c.on_user_state("away")
        check("silence: exactly one nudge", m.counters.nudges == 1
              and [t for t, _ in session.said].count(SILENCE_NUDGE) == 1)
        c.on_user_state("speaking")
        m.to(S.PROCESSING); m.to(S.SPEAKING); m.to(S.LISTENING)
        c.on_user_state("away")
        check("after the applicant speaks again, a new silence may be nudged once",
              m.counters.nudges == 2)
        m.to(S.PROCESSING)
        c.on_user_state("away")
        check("no nudge unless the applicant has the floor", m.counters.nudges == 2)
        m.to(S.SPEAKING); m.to(S.LISTENING)

        handle = FakeHandle(interrupted=True)
        c.on_speech_created(handle)
        handle.finish()
        check("a speculative reply discarded UNHEARD is not an interruption",
              m.counters.interruptions == 0)

        handle = FakeHandle(interrupted=True)
        c.on_speech_created(handle)
        c.on_agent_state("thinking"); c.on_agent_state("speaking")  # the applicant hears it
        handle.finish()
        c.on_agent_state("listening")
        check("interrupted interviewer speech that was heard IS counted", m.counters.interruptions == 1)
        handle = FakeHandle(interrupted=False)
        c.on_speech_created(handle)
        c.on_agent_state("thinking"); c.on_agent_state("speaking")
        handle.finish()
        c.on_agent_state("listening")
        check("speech that finished normally is not", m.counters.interruptions == 1)

        await c.end("time_limit")
        check("end: interviewer speech interrupted first", session.interrupted == 1)
        check("end: fixed closing line, not interruptible",
              session.said[-1] == (CLOSING, False))
        check("end: ENDING -> COMPLETED, session shut down",
              m.state == S.COMPLETED and m.path()[-2:] == ["ending", "completed"] and session.shut_down)
        c.on_agent_state("listening")
        check("events after COMPLETED change nothing", m.state == S.COMPLETED)

        await asyncio.sleep(0)
        last = published[-1] if published else {}
        check("state is published as a participant attribute",
              last.get(STATE_ATTRIBUTE) == "completed")
        check("counters are published, as numbers only",
              '"answers"' in last.get(COUNTERS_ATTRIBUTE, "") and '"interruptions": 1' in last.get(COUNTERS_ATTRIBUTE, ""))

        # Barge-in during the opening question: must not be pulled back.
        m2 = InterviewStateMachine()
        s2 = FakeSession()
        c2 = InterviewController(s2, m2, "test-room-2", publish=publish,
                                 progress=QuestionProgress(list(PLAN)))

        async def say_then_answer(text, allow_interruptions=None):
            return None

        original = s2.say

        def say(text, allow_interruptions=None):
            h = original(text, allow_interruptions)
            if text == OPENING_QUESTION:
                m2.to(S.PROCESSING)  # the applicant answered over the question
            return h

        s2.say = say
        await c2.run_opening()
        check("answer over the question: state stays PROCESSING", m2.state == S.PROCESSING)

        m3 = InterviewStateMachine(state=S.SPEAKING)
        c3 = InterviewController(FakeSession(), m3, "r3")
        c3.opening_done = True
        c3.on_close("participant_disconnected")
        check("session close -> COMPLETED from anywhere", m3.state == S.COMPLETED)

    asyncio.run(scenario())


def test_policy() -> None:
    section("5. Turn policy values")
    p = turn_policy
    check("a pause shorter than max_delay does not end a mid-thought turn",
          p.MIN_ENDPOINTING_DELAY_S < p.MAX_ENDPOINTING_DELAY_S)
    check("interview-paced: min delay above the 0.3 s streaming default", p.MIN_ENDPOINTING_DELAY_S > 0.3)
    check("min delay clears the measured 0.6 s gap between sentences with margin",
          p.MIN_ENDPOINTING_DELAY_S >= 2 * 0.6)
    check("thinking pauses tolerated up to 4 s", p.MAX_ENDPOINTING_DELAY_S == 4.0)
    check("barge-in needs more than a cough", p.MIN_INTERRUPTION_S >= 0.5)
    check("silence nudge well after a thinking pause",
          p.SILENCE_NUDGE_AFTER_S > p.MAX_ENDPOINTING_DELAY_S * 2)
    check("one nudge per silence", p.MAX_NUDGES_PER_SILENCE == 1)
    th = asyncio.run(_turn_handling())
    check("LiveKit options carry the same numbers",
          th["endpointing"]["min_delay"] == p.MIN_ENDPOINTING_DELAY_S
          and th["endpointing"]["max_delay"] == p.MAX_ENDPOINTING_DELAY_S
          and th["interruption"]["min_duration"] == p.MIN_INTERRUPTION_S)
    check("turn detector is LiveKit's model, not VAD silence alone",
          type(th["turn_detection"]).__name__ == "TurnDetector")


async def _turn_handling():
    return turn_policy.turn_handling()


def main() -> int:
    print("SmartHR - AI Interview Phase 2 turn-taking tests (offline)")
    test_state_machine()
    test_classify()
    test_gate()
    test_controller()
    test_policy()
    print(f"\n{passed} passed, {len(failed)} failed")
    for failure in failed:
        print(f"  - {failure}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
