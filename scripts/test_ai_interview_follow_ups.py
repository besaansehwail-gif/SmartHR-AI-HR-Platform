"""AI Interview - Phase 11.1 controlled follow-up questions tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_follow_ups     # no model, no LiveKit

What is asked, and by whom:

* the Question Bank supplies the follow-up - the first ACTIVE follow_up row
  whose parent is the main question (`interview_plan`), at most one;
* GPT-4o only answers `{"ask_follow_up": true|false}` (`follow_up.py`) - it
  never supplies the words, which are the bank's, appended verbatim by code;
* the controller asks it only after a main question's answer would move on,
  never for a follow-up's answer, never twice for one main question.

Parts: the progression rules (pure Python), the decision contract (a fake
model object implementing LiveKit's `chat()` - GPT-4o is never called), the
real agent turn gate + controller + state machine, the worker's plan parsing,
and the backend - plan building (inside a transaction that is rolled back, so
the Question Bank is not changed), answer storage and analysis (a throwaway
session binding on applicant05's fixture interview, deleted at the end; the
analysis model is a fake provider).
"""

import asyncio
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_ai_interview_cv_context as p5  # noqa: E402

passed = 0
failed: list[str] = []
ROOMS: list[str] = []

LONG = "At my last job I rebuilt the forecasting pipeline after it failed, and I documented every step for the team."


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


def plan_with_follow_ups():
    from app.ai.interview.questions import PlannedQuestion as Q
    fu1 = Q(101, 10, "follow_up", "What was the result of that project, in numbers if you can?")
    fu3 = Q(103, 10, "follow_up", "Which part of that would you do differently now?")
    return [Q(11, 1, "general", "Tell me about yourself.", follow_up=fu1),
            Q(12, 2, "behavioral", "Describe a challenge you faced."),
            Q(13, 3, "general", "How do you work in a team?", follow_up=fu3)]


# -- 1. Progression rules ----------------------------------------------------------------

def test_progression() -> None:
    section("1. Progression: the bank's follow-up, at most once, then the next main question")
    from app.ai.interview.questions import CLOSING_AFTER_LAST, QuestionProgress

    plan = plan_with_follow_ups()
    p = QuestionProgress(plan)
    cand = p.follow_up_candidate("answer", LONG)
    check("main question with an eligible follow-up -> a candidate (main, its follow-up, the answer)",
          cand is not None and cand[0].id == 11 and cand[1].id == 101 and cand[2] == LONG, str(cand))
    d = p.decide("answer", LONG, ask_follow_up=True)
    check("decision yes -> directive 'follow_up' carrying the BANK text verbatim",
          d.kind == "follow_up" and d.say_after == plan[0].follow_up.text, str(d))
    check("...the question number stays the main question's (Question 1 of 3)", d.question_number == 1 and p.number == 1)
    check("...and the follow-up is now the current question", p.current.id == 101 and p.current_main.id == 11)
    check("the main answer is recorded against the MAIN question",
          (p.answers[-1].question_id, p.answers[-1].question_number) == (11, 1))
    check("while answering a follow-up there is no further candidate (no loop)",
          p.follow_up_candidate("answer", LONG) is None)
    d = p.decide("answer", "It cut forecast errors by a third within two months.", ask_follow_up=True)
    check("the follow-up's answer is recorded against the FOLLOW-UP, under the main number",
          (p.answers[-1].question_id, p.answers[-1].question_number) == (101, 1))
    check("...and moves on to the next MAIN question - even if 'ask' is passed again",
          d.kind == "advance" and d.say_after == plan[1].text and p.number == 2 and p.current.id == 12, str(d))
    check("main question with NO follow-up -> no candidate", p.follow_up_candidate("answer", LONG) is None)
    d = p.decide("answer", LONG, ask_follow_up=True)
    check("...and 'ask' is ignored there: straight to the next main question",
          d.kind == "advance" and d.say_after == plan[2].text)
    check("follow-up for the LAST main question -> asked", p.decide("answer", LONG, ask_follow_up=True).kind == "follow_up")
    d = p.decide("yes", "yes")
    check("a SHORT follow-up answer is not invited to elaborate - it finishes the interview",
          d.kind == "finish" and d.say_after == CLOSING_AFTER_LAST)
    seqs = p.commit()
    check("final answers are numbered in order across main and follow-up questions",
          [(r.sequence, r.question_id) for r in seqs] == [(1, 11), (2, 101), (3, 12), (4, 13), (5, 103)], str(seqs))

    q = QuestionProgress(plan_with_follow_ups())
    check("decision no -> the next main question, no follow-up",
          q.decide("answer", LONG, ask_follow_up=False).kind == "advance" and q.current.id == 12)
    check("...and that main question's follow-up can never come back later",
          all(a.question_id != 101 for a in q.answers) and q.follow_up_candidate("answer", LONG) is None)

    r = QuestionProgress(plan_with_follow_ups())
    check("a short answer is an answer: it gets the follow-up decision directly (no elaboration first)",
          r.follow_up_candidate("short", "Yes.") is not None
          and r.follow_up_candidate("short", "Yes.")[2] == "Yes.")
    check("...then the fuller answer gets the decision", r.follow_up_candidate("answer", LONG) is not None)

    s = QuestionProgress(plan_with_follow_ups())
    s.decide("answer", "I lead the data team and", ask_follow_up=True)
    s.reopen()   # the applicant was still talking: the follow-up was never heard
    check("a reopened follow-up decision is undone: not asked, not counted",
          s.in_follow_up is None and not s.followed_up and s.current.id == 11)
    cand = s.follow_up_candidate("answer", "I build forecasting tools.")
    check("...the next turn completes the answer and is decided again, merged",
          cand is not None and cand[2] == "I lead the data team and I build forecasting tools.", str(cand))
    s.decide("answer", "I build forecasting tools.", ask_follow_up=True)
    check("...and the follow-up is asked exactly once", s.followed_up == {11} and s.current.id == 101)


