"""AI Interview - Phase 3 (Question Bank progression) offline tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_questions

No network, no LiveKit room, no database. Covers the agent-side half:

1. deterministic progression and current-question tracking (QuestionProgress);
2. answer -> question association, including across short answers;
3. GPT-4o cannot put a MAIN question in the applicant's ear: the reply
   shaper drops question-like sentences and appends the bank text verbatim;
4. the directive travels with the reply's context, and stale ones are ignored;
5. the controller walks Q1 -> Q2 -> Q3 -> ENDING -> COMPLETED from LiveKit
   events, with the right state per spoken line;
6. no plan -> the interview ends instead of improvising;
7. the worker's plan parsing refuses malformed or mismatched plans;
8. the agent token: minted/verified, and everything else refused.

The HTTP half (CRUD, RBAC, the plan endpoint) is
`scripts/test_ai_interview_question_bank.py`.
"""

import asyncio
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from livekit import api  # noqa: E402
from livekit.agents import StopResponse, llm  # noqa: E402

from app.ai.interview import agent_auth  # noqa: E402
from app.ai.interview.agent import (  # noqa: E402
    DIRECTIVE_KEY, PLAN_UNAVAILABLE, WELCOME, InterviewerAgent, find_directive, shape_reply,
)
from app.ai.interview.controller import QUESTION_ATTRIBUTE, STATE_ATTRIBUTE, InterviewController  # noqa: E402
from app.ai.interview.plan_client import PlanUnavailable, parse_plan  # noqa: E402
from app.ai.interview.questions import (  # noqa: E402
    ACK_NOTE, CLOSING_AFTER_LAST, FALLBACK_ACK, Directive, PlannedQuestion, QuestionProgress,
    is_questionlike, split_sentences,
)
from app.ai.interview.state import InterviewState as S, InterviewStateMachine  # noqa: E402

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


Q1 = PlannedQuestion(11, 10, "general", "Tell me about yourself.")
Q2 = PlannedQuestion(12, 20, "behavioral", "Tell me about a challenging situation you faced.")
Q3 = PlannedQuestion(13, 30, "behavioral", "How do you work within a team?")
PLAN = [Q1, Q2, Q3]


def test_progression() -> None:
    section("1-2. Progression, current question, answer association")
    p = QuestionProgress(list(PLAN))
    check("starts on Q1", p.current == Q1 and p.number == 1 and p.total == 3)

    d = p.decide("answer", "I am Sam, a software engineer.")
    check("answer to Q1 -> advance", d.kind == "advance")
    check("the reply will carry Q2 verbatim", d.say_after == Q2.text)
    check("current is now Q2", p.current == Q2 and p.number == 2)
    check("the answer is recorded against Q1, not Q2",
          p.answers[-1].question_id == Q1.id and p.answers[-1].question_number == 1)

    # A short answer is an answer (the "say a bit more" invitation was
    # removed): it is recorded and the interview moves on.
    d = p.decide("short", "Yes.")
    check("short answer to Q2 -> advance (no elaboration invite)", d.kind == "advance" and p.current == Q3)
    check("the reply carries Q3 verbatim", d.say_after == Q3.text)
    check("no 'elaborate' directive: it is an ordinary acknowledgement", d.note == ACK_NOTE)
    check("the short answer is recorded as kind 'short'", p.answers_for(Q2.id)[-1].kind == "short")
    check("the short answer is associated with Q2 only",
          [a.text for a in p.answers_for(Q2.id)] == ["Yes."])

    d = p.decide("answer", "I like pairing and code review.")
    check("answer to the last question -> finish", d.kind == "finish")
    check("finish appends the closing line", d.say_after == CLOSING_AFTER_LAST)
    check("no current question after finishing", p.current is None and p.number == 0)
    check("nothing more is recorded after finishing", p.decide("answer", "more words here") is None
          and len(p.answers) == 3)
    check("association: Q1 x1, Q2 x1, Q3 x1 (one answer each - no elaboration round)",
          [len(p.answers_for(q.id)) for q in PLAN] == [1, 1, 1])

    p2 = QuestionProgress(list(PLAN))
    check("same plan -> same order (deterministic)",
          [p2.decide("answer", "a b c").say_after for _ in range(2)] == [Q2.text, Q3.text])
    check("empty plan: no current question", QuestionProgress([]).current is None)


