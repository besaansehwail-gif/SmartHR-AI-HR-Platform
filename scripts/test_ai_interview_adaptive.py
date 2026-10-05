"""AI Interview - Phase 11.2 adaptive question order tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_adaptive     # no model, no LiveKit

The rule under test: GPT-4o may choose WHICH predefined main question comes
next - by Question Bank id, from this plan's main questions not asked yet -
and nothing else. It never supplies words; every question spoken is a bank
row's text. Any unusable choice falls back to the Question Bank's own order.

Parts: the progression rules (pure Python), the selection contract (a fake
object implementing LiveKit's LLM.chat() - GPT-4o is never called), the real
agent turn gate + controller + state machine, and the backend - answer
storage in adaptive order, the report and the analysis (a throwaway session
binding on applicant05's fixture interview, deleted at the end; a fake
analysis provider). Phase 11.1 follow-ups are re-checked alongside.
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
from scripts.test_ai_interview_follow_ups import FakeModel, directive_of, turn  # noqa: E402

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


def plan5():
    """Five main questions; Q1 has a follow-up (Phase 11.1)."""
    from app.ai.interview.questions import PlannedQuestion as Q
    fu = Q(101, 10, "follow_up", "What was the result of that project, in numbers if you can?")
    return [Q(11, 1, "general", "Tell me about yourself.", follow_up=fu),
            Q(12, 2, "behavioral", "Describe a challenge you faced."),
            Q(13, 3, "technical", "Which tools do you use for data work?"),
            Q(14, 4, "situational", "What would you do if a deadline slipped?"),
            Q(15, 5, "general", "Why this role?")]


# -- 1. Progression ----------------------------------------------------------------------------

def test_progression() -> None:
    section("1. Progression: a valid bank id is used; anything else is the bank's order")
    from app.ai.interview.questions import CLOSING_AFTER_LAST, QuestionProgress

    plan = plan5()
    texts = {q.id: q.text for q in plan}
    p = QuestionProgress(plan)
    opts = p.adaptive_options("answer", LONG)
    check("options after Q1 = the main questions not asked yet, in plan order (no follow-up ids)",
          opts is not None and [q.id for q in opts[2]] == [12, 13, 14, 15] and opts[1] == LONG, str(opts))
    d = p.decide("answer", LONG, next_question_id=14)
    check("valid id -> that question is next, spoken as its BANK text",
          d.kind == "advance" and d.say_after == texts[14] and p.current.id == 14, str(d))
    check("...and it is numbered by the order ASKED (Question 2), not its plan position", d.question_number == 2 == p.number)
    check("the answer before it stays numbered 1", p.answers[-1].question_number == 1)
    for bad, label in [(999, "a hallucinated id"), (11, "an already-asked id"), (14, "the current question"),
                       (101, "a follow-up id"), (True, "a boolean"), ("12", "a string id"), (None, "no choice")]:
        q = QuestionProgress(plan)
        q.decide("answer", LONG, next_question_id=14)
        d = q.decide("answer", LONG, next_question_id=bad)
        check(f"{label} -> the bank's order (first not-yet-asked: Q2)", d.say_after == texts[12] and q.current.id == 12)

    q = QuestionProgress(plan)
    spoken, seen = [q.current.text], [q.current.id]
    while True:
        d = q.decide("answer", LONG, next_question_id=11)     # always asks for Q1 again
        spoken.append(d.say_after)
        if d.kind == "finish":
            break
        seen.append(q.current.id)
    check("a selector that keeps asking for an asked question: no loop - every main question once",
          sorted(seen) == [11, 12, 13, 14, 15] and len(seen) == 5, str(seen))
    check("...the interview ends after exactly 5 main questions", spoken[-1] == CLOSING_AFTER_LAST and len(spoken) == 6)
    check("...and everything spoken is Question Bank text (or the fixed closing)",
          all(t in texts.values() or t == CLOSING_AFTER_LAST for t in spoken))

    r = QuestionProgress(plan)
    for pick in (15, 13):
        r.decide("answer", LONG, next_question_id=pick)
    check("order asked is tracked; numbers are 1, 2, 3 in that order",
          [r.questions[i].id for i in r.asked] == [11, 15, 13] and r.number == 3)
    r.decide("answer", LONG, next_question_id=12)
    check("with ONE question left there is no choice to make (no options)", r.adaptive_options("answer", LONG) is None)

    s = QuestionProgress(plan)
    check("a short answer is an answer: options are offered directly (no elaboration first)",
          s.adaptive_options("short", "Yes.") is not None
          and QuestionProgress(plan).decide("short", "Yes.").kind == "advance")
    s.decide("answer", "I lead the data team and", next_question_id=15)
    s.reopen()
    check("a reopened choice is undone: nothing new asked", s.asked == [0] and s.current.id == 11)
    opts = s.adaptive_options("answer", "I build forecasting tools.")
    check("...and decided again on the merged answer",
          opts is not None and opts[1] == "I lead the data team and I build forecasting tools.",
          str(opts and opts[1]))

    section("2. Phase 11.1 follow-ups are unchanged and come first")
    f = QuestionProgress(plan5())
    d = f.decide("answer", LONG, ask_follow_up=True, next_question_id=15)
    check("follow-up asked -> the follow-up, whatever id was passed", d.kind == "follow_up" and f.current.id == 101)
    check("while answering a follow-up there are no adaptive options", f.adaptive_options("answer", LONG) is None)
    d = f.decide("answer", "It cut errors by a third.", next_question_id=15)
    check("after the follow-up's answer: the bank's order (Q2), never the passed id",
          d.say_after == plan5()[1].text and f.current.id == 12 and f.number == 2)
    check("the follow-up answer shares its main question's number",
          [(a.question_id, a.question_number) for a in f.answers] == [(11, 1), (101, 1)])


# -- 3. Selection contract ----------------------------------------------------------------------

def test_contract() -> None:
    section("3. Selection contract: {\"next_question_id\": <an offered id>} and nothing else")
    from app.ai.interview.adaptive import SELECT_FIELD, SELECT_SCHEMA, SELECT_TOOL, choose_with_model, parse_choice

    props = SELECT_SCHEMA["parameters"]["properties"]
    check("the tool's only parameter is next_question_id, an integer; nothing else allowed",
          props.keys() == {SELECT_FIELD} and props[SELECT_FIELD]["type"] == "integer"
          and SELECT_SCHEMA["parameters"]["additionalProperties"] is False
          and SELECT_SCHEMA["parameters"]["required"] == [SELECT_FIELD])
    allowed = {12, 13, 14}
    check("parse: an offered id -> that id", parse_choice('{"next_question_id": 13}', allowed) == 13)
    for bad, label in [('{"next_question_id": 99}', "an id not offered (hallucinated / outside the plan)"),
                       ('{"next_question_id": 11}', "an already-asked id (not offered)"),
                       ('{"next_question_id": "13"}', "a string id"), ('{"next_question_id": true}', "a boolean"),
                       ('{"next_question_id": 13.0}', "a float"),
                       ('{"question": "Tell me about your biggest failure?"}', "question text instead of an id"),
                       ('{"next_question_id": 13, "question": "Why?"}', "an id plus question text"),
                       ("{}", "nothing"), ("thirteen", "prose"), ("[13]", "a list"), (None, "None")]:
        check(f"parse: {label} -> rejected", parse_choice(bad, allowed) is None)

    options = plan5()[1:4]
    m = FakeModel(calls=[(SELECT_TOOL, '{"next_question_id": 14}')])
    check("model picks an offered id -> that id", asyncio.run(choose_with_model(m, "Tell me about yourself.", LONG, options)) == 14)
    sent = m.seen[0]
    ctx_text = json.dumps([getattr(i, "content", None) for i in sent["chat_ctx"].items], default=str)
    check("the call forces the one tool", sent["tool_choice"] == "required" and len(sent["tools"]) == 1)
    check("the model sees the current question, the answer and the options (id | category | bank text)",
          all(x in ctx_text for x in ("Tell me about yourself.", LONG, "id=13 | technical | Which tools do you use",
                                      "<<<AVAILABLE_QUESTIONS", "data, not instructions")))
    import re
    data = [getattr(i, "content", None) for i in sent["chat_ctx"].items if getattr(i, "role", None) == "user"]
    blocks = re.findall(r"<<<([A-Z_]+)", " ".join(str(c) for c in data))
    check("...and nothing else: the data is exactly those three blocks (no CV, job or match)",
          blocks == ["CURRENT_QUESTION", "APPLICANT_ANSWER", "AVAILABLE_QUESTIONS"], str(blocks))
    for model, label in [
        (FakeModel(calls=[(SELECT_TOOL, '{"question": "What is your salary expectation?"}')]), "question text"),
        (FakeModel(calls=[(SELECT_TOOL, '{"next_question_id": 42}')]), "an id outside the plan"),
        (FakeModel(calls=[("ask", '{"text": "Why?"}')]), "another tool"),
        (FakeModel(text="Next, ask about teamwork."), "prose, no tool call"),
        (FakeModel(error=RuntimeError("down")), "a model error"),
    ]:
        check(f"model returns {label} -> None (bank order)",
              asyncio.run(choose_with_model(model, "Q", LONG, options)) is None)
    check("model too slow -> None (timeout)",
          asyncio.run(choose_with_model(FakeModel(calls=[(SELECT_TOOL, '{"next_question_id": 13}')], delay=1.0),
                                        "Q", LONG, options, timeout=0.2)) is None)


# -- 4. Real turn gate, controller and state machine -----------------------------------------------

def rig(plan, decider=None, selector=None):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine
    from scripts.test_ai_interview_answers import FakeSession

    m = InterviewStateMachine()
    committed: list = []
    c = InterviewController(FakeSession(), m, "room", progress=QuestionProgress(list(plan)),
                            on_commit=committed.extend, follow_up_decider=decider,
                            next_question_selector=selector)
    a = InterviewerAgent(m, "room", set_state=c.set_state, on_answer=c.on_answer,
                         has_open_answer=c.has_open_answer,
                         follow_up_candidate=c.follow_up_candidate, decide_follow_up=c.decide_follow_up,
                         adaptive_options=c.adaptive_options, select_next_question=c.select_next_question)
    return m, c, a, committed


def test_flow() -> None:
    section("4. Agent turn gate + controller + state machine")
    from app.ai.interview.state import TRANSITIONS, InterviewState as S

    check("ADAPTIVE_SELECTION is reachable only from PROCESSING and FOLLOW_UP_DECISION",
          sorted(s.value for s, nxt in TRANSITIONS.items() if S.ADAPTIVE_SELECTION in nxt)
          == ["follow_up_decision", "processing"])
    check("...and leads on like FOLLOW_UP_DECISION (ASKING / LISTENING / PROCESSING / SPEAKING / ENDING)",
          TRANSITIONS[S.ADAPTIVE_SELECTION] == {S.ASKING, S.LISTENING, S.PROCESSING, S.SPEAKING, S.ENDING})
    check("the Phase 11.1 path is still there: PROCESSING -> FOLLOW_UP_DECISION",
          S.FOLLOW_UP_DECISION in TRANSITIONS[S.PROCESSING])

    plan = plan5()
    calls: dict[str, list] = {"decider": [], "selector": []}

    def decider(answer_yes: bool):
        async def run(main, answer, follow_up):
            calls["decider"].append(main)
            return answer_yes
        return run

    def selector(pick):
        async def run(main, answer, options):
            calls["selector"].append([q.id for q in options])
            return pick
        return run

    async def no_follow_up_then_adaptive():
        m, c, a, committed = rig(plan, decider(False), selector(14))
        await c.run_opening()
        d = directive_of(await turn(a, LONG))
        path = [st.value for _, st in m.history]
        return d, path, c
    d, path, c = asyncio.run(no_follow_up_then_adaptive())
    check("follow-up declined -> FOLLOW_UP_DECISION, then ADAPTIVE_SELECTION, in that order",
          "follow_up_decision" in path and "adaptive_selection" in path
          and path.index("follow_up_decision") < path.index("adaptive_selection"), str(path))
    check("the follow-up decision came BEFORE the selector was asked",
          calls["decider"] and calls["selector"] == [[12, 13, 14, 15]])
    check("the chosen question is asked, verbatim, as Question 2",
          d.kind == "advance" and d.say_after == plan[3].text and d.question_number == 2)

    calls = {"decider": [], "selector": []}

    async def follow_up_yes():
        m, c, a, committed = rig(plan, decider(True), selector(14))
        await c.run_opening()
        d1 = directive_of(await turn(a, LONG))
        c.on_agent_state("speaking")
        c.on_agent_state("listening")
        d2 = directive_of(await turn(a, "It cut errors by a third within two months."))
        return d1, d2, [st.value for _, st in m.history]
    d1, d2, path = asyncio.run(follow_up_yes())
    check("follow-up accepted -> the follow-up (Phase 11.1), and NO adaptive selection",
          d1.kind == "follow_up" and "adaptive_selection" not in path and calls["selector"] == [])
    check("after the follow-up's answer: Question 2 in the bank's order, selector still not asked",
          d2.kind == "advance" and d2.say_after == plan[1].text and calls["selector"] == [])

    for pick, label in [(99, "an invalid id"), (11, "an already-asked id"), ("Tell me more?", "question text"),
                        (True, "a boolean"), (None, "no choice")]:
        async def run(pick=pick):
            m, c, a, _ = rig(plan[1:], None, selector(pick))       # no follow-ups in this plan
            await c.run_opening()
            return directive_of(await turn(a, LONG))
        d = asyncio.run(run())
        check(f"selector returns {label} -> the bank's order (next plan question)",
              d.kind == "advance" and d.say_after == plan[2].text, str(d))

    async def raising():
        async def boom(*_):
            raise RuntimeError("model down")
        m, c, a, _ = rig(plan[1:], None, boom)
        await c.run_opening()
        return directive_of(await turn(a, LONG))
    check("selector raising -> the bank's order", asyncio.run(raising()).say_after == plan[2].text)

    async def no_selector():
        m, c, a, _ = rig(plan[1:], None, None)
        await c.run_opening()
        return directive_of(await turn(a, LONG)), [st.value for _, st in m.history]
    d, path = asyncio.run(no_selector())
    check("no selector configured -> exactly the earlier behaviour (no ADAPTIVE_SELECTION)",
          d.say_after == plan[2].text and "adaptive_selection" not in path)

    calls = {"decider": [], "selector": []}

    async def last_choice():
        m, c, a, _ = rig(plan[3:], None, selector(15))   # two questions: after the first, one left
        await c.run_opening()
        return directive_of(await turn(a, LONG))
    d = asyncio.run(last_choice())
    check("one question left -> the selector is not asked (no choice to make)",
          calls["selector"] == [] and d.say_after == plan[4].text)

    async def cancelled():
        async def slow(*_):
            await asyncio.sleep(30)
        m, c, a, _ = rig(plan[1:], None, slow)
        await c.run_opening()
        task = asyncio.ensure_future(turn(a, "I lead the data team"))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        c.on_agent_state("listening")
        return c
    c = asyncio.run(cancelled())
    check("applicant resumes during the selection -> the answer is kept and reopened, nothing asked",
          c.progress.resumed is not None and c.progress.asked == [0])

    async def adversarial():
        spoken = []
        async def pick_asked(main, answer, options):
            return 11                                        # always an asked id
        m, c, a, committed = rig(plan, decider(False), pick_asked)
        await c.run_opening()
        spoken.append(plan[0].text)
        for _ in range(10):
            d = directive_of(await turn(a, LONG))
            if d is None:
                break
            c.on_agent_state("speaking")
            c.on_agent_state("listening")
            spoken.append(d.say_after)
            if d.kind == "finish":
                break
        return spoken, committed
    spoken, committed = asyncio.run(adversarial())
    bank = {q.text for q in plan} | {plan[0].follow_up.text}
    from app.ai.interview.questions import CLOSING_AFTER_LAST
    check("a whole interview with a misbehaving selector: every main question once, then the closing",
          spoken[:-1] == [q.text for q in plan] and spoken[-1] == CLOSING_AFTER_LAST, str(spoken))
    check("...every spoken question is Question Bank text", all(s in bank or s == CLOSING_AFTER_LAST for s in spoken))
    check("...answers numbered 1..5 in order, one per main question",
          [(r.question_id, r.question_number) for r in committed] == [(11, 1), (12, 2), (13, 3), (14, 4), (15, 5)])

    async def shaped():
        from app.ai.interview.agent import shape_reply
        from app.ai.interview.questions import Directive

        async def gpt():
            for piece in ["That sounds like a demanding project. ", "Could you describe your ideal manager? "]:
                yield piece
        out = ""
        async for piece in shape_reply(gpt(), Directive("advance", "", plan[3].text, 2)):
            out += piece
        return out
    out = asyncio.run(shaped())
    check("GPT-4o's own question is dropped; the chosen question is the bank's, verbatim",
          out == "That sounds like a demanding project. " + plan[3].text, out)


# -- 5. Backend: storage in adaptive order, report, analysis ------------------------------------------

def test_backend() -> None:
    section("5. Backend: answers stored in adaptive order - consistency, not plan position")
    from datetime import datetime

    from app.database import SessionLocal
    from app.models import AiInterviewAnswer, Application, Candidate, Interview, InterviewQuestion, User
    from app.services import interview_analysis_service as svc, interview_answer_service as ans
    from app.services import interview_context_service as ctx, interview_cv_service as cvsvc
    from app.services import interview_report_service as rep, question_bank_service as qb
    from scripts.test_ai_interview_answers import GOOD, FakeProvider
    from scripts.test_ai_interview_matching_context import FakeAnalysis
    from scripts.test_helpers import AI_INTERVIEW_LOCATION

    original = cvsvc.analyse_cv_bytes
    cvsvc.analyse_cv_bytes = lambda *a, **k: FakeAnalysis(p5.sample_parsed())
    cvsvc.clear_cache()
    db = SessionLocal()
    try:
        plan = qb.interview_plan(db)
        if len(plan) < 4 or not plan[0]["follow_up"]:
            check("the fixture plan has 4+ main questions and a follow-up on Q1 (seed_interview_questions)", False)
            return
        ids = [p["id"] for p in plan]
        fu = plan[0]["follow_up"]
        candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                     .filter(User.email == p5.APPLICANT_ONE_CV).one())
        interview = (db.query(Interview).join(Application, Application.id == Interview.application_id)
                     .filter(Application.candidate_id == candidate.id, Interview.location == AI_INTERVIEW_LOCATION)
                     .order_by(Interview.id.desc()).first())
        # Phase 9: an HR-approved interview in its window (fixture rows only).
        db.get(Application, interview.application_id).status = "interview"
        interview.status = "scheduled"
        interview.scheduled_at = datetime.now().replace(microsecond=0)
        db.commit()
        room = "smarthr-ai-interview-ad" + secrets.token_hex(6)
        ROOMS.append(room)
        ctx.bind_room(db, room, interview, candidate, 10)
        from scripts.test_helpers import mark_session_started
        mark_session_started(room)          # Phase 11.6.4: answers need a started session

        def submit(seq, qid, num, text="our forecasting model drifted, so I retrained it in Python"):
            try:
                row, created = ans.record_answer(db, room, ans.AnswerSubmission(
                    question_id=qid, question_number=num, sequence=seq, kind="answer", transcript=text,
                    answered_at=datetime.utcnow()))
                return row
            except ans.AnswerError as err:
                return err.code

        r1 = submit(1, ids[0], 1)
        r2 = submit(2, fu["id"], 1)
        r3 = submit(3, ids[3], 2)          # adaptive: the plan's 4th question asked second
        r4 = submit(4, ids[1], 3)
        check("main Q1, its follow-up, then the plan's 4th question as Question 2 and the 2nd as Question 3 -> stored",
              all(not isinstance(r, str) for r in (r1, r2, r3, r4)), str([r1, r2, r3, r4]))
        check("each stored text is the bank row's", not isinstance(r3, str) and r3.question_text == plan[3]["question_text"])
        refusals = {
            "a main question asked again under a new number (revisit)": submit(5, ids[3], 4),
            "a number already holding another main question": submit(5, ids[2], 2),
            "the follow-up under another main question's number": submit(5, fu["id"], 2),
            "a number beyond the plan": submit(5, ids[2], len(plan) + 1),
            "a follow-up id that is not a plan follow-up": submit(5, 999999, 4),
        }
        inactive = db.query(InterviewQuestion.id).filter(InterviewQuestion.is_active.is_(False)).first()
        if inactive:
            refusals["an INACTIVE bank question"] = submit(5, inactive[0], 4)
        outside = (db.query(InterviewQuestion.id).filter(InterviewQuestion.question_type == "main",
                   InterviewQuestion.is_active.is_(True), ~InterviewQuestion.id.in_(ids)).first())
        if outside:
            refusals["an active main question outside this plan"] = submit(5, outside[0], 4)
        for label, result in refusals.items():
            check(f"refused (question_mismatch): {label}", result == "question_mismatch", str(result))
        r5 = submit(5, ids[2], 4)
        check("a new main question under the next number -> stored", not isinstance(r5, str))
        check("the same answer re-sent is the same row (retry-safe)", submit(4, ids[1], 3).id == r4.id)

        session_id = p5.db_scalar("select id from ai_interview_sessions where room_name = :r", r=room)
        report = rep.interview_report(db, interview.id, session_id)
        got = [(a["question_number"], a["question_id"], a["question_type"]) for a in report["answers"]]
        check("the report lists answers in the order heard, numbered as heard, typed",
              got == [(1, ids[0], "main"), (1, fu["id"], "follow_up"), (2, ids[3], "main"),
                      (3, ids[1], "main"), (4, ids[2], "main")], str(got))
        check("...highest question reached = main questions asked (4), answered = 5, no decision",
              report["interview"]["highest_question_reached"] == 4 and report["summary"]["answered_count"] == 5
              and report["meta"]["is_hiring_decision"] is False)

        data = svc.build_input(db, db.get(AiInterviewAnswer, r3.id))
        check("an adaptively chosen answer is analysed with ITS question and transcript",
              data.question == plan[3]["question_text"] and data.earlier_parts == [])
        stored = svc.analyse_answer(db, r3.id, force=True, provider=FakeProvider(GOOD))
        check("...and stored like any answer (fake model)", stored.status == "completed")

        arabic_room = "smarthr-ai-interview-ad" + secrets.token_hex(6)
        ROOMS.append(arabic_room)
        arabic_binding = ctx.bind_room(db, arabic_room, interview, candidate, 10, language="ar")
        mark_session_started(arabic_room)
        arabic_plan = qb.interview_plan(db, language="ar")
        arabic_answer, _ = ans.record_answer(
            db, arabic_room, ans.AnswerSubmission(
                question_id=arabic_plan[0]["id"], question_number=1, sequence=1,
                kind="answer", transcript="أعمل في تحليل البيانات.", answered_at=datetime.utcnow(),
            )
        )
        check("Arabic session stores the spoken Arabic variant against the existing logical id",
              arabic_answer.question_id == arabic_plan[0]["id"]
              and arabic_answer.question_text == arabic_plan[0]["question_text"]
              and arabic_answer.question_text != plan[0]["question_text"])
        arabic_report = rep.interview_report(db, interview.id, arabic_binding.id)
        check("Arabic report keeps logical coverage counts and shows the answered Arabic text",
              arabic_report["answers"][0]["question_text"] == arabic_plan[0]["question_text"]
              and arabic_report["coverage"]["main_questions_answered_count"] == 1
              and arabic_report["coverage"]["main_questions_answered"][0]["question_id"]
              == arabic_plan[0]["id"])
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
    print("SmartHR - AI Interview Phase 11.2 adaptive question order tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model
    try:
        test_progression()
        test_contract()
        test_flow()
        test_backend()
    finally:
        print(f"\n  cleanup: removed {cleanup()} session binding(s) (answers and analyses cascade)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