# -- 2. The decision contract ---------------------------------------------------------------

class FakeCall:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class FakeStream:
    def __init__(self, chunks, delay=0.0, error=None):
        self.chunks, self.delay, self.error, self.closed = chunks, delay, error, False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        for c in self.chunks:
            yield c

    async def aclose(self):
        self.closed = True


class FakeModel:
    """Implements LiveKit's LLM.chat() - nothing is sent anywhere."""

    def __init__(self, calls=None, text=None, delay=0.0, error=None):
        from types import SimpleNamespace as NS
        chunks = []
        if text:
            chunks.append(NS(delta=NS(content=text, tool_calls=[])))
        if calls:
            chunks.append(NS(delta=NS(content=None, tool_calls=[FakeCall(n, a) for n, a in calls])))
        self.chunks, self.delay, self.error, self.seen = chunks, delay, error, []

    def chat(self, **kwargs):
        self.seen.append(kwargs)
        self.stream = FakeStream(self.chunks, self.delay, self.error)
        return self.stream


def test_decision_contract() -> None:
    section("2. The decision contract: {\"ask_follow_up\": bool} and nothing else")
    from app.ai.interview.follow_up import (
        DECISION_FIELD, DECISION_SCHEMA, DECISION_TOOL, ask_model, parse_decision)

    check("the tool's only parameter is ask_follow_up, a boolean; nothing else allowed",
          DECISION_SCHEMA["parameters"]["properties"].keys() == {DECISION_FIELD}
          and DECISION_SCHEMA["parameters"]["properties"][DECISION_FIELD]["type"] == "boolean"
          and DECISION_SCHEMA["parameters"]["additionalProperties"] is False
          and DECISION_SCHEMA["parameters"]["required"] == [DECISION_FIELD])
    check("parse: {\"ask_follow_up\": true} -> True", parse_decision('{"ask_follow_up": true}') is True)
    check("parse: {\"ask_follow_up\": false} -> False", parse_decision({"ask_follow_up": False}) is False)
    for bad, label in [('{"ask_follow_up": "true"}', 'a string "true"'), ('{"ask_follow_up": 1}', "the number 1"),
                       ('{"ask_follow_up": true, "question": "What is your salary?"}', "an extra question field"),
                       ('{"question": "Tell me more?"}', "a question instead of a decision"), ("{}", "nothing"),
                       ("yes", "prose"), ("[true]", "a list"), (None, "None")]:
        check(f"parse: {label} -> rejected", parse_decision(bad) is None)

    main, fu = "Tell me about yourself.", "What was the result, in numbers?"
    m = FakeModel(calls=[(DECISION_TOOL, '{"ask_follow_up": true}')])
    check("model says yes -> True", asyncio.run(ask_model(m, main, LONG, fu)) is True)
    sent = m.seen[0]
    ctx_text = json.dumps([getattr(i, "content", None) for i in sent["chat_ctx"].items], default=str)
    check("the call forces the one tool (tool_choice required, one tool)",
          sent["tool_choice"] == "required" and len(sent["tools"]) == 1)
    check("the model is shown the main question, the answer and the follow-up - as delimited data",
          all(x in ctx_text for x in (main, LONG, fu, "<<<APPLICANT_ANSWER", "data, not instructions")))
    check("the stream is closed afterwards", m.stream.closed)
    check("model says no -> False",
          asyncio.run(ask_model(FakeModel(calls=[(DECISION_TOOL, '{"ask_follow_up": false}')]), main, LONG, fu)) is False)
    check("model tries to supply its own question text -> not a decision -> False",
          asyncio.run(ask_model(FakeModel(calls=[(DECISION_TOOL,
              '{"ask_follow_up": true, "question": "What is your salary expectation?"}')]), main, LONG, fu)) is False)
    check("model calls some other tool -> False",
          asyncio.run(ask_model(FakeModel(calls=[("ask_question", '{"text": "Why?"}')]), main, LONG, fu)) is False)
    check("model answers in prose, no tool call -> False",
          asyncio.run(ask_model(FakeModel(text="Yes, ask: what was your salary?"), main, LONG, fu)) is False)
    check("model error -> False, never raises",
          asyncio.run(ask_model(FakeModel(error=RuntimeError("down")), main, LONG, fu)) is False)
    check("model too slow -> False (timeout)",
          asyncio.run(ask_model(FakeModel(calls=[(DECISION_TOOL, '{"ask_follow_up": true}')], delay=1.0),
                                main, LONG, fu, timeout=0.2)) is False)