async def fake_stream(pieces):
    for piece in pieces:
        yield llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=piece))


def shaped(pieces, directive):
    async def go():
        return "".join([p async for p in shape_reply(fake_stream(pieces), directive)])
    return asyncio.run(go())


def test_shaper() -> None:
    section("3. GPT-4o cannot supply the MAIN question")
    adv = Directive("advance", "", Q2.text, 2)

    out = shaped(["Thanks for sharing that", " background. ", "What motivates you", " most?"], adv)
    check("a generated question is dropped, the bank question appended",
          "motivates" not in out and out.strip().endswith(Q2.text) and out.startswith("Thanks"), out)
    out = shaped(["Great. Tell me more about your last role. ", "Could you describe it?"], adv)
    check("imperative / 'could you' prompts are dropped too",
          "Tell me more" not in out and "Could you" not in out and out.endswith(Q2.text), out)
    out = shaped(["Why did you leave?"], adv)
    check("all sentences dropped -> fixed fallback + bank question",
          out == f"{FALLBACK_ACK} {Q2.text}", out)
    out = shaped(["One. Two. Three. Four."], adv)
    check("acknowledgement capped at two sentences", out == f"One. Two. {Q2.text}", out)
    out = shaped(["Thank you, that is helpful."], Directive("finish", "", CLOSING_AFTER_LAST, 3))
    check("finish: acknowledgement + closing line", out == f"Thank you, that is helpful. {CLOSING_AFTER_LAST}", out)
    check("the appended bank text is exactly the bank text (not rephrased)",
          shaped(["Okay."], adv).split("Okay. ", 1)[1] == Q2.text)

    for text, expected in (("What was your role?", True), ("Tell me more.", True),
                           ("Describe it.", True), ("Thanks for that.", False),
                           ("That sounds like a real challenge.", False)):
        check(f"is_questionlike({text!r}) = {expected}", is_questionlike(text) == expected)
    done, rest = split_sentences("First one. Second one? Third")
    check("sentence splitter keeps the unfinished tail", done == ["First one.", "Second one?"] and rest == " Third")


def test_directive_context() -> None:
    section("4. The directive travels with one reply only")
    ctx = llm.ChatContext.empty()
    ctx.add_message(role="user", content="my answer")
    ctx.add_message(role="system", content="note",
                    extra={DIRECTIVE_KEY: {"kind": "advance", "say_after": Q2.text, "question_number": 2}})
    d = find_directive(ctx.copy())
    check("found after a context copy", d is not None and d.say_after == Q2.text)
    ctx.add_message(role="user", content="a later answer")
    check("a directive before the latest applicant turn is stale -> ignored", find_directive(ctx) is None)
    bad = llm.ChatContext.empty()
    bad.add_message(role="user", content="x")
    bad.add_message(role="system", content="n", extra={DIRECTIVE_KEY: {"kind": "invent_question"}})
    check("unknown directive kinds are ignored", find_directive(bad) is None)

    # The gate attaches the controller's directive and JSON-safe data only.
    m = InterviewStateMachine(state=S.LISTENING)
    p = QuestionProgress(list(PLAN))
    agent = InterviewerAgent(m, "r", on_answer=lambda k, t: p.decide(k, t))
    turn = llm.ChatContext.empty()
    asyncio.run(agent.on_user_turn_completed(turn, llm.ChatMessage(role="user", content=["I build systems for banks."])))
    data = (turn.items[-1].extra or {}).get(DIRECTIVE_KEY)
    check("gate attaches the directive to this reply's context",
          data == {"kind": "advance", "say_after": Q2.text, "question_number": 2}, str(data))
    check("directive data is JSON-serialisable", json.loads(json.dumps(data)) == data)
    m2 = InterviewStateMachine(state=S.LISTENING)
    agent2 = InterviewerAgent(m2, "r", on_answer=lambda k, t: (_ for _ in ()).throw(AssertionError("called")))
    try:
        asyncio.run(agent2.on_user_turn_completed(llm.ChatContext.empty(),
                                                  llm.ChatMessage(role="user", content=["uh"])))
        check("filler never reaches the controller or GPT-4o", False)
    except StopResponse:
        check("filler never reaches the controller or GPT-4o", True)


