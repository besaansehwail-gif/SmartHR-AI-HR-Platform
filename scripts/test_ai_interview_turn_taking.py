"""AI Interview - Phase 11.6.2 turn-taking tests. Offline and deterministic.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_turn_taking

No LiveKit, no model: the REAL agent turn gate (`InterviewerAgent`), the real
`InterviewController`, `QuestionProgress` and state machine, driven with a
fake session (which records whether each utterance may be interrupted) and
fake deciders (some of which wait, to put two turns in flight at once).
LiveKit's own mechanisms (VAD, the turn detector, endpointing, barge-in) are
checked as the configuration SmartHR hands to LiveKit.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

passed = 0
failed: list[str] = []


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


class Handle:
    def __init__(self):
        self.interrupted, self._cbs = False, []

    async def _p(self):
        return None

    def wait_for_playout(self):
        return self._p()

    def add_done_callback(self, cb):
        self._cbs.append(cb)

    def finish(self, interrupted=False):
        self.interrupted = interrupted
        for cb in self._cbs:
            cb(self)


class Session:
    """Records every `say` with its interruptibility, as LiveKit receives it."""

    def __init__(self):
        self.said: list[tuple[str, object]] = []
        self.handles: list[Handle] = []
        self.shut = False

    def on(self, *_a):
        pass

    def say(self, text, allow_interruptions=None):
        self.said.append((text, allow_interruptions))
        h = Handle()
        self.handles.append(h)
        return h

    def interrupt(self, force=False):
        pass

    def shutdown(self, drain=True):
        self.shut = True


def plan():
    from app.ai.interview.questions import PlannedQuestion as Q
    fu = Q(101, 10, "follow_up", "What was the result of that project, in numbers if you can?")
    return [Q(11, 1, "general", "Tell me about yourself.", follow_up=fu),
            Q(12, 2, "behavioral", "Describe a challenge you faced."),
            Q(13, 3, "technical", "Which tools do you use for data work?"),
            Q(14, 4, "general", "Why this role?")]


def rig(questions=None, decider=None, selector=None, absorb=True):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine

    m = InterviewStateMachine()
    s = Session()
    committed: list = []
    published: list = []

    async def publish(attrs):
        published.append(attrs)

    c = InterviewController(s, m, "room", publish=publish, progress=QuestionProgress(list(questions or plan())),
                            on_commit=committed.extend, follow_up_decider=decider, next_question_selector=selector)
    a = InterviewerAgent(m, "room", set_state=c.set_state, on_answer=c.on_answer, has_open_answer=c.has_open_answer,
                         follow_up_candidate=c.follow_up_candidate, decide_follow_up=c.decide_follow_up,
                         adaptive_options=c.adaptive_options, select_next_question=c.select_next_question,
                         absorb_unheard=c.absorb_unheard if absorb else None)
    return m, s, c, a, committed, published


async def turn(agent, text):
    """One completed applicant turn through the real gate. None if refused."""
    from livekit.agents import StopResponse, llm
    from app.ai.interview.agent import find_directive
    ctx = llm.ChatContext.empty()
    try:
        await agent.on_user_turn_completed(ctx, llm.ChatMessage(role="user", content=[text]))
    except StopResponse:
        return None
    return find_directive(ctx) or "free"


async def settle():
    """Let the controller's spawned publish tasks run (it publishes in order,
    on the event loop, as LiveKit participant attributes are set)."""
    for _ in range(3):
        await asyncio.sleep(0)


def shown_number(published) -> int | None:
    return json.loads(published[-1]["smarthr.interview.question"])["number"] if published else None


LONG = "At my last job I rebuilt the forecasting pipeline after it failed, and I documented every step."


def test_policy() -> None:
    section("1. What SmartHR hands to LiveKit - the existing principles, preserved")
    from app.ai.interview import turn_policy as tp
    h = tp.turn_handling()
    check("speech starts after 0.1 s of VAD speech (unchanged)", tp.VAD_MIN_SPEECH_S == 0.1)
    check("a finished-sounding sentence ends the turn after 1.2 s of silence (unchanged)",
          h["endpointing"] == {"mode": "fixed", "min_delay": 1.2, "max_delay": 4.0})
    check("short pauses do NOT end it: 1.2 s is twice the ~0.6 s gap between sentences",
          tp.MIN_ENDPOINTING_DELAY_S >= 2 * 0.6)
    check("mid-thought gets more time: up to 4.0 s before the turn is given up", tp.MAX_ENDPOINTING_DELAY_S == 4.0
          and tp.MAX_ENDPOINTING_DELAY_S > tp.MIN_ENDPOINTING_DELAY_S)
    check("LiveKit's turn detector decides finished-vs-pausing", type(h["turn_detection"]).__name__ == "TurnDetector")
    check("barge-in threshold unchanged: 0.6 s of speech", h["interruption"]["min_duration"] == 0.6)
    check("...and now also at least one transcribed WORD - noise that makes no words cannot interrupt",
          h["interruption"]["min_words"] == 1 and tp.MIN_INTERRUPTION_WORDS == 1)
    check("a noise-triggered stop still resumes (false-interruption resume, 2 s)",
          h["interruption"]["resume_false_interruption"] is True and h["interruption"]["false_interruption_timeout"] == 2.0)
    check("no speculative replies (the directive must exist first)", h["preemptive_generation"] == {"enabled": False})
    check("no user_turn_limit: a long answer is never cut by a forced reply", "user_turn_limit" not in h)


def test_turns() -> None:
    section("2. Answers and pauses")
    from app.ai.interview.state import InterviewState as S

    async def short_pause():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        d1 = await turn(a, "At my last job I")          # LiveKit ended the turn at a pause...
        c.on_agent_state("thinking")
        c.on_agent_state("listening")                    # ...its reply dropped unheard: still talking
        reopened = c.progress.resumed is not None and c.progress.current.id == 11
        d2 = await turn(a, "rebuilt the forecasting pipeline after it failed.")
        c.on_agent_state("speaking")
        return d1, reopened, d2, committed, c
    d1, reopened, d2, committed, c = asyncio.run(short_pause())
    check("short pause inside an answer: the premature decision is undone, question 1 stays open", reopened)
    check("...the rest joins the SAME answer, stored once when its reply is heard",
          [(r.question_id, r.text) for r in committed]
          == [(11, "At my last job I rebuilt the forecasting pipeline after it failed.")], str(committed))

    async def normal():
        m, s, c, a, committed, published = rig()
        await c.run_opening()
        d = await turn(a, LONG)
        c.on_agent_state("thinking")
        await settle()
        before = shown_number(published)
        c.on_agent_state("speaking")
        await settle()
        return d, before, shown_number(published), committed, m
    d, before, after, committed, m = asyncio.run(normal())
    check("a normal completed answer -> one decision, the next bank question", d.kind == "advance"
          and d.say_after == plan()[1].text)
    check("question number shown stays 1 while the next question is only DECIDED", before == 1, str(before))
    check("...and becomes 2 only when it is spoken (ASKING)", after == 2 and m.state == S.ASKING, str(after))
    check("the answer is final (stored) exactly when the reply starts playing",
          [(r.sequence, r.question_id) for r in committed] == [(1, 11)])

    async def mid_thought():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, "I think the hardest part was, and then")
        c.on_agent_state("thinking")
        c.on_agent_state("listening")
        d = await turn(a, "uh")                      # a filler that ENDS the open answer
        c.on_agent_state("speaking")
        return d, committed
    d, committed = asyncio.run(mid_thought())
    check("mid-thought: after the pause, even an 'uh' completes the open answer (not dropped as noise)",
          d.kind == "advance" and committed[0].text == "I think the hardest part was, and then uh")

    words = " ".join(["I also led the migration of our reporting stack and trained two new analysts."] * 18)

    async def long_answer():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        d = await turn(a, words)
        c.on_agent_state("speaking")
        return d, committed
    d, committed = asyncio.run(long_answer())
    check(f"a long valid answer ({len(words.split())} words) is one answer, kept whole",
          d.kind == "advance" and committed[0].text == words and committed[0].words == len(words.split()))

    async def noise():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        results = [await turn(a, t) for t in ("", "   ", "uh", "hmm um")]
        return results, c, m
    results, c, m = asyncio.run(noise())
    check("noise / silence / fillers never become an answer",
          results == [None, None, None, None] and c.progress.answers == [] and m.counters.ignored == 4)


def test_interruptions() -> None:
    section("3. Interruptions")

    async def opening():
        m, s, c, a, *_ = rig()
        await c.run_opening()
        return s
    s = asyncio.run(opening())
    check("the welcome is NOT interruptible (unchanged)", s.said[0][1] is False)
    check("the question is interruptible (LiveKit's default - not disabled)", s.said[1][1] is None)

    async def barge_in():
        import time
        m, s, c, a, *_ = rig()
        await c.run_opening()
        heard = Handle()
        c.on_speech_created(heard)
        c._last_spoke_at = time.monotonic() + 1          # it was audibly playing
        heard.finish(interrupted=True)
        c._last_spoke_at = None                          # nothing has played since
        unheard = Handle()
        c.on_speech_created(unheard)                     # speculative, never played
        unheard.finish(interrupted=True)
        return m.counters.interruptions, c.progress.answers
    count, answers = asyncio.run(barge_in())
    check("an interruption of audible speech is counted; a discarded unheard reply is not", count == 1)
    check("an interruption creates no answer by itself", answers == [])


def test_processing_once() -> None:
    section("4. Processing protection: one decision per finalized answer")

    async def concurrent():
        gate = asyncio.Event()
        calls: list[str] = []

        async def slow_decider(main, answer, follow_up):
            calls.append(answer)
            if len(calls) == 1:
                await gate.wait()                         # the first decision is still running...
            return True

        m, s, c, a, committed, published = rig(decider=slow_decider)
        await c.run_opening()
        first = asyncio.ensure_future(turn(a, "I lead the data team and"))
        await asyncio.sleep(0.01)
        second = asyncio.ensure_future(turn(a, "I build forecasting tools for retailers."))
        await asyncio.sleep(0.01)
        in_flight = len(calls)                            # the second turn must be WAITING
        gate.set()
        d1, d2 = await first, await second
        c.on_agent_state("speaking")
        return in_flight, calls, d1, d2, c, committed
    in_flight, calls, d1, d2, c, committed = asyncio.run(concurrent())
    check("a second turn arriving mid-decision waits - no second decision in parallel", in_flight == 1, str(in_flight))
    check("...the premature decision is reopened and decided again on the MERGED answer",
          calls == ["I lead the data team and", "I lead the data team and I build forecasting tools for retailers."],
          str(calls))
    check("...one answer stored for question 1 (no answer recorded against the next question)",
          [(r.question_id, r.text) for r in committed]
          == [(11, "I lead the data team and I build forecasting tools for retailers.")], str(committed))
    check("...the follow-up is asked once, from the bank", d2.kind == "follow_up" and c.progress.followed_up == {11}
          and d2.say_after == plan()[0].follow_up.text)

    async def duplicate():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, LONG)
        await turn(a, LONG)                               # the same words delivered again, unheard
        c.on_agent_state("speaking")
        return committed, c
    committed, c = asyncio.run(duplicate())
    check("a duplicated turn saves ONE answer, not the words twice",
          [(r.question_id, r.text) for r in committed] == [(11, LONG)], str(committed))
    check("...and the interview moved on exactly once (to question 2)", c.progress.current.id == 12)

    async def repeated_events():
        m, s, c, a, committed, published = rig()
        await c.run_opening()
        await turn(a, LONG)
        for _ in range(3):
            c.on_agent_state("speaking")                  # duplicate LiveKit events
        await settle()
        return committed, shown_number(published), c
    committed, shown, c = asyncio.run(repeated_events())
    check("repeated 'speaking' events commit once and advance once", len(committed) == 1 and shown == 2
          and c.progress.current.id == 12)

    async def adaptive_once():
        calls: list = []

        async def selector(main, answer, options):
            calls.append([q.id for q in options])
            return 14
        m, s, c, a, committed, _ = rig(questions=plan()[1:], selector=selector)
        await c.run_opening()
        await turn(a, LONG)
        for _ in range(2):
            c.on_agent_state("speaking")
        c.on_agent_state("listening")
        return calls, c
    calls, c = asyncio.run(adaptive_once())
    check("adaptive selection runs once for a finalized answer; events do not re-run it",
          calls == [[13, 14]] and [c.progress.questions[i].id for i in c.progress.asked] == [12, 14])


def test_follow_up_timing() -> None:
    section("5. Follow-up decision waits for the finalized answer")

    async def cancelled_decision():
        seen: list[str] = []

        async def decider(main, answer, follow_up):
            seen.append(answer)
            if len(seen) == 1:
                await asyncio.sleep(30)                   # LiveKit cancels this turn: still talking
            return False
        m, s, c, a, committed, _ = rig(decider=decider)
        await c.run_opening()
        task = asyncio.ensure_future(turn(a, "I lead the data team"))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        c.on_agent_state("listening")
        d = await turn(a, "and I build forecasting tools.")
        c.on_agent_state("speaking")
        return seen, d, committed
    seen, d, committed = asyncio.run(cancelled_decision())
    check("the decision is only ever asked about a completed turn, then re-asked on the merged answer",
          seen == ["I lead the data team", "I lead the data team and I build forecasting tools."], str(seen))
    check("...the partial answer was never stored as final on its own",
          [r.text for r in committed] == ["I lead the data team and I build forecasting tools."], str(committed))


def test_closing_and_timeouts() -> None:
    section("6. Closing and time limits")
    from app.ai.interview.state import InterviewState as S

    async def last_question():
        m, s, c, a, committed, _ = rig(questions=plan()[1:2])
        await c.run_opening()
        d = await turn(a, LONG)
        c.on_agent_state("speaking")                      # closing line playing: ENDING
        ending = m.state
        late = await turn(a, "One more thing I wanted to add about my work.")
        c.on_agent_state("listening")                     # closing heard
        return d, ending, late, m, c, committed
    d, ending, late, m, c, committed = asyncio.run(last_question())
    check("the last answer -> the closing line (ENDING)", d.kind == "finish" and ending == S.ENDING)
    check("speech during the closing is refused: no answer, no reply", late is None and len(committed) == 1)
    check("...then COMPLETED, normally", m.state == S.COMPLETED and c.completed_normally is True)

    async def time_limit():
        m, s, c, a, *_ = rig()
        await c.run_opening()
        await c.enforce_time_limit(0.01)
        again = await turn(a, LONG)
        return m, s, c, again
    m, s, c, again = asyncio.run(time_limit())
    check("the time limit still ends the interview with the closing line, not interruptible",
          m.state == S.COMPLETED and s.said[-1][1] is False and c.completed_normally is True)
    check("...and nothing is accepted after it", again is None)

    async def nudge():
        m, s, c, a, *_ = rig()
        await c.run_opening()
        c.on_user_state("away")
        c.on_user_state("away")
        nudges = m.counters.nudges
        c.on_user_state("speaking")
        c.on_user_state("away")
        return nudges, m.counters.nudges
    first, total = asyncio.run(nudge())
    check("silence: one fixed nudge per stretch of silence (unchanged)", first == 1 and total == 2)


def test_containment() -> None:
    section("7. Logging: nothing new that could carry speech")
    import ast
    speech = {"text", "transcript", "answer", "sentence", "said"}
    for name in ("agent.py", "controller.py", "questions.py", "turn_policy.py"):
        tree = ast.parse((ROOT / "app/ai/interview" / name).read_text(encoding="utf-8"))
        leaky = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"):
                # The ARGUMENTS after the format string - not the message's own words.
                for arg in node.args[1:]:
                    names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)} | {
                        n.attr for n in ast.walk(arg) if isinstance(n, ast.Attribute)}
                    if names & speech:
                        leaky.append(f"line {node.lineno}: {sorted(names & speech)}")
        check(f"{name}: no log call passes answer / transcript text as an argument", not leaky, str(leaky))
    check("the worker's log level policy is untouched (livekit.agents pinned to INFO)",
          "configure_worker_logging()" in (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8"))


def main() -> int:
    print("SmartHR - AI Interview Phase 11.6.2 turn-taking tests")
    test_policy()
    test_turns()
    test_interruptions()
    test_processing_once()
    test_follow_up_timing()
    test_closing_and_timeouts()
    test_containment()
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