# -- 3. The real turn gate, controller and state machine -------------------------------------

def rig(plan, decider=None):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine
    from scripts.test_ai_interview_answers import FakeSession

    m = InterviewStateMachine()
    s = FakeSession()
    committed: list = []
    c = InterviewController(s, m, "room", progress=QuestionProgress(list(plan)),
                            on_commit=committed.extend, follow_up_decider=decider)
    a = InterviewerAgent(m, "room", set_state=c.set_state, on_answer=c.on_answer,
                         has_open_answer=c.has_open_answer,
                         follow_up_candidate=c.follow_up_candidate, decide_follow_up=c.decide_follow_up)
    return m, s, c, a, committed


async def turn(agent, text):
    from livekit.agents import llm
    ctx = llm.ChatContext.empty()
    await agent.on_user_turn_completed(ctx, llm.ChatMessage(role="user", content=[text]))
    return ctx


def directive_of(ctx):
    from app.ai.interview.agent import find_directive
    return find_directive(ctx)


def test_flow() -> None:
    section("3. Agent turn gate + controller + state machine")
    from app.ai.interview.state import TRANSITIONS, InterviewState as S

    check("PROCESSING -> FOLLOW_UP_DECISION is a legal transition", S.FOLLOW_UP_DECISION in TRANSITIONS[S.PROCESSING])
    # Phase 11.2 adds ADAPTIVE_SELECTION: a "no" leads on to choosing the next main question.
    check("FOLLOW_UP_DECISION -> ASKING / LISTENING / PROCESSING / SPEAKING / ENDING / ADAPTIVE_SELECTION",
          TRANSITIONS[S.FOLLOW_UP_DECISION] == {S.ASKING, S.LISTENING, S.PROCESSING, S.SPEAKING, S.ENDING,
                                                S.ADAPTIVE_SELECTION})
    check("it is reachable only from PROCESSING",
          [s for s, nxt in TRANSITIONS.items() if S.FOLLOW_UP_DECISION in nxt] == [S.PROCESSING])

    asked: list = []

    async def yes(main, answer, follow_up):
        asked.append((main, answer, follow_up))
        return True

    plan = plan_with_follow_ups()

    async def scenario():
        m, s, c, a, committed = rig(plan, yes)
        await c.run_opening()
        ctx = await turn(a, LONG)
        d = directive_of(ctx)
        path = [st.value for _, st in m.history]
        check("answer to a main question with a follow-up -> PROCESSING -> FOLLOW_UP_DECISION",
              "follow_up_decision" in path and path.index("processing") < path.index("follow_up_decision"), str(path))
        check("the decider saw the main question, the answer and the bank's follow-up",
              asked == [(plan[0].text, LONG, plan[0].follow_up.text)])
        check("the reply directive is 'follow_up' with the bank text", d and d.kind == "follow_up"
              and d.say_after == plan[0].follow_up.text, str(d))
        c.on_agent_state("thinking")
        c.on_agent_state("speaking")
        check("the follow-up is spoken in ASKING (a bank question), still 'Question 1'",
              m.state == S.ASKING and c.progress.number == 1)
        check("hearing it makes the main answer final (sequence 1, main question)",
              [(r.sequence, r.question_id, r.question_number) for r in committed] == [(1, 11, 1)])
        c.on_agent_state("listening")

        asked.clear()
        ctx = await turn(a, "It cut forecast errors by a third within two months.")
        d = directive_of(ctx)
        check("the follow-up's answer is NOT sent for another decision (no loop)", asked == [])
        check("...and moves on to main question 2, verbatim", d.kind == "advance" and d.say_after == plan[1].text)
        c.on_agent_state("speaking")
        check("the follow-up answer is final and stored against the follow-up id, under number 1",
              [(r.sequence, r.question_id, r.question_number) for r in committed][-1] == (2, 101, 1))
        c.on_agent_state("listening")

        before = len(m.history)
        ctx = await turn(a, LONG)
        check("main question with no follow-up -> no decision, no FOLLOW_UP_DECISION state",
              asked == [] and all(st != S.FOLLOW_UP_DECISION for _, st in m.history[before:]))
        check("...straight on to question 3", directive_of(ctx).say_after == plan[2].text)

    asyncio.run(scenario())

    async def failing(main, answer, follow_up):
        raise RuntimeError("model down")

    async def truthy(main, answer, follow_up):
        return "yes"

    for decider, label in ((failing, "a failing decider"), (truthy, "a non-boolean 'yes'")):
        async def run(decider=decider):
            m, s, c, a, _ = rig(plan, decider)
            await c.run_opening()
            return directive_of(await turn(a, LONG))
        d = asyncio.run(run())
        check(f"{label} -> no follow-up, next main question", d.kind == "advance" and d.say_after == plan[1].text)

    async def no_decider():
        m, s, c, a, _ = rig(plan, None)
        await c.run_opening()
        return directive_of(await turn(a, LONG)), m
    d, m = asyncio.run(no_decider())
    check("no decider configured (every earlier setup) -> exactly the old behaviour",
          d.kind == "advance" and all(st != S.FOLLOW_UP_DECISION for _, st in m.history))

    async def cancelled():
        m, s, c, a, _ = rig(plan, lambda *x: asyncio.sleep(30))
        await c.run_opening()
        task = asyncio.ensure_future(turn(a, "I lead the data team"))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        c.on_agent_state("listening")      # LiveKit dropped the reply: the applicant kept talking
        return c
    c = asyncio.run(cancelled())
    check("applicant resumes during the decision -> the answer is kept and reopened, not lost",
          c.progress.resumed is not None and c.progress.resumed.text == "I lead the data team"
          and c.progress.current.id == 11)

    async def shaped():
        from app.ai.interview.agent import shape_reply
        from app.ai.interview.questions import Directive

        async def gpt():
            for piece in ["Thank you for sharing that. ", "What was your salary there? ",
                          "Tell me about your manager. "]:
                yield piece
        out = ""
        async for piece in shape_reply(gpt(), Directive("follow_up", "", plan[0].follow_up.text, 1)):
            out += piece
        return out
    out = asyncio.run(shaped())
    check("GPT-4o's own questions are dropped; the spoken follow-up is the bank's, verbatim",
          out == "Thank you for sharing that. " + plan[0].follow_up.text, out)