class FakeHandle:
    def __init__(self):
        self.interrupted = False

    async def _p(self):
        return None

    def wait_for_playout(self):
        return self._p()

    def add_done_callback(self, cb):
        pass


class FakeSession:
    def __init__(self):
        self.said, self.shut = [], False

    def on(self, *_a):
        pass

    def say(self, text, allow_interruptions=None):
        self.said.append(text)
        return FakeHandle()

    def interrupt(self, force=False):
        pass

    def shutdown(self, drain=True):
        self.shut = True


def test_controller_flow() -> None:
    section("5-6. Controller: Q1 -> Q2 -> Q3 -> ENDING -> COMPLETED")
    published = []

    async def publish(a):
        published.append(a)

    async def scenario():
        m = InterviewStateMachine()
        s = FakeSession()
        c = InterviewController(s, m, "room", publish=publish, progress=QuestionProgress(list(PLAN)))
        await c.run_opening()
        check("opening: welcome with the question count, then Q1 verbatim",
              s.said == [WELCOME.format(count=3), Q1.text], str(s.said))
        check("after Q1: LISTENING", m.state == S.LISTENING)

        spoken_states = []
        for n, answer in enumerate(["I'm Sam.", "A migration went wrong once.", "Pairing daily."], 1):
            m.to(S.PROCESSING)            # the gate, on an accepted answer
            d = c.on_answer("answer", answer)
            c.on_agent_state("thinking")
            c.on_agent_state("speaking")  # GPT-4o's ack + the appended text plays
            spoken_states.append(m.state)
            c.on_agent_state("listening")
            if n < 3:
                check(f"answer {n} -> reply is ASKING Q{n + 1}", m.state == S.LISTENING
                      and spoken_states[-1] == S.ASKING and d.say_after == PLAN[n].text)
        check("after the last answer the reply is ENDING", spoken_states[-1] == S.ENDING)
        check("ENDING -> COMPLETED once the closing is spoken, session shut down",
              m.state == S.COMPLETED and s.shut)
        check("path: ... asking > listening > processing > asking ... > ending > completed",
              m.path()[-4:] == ["listening", "processing", "ending", "completed"]
              and m.path().count("asking") == 3, str(m.path()))
        check("each answer associated with the question asked",
              [(a.question_id, a.question_number) for a in c.progress.answers]
              == [(Q1.id, 1), (Q2.id, 2), (Q3.id, 3)])
        await asyncio.sleep(0)
        qattr = [json.loads(p[QUESTION_ATTRIBUTE]) for p in published]
        check("'question N of M' is published (no ids, no text)",
              {"number": 2, "total": 3} in qattr and all(set(q) == {"number", "total"} for q in qattr))
        check("final published state is completed", published[-1][STATE_ATTRIBUTE] == "completed")

        # A short answer is an answer: its reply carries Q2 (ASKING).
        m2 = InterviewStateMachine()
        c2 = InterviewController(FakeSession(), m2, "r2", progress=QuestionProgress(list(PLAN)))
        await c2.run_opening()
        m2.to(S.PROCESSING)
        d = c2.on_answer("short", "Yes.")
        c2.on_agent_state("speaking")
        check("short answer: advances - the reply is ASKING Q2",
              d.kind == "advance" and m2.state == S.ASKING and c2.progress.current == Q2)

        # No plan: end politely, never improvise.
        m3 = InterviewStateMachine()
        s3 = FakeSession()
        c3 = InterviewController(s3, m3, "r3", progress=QuestionProgress([]))
        await c3.run_opening()
        check("no plan -> says why and ends", s3.said == [PLAN_UNAVAILABLE] and m3.state == S.COMPLETED and s3.shut)
        check("no plan -> no question was ever asked", "asking" not in m3.path())

        # The time-limit ending: the interrupt's "listening" must not complete early.
        m4 = InterviewStateMachine()
        s4 = FakeSession()
        c4 = InterviewController(s4, m4, "r4", progress=QuestionProgress(list(PLAN)))
        await c4.run_opening()
        c4._ending_via_end = True
        m4.to(S.ENDING)
        c4.on_agent_state("listening")
        check("time-limit ENDING is not completed by a stray 'listening'", m4.state == S.ENDING)

    asyncio.run(scenario())


