"""AI Interview - turn labels, turn state machine, never-silent replies, observability.
Offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_turn_labels

No LiveKit, no model, no database. The REAL agent turn gate, controller,
QuestionProgress, state machine and llm_node run against the fake session the
turn-taking suite uses; the classifier is a fake returning chosen labels; the
GPT stream is a fake (normal / raising / slow). Uses the example sentences
from the live test.
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_ai_interview_turn_taking import LONG, Session, plan, settle  # noqa: E402

passed = 0
failed: list[str] = []
ROOM = "smarthr-ai-interview-turnlabels1"
TRANSCRIPT_SENTINEL = "synthetic-transcript-marker"
SPOKEN: list[str] = []


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


def say(text: str) -> str:
    SPOKEN.append(text)
    return text


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.diag: list[dict] = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))
        if getattr(record, "smarthr_diag", None) is not None:
            self.diag.append(dict(record.smarthr_diag))


CAP = Capture()


def rig(labels=None, questions=None, decider=None, selector=None, session=None, classifier_fn=None):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine

    m, s = InterviewStateMachine(), session or Session()
    committed, published, seen = [], [], []
    queue = list(labels or [])

    async def publish(attrs):
        published.append(attrs)

    async def classifier(question, words, is_follow_up):
        seen.append({"question": question, "words": words, "is_follow_up": is_follow_up})
        return queue.pop(0) if queue else "ANSWER"

    c = InterviewController(s, m, ROOM, publish=publish,
                            progress=QuestionProgress(list(plan() if questions is None else questions)),
                            on_commit=committed.extend, follow_up_decider=decider, next_question_selector=selector,
                            utterance_classifier=classifier_fn or classifier)
    a = InterviewerAgent(m, ROOM, set_state=c.set_state, on_answer=c.on_answer, has_open_answer=c.has_open_answer,
                         follow_up_candidate=c.follow_up_candidate, decide_follow_up=c.decide_follow_up,
                         adaptive_options=c.adaptive_options, select_next_question=c.select_next_question,
                         absorb_unheard=c.absorb_unheard, classify_turn=c.classify_turn,
                         non_answer_directive=c.non_answer_directive, begin_turn=c.begin_turn,
                         reply_expected=c.reply_expected)
    return SimpleNamespace(m=m, s=s, c=c, a=a, committed=committed, published=published, seen=seen)


async def turn(agent, text, confidence=None):
    """One completed turn through the real gate: (directive, chat context) or (None, None)."""
    from livekit.agents import StopResponse, llm
    from app.ai.interview.agent import find_directive
    ctx = llm.ChatContext.empty()
    msg = llm.ChatMessage(role="user", content=[text])
    if confidence is not None:
        msg.transcript_confidence = confidence
    try:
        await agent.on_user_turn_completed(ctx, msg)
    except StopResponse:
        return None, None
    return find_directive(ctx), ctx


async def reply(agent, ctx):
    return "".join([piece async for piece in agent.llm_node(ctx, [], None)])


def shown(published):
    return json.loads(published[-1]["smarthr.interview.question"])["number"] if published else None


def spy(result):
    calls = []

    async def fn(*args):
        calls.append(args)
        return result
    return fn, calls


def stop_watchdog(r):
    r.c._cancel_watchdog()


# -- 1. ANSWER ---------------------------------------------------------------------------------------

def test_answer() -> None:
    section("1. ANSWER -> save -> (analysed by the backend) -> next question")
    for text in ("I build many projects.", "I don't learn Python.", "No."):
        decider, d_calls = spy(False)

        async def run(text=text, decider=decider):
            r = rig(labels=["ANSWER"], decider=decider)
            await r.c.run_opening()
            d, ctx = await turn(r.a, say(text))
            r.c.on_agent_state("speaking")
            await settle()
            stop_watchdog(r)
            return r, d
        r, d = asyncio.run(run())
        check(f"{text!r}: ANSWER -> saved (committed) and the interview advances to question 2",
              d.kind == "advance" and [x.text for x in r.committed] == [text] and r.c.progress.number == 2
              and shown(r.published) == 2)
        check(f"{text!r}: the follow-up decision ran (existing ANSWER flow)", len(d_calls) == 1)
    check("no 'elaborate' directive exists for short answers any more",
          "elaborate_note" not in dir(__import__("app.ai.interview.questions", fromlist=["x"])))


# -- 2. SIDE_QUESTION / REPEAT_REQUEST -------------------------------------------------------------------

def test_side_and_repeat() -> None:
    section("2. SIDE_QUESTION and REPEAT_REQUEST: nothing saved, the same question again")
    q1 = plan()[0]
    decider, d_calls = spy(True)
    selector, s_calls = spy(14)

    async def side():
        r = rig(labels=["SIDE_QUESTION"], decider=decider, selector=selector)
        await r.c.run_opening()
        await settle()
        d, ctx = await turn(r.a, say("Can you hear me?"))
        r.c.on_agent_state("speaking")
        r.c.on_agent_state("listening")
        await settle()
        stop_watchdog(r)
        return r, d
    r, d = asyncio.run(side())
    check("'Can you hear me?' -> side_reply, then the CURRENT question verbatim",
          d.kind == "side_reply" and d.say_after == q1.text and d.question_number == 1)
    check("...not saved, question index unchanged, no follow-up/adaptive call",
          r.committed == [] and r.c.progress.answers == [] and r.c.progress.number == 1 and shown(r.published) == 1
          and d_calls == [] and s_calls == [])
    from app.ai.interview.agent import shape_reply

    async def shaped(pieces):
        async def stream():
            for p in pieces:
                yield p
        return "".join([x async for x in shape_reply(stream(), d)])
    check("side reply: at most ONE very short model sentence, then the question",
          asyncio.run(shaped(["Yes, I can hear you. ", "Great to meet you. ", "Ready?"])) == "Yes, I can hear you. " + q1.text)

    async def repeat():
        r = rig(labels=["REPEAT_REQUEST"], decider=decider)
        await r.c.run_opening()
        d, ctx = await turn(r.a, say("Can you repeat that?"))
        spoken = await reply(r.a, ctx)          # fixed lead: no model involved
        r.c.on_agent_state("speaking")
        await settle()
        stop_watchdog(r)
        return r, d, spoken
    r, d, spoken = asyncio.run(repeat())
    check("'Can you repeat that?' -> 'Of course.' + the current question, word for word (no model call)",
          d.kind == "repeat" and spoken == "Of course. " + q1.text, spoken)
    check("...not saved, index unchanged", r.committed == [] and r.c.progress.number == 1)


# -- 3. NOISE_OR_INCOMPLETE ---------------------------------------------------------------------------------

def test_noise() -> None:
    section("3. NOISE_OR_INCOMPLETE: re-ask twice, then move on")
    q1, q2 = plan()[0], plan()[1]

    async def run():
        r = rig()
        await r.c.run_opening()
        out = []
        for text in ("That's", "uh... that's", "That's"):
            d, ctx = await turn(r.a, say(text))
            out.append((d, await reply(r.a, ctx)))
            r.c.on_agent_state("speaking")
            r.c.on_agent_state("listening")
        await settle()
        stop_watchdog(r)
        return r, out
    r, out = asyncio.run(run())
    check("1st noise -> 'Sorry, I didn't catch that.' + the current question",
          out[0][0].kind == "reask" and out[0][1] == "Sorry, I didn't catch that. " + q1.text, out[0][1])
    check("2nd noise -> re-asked again", out[1][0].kind == "reask" and out[1][1].endswith(q1.text))
    check("3rd noise -> moves on to question 2 ('Let's move on...' + Q2)",
          out[2][0].kind == "skip" and out[2][1] == "Let's move on to the next question. " + q2.text
          and r.c.progress.number == 2 and shown(r.published) == 2, out[2][1])
    check("...nothing saved for question 1, and the model classifier was never asked (deterministic)",
          r.committed == [] and r.c.progress.answers == [] and r.seen == [])

    async def last():
        r = rig(questions=[plan()[0]])
        await r.c.run_opening()
        for _ in range(3):
            d, ctx = await turn(r.a, say("and the"))
            r.c.on_agent_state("speaking")
            r.c.on_agent_state("listening")
        await settle()
        return r, d
    r, d = asyncio.run(last())
    from app.ai.interview.questions import CLOSING_AFTER_LAST
    check("noise x3 on the LAST question -> closing line, interview completes",
          d.kind == "skip" and d.say_after == CLOSING_AFTER_LAST and r.m.state.value == "completed"
          and r.c.completed_normally is True)

    async def low_conf():
        r = rig()
        await r.c.run_opening()
        d, _ = await turn(r.a, say("I worked at the bank for years"), confidence=0.1)
        stop_watchdog(r)
        return r, d
    r, d = asyncio.run(low_conf())
    check("a transcript with very low STT confidence -> re-asked, not saved", d.kind == "reask" and r.committed == [])


# -- 4. Reopened answers ---------------------------------------------------------------------------------------

def test_reopen() -> None:
    section("4. Reopened answers: classified on the merged text")
    part1, part2 = say("At my last job I rebuilt the forecasting pipeline"), say("after it failed.")

    async def run():
        r = rig(labels=["ANSWER", "ANSWER"])
        await r.c.run_opening()
        await turn(r.a, part1)
        d, _ = await turn(r.a, part2)
        r.c.on_agent_state("speaking")
        stop_watchdog(r)
        return r, d
    r, d = asyncio.run(run())
    check("the classifier saw the merged answer", r.seen[1]["words"] == f"{part1} {part2}")
    check("one merged answer saved", [x.text for x in r.committed] == [f"{part1} {part2}"] and d.kind == "advance")


# -- 5. Never silent -------------------------------------------------------------------------------------------------

def test_never_silent() -> None:
    section("5. Never silent: GPT failure/timeout fallback, reply watchdog")
    from livekit.agents import Agent

    import app.ai.interview.agent as agent_mod
    import app.ai.interview.controller as ctrl_mod
    q2 = plan()[1]
    real = Agent.default.llm_node

    def fake(mode):
        async def node(self, chat_ctx, tools, model_settings):
            if mode == "raise":
                raise RuntimeError(f"gateway down {TRANSCRIPT_SENTINEL}")
            if mode == "slow":
                await asyncio.sleep(5)
            if mode == "midway":
                yield "Thanks for sharing that. "
                raise RuntimeError("stream broke")
            yield "Thanks for sharing that. "
        return node

    async def one(mode):
        r = rig(labels=["ANSWER"], decider=spy(False)[0])
        await r.c.run_opening()
        d, ctx = await turn(r.a, say(LONG))
        Agent.default.llm_node = fake(mode)
        try:
            return await reply(r.a, ctx), r
        finally:
            Agent.default.llm_node = real
            stop_watchdog(r)
    saved_timeout = agent_mod.LLM_FIRST_SENTENCE_TIMEOUT_S
    agent_mod.LLM_FIRST_SENTENCE_TIMEOUT_S = 0.05
    try:
        ok, _ = asyncio.run(one("ok"))
        boom, _ = asyncio.run(one("raise"))
        slow, _ = asyncio.run(one("slow"))
        mid, _ = asyncio.run(one("midway"))
    finally:
        agent_mod.LLM_FIRST_SENTENCE_TIMEOUT_S = saved_timeout
    check("normal: GPT's acknowledgement + the next question", ok == "Thanks for sharing that. " + q2.text, ok)
    check("GPT raises -> 'Thank you.' + the next question (never silent)", boom == "Thank you. " + q2.text, boom)
    check("GPT too slow -> the same fallback", slow == "Thank you. " + q2.text, slow)
    check("GPT breaks mid-reply -> what was said + the question it still owed",
          mid == "Thanks for sharing that. " + q2.text, mid)
    rec = [x for x in CAP.diag if x["event"] == "llm_reply" and x.get("fallback") is True]
    check("each fallback is logged: llm_reply fallback=true with a code (model_error / timeout)",
          {x.get("code") for x in rec} >= {"model_error", "timeout"})

    async def watchdog(speak_in_time: bool):
        r = rig(labels=["ANSWER"], decider=spy(False)[0])
        await r.c.run_opening()
        said_before = len(r.s.said)
        d, _ = await turn(r.a, say(LONG))
        if speak_in_time:
            r.c.on_agent_state("speaking")
        await asyncio.sleep(0.1)
        return r, r.s.said[said_before:], d
    saved = ctrl_mod.REPLY_DEADLINE_S
    ctrl_mod.REPLY_DEADLINE_S = 0.05
    try:
        r, said, d = asyncio.run(watchdog(False))
        check("no reply started in time -> the controller speaks a fallback + the next question",
              said and said[-1][0] == "Thank you. " + q2.text, str(said))
        check("...and logs pipeline_error no_reply for that turn",
              any(x["event"] == "pipeline_error" and x.get("code") == "no_reply" for x in CAP.diag))
        r, said, d = asyncio.run(watchdog(True))
        check("a reply that started in time -> no fallback spoken", said == [], str(said))
    finally:
        ctrl_mod.REPLY_DEADLINE_S = saved


# -- 6. Observability, configuration, debug capture ----------------------------------------------------

def test_observability() -> None:
    section("6. Turn ids, configuration, debug capture")
    from app.ai.interview import diagnostics as diag

    turned = [x for x in CAP.diag if x["event"] in ("turn_finalized", "stt_turn", "turn_classified", "turn_decided",
                                                     "llm_reply", "reply_started")]
    check("every stage event carries a turn id (STT, classifier, decision, GPT, reply)",
          turned and all(isinstance(x.get("turn"), int) for x in turned))
    check("classification events: label, noise reason when deterministic, duration",
          any(x["event"] == "turn_classified" and x.get("noise_reason") == "dangling" for x in CAP.diag)
          and all("duration_ms" in x for x in CAP.diag if x["event"] == "turn_classified"))
    check("stt_turn carries the STT confidence when known",
          any(x["event"] == "stt_turn" and x.get("confidence_pct") == 10 for x in CAP.diag))
    check("reply_started carries the latency from turn end to audio",
          any(x["event"] == "reply_started" and isinstance(x.get("latency_ms"), int) for x in CAP.diag))
    check("no diagnostic value was redacted", not [x for x in CAP.diag if diag.REDACTED in x.values()])

    from app.ai.interview.config import stt_language
    check("STT language: en / ar / multi / en-US accepted; junk falls back to en",
          [stt_language(v) for v in ("en", "ar", "multi", "en-US", "arabic!!", "", None)]
          == ["en", "ar", "multi", "en-US", "en", "en", "en"])
    from app.ai.interview import turn_policy as tp
    saved = {k: os.environ.get(k) for k in (tp.ENDPOINT_MIN_VAR, tp.ENDPOINT_MAX_VAR)}
    try:
        for k in saved:
            os.environ.pop(k, None)
        check("turn timing defaults unchanged (1.2 s / 4.0 s)", tp.endpointing_delays() == (1.2, 4.0))
        os.environ[tp.ENDPOINT_MIN_VAR] = "1.5"
        check("SMARTHR_INTERVIEW_ENDPOINT_MIN_S=1.5 is applied", tp.endpointing_delays() == (1.5, 4.0))
        os.environ[tp.ENDPOINT_MIN_VAR] = "0.1"
        check("an out-of-range value is ignored", tp.endpointing_delays() == (1.2, 4.0))
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    from livekit import rtc

    from app.ai.interview import debug_capture as dc
    with tempfile.TemporaryDirectory() as tmp:
        cap = dc.TurnCapture(ROOM, enabled=True, root=Path(tmp))
        for _ in range(5):
            cap.add_frame(rtc.AudioFrame.create(16000, 1, 160))
        cap.end_turn(3, transcript="I build many projects.", stt_confidence=0.9)
        cap.update(3, classification="ANSWER", reply="Thank you.")
        folder = Path(tmp) / ROOM
        data = json.loads((folder / "turn-3.json").read_text(encoding="utf-8"))
        check("debug capture ON: turn WAV + JSON written side by side",
              (folder / "turn-3.wav").stat().st_size > 44 and data["transcript"] == "I build many projects."
              and data["classification"] == "ANSWER" and data["audio_file"] == "turn-3.wav")
        off = dc.TurnCapture(ROOM + "x", enabled=False, root=Path(tmp))
        off.add_frame(rtc.AudioFrame.create(16000, 1, 160))
        off.end_turn(1, transcript=TRANSCRIPT_SENTINEL)
        check("debug capture OFF: nothing is written", not (Path(tmp) / (ROOM + "x")).exists())
    saved_env = {k: os.environ.get(k) for k in ("SMARTHR_ENV", dc.CAPTURE_VAR, "SMARTHR_INTERVIEW_BACKEND_URL")}
    try:
        os.environ[dc.CAPTURE_VAR] = "true"
        os.environ["SMARTHR_ENV"] = "development"
        check("capture requested in development -> enabled", dc.capture_enabled() is True)
        os.environ["SMARTHR_ENV"] = "production"
        check("capture requested in PRODUCTION -> never enabled", dc.capture_enabled() is False)
        os.environ["SMARTHR_INTERVIEW_BACKEND_URL"] = "https://smarthr.example.com"
        from app.ai.interview import production
        try:
            production.validate_production()
            refused = False
        except production.WorkerConfigurationError as e:
            refused = dc.CAPTURE_VAR in str(e)
        check("the production worker refuses to start with debug capture on", refused)
    finally:
        for k, v in saved_env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    async def conn():
        import app.ai.interview.worker as w
        return w.build_session().conn_options.llm_conn_options
    o = asyncio.run(conn())
    check("GPT calls fail fast: 6 s timeout, 1 retry (was 10 s x 4 attempts)", (o.timeout, o.max_retry) == (6.0, 1))


# -- 7. A re-ask / skip takes effect only when heard -------------------------------------------------------

async def _noise_until_skip(r):
    """Two re-asks the applicant HEARD, then a third noisy turn: the skip decision."""
    for _ in range(2):
        await turn(r.a, say("That's"))
        r.c.on_agent_state("speaking")
        r.c.on_agent_state("listening")
    d, _ = await turn(r.a, say("That's"))
    return d


def test_skip_when_heard() -> None:
    section("7. A skip / re-ask takes effect only when its reply is heard")
    import app.ai.interview.controller as ctrl_mod
    q1, q2 = plan()[0], plan()[1]

    async def normal():
        r = rig()
        await r.c.run_opening()
        d = await _noise_until_skip(r)
        provisional = r.c.progress._pending is not None
        r.c.on_agent_state("speaking")
        r.c.on_agent_state("listening")
        await settle()
        stop_watchdog(r)
        return r, d, provisional
    r, d, provisional = asyncio.run(normal())
    check("normal flow: the skip is provisional until heard, then the interview is on question 2",
          d.kind == "skip" and provisional and r.c.progress._pending is None
          and r.c.progress.number == 2 and r.c.progress.current.id == q2.id and shown(r.published) == 2)

    async def cut_off():
        r = rig()
        await r.c.run_opening()
        await _noise_until_skip(r)
        r.c.on_agent_state("thinking")
        r.c.on_agent_state("listening")              # the skip reply was dropped unheard
        stayed = (r.c.progress.current.id, r.c.progress.number, r.c.progress.noise_reasks.get(q1.id))
        d, _ = await turn(r.a, say(LONG))
        r.c.on_agent_state("speaking")
        await settle()
        stop_watchdog(r)
        return r, stayed, d
    r, stayed, d = asyncio.run(cut_off())
    check("reply cut off: still on question 1 (the one heard), both heard re-asks still counted",
          stayed == (q1.id, 1, 2), str(stayed))
    check("...the next answer is recorded against question 1, then the interview advances",
          [(x.question_id, x.question_number) for x in r.committed] == [(q1.id, 1)] and d.kind in ("advance", "follow_up"))
    check("...and it is diagnosed as reply_not_heard",
          any(x["event"] == "reply_not_heard" and x.get("question") == 1 for x in CAP.diag))

    async def spoke_first():
        r = rig()
        await r.c.run_opening()
        await _noise_until_skip(r)
        d, _ = await turn(r.a, say(LONG))           # the applicant spoke before the skip played
        r.c.on_agent_state("speaking")
        stop_watchdog(r)
        return r
    r = asyncio.run(spoke_first())
    check("the applicant speaks again before the skip plays: reverted, the answer goes to question 1",
          [(x.question_id, x.question_number) for x in r.committed] == [(q1.id, 1)])

    async def tts_failure():
        r = rig()
        await r.c.run_opening()
        await _noise_until_skip(r)
        before = len(r.s.said)
        await asyncio.sleep(0.1)                     # no "speaking" ever arrives
        return r, r.s.said[before:]
    saved = ctrl_mod.REPLY_DEADLINE_S
    ctrl_mod.REPLY_DEADLINE_S = 0.05
    try:
        r, said = asyncio.run(tts_failure())
    finally:
        ctrl_mod.REPLY_DEADLINE_S = saved
    check("TTS failure: the watchdog re-speaks the CURRENT question, not the next one",
          said and said[-1][0] == "Sorry, I didn't catch that. " + q1.text, str(said))
    check("...and the interview did not move on", r.c.progress.current.id == q1.id and r.c.progress.number == 1)

    async def reask_unheard():
        r = rig()
        await r.c.run_opening()
        d, _ = await turn(r.a, say("That's"))
        r.c.on_agent_state("thinking")
        r.c.on_agent_state("listening")              # the re-ask was never heard
        stop_watchdog(r)
        return r, d
    r, d = asyncio.run(reask_unheard())
    check("an unheard re-ask does not count toward the limit", d.kind == "reask"
          and r.c.progress.noise_reasks.get(q1.id, 0) == 0)

    async def last_question():
        r = rig(questions=[q1])
        await r.c.run_opening()
        d = await _noise_until_skip(r)
        r.c.on_agent_state("thinking")
        r.c.on_agent_state("listening")              # the closing line was never heard
        stop_watchdog(r)
        return r, d
    r, d = asyncio.run(last_question())
    check("last question: an unheard skip-to-closing is reverted - the interview is still running on Q1",
          d.kind == "skip" and r.c.progress.finished is False and r.m.active and r.c.progress.current.id == q1.id)


# -- 8. Speech during the welcome -------------------------------------------------------------------------

class WelcomeSession(Session):
    """Fires `hook` while the first thing (the welcome) is being said."""

    def __init__(self):
        super().__init__()
        self.hook = None

    def say(self, text, allow_interruptions=None):
        handle = super().say(text, allow_interruptions)
        if len(self.said) == 1 and self.hook is not None:
            self.hook()
        return handle


def test_welcome() -> None:
    section("8. Speech during the (uninterruptible) welcome")
    from app.ai.interview.agent import SPOKE_DURING_WELCOME, WELCOME, WELCOME_FOR_ROLE
    q1 = plan()[0]

    async def opening(speak: bool):
        s = WelcomeSession()
        r = rig(session=s)
        if speak:
            s.hook = lambda: r.c.on_user_state("speaking")
        await r.c.run_opening()
        return r
    r = asyncio.run(opening(True))
    check("the welcome stays uninterruptible; Q1 stays interruptible",
          r.s.said[0] == (WELCOME.format(count=len(plan())), False) and r.s.said[1][1] is None)
    check("the applicant spoke during the welcome -> told why, then Q1 verbatim, then listening",
          r.s.said[1][0] == f"{SPOKE_DURING_WELCOME} {q1.text}" and r.m.state.value == "listening", str(r.s.said))
    check("...diagnosed as speech_during_welcome", any(x["event"] == "speech_during_welcome" for x in CAP.diag))
    r = asyncio.run(opening(False))
    check("no speech during the welcome -> Q1 alone, verbatim", r.s.said[1][0] == q1.text)

    async def during_q1():
        r = rig()
        await r.c.run_opening()
        r.c.on_user_state("speaking")                # speaking during/after Q1 is normal
        return r
    check("speaking after the welcome is not flagged", asyncio.run(during_q1()).c._spoke_during_welcome is False)
    check("the welcome is short and says when to answer",
          all("please answer after each one" in w and w.endswith("Here is the first.") for w in (WELCOME, WELCOME_FOR_ROLE))
          and len(WELCOME.format(count=5).split()) <= 25)


# -- 9. Trimmed debug audio -----------------------------------------------------------------------------------

def test_trimmed_capture() -> None:
    section("9. Debug audio is trimmed to the speech (+-300 ms)")
    import wave

    from livekit import rtc

    from app.ai.interview import debug_capture as dc

    def fill(cap, seconds=3.0, start=1000.0):
        for i in range(int(seconds * 100)):                      # 10 ms frames at 16 kHz
            cap.add_frame(rtc.AudioFrame.create(16000, 1, 160), now=start if i == 0 else None)

    def duration(path):
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cap = dc.TurnCapture(ROOM, enabled=True, root=root, raw=False)
        fill(cap)                                                   # t0 = 999.99 .. 1002.99
        cap.end_turn(1, start=1001.0, stop=1001.5, transcript="Yes")
        folder = root / ROOM
        meta = json.loads((folder / "turn-1.json").read_text(encoding="utf-8"))
        got = duration(folder / "turn-1.wav")
        check("the WAV holds the speech window + 300 ms each side (0.5 s speech -> ~1.1 s)",
              abs(got - 1.1) <= 0.02, f"{got:.3f}s")
        check("...recorded as trimmed, with window and padding", meta["trimmed"] is True
              and meta["speech_window_ms"] == 500 and meta["padding_ms"] == 300 and meta["raw_audio_file"] is None)
        check("no raw copy unless asked for", not (folder / "turn-1.raw.wav").exists())

        fill(cap)
        cap.end_turn(2, transcript="no times known")
        meta = json.loads((folder / "turn-2.json").read_text(encoding="utf-8"))
        check("no speech times known -> the whole buffer, trimmed=false",
              abs(duration(folder / "turn-2.wav") - 3.0) <= 0.02 and meta["trimmed"] is False)

        edge = dc.TurnCapture(ROOM + "-edge", enabled=True, root=root, raw=False)
        ef = root / (ROOM + "-edge")

        def edge_case(n, start, stop):
            fill(edge)                                              # 999.99 .. 1002.99 again, per turn
            edge.end_turn(n, start=start, stop=stop)
            return duration(ef / f"turn-{n}.wav"), json.loads((ef / f"turn-{n}.json").read_text(encoding="utf-8"))
        # the sample clock continues across turns: each fill() is the next 3 s
        d, m = edge_case(1, 1001.0, 1001.5)
        check("edge: a normal window on the first buffer", abs(d - 1.1) <= 0.02 and m["trimmed"] is True)
        d, m = edge_case(2, 1004.5, 1099.0)                          # stop far beyond the buffer end (1005.99)
        check("edge: stop beyond the buffer -> clipped to the end (start-0.3 .. end)",
              abs(d - 1.79) <= 0.03 and m["trimmed"] is True, f"{d:.3f}")
        d, m = edge_case(3, -5.0, 1.0)
        check("edge: negative start -> the whole buffer, trimmed=false, noted",
              abs(d - 3.0) <= 0.02 and m["trimmed"] is False and m["trim_note"] == "unusable speech times")
        d, m = edge_case(4, 5000.0, 5001.0)
        check("edge: a window entirely outside the buffer -> the whole buffer, noted",
              abs(d - 3.0) <= 0.02 and m["trimmed"] is False and "outside" in m["trim_note"])
        d, m = edge_case(5, 1014.0, 1013.0)
        check("edge: stop before start -> the whole buffer", abs(d - 3.0) <= 0.02 and m["trimmed"] is False)
        d, m = edge_case(6, float("nan"), 1016.0)
        check("edge: a NaN time -> the whole buffer", abs(d - 3.0) <= 0.02 and m["trimmed"] is False)
        d, m = edge_case(7, None, None)
        check("edge: times missing -> the whole buffer, no note", abs(d - 3.0) <= 0.02 and m["trim_note"] is None)

        raw = dc.TurnCapture(ROOM + "-raw", enabled=True, root=root, raw=True)
        fill(raw)
        raw.end_turn(1, start=1001.0, stop=1001.5)
        rf = root / (ROOM + "-raw")
        check("raw mode: the trimmed WAV AND the untrimmed .raw.wav",
              abs(duration(rf / "turn-1.wav") - 1.1) <= 0.02 and abs(duration(rf / "turn-1.raw.wav") - 3.0) <= 0.02)

        off = dc.TurnCapture(ROOM + "-off", enabled=False, root=root)
        fill(off)
        off.end_turn(1, start=1001.0, stop=1001.5)
        check("disabled: nothing written", not (root / (ROOM + "-off")).exists())
    saved = os.environ.get(dc.CAPTURE_VAR)
    try:
        os.environ[dc.CAPTURE_VAR] = "raw"
        check("SMARTHR_INTERVIEW_DEBUG_CAPTURE=raw is a capture request", dc.capture_mode() == "raw" and dc.capture_requested())
        os.environ[dc.CAPTURE_VAR] = "false"
        check("false -> off", dc.capture_mode() is None and not dc.capture_requested())
    finally:
        os.environ.pop(dc.CAPTURE_VAR, None) if saved is None else os.environ.__setitem__(dc.CAPTURE_VAR, saved)


# -- 10. Coverage carried over from the earlier classifier suite ---------------------------------------------

def test_restored_coverage() -> None:
    section("10. Checks restored from the earlier classifier suite (new labels)")
    src = (ROOT / "app/ai/interview/agent.py").read_text(encoding="utf-8")
    body = src[src.index("async def _decide"):src.index("def _current_instructions")]
    check("the classifier runs FIRST in _decide, before follow-up / adaptive / on_answer",
          body.index("self.classify_turn(") < body.index("self.follow_up_candidate(")
          < body.index("self.adaptive_options(") < body.index("return self.on_answer(kind, text)"))
    gate = src[src.index("async def on_user_turn_completed"):src.index("async def _decide")]
    check("the empty/filler gate, the turn lock and absorb_unheard still come first",
          gate.index('if kind in ("empty", "filler")') < gate.index("async with self._turn_lock")
          < gate.index("self.absorb_unheard()") < gate.index("await self._decide("))

    async def counters():
        r = rig(labels=["SIDE_QUESTION", "REPEAT_REQUEST"])
        await r.c.run_opening()
        for text in ("Can you hear me?", "Can you repeat that?", "That's"):
            await turn(r.a, say(text))
            r.c.on_agent_state("speaking")
            r.c.on_agent_state("listening")
        stop_watchdog(r)
        return r
    r = asyncio.run(counters())
    check("non-answers never increment the answer counters", r.m.counters.answers == 0 and r.m.counters.short == 0)

    async def cancelled():
        async def slow(*_a):
            await asyncio.sleep(5)
        r = rig(classifier_fn=slow)
        await r.c.run_opening()
        task = asyncio.ensure_future(turn(r.a, say(LONG)))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        stop_watchdog(r)
        return r
    r = asyncio.run(cancelled())
    check("a turn cancelled mid-classification is recorded (can be reopened and merged)",
          len(r.c.progress.answers) == 1 and r.m.counters.answers == 1)

    async def follow_up_current():
        r = rig(labels=["ANSWER", "REPEAT_REQUEST"], decider=spy(True)[0])
        await r.c.run_opening()
        await turn(r.a, say(LONG))
        r.c.on_agent_state("speaking")
        r.c.on_agent_state("listening")
        d, _ = await turn(r.a, say("Could you say that again please?"))
        stop_watchdog(r)
        return d
    d = asyncio.run(follow_up_current())
    check("while a follow-up is current, a repeat request repeats the FOLLOW-UP verbatim under Q1's number",
          d.kind == "repeat" and d.say_after == plan()[0].follow_up.text and d.question_number == 1)

    async def dropped_then_answer():
        r = rig(labels=["SIDE_QUESTION", "ANSWER"])
        await r.c.run_opening()
        await turn(r.a, say("Can you hear me?"))
        r.c.on_agent_state("thinking")
        r.c.on_agent_state("listening")              # the side reply was dropped unheard
        nothing_pending = not r.c._non_answer_pending and r.c._next_speech_state is None
        d, _ = await turn(r.a, say(LONG))
        r.c.on_agent_state("speaking")
        await settle()
        stop_watchdog(r)
        return r, d, nothing_pending
    r, d, nothing_pending = asyncio.run(dropped_then_answer())
    check("a non-answer reply dropped unheard leaves nothing pending", nothing_pending)
    check("...and the next ANSWER proceeds normally (answer 1 on question 1, Q2 spoken)",
          [(x.sequence, x.question_id) for x in r.committed] == [(1, 11)] and shown(r.published) == 2)
    check("turn_decided shows every non-answer directive",
          {"side_reply", "repeat", "reask", "skip"} <= {x.get("directive") for x in CAP.diag if x["event"] == "turn_decided"})


# -- 11. Startup STT configuration line ------------------------------------------------------------------------

def test_startup_line() -> None:
    section("11. Worker startup: one STT configuration line, Arabic warning")
    from app.ai.interview.worker import log_stt_configuration
    fake = lambda lang, model: SimpleNamespace(language=lang, stt_model=model, tts_model="cartesia/sonic-3",  # noqa: E731
                                               api_key="test-key-" + secrets.token_hex(8),
                                               api_secret=secrets.token_urlsafe(32))
    before = len(CAP.lines)
    warn_ar = log_stt_configuration(fake("ar", "deepgram/nova-3"))
    warn_multi = log_stt_configuration(fake("multi", "deepgram/nova-3"))
    warn_en = log_stt_configuration(fake("en", "deepgram/nova-3"))
    warn_other = log_stt_configuration(fake("ar", "speechmatics/enhanced"))
    lines = CAP.lines[before:]
    check("ar / multi on deepgram/nova-3 -> a warning naming SMARTHR_INTERVIEW_STT_MODEL",
          warn_ar and warn_multi and "SMARTHR_INTERVIEW_STT_MODEL" in warn_ar and "speechmatics/enhanced" in warn_ar)
    check("en, or another model -> no warning", warn_en is None and warn_other is None)
    check("the line carries language and models - never a key or secret",
          any("language=ar stt=deepgram/nova-3" in l for l in lines)
          and not any("NEVER-LOGGED" in l for l in lines))


def main() -> int:
    print("SmartHR - AI Interview turn labels / state machine / never-silent tests")
    from app.ai.interview import diagnostics as diag
    diag.reset()
    root = logging.getLogger()
    root.addHandler(CAP)
    level = root.level
    root.setLevel(logging.DEBUG)
    try:
        test_answer()
        test_side_and_repeat()
        test_noise()
        test_reopen()
        test_never_silent()
        test_skip_when_heard()
        test_welcome()
        test_trimmed_capture()
        test_restored_coverage()
        test_startup_line()
        test_observability()
    finally:
        root.removeHandler(CAP)
        root.setLevel(level)
    section("7. Privacy: normal logs carry no transcript")
    leaked = [l for l in CAP.lines for s in SPOKEN + [TRANSCRIPT_SENTINEL] if len(s) > 8 and s in l]
    check(f"{len(CAP.lines)} log lines; none contains what the applicant said", not leaked,
          leaked[0][:100] if leaked else "")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
