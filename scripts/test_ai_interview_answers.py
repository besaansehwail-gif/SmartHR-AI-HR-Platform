"""AI Interview - Phase 7 Answers & Analysis tests. No LiveKit, no real model.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_answers

Four parts:

* **offline** - when an answer becomes final and how it is numbered
  (`QuestionProgress.commit` / `flush`), what the controller hands on and what
  it does not (ignored filler, reopened halves, interruptions), the worker's
  request body and its retry rules, and the analysis module: the schema has
  no field for a score or a decision, the prompt carries the real question
  and answer and never the Match Score, and validation drops unquoted
  claims, verdicts, invented terms and non-requirements. Plus containment:
  the worker still never touches the database.
* **worker -> backend, end to end** - a real `InterviewerAgent` +
  `InterviewController` + `AnswerSink` (fake LiveKit session, real HTTP) run
  an interview with an ignored filler, a mid-answer pause, an interruption,
  a short answer and an unheard last reply; the rows in PostgreSQL are then
  compared with what was said.
* **HTTP** - its own backend on port 8050 (fake LiveKit credentials, no
  model): ownership from the room binding, question association against the
  bank, duplicates, ordering, transcripts kept exactly, every refusal, and
  the Admin/HR-only review routes.
* **analysis, in process** - a fake provider over the real service: the
  model is shown the stored question and transcript with the real Job, CV
  and Matching Context, and what is stored has been through the guards.

Uses the Phase 5 fixtures (applicant05 / applicant10); creates no CV and no
application. Session bindings created here are deleted at the end, and their
answers and analyses go with them (ON DELETE CASCADE).
"""

import asyncio
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_ai_interview_cv_context as p5  # noqa: E402
from scripts import test_helpers as e2e  # noqa: E402

PORT = 8050
BASE = f"http://127.0.0.1:{PORT}"

HR = "aiinterview.hr@smarthr.test"
MANAGER = "aiinterview.manager@smarthr.test"
EMPLOYEE = "aiinterview.employee@smarthr.test"
ADMIN = "aiinterview.admin@smarthr.test"

passed = 0
failed: list[str] = []
ROOMS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  FAIL  {name}{f' - {detail}' if detail else ''}")
    return bool(ok)