def test_plan_parse() -> None:
    section("7. The worker validates the plan it receives")
    good = {"room_name": "smarthr-ai-interview-aa", "questions": [
        {"id": 1, "position": 10, "category": "general", "question_text": "  Tell   me about yourself. "}]}
    plan = parse_plan(good, "smarthr-ai-interview-aa")
    check("valid plan parsed, whitespace normalised", plan[0].text == "Tell me about yourself." and plan[0].id == 1)
    for label, payload in (
        ("plan for another room", {**good, "room_name": "smarthr-ai-interview-bb"}),
        ("no question list", {"room_name": "smarthr-ai-interview-aa"}),
        ("non-integer id", {**good, "questions": [{"id": "x", "question_text": "abc de"}]}),
        ("empty text", {**good, "questions": [{"id": 1, "question_text": "  "}]}),
        ("oversized text", {**good, "questions": [{"id": 1, "question_text": "a" * 501}]}),
    ):
        try:
            parse_plan(payload, "smarthr-ai-interview-aa")
            check(f"refused: {label}", False)
        except PlanUnavailable:
            check(f"refused: {label}", True)


def test_agent_token() -> None:
    section("8. The agent token")
    key, secret = "APItest" + secrets.token_hex(3), secrets.token_urlsafe(32)
    room = "smarthr-ai-interview-0011"
    tok = agent_auth.mint_agent_token(key, secret, room)
    check("minted token verifies and names its room", agent_auth.verify_agent_token(tok, key, secret) == room)

    def refused(label, token, k=key, sec=secret):
        try:
            agent_auth.verify_agent_token(token, k, sec)
            check(f"refused: {label}", False)
        except agent_auth.AgentAuthError:
            check(f"refused: {label}", True)

    refused("wrong secret", tok, sec="x" + secret)
    refused("garbage", "not.a.jwt")
    applicant = (api.AccessToken(key, secret).with_identity("applicant-5")
                 .with_grants(api.VideoGrants(room_join=True, room=room)).to_jwt())
    refused("an applicant's room token", applicant)
    no_purpose = (api.AccessToken(key, secret).with_identity(agent_auth.AGENT_IDENTITY)
                  .with_grants(api.VideoGrants(room=room, agent=True)).to_jwt())
    refused("agent-shaped token without the purpose", no_purpose)
    other_room = agent_auth.mint_agent_token(key, secret, "someone-elses-room")
    refused("token for a non-SmartHR room", other_room)