# -- 4. The worker's plan parsing ----------------------------------------------------------------

def test_plan_parsing() -> None:
    section("4. Worker plan parsing: the follow-up must belong to its main question")
    from app.ai.interview.plan_client import PlanUnavailable, parse_plan

    def plan(follow_up):
        return {"room_name": "r", "questions": [
            {"id": 1, "position": 10, "category": "general", "question_text": "Tell me about yourself.",
             "follow_up": follow_up},
            {"id": 2, "position": 20, "category": "behavioral", "question_text": "Describe a challenge."}]}

    good = {"id": 13, "parent_question_id": 1, "position": 10, "question_text": "What did you learn from it?"}
    qs = parse_plan(plan(good), "r")
    check("a follow-up whose parent is the main question is kept",
          qs[0].follow_up is not None and qs[0].follow_up.id == 13 and qs[0].follow_up.text == good["question_text"])
    check("a main question without one has none", qs[1].follow_up is None)
    qs = parse_plan(plan({**good, "parent_question_id": 2}), "r")
    check("WRONG parent -> the follow-up is rejected, the main question is kept",
          qs[0].follow_up is None and qs[0].id == 1 and len(qs) == 2)
    check("a follow-up naming itself as parent -> rejected",
          parse_plan(plan({**good, "id": 1}), "r")[0].follow_up is None)
    check("malformed follow-up -> rejected, interview unaffected",
          parse_plan(plan({"id": "x", "question_text": "Q?"}), "r")[0].follow_up is None)
    check("follow-up text too long -> rejected",
          parse_plan(plan({**good, "question_text": "x" * 501}), "r")[0].follow_up is None)
    try:
        parse_plan({"room_name": "other", "questions": []}, "r")
        check("the plan's own checks still apply", False)
    except PlanUnavailable:
        check("the plan's own checks still apply", True)