def utcnow() -> datetime:
    """Naive UTC, as the AI Interview tables store it."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# --------------------------------------------------------------------------
# Offline: when an answer is final, and what is handed on
# --------------------------------------------------------------------------

def _plan():
    from app.ai.interview.questions import PlannedQuestion
    return [PlannedQuestion(11, 1, "general", "Tell me about yourself."),
            PlannedQuestion(12, 2, "behavioral", "Describe a challenge you faced."),
            PlannedQuestion(13, 3, "general", "How do you work in a team?")]


def test_progress() -> None:
    section("1. An answer is final when its reply is heard - numbered once, in order")
    from app.ai.interview.questions import QuestionProgress

    p = QuestionProgress(_plan())
    p.decide("answer", "I am a data engineer from Beirut.")
    check("a decided answer is not final yet (no sequence)", p.answers[-1].sequence is None)
    done = p.commit()
    check("commit -> sequence 1, against the question that was asked",
          [(r.sequence, r.question_id, r.question_number) for r in done] == [(1, 11, 1)])
    check("a second commit hands on nothing (no duplicate)", p.commit() == [])

    p.decide("answer", "Once a migration")
    reopened = p.reopen()
    check("a reopened half is not handed on", reopened is not None and reopened.sequence is None
          and p.commit() == [])
    p.decide("filler", "uh failed and I fixed it overnight.")
    merged = p.commit()
    check("the merged answer is ONE final answer, sequence 2, same question",
          [(r.sequence, r.question_id) for r in merged] == [(2, 12)])
    check("its transcript is the two accepted parts, exactly",
          merged[0].text == "Once a migration uh failed and I fixed it overnight.", merged[0].text)

    # A short answer is an answer (no elaboration round): final on its own,
    # and on the last question it finishes the interview.
    d = p.decide("short", "Yes.")
    first = p.commit()
    second = p.decide("answer", "I pair with colleagues and review their code daily.")
    check("short answer: ONE final answer on the last question, and the interview finishes",
          [(r.sequence, r.question_id, r.kind) for r in first] == [(3, 13, "short")]
          and d.kind == "finish" and second is None and p.commit() == [])

    q = QuestionProgress(_plan())
    q.decide("answer", "An answer whose reply never played.")
    flushed = q.flush()
    check("flush: an accepted answer whose reply never played is kept (sequence 1)",
          [(r.sequence, r.question_id) for r in flushed] == [(1, 11)])
    q.decide("answer", "The start of an answer")
    q.reopen()
    flushed = q.flush()
    check("flush: the first half of a reopened answer whose rest never came is kept",
          [(r.sequence, r.text) for r in flushed] == [(2, "The start of an answer")], str(flushed))
    check("flush twice hands on nothing", q.flush() == [])
    check("sequences are never reused", [a.sequence for a in q.answers] == [1, 2])
    check("wall-clock time is recorded for answered_at", all(abs(a.wall - time.time()) < 60 for a in q.answers))


class FakeHandle:
    def __init__(self):
        self.interrupted = False
        self._cbs = []

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


class FakeSession:
    def __init__(self):
        self.said, self.shut, self.handles = [], False, []

    def on(self, *_a):
        pass

    def say(self, text, allow_interruptions=None):
        self.said.append(text)
        h = FakeHandle()
        self.handles.append(h)
        return h

    def interrupt(self, force=False):
        pass

    def shutdown(self, drain=True):
        self.shut = True


async def _turn(agent, text: str) -> bool:
    """One applicant turn through the REAL turn gate. False if it was ignored."""
    from livekit.agents import StopResponse, llm
    try:
        await agent.on_user_turn_completed(llm.ChatContext.empty(),
                                           llm.ChatMessage(role="user", content=[text]))
        return True
    except StopResponse:
        return False


def _rig(plan, on_commit):
    from app.ai.interview.agent import InterviewerAgent
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import QuestionProgress
    from app.ai.interview.state import InterviewStateMachine

    m = InterviewStateMachine()
    s = FakeSession()
    c = InterviewController(s, m, "room", progress=QuestionProgress(list(plan)), on_commit=on_commit)
    a = InterviewerAgent(m, "room", set_state=c.set_state, on_answer=c.on_answer,
                         has_open_answer=c.has_open_answer)
    return m, s, c, a


def test_controller() -> None:
    section("2. The controller hands on final answers only - never ignored, reopened or interrupted turns")
    handed: list = []

    async def scenario():
        m, s, c, a = _rig(_plan(), lambda records: handed.extend(records))
        await c.run_opening()

        check("an ignored filler is not an answer", not await _turn(a, "um") and handed == []
              and c.progress.answers == [])

        await _turn(a, "I am a data engineer and I like building pipelines.")
        c.on_agent_state("thinking")
        check("accepted but its reply not yet heard -> nothing handed on", handed == [])
        c.on_agent_state("speaking")
        check("reply heard -> answer 1 handed on", [r.sequence for r in handed] == [1])
        c.on_agent_state("listening")

        # The applicant talks over the interviewer's (audibly playing) speech.
        interrupted = FakeHandle()
        c.on_speech_created(interrupted)
        c._last_spoke_at = time.monotonic() + 1
        interrupted.finish(interrupted=True)
        check("an interruption is counted - and creates no answer",
              m.counters.interruptions == 1 and len(c.progress.answers) == 1 and len(handed) == 1)

        await _turn(a, "The hardest thing I did was")
        c.on_agent_state("thinking")
        c.on_agent_state("listening")           # reply cancelled unheard: still talking
        check("a turn cut by a pause is NOT handed on (reopened)", len(handed) == 1 and c.has_open_answer())
        await _turn(a, "uh")                      # a filler that ENDS the open answer
        c.on_agent_state("speaking")
        check("...the completed answer is handed on once, merged",
              [(r.sequence, r.question_number, r.text) for r in handed[1:]]
              == [(2, 2, "The hardest thing I did was uh")], str(handed[1:]))
        c.on_agent_state("listening")

        await _turn(a, "I share everything with the team every morning.")   # Q3, last
        c.on_agent_state("thinking")
        c.flush_answers()                        # the session ends before the reply plays
        check("session end -> the last accepted answer is handed on",
              [(r.sequence, r.question_number) for r in handed[2:]] == [(3, 3)])
        c.flush_answers()
        check("flushing again hands on nothing", len(handed) == 3)

    asyncio.run(scenario())

    boom = []

    async def failing():
        _, _, c, a = _rig(_plan(), lambda records: (_ for _ in ()).throw(RuntimeError("down")))
        await c.run_opening()
        await _turn(a, "An answer while the hand-off is broken.")
        c.on_agent_state("speaking")
        boom.append(c.machine.state.value)

    asyncio.run(failing())
    check("a failing hand-off never breaks the interview", boom == ["asking"], str(boom))


def test_client() -> None:
    section("3. The worker's request: six fields, no ids, retried safely")
    from app.ai.interview.answer_client import AnswerSink, answer_payload
    from app.ai.interview.questions import QuestionProgress
    import app.ai.interview.answer_client as client

    p = QuestionProgress(_plan())
    p.decide("answer", "I build data pipelines.")
    record = p.commit()[0]
    body = answer_payload(record)
    check("exactly question_id, question_number, sequence, kind, transcript, answered_at",
          set(body) == {"question_id", "question_number", "sequence", "kind", "transcript", "answered_at"},
          str(sorted(body)))
    check("no candidate / interview / application / question text in the body",
          not any(k in json.dumps(body) for k in ("candidate", "interview", "application", "Tell me")))
    check("answered_at is UTC ISO-8601", body["answered_at"].endswith("+00:00"), body["answered_at"])
    try:
        answer_payload(type(record)(1, 1, "x", "answer", 1))
        check("an answer that is not final cannot be sent", False)
    except ValueError:
        check("an answer that is not final cannot be sent", True)

    client.RETRY_DELAYS_S = (0.0, 0.0)
    for label, statuses, delivered, refused, undelivered, calls in (
        ("5xx then 200 -> retried, delivered", [500, 200], [1], [], [], 2),
        ("network error then 200 -> retried, delivered", [ConnectionError(), 200], [1], [], [], 2),
        ("409 -> refused, NOT retried", [409], [], [(1, 409)], [], 1),
        ("always 503 -> given up after 3 attempts", [503, 503, 503], [], [], [1], 3),
    ):
        seen = []

        async def post(payload, queue=list(statuses)):
            seen.append(payload)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        async def run():
            sink = AnswerSink("room", post=post)
            sink.submit([record])
            await sink.drain(5)
            return sink

        sink = asyncio.run(run())
        check(label, (sink.delivered, sink.refused, sink.undelivered, len(seen))
              == (delivered, refused, undelivered, calls), f"{sink.delivered} {sink.refused} {sink.undelivered} {len(seen)}")
        if len(seen) > 1:
            check(f"{label}: every retry is the identical request (same sequence)",
                  all(s == seen[0] for s in seen))

    order = []

    async def ordered():
        async def post(payload):
            await asyncio.sleep(0.01 * (3 - payload["sequence"]))
            order.append(payload["sequence"])
            return 200
        sink = AnswerSink("room", post=post)
        q = QuestionProgress(_plan())
        for text in ("One answer here.", "Two answer here.", "Three answer here."):
            q.decide("answer", text)
            sink.submit(q.commit())
        await sink.drain(5)

    asyncio.run(ordered())
    check("delivery is one at a time, in answer order", order == [1, 2, 3], str(order))


# --------------------------------------------------------------------------
# Offline: the analysis module
# --------------------------------------------------------------------------

JOB = {"job_id": 8, "title": "DEMO - AI Engineering Intern", "department": "Engineering",
       "employment_type": "internship", "description": "Build ML features.",
       "requirements": ["Python", "Machine Learning", "SQL", "Git"]}
CV = {"skills": ["Python", "Machine Learning", "TensorFlow"],
      "experience": [{"job_title": "ML Engineer", "company": "Cedar Analytics"}]}
QUESTION = "Tell me about a challenging situation you faced and how you handled it."
TRANSCRIPT = ("At Cedar Analytics our forecasting model drifted, so I retrained it in Python "
              "and I also deployed it on Kubernetes myself.")


def analysis_input(**over):
    from app.ai.interview_analysis import AnalysisInput
    data = dict(question=QUESTION, transcript=TRANSCRIPT, job=JOB, cv=CV,
                matching_skills=["Python", "Machine Learning"], skill_gaps=["SQL", "Git"],
                matching_available=True)
    data.update(over)
    return AnalysisInput(**data)


GOOD = {
    "addresses_question": "fully",
    "summary": "The applicant described retraining a drifting forecasting model at Cedar Analytics.",
    "evidence": [{"point": "Describes handling model drift.", "quote": "our forecasting model drifted",
                  "type": "example"}],
    "skills_mentioned": [{"skill": "Python", "quote": "I retrained it in Python"},
                         {"skill": "Kubernetes", "quote": "I also deployed it on Kubernetes myself"}],
    "job_requirements_referenced": ["python"],
    "cv_relation": [{"statement": "I also deployed it on Kubernetes myself", "relation": "not_in_cv"}],
    "specificity": "specific",
    "clarity": "clear",
    "not_covered": ["How the result was measured."],
}


class FakeProvider:
    name, model, configured = "fake", "fake-gpt-4o", True

    def __init__(self, payload=None, text=None):
        self.payload, self.text, self.calls = payload, text, []

    def complete(self, system, messages, tools=None):
        from app.ai.provider import LlmReply, ToolCall
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        if self.text is not None:
            return LlmReply(text=self.text)
        return LlmReply(tool_call=ToolCall(tools[0]["name"], json.loads(json.dumps(self.payload))))


def test_analysis_schema() -> None:
    section("4. The analysis schema: evidence only - no score, no match, no decision")
    from app.ai.interview_analysis import ANALYSIS_FIELDS, ANALYSIS_SCHEMA, SYSTEM_PROMPT

    props = set(ANALYSIS_SCHEMA["properties"])
    check("schema fields are exactly the analysis fields", props == set(ANALYSIS_FIELDS), str(sorted(props)))
    forbidden = re.compile(r"score|rating|rank|match|fit|hire|reject|decision|verdict|recommend|pass|fail|suitab",
                           re.I)
    check("no schema property can hold a score, a match or a decision",
          not [p for p in props if forbidden.search(p)], str(props))
    enums = json.dumps([v.get("enum") for v in ANALYSIS_SCHEMA["properties"].values()])
    check("no enum value is a verdict", not re.search(r"hire|reject|pass|fail|suitable|qualified", enums), enums)
    check("the instructions forbid decisions, scores and invented facts",
          all(w in SYSTEM_PROMPT for w in ("hired", "rejected", "score", "copied exactly", "not proof",
                                           "not a sign")))


def test_analysis_prompt() -> None:
    section("5. GPT-4o is shown the actual question and answer - and never the Match Score")
    from app.ai.interview_analysis import analyse, build_user_message

    message = build_user_message(analysis_input(earlier_parts=["Yes."]))
    check("the question is in the prompt, verbatim", QUESTION in message)
    check("the transcript is in the prompt, verbatim", TRANSCRIPT in message)
    check("earlier parts of the same answer are included", "EARLIER PART OF THE SAME ANSWER" in message
          and "Yes." in message)
    check("the job's requirements are in the prompt", "Python; Machine Learning; SQL; Git" in message)
    check("the CV Context is in the prompt, labelled as claims", "Cedar Analytics" in message and "claims" in message)
    check("matching skills and gaps are there, labelled 'not proof'",
          "not proof" in message and "SQL; Git" in message)
    check("no Match Score, number or percentage from matching reaches the prompt",
          "score" not in message.lower() and "50" not in message and "%" not in message)
    check("the answer is delimited as data", "<<<ANSWER" in message and "ANSWER>>>" in message)

    bare = build_user_message(analysis_input(cv=None, matching_available=False, matching_skills=[], skill_gaps=[]))
    check("no CV -> the prompt says so and asks for no cv_relation", "CV CONTEXT: not available" in bare)
    check("no matching -> the prompt says so", "MATCHING: not available" in bare)

    fake = FakeProvider(GOOD)
    result = analyse(analysis_input(), provider=fake)
    check("one model call, through the tool schema", len(fake.calls) == 1
          and fake.calls[0]["tools"][0]["name"] == "record_answer_analysis")
    check("a valid reply is stored with the model's name", result.model == "fake-gpt-4o")

    fenced = analyse(analysis_input(), provider=FakeProvider(text="```json\n" + json.dumps(GOOD) + "\n```"))
    check("a fenced-JSON reply is salvaged into the same schema", fenced.analysis["addresses_question"] == "fully")


def test_analysis_validation() -> None:
    section("6. Validation: every claim traceable to the answer; verdicts and scores removed")
    from app.ai.interview_analysis import (
        AnalysisError, ANALYSIS_FIELDS, analyse, validate_analysis, verdict_claim,
    )

    a = validate_analysis(GOOD, analysis_input())
    check("stored fields = the analysis fields + meta", set(a) == set(ANALYSIS_FIELDS) | {"meta"}, str(sorted(a)))
    check("meta says it is not a hiring decision", a["meta"]["is_hiring_decision"] is False)
    check("skills are recorded as the applicant's statement",
          all(s["source"] == "applicant_statement" for s in a["skills_mentioned"]))
    check("a skill the CV does not list is kept as a statement, marked not_in_cv (not 'false')",
          a["cv_relation"] == [{"statement": "I also deployed it on Kubernetes myself", "relation": "not_in_cv"}])
    check("requirements are normalised to the job's exact phrase", a["job_requirements_referenced"] == ["Python"])
    check("no numeric score anywhere in the stored analysis",
          "score" not in json.dumps(a).lower() and not re.search(r'":\s*\d', json.dumps({k: v for k, v in a.items()
                                                                                          if k != "meta"})))

    bad = json.loads(json.dumps(GOOD))
    bad["summary"] = ("The applicant retrained a model in Python. The applicant is a strong candidate and "
                      "should be hired. Their match score is 50%. The applicant lacks SQL experience. "
                      "The applicant previously worked at Google for ten years.")
    bad["evidence"].append({"point": "Led a team of 40.", "quote": "I led a team of forty engineers", "type": "experience"})
    bad["evidence"].append({"point": "The applicant is unsuitable for the role.", "quote": "our forecasting model drifted",
                            "type": "other"})
    bad["skills_mentioned"].append({"skill": "Rust", "quote": "I wrote it in Rust"})
    bad["skills_mentioned"].append({"skill": "SQL", "quote": "I retrained it in Python"})
    bad["job_requirements_referenced"] += ["Kubernetes", "10 years of experience"]
    bad["not_covered"] = ["The applicant does not have experience with SQL.", "How success was measured."]
    v = validate_analysis(bad, analysis_input())
    check("verdict / score / 'lacks' sentences are removed from the summary",
          not any(w in v["summary"].lower() for w in ("strong candidate", "hired", "score", "50", "lacks")), v["summary"])
    check("a fact the answer never states (Google) is removed", "Google" not in v["summary"], v["summary"])
    check("...while the supported sentence stays", v["summary"] == "The applicant retrained a model in Python.",
          v["summary"])
    check("evidence whose quote is not in the answer is dropped", len(v["evidence"]) == 1, str(v["evidence"]))
    check("a skill the applicant never said is dropped (Rust), as is a skill not in its own quote (SQL)",
          [s["skill"] for s in v["skills_mentioned"]] == ["Python", "Kubernetes"], str(v["skills_mentioned"]))
    check("'requirements' that are not the job's are dropped", v["job_requirements_referenced"] == ["Python"])
    check("'not covered' keeps the question's gaps, drops claims about the person",
          v["not_covered"] == ["How success was measured."], str(v["not_covered"]))
    g = v["meta"]["guards"]
    check("every removal is counted", g["verdict"] >= 3 and g["unquoted"] >= 3 and g["not_a_requirement"] == 2
          and g["unsupported_term"] >= 1, str(g))

    no_cv = validate_analysis(GOOD, analysis_input(cv=None))
    check("cv_relation without a CV context is dropped", no_cv["cv_relation"] == []
          and no_cv["meta"]["guards"]["cv_without_cv"] == 1)

    for label, payload in (("not an object", ["x"]),
                           ("an unknown addresses_question", {**GOOD, "addresses_question": "hired"}),
                           ("an unknown clarity", {**GOOD, "clarity": "excellent"})):
        try:
            validate_analysis(payload, analysis_input())
            check(f"refused: {label}", False)
        except AnalysisError as exc:
            check(f"refused: {label}", exc.code == "invalid_structure")

    for text, flagged in (("The applicant should be hired.", True), ("They would be a good fit.", True),
                          ("Scored 8/10 on this answer.", True), ("A 75% match with the role.", True),
                          ("The applicant is qualified.", True), ("The applicant passed the interview.", True),
                          ("The applicant has no experience with SQL.", True), ("I recommend moving forward.", True),
                          ("The applicant described a data pipeline.", False),
                          ("The answer gave a concrete example.", False)):
        check(f"verdict_claim({text!r}) = {flagged}", verdict_claim(text) == flagged)

    for code, provider in (("llm_not_configured", None), ("malformed_response", FakeProvider(text="no json here"))):
        try:
            if provider is None:
                from app.ai.provider import UnconfiguredProvider
                provider = UnconfiguredProvider()
            analyse(analysis_input(), provider=provider)
            check(f"failure is a coded error: {code}", False)
        except AnalysisError as exc:
            check(f"failure is a coded error: {code}", exc.code == code, exc.code)
    try:
        analyse(analysis_input(transcript="   "), provider=FakeProvider(GOOD))
        check("an empty answer is not sent to the model", False)
    except AnalysisError as exc:
        check("an empty answer is not sent to the model", exc.code == "empty_answer")


def test_containment() -> None:
    section("7. Containment: the worker still never touches the database")
    for path in sorted((ROOT / "app" / "ai" / "interview").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        bad = [m for m in ("app.models", "app.database", "sqlalchemy", "SessionLocal", "psycopg")
               if m in text]
        if path.name in ("answer_client.py", "questions.py", "controller.py", "worker.py"):
            check(f"{path.name}: no database access", not bad, ", ".join(bad))
    text = (ROOT / "app" / "ai" / "interview_analysis.py").read_text(encoding="utf-8")
    check("the analysis module does not touch the database either (the service does)",
          not any(m in text for m in ("app.models", "app.database", "SessionLocal", "db.commit")))
    service = (ROOT / "app" / "services" / "interview_analysis_service.py").read_text(encoding="utf-8")
    check("no second matching or CV pipeline: the analysis uses the Phase 4-6 builders",
          all(f in service for f in ("job_context(", "cv_for_candidate(", "matching_for_candidate("))
          and "match_skills" not in service and "analyse_cv_bytes" not in service)


# --------------------------------------------------------------------------
# HTTP + database
# --------------------------------------------------------------------------

def answer_call(bearer: str | None, body: dict):
    req = urllib.request.Request(BASE + "/ai-interview/agent/answers", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": bearer} if bearer else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, None


def plan_call(bearer: str) -> dict:
    req = urllib.request.Request(BASE + "/ai-interview/agent/plan", method="POST", data=b"",
                                 headers={"Authorization": bearer})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def rows_for(room: str):
    return p5.db_rows(
        """select a.sequence, a.question_id, a.question_number, a.question_text, a.answer_kind,
                  a.transcript, a.word_count, a.interview_id, a.answered_at, a.created_at
           from ai_interview_answers a join ai_interview_sessions s on s.id = a.session_id
           where s.room_name = :r order by a.sequence""", r=room)


def test_http() -> None:
    e2e.BASE = BASE
    p5.BASE = BASE
    R = e2e.request

    section("8. Setup: existing candidates, real interviews, one voice session each")
    tok_a = p5.fixture_login(p5.APPLICANT_ONE_CV)
    tok_b = p5.fixture_login(p5.APPLICANT_MANY_CVS)
    iv_a = e2e.ensure_ai_interview(tok_a)
    iv_b = e2e.ensure_ai_interview(tok_b)

    def session_for(token, interview_id):
        r = R("POST", "/ai-interview/session", token=token, json_body={"interview_id": interview_id})
        if r.ok:
            ROOMS.append(r.body["room_name"])
        return r

    s_a, s_b = session_for(tok_a, iv_a["interview_id"]), session_for(tok_b, iv_b["interview_id"])
    check("sessions issued", s_a.ok and s_b.ok, f"{s_a.status} {s_b.status}")
    room_a, room_b = s_a.body["room_name"], s_b.body["room_name"]
    # Phase 11.6.4: answers are accepted only for a session whose agent started.
    e2e.mark_session_started(room_a)
    e2e.mark_session_started(room_b)
    bearer_a, bearer_b = p5.agent_bearer(room_a), p5.agent_bearer(room_b)
    plan = plan_call(bearer_a)["questions"]
    check("the bank plan is available to the agent", len(plan) >= 3, str(len(plan)))

    def body(seq, number, text, kind="answer", **extra):
        return {"question_id": plan[number - 1]["id"], "question_number": number, "sequence": seq,
                "kind": kind, "transcript": text, "answered_at": utcnow().isoformat() + "Z", **extra}

    section("9. Answer creation, ownership and question association")
    exact = "I led the migration  to PostgreSQL — twice, in 2024.  Then I documented it. "
    status_, resp = answer_call(bearer_a, body(1, 1, exact))
    check("an accepted answer is stored -> 200, created", status_ == 200 and resp["created"] is True
          and resp["sequence"] == 1, str(resp))
    rows = rows_for(room_a)
    check("one row", len(rows) == 1)
    row = rows[0]
    check("stored against the ROOM's interview (from the binding, not the request)",
          row.interview_id == iv_a["interview_id"], f"{row.interview_id} vs {iv_a['interview_id']}")
    owner = p5.db_scalar("""select a.candidate_id from interviews i join applications a on a.id = i.application_id
                            where i.id = :i""", i=row.interview_id)
    me = p5.db_scalar("select c.id from users u join candidates c on c.user_id = u.id where u.email = :e",
                      e=p5.APPLICANT_ONE_CV)
    check("...whose application belongs to the applicant the session was issued to", owner == me)
    check("question id and number are the bank plan's", (row.question_id, row.question_number)
          == (plan[0]["id"], 1))
    bank_text = p5.db_scalar("select question_text from interview_questions where id = :i", i=plan[0]["id"])
    check("question text is copied from the Question Bank row", row.question_text == bank_text == plan[0]["question_text"])
    check("the transcript is stored EXACTLY (spacing, dash, trailing space)", row.transcript == exact,
          repr(row.transcript))
    check("word count is derived from it", row.word_count == len(exact.split()))
    check("timestamps are UTC and plausible", abs((row.created_at - utcnow()).total_seconds()) < 120
          and abs((row.answered_at - row.created_at).total_seconds()) < 120)

    status_, _ = answer_call(bearer_a, {**body(2, 1, "An answer."), "question_id": plan[1]["id"]})
    check("question id that is not the plan's question at that number -> 409", status_ == 409, str(status_))
    status_, _ = answer_call(bearer_a, {**body(2, 1, "An answer."), "question_number": len(plan) + 1})
    check("a question number beyond the plan -> 409", status_ == 409, str(status_))
    check("nothing was stored by either", len(rows_for(room_a)) == 1)

    section("10. Duplicate protection")
    status_, resp = answer_call(bearer_a, body(1, 1, exact))
    check("the same answer again (a retry) -> 200, created: false", status_ == 200 and resp["created"] is False)
    status_, _ = answer_call(bearer_a, body(1, 1, "A different, later text."))
    check("a DIFFERENT answer under a used sequence -> 409", status_ == 409, str(status_))
    status_, _ = answer_call(bearer_a, body(1, 2, exact))
    check("the same sequence for another question -> 409", status_ == 409, str(status_))
    check("still exactly one row, unchanged", [r.transcript for r in rows_for(room_a)] == [exact])

    section("11. Ordering")
    answer_call(bearer_b, body(3, 3, "Third, sent first."))
    answer_call(bearer_b, body(1, 1, "First, sent second."))
    answer_call(bearer_b, body(2, 2, "Second, sent last.", kind="short"))
    check("stored in answer order whatever the arrival order",
          [(r.sequence, r.question_number, r.transcript) for r in rows_for(room_b)]
          == [(1, 1, "First, sent second."), (2, 2, "Second, sent last."), (3, 3, "Third, sent first.")])
    check("room B's answers are on room B's interview only",
          {r.interview_id for r in rows_for(room_b)} == {iv_b["interview_id"]})

    section("12. Refused input - nothing can name another candidate or an interview")
    for field, value in (("candidate_id", me), ("interview_id", iv_b["interview_id"]),
                         ("application_id", 1), ("question_text", "An invented question?"),
                         ("room_name", room_b), ("score", 90)):
        status_, _ = answer_call(bearer_a, body(9, 1, "x y z", **{field: value}))
        check(f"body with {field} -> 422 (refused, not ignored)", status_ == 422, str(status_))
    for label, b in (("an empty transcript", body(9, 1, "   ")),
                     ("kind 'empty'", body(9, 1, "words here", kind="empty")),
                     ("sequence 0", body(0, 1, "words here"))):
        status_, _ = answer_call(bearer_a, b)
        check(f"{label} -> 422", status_ == 422, str(status_))
    check("nothing stored by any of them", len(rows_for(room_a)) == 1)

    section("13. Unauthorised access")
    check("no token -> 401", answer_call(None, body(5, 1, "x y"))[0] == 401)
    check("the applicant's SmartHR JWT -> 403", answer_call(f"Bearer {tok_a}", body(5, 1, "x y"))[0] == 403)
    check("the applicant's own LiveKit room token -> 403 (an applicant cannot submit answers directly)",
          answer_call(f"Bearer {s_a.body['participant_token']}", body(5, 1, "x y"))[0] == 403)
    check("applicant B's room token cannot write into A's interview either",
          answer_call(f"Bearer {s_b.body['participant_token']}", body(5, 1, "x y"))[0] == 403)
    check("agent token for an unbound room -> 404",
          answer_call(p5.agent_bearer("smarthr-ai-interview-" + secrets.token_hex(8)), body(5, 1, "x y"))[0] == 404)
    from app.ai.interview.agent_auth import mint_agent_token
    forged = mint_agent_token(p5.FAKE_KEY, "not-the-secret-" + secrets.token_hex(16), room_a)
    check("agent token signed with the wrong secret -> 403", answer_call(f"Bearer {forged}", body(5, 1, "x y"))[0] == 403)

    from app.services.interview_answer_service import answer_grace
    grace = answer_grace()
    from sqlalchemy import text
    from app.database import engine

    from app.services.interview_context_service import utc_to_local

    def set_expiry(room, when):
        # Phase 9: a session is only valid if it was started inside its
        # interview's window, so a session "started" in the past is one whose
        # interview was scheduled then (the fixture interview, test rows only).
        started = when - timedelta(minutes=10)
        with engine.begin() as conn:
            conn.execute(text("update ai_interview_sessions set expires_at = :e, created_at = :c where room_name = :r"),
                         {"e": when, "c": started, "r": room})
            conn.execute(text("update interviews set scheduled_at = :s where id = :i"),
                         {"s": utc_to_local(started).replace(microsecond=0), "i": iv_a["interview_id"]})

    set_expiry(room_a, utcnow() - grace + timedelta(seconds=60))
    status_, _ = answer_call(bearer_a, body(2, 2, "An answer after the join window closed."))
    check("after the JOIN window but inside the interview's run time -> accepted", status_ == 200, str(status_))
    set_expiry(room_a, utcnow() - grace - timedelta(seconds=60))
    status_, _ = answer_call(bearer_a, body(3, 3, "Far too late."))
    check("after the interview could possibly have ended -> 404", status_ == 404, str(status_))
    set_expiry(room_a, utcnow() + timedelta(minutes=10))
    status_, _ = answer_call(bearer_a, {"question_id": plan[2]["id"], "question_number": 3, "sequence": 3,
                                        "kind": "answer", "transcript": "No clock sent.",
                                        "answered_at": "2001-01-01T00:00:00Z"})
    last = rows_for(room_a)[-1]
    check("an implausible worker clock is replaced by the server's", status_ == 200
          and last.answered_at.year > 2001 and last.answered_at >= last.created_at - timedelta(seconds=5))

    e2e.ensure_staff_account(HR, 2)
    hr = e2e.login(HR)
    R("PATCH", f"/interviews/{iv_b['interview_id']}/status", token=hr, json_body={"status": "cancelled"})
    check("a cancelled interview's room takes no answers -> 404",
          answer_call(bearer_b, body(4, 4, "After cancellation."))[0] == 404)
    R("PATCH", f"/interviews/{iv_b['interview_id']}/status", token=hr, json_body={"status": "scheduled"})

    section("14. Review routes: Admin and HR only")
    tokens = {}
    for email, role in ((ADMIN, 1), (HR, 2), (MANAGER, 3), (EMPLOYEE, 4)):
        e2e.ensure_staff_account(email, role)
        tokens[role] = e2e.login(email)
    tokens[5] = tok_a
    path = f"/ai-interview/answers/{iv_a['interview_id']}"
    check("anonymous -> 401", R("GET", path).status == 401)
    for role, expected in ((1, 200), (2, 200), (3, 403), (4, 403), (5, 403)):
        check(f"role {role} -> {expected}", R("GET", path, token=tokens[role]).status == expected)
        check(f"role {role} analyse -> {expected}",
              R("POST", path + "/analyse", token=tokens[role]).status == expected)
    check("an unknown interview -> 404", R("GET", "/ai-interview/answers/999999999", token=tokens[2]).status == 404)

    view = R("GET", path, token=tokens[2]).body
    ours = [s for s in view["sessions"] if s["answers"]
            and s["session_id"] == p5.db_scalar("select id from ai_interview_sessions where room_name = :r", r=room_a)]
    answers = ours[0]["answers"] if ours else []
    check("the review lists this session's answers in order", [a["sequence"] for a in answers] == [1, 2, 3],
          str([a["sequence"] for a in answers]))
    check("each carries question, transcript and an analysis block",
          all({"question_text", "transcript", "question_number", "analysis"} <= set(a) for a in answers))
    check("labelled for review, not a decision", view["is_hiring_decision"] is False)
    check("no candidate PII in the review payload",
          not any(k in json.dumps(view) for k in ("@smarthr", "email", "phone", "full_name")))

    # Only THIS test's session: the interview is a shared fixture and can hold
    # real sessions from live runs (e.g. with completed gpt-4o analyses).
    own_session = p5.db_scalar("select id from ai_interview_sessions where room_name = :r", r=room_a)

    def own_answers():
        return [a for s in R("GET", path, token=tokens[2]).body["sessions"]
                if s["session_id"] == own_session for a in s["answers"]]

    deadline = time.time() + 30
    while time.time() < deadline:
        statuses = [a["analysis"]["status"] for a in own_answers()]
        if statuses and "pending" not in statuses:
            break
        time.sleep(0.5)
    analyses = [a["analysis"] for a in own_answers()]
    check("a new answer is analysed in the background; with no model it is recorded as failed "
          "(llm_not_configured), never faked", analyses and all(
              x["status"] == "failed" and x["error_code"] == "llm_not_configured" and x["result"] is None
              for x in analyses), str(analyses[:2]))
    r = R("POST", path + "/analyse", token=tokens[2])
    check("HR can re-run analysis; failed ones are retried", r.ok and r.body["attempted"] >= 3, str(r.body)[:200])

    section("15. Nothing about answers reaches LiveKit or the browser's session")
    from livekit import api
    claims = api.TokenVerifier(p5.FAKE_KEY, p5.FAKE_SECRET).verify(s_a.body["participant_token"])
    dispatch = claims.room_config.agents if claims.room_config else []
    check("the LiveKit token and dispatch carry no metadata",
          not claims.metadata and all(not d.metadata for d in dispatch))
    check("the session response carries nothing about answers",
          not any(k in s_a.raw for k in ("transcript", "answer", "analysis")))

    r = R("GET", "/openapi.json")
    check("openapi serves 128 paths (Phase 12 intelligence; Phase 11.5.3 analytics; Phase 7 adds /agent/answers, /answers/{id}, /answers/{id}/analyse, Phase 8 report, Phase 9 /agent/progress)",
          len(r.body.get("paths", {})) == 128, str(len(r.body.get("paths", {}))))


def test_end_to_end() -> None:
    section("16. Worker -> backend end to end: what was said is what is stored")
    os.environ.update({"LIVEKIT_URL": p5.FAKE_URL, "LIVEKIT_API_KEY": p5.FAKE_KEY,
                       "LIVEKIT_API_SECRET": p5.FAKE_SECRET, "SMARTHR_INTERVIEW_BACKEND_URL": BASE})
    from app.ai.interview.answer_client import AnswerSink
    from app.ai.interview.plan_client import parse_interview

    tok = p5.fixture_login(p5.APPLICANT_ONE_CV)
    iv = e2e.ensure_ai_interview(tok)
    r = e2e.request("POST", "/ai-interview/session", token=tok, json_body={"interview_id": iv["interview_id"]})
    room = r.body["room_name"]
    ROOMS.append(room)
    e2e.mark_session_started(room)          # Phase 11.6.4: a started session
    plan = parse_interview(plan_call(p5.agent_bearer(room)), room).questions

    said = {}

    async def scenario():
        sink = AnswerSink(room)
        m, s, c, a = _rig(plan, sink.submit)
        await c.run_opening()
        await _turn(a, "hmm")                                           # ignored
        await _turn(a, "I studied computer science and now I build ML services.")
        c.on_agent_state("thinking"); c.on_agent_state("speaking"); c.on_agent_state("listening")
        interrupted = FakeHandle()                                      # an interruption
        c.on_speech_created(interrupted)
        c._last_spoke_at = time.monotonic() + 1
        interrupted.finish(interrupted=True)
        await _turn(a, "At my last job I")                              # cut by a pause
        c.on_agent_state("thinking"); c.on_agent_state("listening")     # reply cancelled unheard
        await _turn(a, "rebuilt the forecasting pipeline after it failed.")
        c.on_agent_state("thinking"); c.on_agent_state("speaking"); c.on_agent_state("listening")
        await _turn(a, "Yes.")                                          # short: an answer, moves on
        c.on_agent_state("thinking"); c.on_agent_state("speaking"); c.on_agent_state("listening")
        await _turn(a, "I review code with my team every day and we pair on hard bugs.")
        c.on_agent_state("thinking"); c.on_agent_state("speaking"); c.on_agent_state("listening")
        await _turn(a, "I learn by building small projects in the evenings.")
        c.on_agent_state("thinking")                                    # session ends: reply never heard
        c.flush_answers()
        await sink.drain(15)
        said["sink"] = (sink.delivered, sink.refused, sink.undelivered)

    asyncio.run(scenario())
    check("every final answer delivered, none refused or lost", said["sink"] == ([1, 2, 3, 4, 5], [], []),
          str(said["sink"]))
    rows = rows_for(room)
    got = [(r.sequence, r.question_number, r.answer_kind, r.transcript) for r in rows]
    expected = [
        (1, 1, "answer", "I studied computer science and now I build ML services."),
        (2, 2, "answer", "At my last job I rebuilt the forecasting pipeline after it failed."),
        (3, 3, "short", "Yes."),
        (4, 4, "answer", "I review code with my team every day and we pair on hard bugs."),
        (5, 5, "answer", "I learn by building small projects in the evenings."),
    ]
    check("stored rows == what was accepted: order, question, kind, exact transcript", got == expected,
          "\n" + "\n".join(map(str, got)))
    check("the ignored filler and the interruption stored nothing", not any("hmm" in g[3] for g in got))
    check("the half cut by a pause did not become its own answer",
          not any(g[3] == "At my last job I" for g in got))
    check("each row's question is the bank's question at that number",
          all(r.question_id == plan[r.question_number - 1].id and r.question_text == plan[r.question_number - 1].text
              for r in rows))


def test_analysis_service(room: str) -> None:
    section("17. Analysis in process: the real contexts, the stored question and answer, the guards")
    from app.database import SessionLocal
    from app.models import AiInterviewAnswer
    from app.services import interview_analysis_service as svc, interview_cv_service as cvsvc
    from scripts.test_ai_interview_matching_context import FakeAnalysis

    parsed = p5.sample_parsed()
    original = cvsvc.analyse_cv_bytes
    cvsvc.analyse_cv_bytes = lambda *a, **k: FakeAnalysis(parsed)
    cvsvc.clear_cache()
    db = SessionLocal()
    try:
        answer_id = p5.db_scalar("""select a.id from ai_interview_answers a join ai_interview_sessions s
                                    on s.id = a.session_id where s.room_name = :r and a.sequence = 2""", r=room)
        answer = db.get(AiInterviewAnswer, answer_id)
        data = svc.build_input(db, answer)
        check("the model input is the stored question and the stored transcript",
              data.question == answer.question_text and data.transcript == answer.transcript)
        check("the Job Context is the interview's job (Phase 4 builder)",
              data.job and data.job["title"] == p5.db_scalar(
                  """select j.title from interviews i join applications a on a.id = i.application_id
                     join jobs j on j.id = a.job_id where i.id = :i""", i=answer.interview_id))
        check("the CV Context is the candidate's (Phase 5 builder, contact fields excluded)",
              data.cv and "Cedar Analytics" in json.dumps(data.cv) and "rana.haddad" not in json.dumps(data.cv))
        check("the Matching Context is Phase 6's result - skills and gaps, never the score",
              data.matching_available and not hasattr(data, "score") and "score" not in repr(data).lower())

        payload = json.loads(json.dumps(GOOD))
        payload["summary"] = ("The applicant described rebuilding a failed forecasting pipeline. "
                              "The applicant should be hired and would score 90%.")
        payload["evidence"] = [{"point": "Rebuilt a pipeline after a failure.",
                                "quote": "rebuilt the forecasting pipeline after it failed", "type": "example"},
                               {"point": "Managed 12 people.", "quote": "I managed twelve people", "type": "experience"}]
        payload["skills_mentioned"] = []
        payload["cv_relation"] = []
        fake = FakeProvider(payload)
        row = svc.analyse_answer(db, answer_id, force=True, provider=fake)
        sent = fake.calls[0]["messages"][0]["content"]
        check("GPT-4o was shown the actual question and the actual transcript",
              answer.question_text in sent and answer.transcript in sent)
        check("...and no match score", "score" not in sent.lower())
        check("stored: completed, by the model named", row.status == "completed" and row.model == "fake-gpt-4o")
        check("stored summary has no verdict and no score",
              row.analysis["summary"] == "The applicant described rebuilding a failed forecasting pipeline.",
              row.analysis["summary"])
        check("stored evidence has only what the answer contains", [e["quote"] for e in row.analysis["evidence"]]
              == ["rebuilt the forecasting pipeline after it failed"])

        again = svc.analyse_answer(db, answer_id, provider=FakeProvider(GOOD))
        check("a completed analysis is not silently replaced (stable)", again.id == row.id
              and again.analysis["summary"] == row.analysis["summary"])
        failed_row = svc.analyse_answer(db, answer_id, force=True, provider=FakeProvider(text="nope"))
        check("a failed re-run is recorded as failed with its code, no result",
              failed_row.status == "failed" and failed_row.error_code == "malformed_response"
              and failed_row.analysis is None)
        count = p5.db_scalar("select count(*) from ai_interview_answer_analyses where answer_id = :a", a=answer_id)
        check("one analysis row per answer, whatever the number of runs", count == 1)
        check("the answer itself was never changed by analysis",
              p5.db_scalar("select transcript from ai_interview_answers where id = :a", a=answer_id)
              == "At my last job I rebuilt the forecasting pipeline after it failed.")
    finally:
        db.close()
        cvsvc.analyse_cv_bytes = original
        cvsvc.clear_cache()


def main() -> int:
    print("SmartHR - AI Interview Phase 7 Answers & Analysis tests")
    test_progress()
    test_controller()
    test_client()
    test_analysis_schema()
    test_analysis_prompt()
    test_analysis_validation()
    test_containment()
    p5.ROOMS = ROOMS
    try:
        with p5.Server(PORT, False):
            test_http()
            test_end_to_end()
            test_analysis_service(ROOMS[-1])
    finally:
        print(f"\n  cleanup: removed {p5.cleanup()} session binding(s) (answers and analyses cascade)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