def test_split_answer() -> None:
    section("9. An answer split by a mid-answer pause stays ONE answer to ONE question")

    async def scenario():
        m = InterviewStateMachine()
        s = FakeSession()
        c = InterviewController(s, m, "room", progress=QuestionProgress(list(PLAN)))
        await c.run_opening()

        # The turn detector ends the turn at a pause; the controller decides...
        m.to(S.PROCESSING)
        m.counters.answers += 1                       # (the agent's gate counts it)
        d = c.on_answer("answer", "I studied computer science and then I worked at a bank for three years")
        check("the first half provisionally advances to Q2", d.kind == "advance" and c.progress.number == 2)
        # ...but the applicant keeps talking, and LiveKit cancels the reply unheard.
        c.on_agent_state("thinking")
        c.on_agent_state("listening")
        check("cancelled unheard -> back on Q1", c.progress.number == 1 and c.progress.current == Q1)
        check("...nothing recorded against Q1 or Q2 yet",
              not c.progress.answers_for(Q1.id) and not c.progress.answers_for(Q2.id))
        check("...the half-answer is kept open", c.has_open_answer())
        check("...and not counted twice", m.counters.answers == 0, str(m.counters.as_dict()))
        check("...state back to LISTENING", m.state == S.LISTENING)

        # The rest of the answer arrives as the next turn.
        m.to(S.PROCESSING)
        m.counters.answers += 1
        d = c.on_answer("answer", "and now I build backend services.")
        rec = c.progress.answers_for(Q1.id)
        check("both halves are ONE answer, recorded against Q1",
              len(rec) == 1 and "bank" in rec[0].text and "backend" in rec[0].text, str(rec))
        check("nothing was recorded against Q2", not c.progress.answers_for(Q2.id))
        check("the directive now carries Q2 (not Q3)", d.say_after == Q2.text, str(d))
        c.on_agent_state("thinking")
        c.on_agent_state("speaking")
        check("heard -> ASKING question 2", m.state == S.ASKING and c.progress.number == 2)
        c.on_agent_state("listening")
        check("a later 'listening' does not reopen a heard decision", c.progress.number == 2
              and not c.has_open_answer())
        check("one answer counted", m.counters.answers == 1, str(m.counters.as_dict()))

        # A short or filler tail completes the open answer instead of being judged alone.
        m.to(S.PROCESSING)
        m.counters.answers += 1
        c.on_answer("answer", "Last year a release failed and I rolled it back quickly")
        c.on_agent_state("thinking")
        c.on_agent_state("listening")
        agent = InterviewerAgent(m, "room", set_state=c.set_state, on_answer=c.on_answer,
                                 has_open_answer=c.has_open_answer)
        turn = llm.ChatContext.empty()
        await agent.on_user_turn_completed(turn, llm.ChatMessage(role="user", content=["uh."]))
        rec = c.progress.answers_for(Q2.id)
        check("a filler that ends an open answer is passed on, not dropped",
              len(rec) == 1 and rec[0].text.endswith("uh."), str(rec))
        check("...and the merged answer advances normally (not 'elaborate')",
              c.progress.number == 3 and rec[0].kind == "answer")
        check("counters: two answers, no short, no ignored",
              m.counters.answers == 2 and m.counters.short == 0 and m.counters.ignored == 0,
              str(m.counters.as_dict()))

    asyncio.run(scenario())

    m = InterviewStateMachine(state=S.LISTENING)
    agent = InterviewerAgent(m, "r", on_answer=lambda k, t: (_ for _ in ()).throw(AssertionError("called")))
    try:
        asyncio.run(agent.on_user_turn_completed(llm.ChatContext.empty(),
                                                 llm.ChatMessage(role="user", content=["uh"])))
        check("with NO open answer, filler is still ignored", False)
    except StopResponse:
        check("with NO open answer, filler is still ignored", True)


def main() -> int:
    print("SmartHR - AI Interview Phase 3 Question Bank progression tests (offline)")
    test_progression()
    test_shaper()
    test_directive_context()
    test_controller_flow()
    test_plan_parse()
    test_agent_token()
    test_split_answer()
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