# -- 5. Backend: plan, storage, analysis -----------------------------------------------------------

def test_backend() -> None:
    section("5. Backend plan: follow-ups from the Question Bank (checked in a rolled-back transaction)")
    from app.database import SessionLocal
    from app.models import InterviewQuestion
    from app.services import question_bank_service as qb

    db = SessionLocal()
    try:
        plan = qb.interview_plan(db)
        mains = [p["id"] for p in plan]
        main_rows = (db.query(InterviewQuestion).filter(InterviewQuestion.question_type == "main",
                     InterviewQuestion.is_active.is_(True))
                     .order_by(InterviewQuestion.position, InterviewQuestion.id).limit(len(plan)).all())
        check("the MAIN questions and their order are unchanged", mains == [q.id for q in main_rows])
        check("every plan entry has a follow_up key (None or one follow-up)",
              all("follow_up" in p for p in plan))
        attached = {p["id"]: p["follow_up"] for p in plan if p["follow_up"]}
        check("each attached follow-up names its own main question as parent",
              all(f["parent_question_id"] == pid for pid, f in attached.items()), str(attached))
        check("no follow-up field beyond id, parent, position and text (no evaluation_focus)",
              all(set(f) == {"id", "parent_question_id", "position", "question_text"} for f in attached.values()))
        rows = {q.id: q for q in db.query(InterviewQuestion).filter(InterviewQuestion.id.in_(
            [f["id"] for f in attached.values()])).all()}
        check("each follow-up's text is the Question Bank row's text",
              all(rows[f["id"]].question_text == f["question_text"] and rows[f["id"]].question_type == "follow_up"
                  and rows[f["id"]].is_active for f in attached.values()))

        if attached:
            parent, fu = next(iter(attached.items()))
            row = db.get(InterviewQuestion, fu["id"])
            row.is_active = False
            db.flush()
            check("an INACTIVE follow-up is ignored", qb.interview_plan(db)[mains.index(parent)]["follow_up"] is None)
            row.is_active = True
            earlier = InterviewQuestion(question_text="Which tools did you use for it, specifically?",
                                        question_text_ar="ما الأدوات التي استخدمتها تحديدًا؟",
                                        category="general", difficulty="easy", question_type="follow_up",
                                        parent_question_id=parent, position=0, is_active=True)
            db.add(earlier)
            db.flush()
            check("several follow-ups for one main question -> exactly one, the first by position",
                  qb.interview_plan(db)[mains.index(parent)]["follow_up"]["id"] == earlier.id)
            other = next(p for p in mains if p != parent)
            earlier.parent_question_id = other
            db.flush()
            check("a follow-up is attached only under ITS parent",
                  qb.interview_plan(db)[mains.index(parent)]["follow_up"]["id"] == fu["id"]
                  and (qb.interview_plan(db)[mains.index(other)]["follow_up"] or {}).get("id") == earlier.id)
    finally:
        db.rollback()
        db.close()
    db = SessionLocal()
    try:
        check("...and the Question Bank is exactly as it was (rolled back)",
              db.query(InterviewQuestion).filter(
                  InterviewQuestion.question_text == "Which tools did you use for it, specifically?").count() == 0
              and all(q.is_active for q in db.query(InterviewQuestion).filter(
                  InterviewQuestion.id.in_([f["id"] for f in attached.values()])).all()))
    finally:
        db.close()

    if not attached:
        check("the fixture bank has a follow-up to store answers against (run seed_interview_questions)", False)
        return
    parent, fu = next(iter(attached.items()))
    number = mains.index(parent) + 1
    test_storage_and_analysis(parent, fu, number, mains)


