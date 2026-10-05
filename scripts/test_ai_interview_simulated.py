"""AI Interview - whole interviews simulated through a REAL LiveKit AgentSession. Offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_simulated

No microphone, no LiveKit server, no real model (see scripts/sim_interview_harness.py:
livekit-agents' AgentSession/AgentActivity are real; the LLM, the TTS and
the audio sink are fakes). Turns are committed through LiveKit's own
end-of-turn entry point, so the reply runs on LiveKit's scheduler, through
our llm_node, the TTS pipeline, speech handles, interruptions and the
transcript synchronizer.

Covers: the answer flow, "That's" x3, "Can you hear me?", "Can you repeat
that?", LLM raise / hang / fail mid-reply (with timings), TTS that never
starts, interruptions while a skip and a re-ask are playing, speech during
the welcome (VAD event, and a turn LiveKit itself drops) - and that no log
line carries what the applicant said.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.sim_interview_harness as H  # noqa: E402

passed = 0
failed: list[str] = []
SPOKEN: list[str] = []
TIMINGS: dict[str, float] = {}


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


def plan():
    from app.ai.interview.questions import PlannedQuestion as Q
    return [Q(11, 1, "general", "Tell me about yourself."),
            Q(12, 2, "behavioral", "Describe a challenge you faced."),
            Q(13, 3, "technical", "Which tools do you use for data work?")]


def scripted(labels: dict[str, str], reply=("text", "Thanks for sharing that."), side="Yes, I can hear you."):
    """The classifier answers from `labels` (by the applicant's words);
    a side reply says `side`; every other reply is `reply`."""
    from app.ai.interview.utterance import CLASSIFY_TOOL, NON_ANSWER

    def script(ctx, tools):
        text = "\n".join(i.text_content or "" for i in ctx.items if getattr(i, "role", None) in ("user", "system"))
        if CLASSIFY_TOOL in tools:
            # Only the applicant's block - the prompt's own examples mention
            # the same sentences.
            said = text.split("<<<APPLICANT_UTTERANCE", 1)[-1]
            for words, label in labels.items():
                if words in said:
                    return ("tool", CLASSIFY_TOOL, {"classification": label})
            return ("tool", CLASSIFY_TOOL, {"classification": "ANSWER"})
        if "said something aside" in text:
            return ("text", side)
        return reply
    return script


def classify_calls(sim) -> int:
    from app.ai.interview.utterance import CLASSIFY_TOOL
    return sum(1 for c in sim.model.calls if CLASSIFY_TOOL in c)


async def opened(script, **kw):
    H.SECONDS_PER_WORD = kw.pop("spw", 0.0005)
    sim = await H.start_interview(plan(), script, **kw)
    await sim.controller.run_opening()
    return sim


# -- 1. Conversation flow -----------------------------------------------------------------------------

def test_flow() -> None:
    section("1. Whole-interview flow through LiveKit's own scheduler")
    q = plan()

    async def answers():
        sim = await opened(scripted({}))
        r1 = await H.turn_and_reply(sim, say("I build many projects."))
        r2 = await H.turn_and_reply(sim, say("I don't learn Python."))
        await sim.session.aclose()
        return sim, r1, r2
    sim, r1, r2 = asyncio.run(answers())
    check("'I build many projects.' saved, reply = acknowledgement + Q2 verbatim",
          r1 == f"Thanks for sharing that. {q[1].text}" and sim.committed[0].text == "I build many projects.", str(r1))
    check("'I don't learn Python.' saved, the interview advances to Q3",
          r2 == f"Thanks for sharing that. {q[2].text}" and [x.question_id for x in sim.committed] == [11, 12])

    async def noise():
        sim = await opened(scripted({}))
        replies = [await H.turn_and_reply(sim, say("That's")) for _ in range(3)]
        await sim.session.aclose()
        return sim, replies
    sim, replies = asyncio.run(noise())
    check("'That's' -> re-asked twice, then moves on to Q2",
          replies == [f"Sorry, I didn't catch that. {q[0].text}"] * 2 + [f"Let's move on to the next question. {q[1].text}"],
          str(replies))
    check("...nothing saved, the classifier model never asked (deterministic noise)",
          sim.committed == [] and classify_calls(sim) == 0 and sim.controller.progress.number == 2)

    async def side_and_repeat():
        sim = await opened(scripted({"Can you hear me?": "SIDE_QUESTION", "Can you repeat that?": "REPEAT_REQUEST"}))
        a = await H.turn_and_reply(sim, say("Can you hear me?"))
        b = await H.turn_and_reply(sim, say("Can you repeat that?"))
        await sim.session.aclose()
        return sim, a, b
    sim, a, b = asyncio.run(side_and_repeat())
    check("'Can you hear me?' -> one short reply + the SAME question, nothing saved",
          a == f"Yes, I can hear you. {q[0].text}" and sim.committed == [], str(a))
    check("'Can you repeat that?' -> 'Of course.' + the same question", b == f"Of course. {q[0].text}", str(b))
    check("...still on question 1", sim.controller.progress.number == 1)


# -- 2. LLM failures, with timings ----------------------------------------------------------------------

def test_llm_failures() -> None:
    section("2. The LLM raises / hangs / fails mid-reply: fallback + next question, logged, in time")
    from app.ai.interview.agent import LLM_FIRST_SENTENCE_TIMEOUT_S
    q = plan()

    async def run(reply, label):
        sim = await opened(scripted({}, reply=reply))
        began = time.monotonic()
        r = await H.turn_and_reply(sim, say(f"I led the migration project {label}."), timeout=20)
        TIMINGS[label] = time.monotonic() - began
        await sim.session.aclose()
        return sim, r
    for label, reply, expect, limit in (
            ("raise", ("raise",), f"Thank you. {q[1].text}", 4.0),
            ("hang", ("hang",), f"Thank you. {q[1].text}", LLM_FIRST_SENTENCE_TIMEOUT_S + 2.0),
            # Over LiveKit's stream a sentence is released only once the text
            # after it starts, so a failure right after one complete sentence
            # may lose it: then the fixed fallback is spoken instead.
            ("midway", ("midway", "Thanks for sharing that."), (f"Thanks for sharing that. {q[1].text}",
                                                                f"Thank you. {q[1].text}"), 4.0)):
        before = len(CAP.diag)
        sim, r = asyncio.run(run(reply, label))
        rec = [x for x in CAP.diag[before:] if x["event"] == "llm_reply" and x.get("fallback") is True]
        ok = r in expect if isinstance(expect, tuple) else r == expect
        check(f"LLM {label}: the fallback + the next question is spoken ({TIMINGS[label]:.1f}s, limit {limit:.0f}s)",
              ok and TIMINGS[label] <= limit, f"{r!r} {TIMINGS[label]:.2f}s")
        check(f"...logged llm_reply fallback=true ({rec[0].get('code') if rec else None}), answer still saved",
              bool(rec) and [x.text for x in sim.committed] == [f"I led the migration project {label}."])


# -- 3. TTS never starts; interruptions during a skip / re-ask ----------------------------------------------------

def test_tts_and_interruptions() -> None:
    section("3. TTS never starts; interruptions while a skip / re-ask is playing")
    import app.ai.interview.controller as ctrl_mod
    q = plan()

    async def tts_dead():
        sim = await opened(scripted({}))
        for _ in range(2):
            await H.turn_and_reply(sim, say("That's"))
        sim.tts.hang = True                              # the skip reply never produces audio
        H.end_turn(sim, say("That's"))
        await asyncio.sleep(0.3)
        sim.tts.hang = False                             # the fallback itself can be spoken
        ok = await H.wait_for(lambda: any(t.startswith("Sorry, I didn't catch that.") for t in H.spoken(sim)[3:]), 5)
        await asyncio.sleep(0.2)
        await sim.session.aclose()
        return sim, ok
    saved = ctrl_mod.REPLY_DEADLINE_S
    ctrl_mod.REPLY_DEADLINE_S = 1.0
    try:
        sim, ok = asyncio.run(tts_dead())
    finally:
        ctrl_mod.REPLY_DEADLINE_S = saved
    last = [t for t in H.spoken(sim) if t.startswith("Sorry")][-1] if ok else None
    check("TTS never starts the skip reply: the watchdog re-speaks the CURRENT question",
          ok and last == f"Sorry, I didn't catch that. {q[0].text}", str(H.spoken(sim)[-3:]))
    check("...the interview did not move on (still question 1, nothing saved)",
          sim.controller.progress.current.id == 11 and sim.controller.progress.number == 1 and sim.committed == [])

    async def interrupted(kind: str, cut_after: float, spw: float = 0.25):
        sim = await opened(scripted({}), speed=1.0, synced=True)
        reasks = 2 if kind == "skip" else 0
        for _ in range(reasks):
            await H.turn_and_reply(sim, say("That's"))
        H.SECONDS_PER_WORD = spw
        H.end_turn(sim, say("That's"))
        await H.wait_for(lambda: sim.session.agent_state == "speaking", 10)
        await asyncio.sleep(cut_after)
        sim.session.interrupt()                          # a barge-in stops the reply
        await asyncio.sleep(0.6)
        H.SECONDS_PER_WORD = 0.0005
        state = (sim.controller.progress.number, sim.controller.progress.current.id,
                 dict(sim.controller.progress.noise_reasks), H.spoken(sim)[-1] if H.spoken(sim) else None)
        answer = await H.turn_and_reply(sim, say("I rebuilt the forecasting pipeline."))
        await sim.session.aclose()
        return sim, state, answer
    sim, (number, current, noise, played), answer = asyncio.run(interrupted("skip", 0.6))
    check("skip interrupted before the next question was played: undone (back on Q1)",
          number == 1 and current == 11 and not played.endswith(q[1].text), f"{number} {current} {played!r}")
    check("...the barge-in answer is recorded against Q1 (the question heard)",
          [(x.question_id, x.question_number) for x in sim.committed] == [(11, 1)], str(sim.committed))
    sim, (number, current, noise, played), answer = asyncio.run(interrupted("reask", 0.4))
    check("re-ask interrupted before the question was played: it does not count", noise.get(11, 0) == 0
          and number == 1, f"{noise} {played!r}")
    sim, (number, current, noise, played), answer = asyncio.run(interrupted("skip", 3.3, spw=0.2))
    check("skip interrupted AFTER the whole next question played: kept (on Q2)",
          number == 2 and current == 12 and played.endswith(q[1].text), f"{number} {played!r}")
    check("...and the answer then goes to Q2", [(x.question_id, x.question_number) for x in sim.committed] == [(12, 2)])


# -- 4. Welcome --------------------------------------------------------------------------------------------------------

def test_welcome() -> None:
    section("4. Speech during the welcome (VAD event; a turn LiveKit drops)")
    from app.ai.interview.agent import SPOKE_DURING_WELCOME
    q = plan()

    async def run(also_turn: bool):
        H.SECONDS_PER_WORD = 0.05
        sim = await H.start_interview(plan(), scripted({}), speed=1.0)
        opening = asyncio.ensure_future(sim.controller.run_opening())
        await H.wait_for(lambda: sim.session.agent_state == "speaking", 5)    # the welcome is playing
        sim.session._update_user_state("speaking")                           # VAD: the applicant talks
        turns_before = sim.agent.turn_id
        if also_turn:
            H.end_turn(sim, say("Hello, can you hear me now?"))               # LiveKit drops this turn
        sim.session._update_user_state("listening")
        await opening
        await H.wait_for(lambda: sim.session.agent_state == "listening", 5)
        await asyncio.sleep(0.2)
        H.SECONDS_PER_WORD = 0.0005
        await sim.session.aclose()
        return sim, turns_before
    sim, turns_before = asyncio.run(run(True))
    spoken = H.spoken(sim)
    check("speech during the welcome -> Q1 is preceded by the 'couldn't hear you' line",
          spoken[1] == f"{SPOKE_DURING_WELCOME} {q[0].text}", str(spoken))
    check("...the turn that ended during the welcome was dropped by LiveKit: never reached our hook, nothing saved",
          sim.agent.turn_id == turns_before and sim.committed == [])
    check("...diagnosed as speech_during_welcome", any(x["event"] == "speech_during_welcome" for x in CAP.diag))
    sim, _ = asyncio.run(run(False))
    check("(VAD event without a turn gives the same apology line)", H.spoken(sim)[1].startswith(SPOKE_DURING_WELCOME))


# -- 5. An answer is final only once the next question has been HEARD ------------------------------------------

def test_answer_until_heard() -> None:
    section("5. An answer is sent only once the next question has been heard")
    from app.ai.interview.questions import REPEAT_AFTER_CUT
    q = plan()
    ack = "Thanks for sharing that."
    reply_q2 = f"{ack} {q[1].text}"
    first = "I build many projects."

    async def normal():
        sim = await opened(scripted({}), speed=1.0, synced=True, spw=0.2)
        H.end_turn(sim, say(first))
        await H.wait_for(lambda: sim.session.agent_state == "speaking", 10)
        at_start = list(H.sent(sim))                     # the reply (ack + Q2) has only STARTED
        await H.wait_for(lambda: sim.session.agent_state == "listening" and H.sent(sim), 10)
        await sim.session.aclose()
        return sim, at_start
    sim, at_start = asyncio.run(normal())
    check("normal flow: not sent when Q2 starts playing, sent once it has played",
          at_start == [] and H.sent(sim) == [(11, first)] and sim.controller.progress.number == 2)

    async def barge_in_early():
        sim = await opened(scripted({}), speed=1.0, synced=True, spw=0.25)
        H.end_turn(sim, say(first))
        await H.cut_reply(sim, 0.5, barge_in=True)      # the applicant talks over "Thanks for..."
        await asyncio.sleep(0.6)
        held = (list(H.sent(sim)), H.spoken(sim)[-1])
        H.stop_talking(sim)
        H.SECONDS_PER_WORD = 0.0005
        more = say("and I also led the data migration last year.")
        reply = await H.turn_and_reply(sim, more)
        await asyncio.sleep(0.2)
        await sim.session.aclose()
        return sim, held, reply, more
    sim, (held_sent, cut_item), reply, more = asyncio.run(barge_in_early())
    check("Q2 cut off early by the applicant: the answer is NOT sent yet",
          held_sent == [] and not cut_item.endswith(q[1].text), f"{held_sent} {cut_item!r}")
    check("...their next words are APPENDED to the pending answer and Q2 is asked again",
          reply == reply_q2 and H.sent(sim) == [(11, f"{first} {more}")], f"{reply!r} {H.sent(sim)}")
    check("...one answer, one sequence - nothing replaced, nothing duplicated",
          [r.sequence for r in sim.committed] == [1] and sim.controller.progress.number == 2)

    async def playback_failure():
        sim = await opened(scripted({}), speed=1.0, synced=True, spw=0.25)
        H.end_turn(sim, say(first))
        await H.cut_reply(sim, 0.5, barge_in=False)     # playback cut, nobody talking
        await asyncio.sleep(0.3)
        held = list(H.sent(sim))
        H.SECONDS_PER_WORD = 0.0005
        ok = await H.wait_for(lambda: any(t.startswith(REPEAT_AFTER_CUT) for t in H.spoken(sim))
                              and sim.session.agent_state == "listening" and H.sent(sim), 10)
        await sim.session.aclose()
        return sim, held, ok
    sim, held, ok = asyncio.run(playback_failure())
    respoken = [t for t in H.spoken(sim) if t.startswith(REPEAT_AFTER_CUT)]
    check("Q2 cut off with nobody talking (playback failure): not sent, Q2 spoken again",
          held == [] and ok and respoken == [f"{REPEAT_AFTER_CUT} {q[1].text}"], f"{held} {respoken}")
    check("...once the re-spoken Q2 has played, the answer is sent (once)",
          H.sent(sim) == [(11, first)] and [r.sequence for r in sim.committed] == [1])

    async def tts_never_starts():
        import app.ai.interview.controller as ctrl_mod
        saved = ctrl_mod.REPLY_DEADLINE_S
        ctrl_mod.REPLY_DEADLINE_S = 1.0
        try:
            sim = await opened(scripted({}))
            sim.tts.hang = True
            H.end_turn(sim, say(first))
            await asyncio.sleep(0.5)
            held = list(H.sent(sim))
            sim.tts.hang = False
            ok = await H.wait_for(lambda: H.sent(sim), 5)
            await asyncio.sleep(0.2)
            await sim.session.aclose()
            return sim, held, ok
        finally:
            ctrl_mod.REPLY_DEADLINE_S = saved
    sim, held, ok = asyncio.run(tts_never_starts())
    check("the next question never starts (TTS stuck): not sent; the watchdog speaks it, then it is sent",
          held == [] and ok and H.spoken(sim)[-1] == f"Thank you. {q[1].text}" and H.sent(sim) == [(11, first)],
          f"{held} {H.spoken(sim)[-1:]}")

    # Near the end of Q2: the decision must follow what was actually played -
    # sent iff LiveKit recorded the whole of Q2 as played. 9 words x 0.25 s.
    total = 9 * 0.25
    outcomes = []
    for offset in (0.45, 0.25, 0.1):
        async def near_end(offset=offset):
            sim = await opened(scripted({}), speed=1.0, synced=True, spw=0.25)
            H.end_turn(sim, say(first))
            await H.cut_reply(sim, total - offset, barge_in=True)
            await asyncio.sleep(0.6)
            played = H.spoken(sim)[-1]
            decided = list(H.sent(sim))
            await sim.session.aclose()
            return played, decided
        played, decided = asyncio.run(near_end())
        heard = H.IS_HEARD(played, q[1].text)
        outcomes.append((offset, heard, bool(decided)))
        check(f"cut {offset:.2f}s before the end of Q2: sent iff the whole of Q2 was played "
              f"(played {'all' if heard else 'part'} of Q2, {'sent' if decided else 'held'})",
              bool(decided) == heard, f"{played!r} {decided}")
    TIMINGS["near_end"] = outcomes

    async def cut_after_end():
        sim = await opened(scripted({}), speed=1.0, synced=True, spw=0.25)
        H.end_turn(sim, say(first))
        await H.cut_reply(sim, total + 0.3, barge_in=True)   # Q2 had fully played
        await asyncio.sleep(0.6)
        decided = list(H.sent(sim))
        await sim.session.aclose()
        return decided
    check("an interruption after Q2 had fully played: the answer is sent (heard)",
          asyncio.run(cut_after_end()) == [(11, first)])


def main() -> int:
    print("SmartHR - AI Interview simulated interviews (real LiveKit AgentSession, fake model/TTS/audio)")
    from app.ai.interview import diagnostics as diag
    diag.reset()
    root = logging.getLogger()
    root.addHandler(CAP)
    level = root.level
    root.setLevel(logging.DEBUG)
    logging.getLogger("livekit.agents").setLevel(logging.INFO)   # the worker's own logging policy
    try:
        test_flow()
        test_llm_failures()
        test_tts_and_interruptions()
        test_welcome()
        test_answer_until_heard()
    finally:
        root.removeHandler(CAP)
        root.setLevel(level)
    section("6. Privacy: no applicant words in any log line (normal, non-debug logging)")
    leaked = [l for l in CAP.lines for s in SPOKEN if len(s) > 8 and s in l]
    check(f"{len(CAP.lines)} log lines from these runs; none contains what the applicant said", not leaked,
          leaked[0][:120] if leaked else "")
    print("\n  timings: " + ", ".join(f"{k} {v:.2f}s" for k, v in TIMINGS.items() if isinstance(v, float)))
    if "near_end" in TIMINGS:
        print("  near the end of Q2 (seconds before end, whole Q2 played?, sent?): " + str(TIMINGS["near_end"]))
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