def test_storage_and_analysis(parent: int, fu: dict, number: int, mains: list[int]) -> None:
    section("6. Follow-up answers are stored and analysed like any answer (throwaway binding)")
    from datetime import datetime

    from app.database import SessionLocal
    from app.models import AiInterviewAnswer, Application, Candidate, Interview, User
    from app.services import interview_analysis_service as svc, interview_answer_service as ans
    from app.services import interview_context_service as ctx, interview_cv_service as cvsvc
    from app.services import interview_report_service as rep
    from scripts.test_ai_interview_answers import GOOD, FakeProvider
    from scripts.test_ai_interview_matching_context import FakeAnalysis
    from scripts.test_helpers import AI_INTERVIEW_LOCATION

    original = cvsvc.analyse_cv_bytes
    cvsvc.analyse_cv_bytes = lambda *a, **k: FakeAnalysis(p5.sample_parsed())
    cvsvc.clear_cache()
    db = SessionLocal()
    try:
        candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                     .filter(User.email == p5.APPLICANT_ONE_CV).one())
        interview = (db.query(Interview).join(Application, Application.id == Interview.application_id)
                     .filter(Application.candidate_id == candidate.id, Interview.location == AI_INTERVIEW_LOCATION)
                     .order_by(Interview.id.desc()).first())
        # Phase 9: answers are recorded only for an HR-approved interview in its
        # window - the fixture (test rows only) is made so, as the report suite does.
        db.get(Application, interview.application_id).status = "interview"
        interview.status = "scheduled"
        interview.scheduled_at = datetime.now().replace(microsecond=0)
        db.commit()
        room = "smarthr-ai-interview-fu" + secrets.token_hex(6)
        ROOMS.append(room)
        ctx.bind_room(db, room, interview, candidate, 10)
        from scripts.test_helpers import mark_session_started
        mark_session_started(room)          # Phase 11.6.4: answers need a started session

        def submit(seq, qid, num, text):
            return ans.record_answer(db, room, ans.AnswerSubmission(
                question_id=qid, question_number=num, sequence=seq, kind="answer", transcript=text,
                answered_at=datetime.utcnow()))

        main_text = "our forecasting model drifted, so I retrained it in Python and I also deployed it on Kubernetes myself"
        row_main, _ = submit(1, parent, number, main_text)
        follow_text = "our forecasting model drifted twice, and I retrained it in Python each time"
        row_fu, created = submit(2, fu["id"], number, follow_text)
        check("a follow-up answer is accepted: its own id, the main question's number", created
              and (row_fu.question_id, row_fu.question_number) == (fu["id"], number))
        check("...its stored question text is the BANK's follow-up text", row_fu.question_text == fu["question_text"])
        check("...and the transcript exactly as sent", row_fu.transcript == follow_text)
        for qid, num, label in ((fu["id"], number + 1, "under another question's number"),
                                (999999, number, "an id that is not the plan's follow-up")):
            try:
                submit(3, qid, num, "x y z")
                check(f"a follow-up {label} -> refused", False)
            except ans.AnswerError as err:
                check(f"a follow-up {label} -> refused (question_mismatch)", err.code == "question_mismatch")
        other = next((m for m in mains if m != parent), None)
        if other is not None:
            try:
                submit(3, fu["id"], mains.index(other) + 1, "x y z")
                check("a follow-up claimed for the WRONG parent -> refused", False)
            except ans.AnswerError as err:
                check("a follow-up claimed for the WRONG parent -> refused", err.code == "question_mismatch")
        again, created = submit(2, fu["id"], number, follow_text)
        check("a retried follow-up answer is the same row (created: false)", not created and again.id == row_fu.id)

        view = ans.answers_for_interview(db, interview.id)
        ours = next(s for s in view["sessions"] if s["answers"] and s["answers"][0]["answer_id"] == row_main.id)
        check("the review marks each answer's type: main, then follow_up",
              [(a["question_id"], a["question_type"]) for a in ours["answers"]]
              == [(parent, "main"), (fu["id"], "follow_up")], str(ours["answers"]))

        data = svc.build_input(db, db.get(AiInterviewAnswer, row_fu.id))
        check("the follow-up's analysis input is ITS question and ITS transcript",
              data.question == fu["question_text"] and data.transcript == follow_text)
        check("...and the main answer is not merged into it as an 'earlier part'", data.earlier_parts == [])
        stored = svc.analyse_answer(db, row_fu.id, force=True, provider=FakeProvider(GOOD))
        check("the follow-up answer is analysed and stored like any answer (fake model)",
              stored.status == "completed" and stored.analysis["summary"] == GOOD["summary"], str(stored.status))

        session_id = p5.db_scalar("select id from ai_interview_sessions where room_name = :r", r=room)
        report = rep.interview_report(db, interview.id, session_id)
        types = [(a["question_number"], a["question_type"]) for a in report["answers"]]
        check("the HR report lists the follow-up under its main question's number, typed",
              types == [(number, "main"), (number, "follow_up")], str(types))
        check("...and still claims no planned total and no decision",
              report["meta"]["is_hiring_decision"] is False
              and report["summary"]["answered_count"] == 2 and report["interview"]["highest_question_reached"] == number)
    finally:
        db.close()
        cvsvc.analyse_cv_bytes = original
        cvsvc.clear_cache()


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    if not ROOMS:
        return 0
    with engine.begin() as conn:
        return conn.execute(text("delete from ai_interview_sessions where room_name = any(:r)"),
                            {"r": ROOMS}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 11.1 follow-up questions tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    # Where the analysis actually looks its provider up - so an accidental
    # call without the fake provider fails instead of reaching GPT-4o.
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model
    try:
        test_progression()
        test_decision_contract()
        test_flow()
        test_plan_parsing()
        test_backend()
    finally:
        print(f"\n  cleanup: removed {cleanup()} session binding(s) (answers and analyses cascade)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
