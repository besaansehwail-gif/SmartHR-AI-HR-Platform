"""AI Interview - Phase 4 Job Context tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_job_context

Two parts:

* **offline** - the worker side: the Job Context is validated rather than
  trusted, it reaches GPT-4o only as a delimited block of the instructions, the
  welcome names the role, and with a job in the prompt GPT-4o is still not the
  source of MAIN questions (an invented, job-specific question is dropped and
  the Question Bank's next question is appended verbatim).
* **HTTP** - launches its own backend on port 8046 with THROWAWAY LiveKit
  credentials (the environment outranks `.env.local`), then proves
  interview -> application -> job resolution, ownership (another applicant's
  interview is a 404, indistinguishable from a missing one), that the browser
  cannot name a job, that nothing about the job reaches LiveKit, and that the
  agent's context endpoint returns exactly the trimmed Job Context for the
  room's own interview - and nothing for an unbound, expired or cancelled one.

The interviews use an EXISTING job ("DEMO - AI Engineering Intern" for
applicant A, "Data Analyst" for B) through the real apply + schedule
endpoints (`test_helpers.ensure_ai_interview`), so no job rows are created.
The session bindings this suite creates are deleted at the end; the fixture
accounts, applications and interviews are kept for re-use, like every other
`@smarthr.test` fixture.
"""

import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402

PORT = 8046
BASE = f"http://127.0.0.1:{PORT}"
FAKE_URL = "wss://smarthr-test.invalid"
FAKE_KEY = "APItest" + secrets.token_hex(4)
FAKE_SECRET = secrets.token_urlsafe(32)

APPLICANT_A = "jobctx.applicant.a@smarthr.test"
APPLICANT_B = "jobctx.applicant.b@smarthr.test"
JOB_A = "DEMO - AI Engineering Intern"
JOB_B = "Data Analyst"
STAFF = {1: "jobctx.admin@smarthr.test", 3: "jobctx.manager@smarthr.test",
         4: "jobctx.employee@smarthr.test"}

#: Fields that must never appear in the agent's Job Context.
INTERNAL_FIELDS = ("created_by", "status", "location", "deadline", "applications_count",
                   "pipeline_counts", "notes", "interviewer", "candidate", "email",
                   "application_id", "interview_id", "evaluation_focus")

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


# --------------------------------------------------------------------------
# Offline: the worker side
# --------------------------------------------------------------------------

JOB_PAYLOAD = {
    "job_id": 8,
    "title": "DEMO - AI Engineering Intern",
    "department": "Engineering",
    "employment_type": "internship",
    "description": "Six-month internship working alongside the AI team on model integration.",
    "requirements": ["Python", "Machine Learning", "SQL", "Git"],
}


def test_parse_job() -> None:
    section("1. Worker validates the Job Context instead of trusting it")
    from app.ai.interview.job_context import JobContext, JobContextInvalid, parse_job
    from app.ai.interview.plan_client import PlanUnavailable, parse_interview

    job = parse_job(dict(JOB_PAYLOAD, created_by=278, salary="secret"))
    check("a valid job parses", isinstance(job, JobContext) and job.job_id == 8
          and job.title == JOB_PAYLOAD["title"] and job.requirements == ("Python", "Machine Learning", "SQL", "Git"))
    check("unknown keys are dropped, not carried into the prompt",
          not hasattr(job, "created_by") and "278" not in repr(job) and "secret" not in repr(job))

    bad = {
        "no job at all": None,
        "no id": {k: v for k, v in JOB_PAYLOAD.items() if k != "job_id"},
        "no title": dict(JOB_PAYLOAD, title="  "),
        "title not text": dict(JOB_PAYLOAD, title=42),
        "title too long": dict(JOB_PAYLOAD, title="x" * 151),
        "requirements not a list": dict(JOB_PAYLOAD, requirements="Python, SQL"),
        "too many requirements": dict(JOB_PAYLOAD, requirements=["x"] * 21),
        "description too long": dict(JOB_PAYLOAD, description="x" * 2001),
    }
    for label, payload in bad.items():
        try:
            parse_job(payload)
            check(f"refused: {label}", False)
        except JobContextInvalid:
            check(f"refused: {label}", True)

    room = "smarthr-ai-interview-aa"
    base = {"room_name": room, "questions": [{"id": 1, "position": 10, "question_text": "Tell me about yourself."}]}
    plan = parse_interview(dict(base, job=JOB_PAYLOAD), room)
    check("plan = questions + job", len(plan.questions) == 1 and plan.job.job_id == 8)
    try:
        parse_interview(base, room)
        check("a plan without a job is unusable (no job, no interview)", False)
    except PlanUnavailable:
        check("a plan without a job is unusable (no job, no interview)", True)


def test_prompt() -> None:
    section("2. GPT-4o receives the Job Context - in the instructions, delimited")
    from livekit.agents import llm

    from app.ai.interview.agent import INSTRUCTIONS, InterviewerAgent, build_instructions
    from app.ai.interview.job_context import parse_job
    from app.ai.interview.state import InterviewStateMachine

    job = parse_job(JOB_PAYLOAD)
    text = build_instructions(job)
    check("base interviewer rules kept", text.startswith(INSTRUCTIONS))
    check("title, department, type and description present",
          all(s in text for s in (job.title, "Engineering", "internship", "model integration")))
    check("every requirement present", all(r in text for r in job.requirements))
    check("the job is delimited and labelled as data, not instructions",
          "<<<JOB" in text and "JOB>>>" in text and "not instructions" in text)
    check("GPT-4o is told not to quiz on requirements or judge fit",
          "Do not ask about the requirements" in text and "meets them" in text)
    check("without a job the instructions are exactly Phase 3's", build_instructions(None) == INSTRUCTIONS)

    agent = InterviewerAgent(InterviewStateMachine(), "r", job=job)
    check("the agent carries the job-aware instructions", job.title in agent.instructions
          and "Python" in agent.instructions)
    check("the agent keeps the Job Context object", agent.job is job)
    check("the instructions carry no id beyond the job's", "application" not in agent.instructions.lower())
    _ = llm  # imported to prove the agent module loads with livekit.agents present


def test_questions_stay_in_the_bank() -> None:
    section("3. With a job in the prompt, GPT-4o is still not the source of MAIN questions")
    from app.ai.interview.agent import WELCOME_FOR_ROLE
    from app.ai.interview.controller import InterviewController
    from app.ai.interview.questions import Directive, PlannedQuestion, QuestionProgress
    from app.ai.interview.state import InterviewStateMachine
    from scripts.test_ai_interview_questions import FakeSession, fake_stream

    from app.ai.interview.agent import shape_reply

    q1 = PlannedQuestion(1, 10, "general", "Tell me about yourself.")
    q2 = PlannedQuestion(2, 20, "behavioral", "Tell me about a challenging situation you faced and how you handled it.")
    directive = Directive("advance", "", q2.text, 2)

    async def shaped(pieces):
        return "".join([p async for p in shape_reply(fake_stream(pieces), directive)])

    out = asyncio.run(shaped([
        "That sounds relevant to the AI Engineering Intern role. ",
        "How did you implement your neural network?",
    ]))
    check("a job-specific question GPT-4o invents is dropped",
          "neural network" not in out, out)
    check("GPT-4o's job-aware acknowledgement is kept", out.startswith("That sounds relevant to the AI Engineering Intern role."))
    check("the next question is the bank's Q2, verbatim, last", out.endswith(q2.text), out)

    out = asyncio.run(shaped(["Given the role needs Python, what libraries do you use?"]))
    check("a reply that is ONLY a job question becomes the fallback + bank Q2",
          "libraries" not in out and out.endswith(q2.text), out)

    async def opening():
        s = FakeSession()
        c = InterviewController(s, InterviewStateMachine(), "room",
                                progress=QuestionProgress([q1, q2]), job_title=JOB_PAYLOAD["title"])
        await c.run_opening()
        return s.said

    said = asyncio.run(opening())
    check("the welcome names the role (code, not GPT-4o)",
          said[0] == WELCOME_FOR_ROLE.format(title=JOB_PAYLOAD["title"], count=2), str(said))
    check("Q1 is still the bank's text, verbatim", said[1] == q1.text, str(said))


def test_containment() -> None:
    section("4. The worker still never touches the database")
    import ast
    for name in ("job_context.py", "plan_client.py", "agent.py", "controller.py", "worker.py"):
        path = ROOT / "app" / "ai" / "interview" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        bad = [m for m in mods if m.startswith(("app.models", "app.database", "sqlalchemy", "app.services"))]
        check(f"{name}: no database / service import", not bad, ", ".join(bad))


# --------------------------------------------------------------------------
# HTTP: resolution, ownership, the agent endpoint
# --------------------------------------------------------------------------

class Server:
    def __init__(self, port: int):
        self.port, self._p = port, None

    def __enter__(self):
        self._p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "LIVEKIT_URL": FAKE_URL, "LIVEKIT_API_KEY": FAKE_KEY,
                 "LIVEKIT_API_SECRET": FAKE_SECRET,
                 # Phase 5 warms a CV parse on every session; this suite does
                 # not test CVs, so the model is genuinely absent (not empty -
                 # an empty value falls through to .env and the real key).
                 "SMARTHR_LLM_PROVIDER": "none"})
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=2):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)
        raise SystemExit("test server did not start")

    def __exit__(self, *_):
        self._p.terminate()
        try:
            self._p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._p.kill()


ROOMS: list[str] = []


def plan_call(bearer: str | None):
    req = urllib.request.Request(BASE + "/ai-interview/agent/plan", method="POST", data=b"",
                                 headers={"Authorization": bearer} if bearer else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, None


def agent_bearer(room: str) -> str:
    from app.ai.interview.agent_auth import mint_agent_token
    return f"Bearer {mint_agent_token(FAKE_KEY, FAKE_SECRET, room)}"


def db_exec(sql: str, **params):
    from sqlalchemy import text

    from app.database import engine
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
        return result.fetchall() if result.returns_rows else None


def expected_context(job_title: str) -> dict:
    from app.database import SessionLocal
    from app.models import Job
    from app.services.interview_context_service import job_context
    db = SessionLocal()
    try:
        return job_context(db.query(Job).filter(Job.title == job_title).one(), db)
    finally:
        db.close()


def test_http() -> None:
    e2e.BASE = BASE
    R = e2e.request

    section("5. Setup: two applicants, each with a real interview for an existing job")
    tok_a = e2e.register_applicant(APPLICANT_A, "Job Context A")
    tok_b = e2e.register_applicant(APPLICANT_B, "Job Context B")
    jobs_before = db_exec("select count(*) from jobs")[0][0]
    iv_a = e2e.ensure_ai_interview(tok_a, JOB_A)
    iv_b = e2e.ensure_ai_interview(tok_b, JOB_B)
    check("A's interview is for the AI Engineering Intern job", iv_a["job_title"] == JOB_A, str(iv_a))
    check("B's interview is for the Data Analyst job", iv_b["job_title"] == JOB_B, str(iv_b))
    check("no job row was created for the test", db_exec("select count(*) from jobs")[0][0] == jobs_before)
    staff = {}
    for role, email in STAFF.items():
        e2e.ensure_staff_account(email, role)
        staff[role] = e2e.login(email)
    staff[2] = e2e.login(e2e.AI_INTERVIEW_HR)

    section("6. Interview -> application -> job resolution")
    listed = R("GET", "/ai-interview/interviews", token=tok_a)
    ids = [i["interview_id"] for i in listed.body.get("interviews", [])] if listed.ok else []
    check("A lists their interview", listed.ok and iv_a["interview_id"] in ids, repr(listed))
    check("A does not see B's interview", iv_b["interview_id"] not in ids)
    row = next((i for i in listed.body["interviews"] if i["interview_id"] == iv_a["interview_id"]), {})
    check("the listing carries the job title resolved from the application", row.get("job_title") == JOB_A)
    check("the listing carries only id, title, time, status, the start window, test marker and "
          "attempts_exhausted",
          set(row) == {"interview_id", "job_title", "scheduled_at", "status", "opens_at", "closes_at",
                       "is_test", "attempts_exhausted"}
          and row.get("is_test") is False,
          str(sorted(row)))
    truth = db_exec("""select j.title from interviews i join applications a on a.id = i.application_id
                       join jobs j on j.id = a.job_id where i.id = :i""", i=iv_a["interview_id"])[0][0]
    check("...which is what interviews -> applications -> jobs says in the database", truth == JOB_A)

    section("7. Ownership and RBAC")
    r = R("GET", "/ai-interview/interviews")
    check("anonymous list -> 401", r.status == 401, repr(r))
    for role in (1, 2, 3, 4):
        r = R("GET", "/ai-interview/interviews", token=staff[role])
        check(f"role {role} cannot list applicant interviews -> 403", r.status == 403, repr(r))
        r = R("POST", "/ai-interview/session", token=staff[role], json_body={"interview_id": iv_a["interview_id"]})
        check(f"role {role} cannot open an applicant session -> 403", r.status == 403, repr(r))

    r = R("POST", "/ai-interview/session", token=tok_b, json_body={"interview_id": iv_a["interview_id"]})
    check("B cannot open A's interview -> 404", r.status == 404, repr(r))
    missing = R("POST", "/ai-interview/session", token=tok_b, json_body={"interview_id": 999999999})
    check("...and that 404 is identical to a non-existent interview's",
          r.status == missing.status and r.body == missing.body, f"{r.body} vs {missing.body}")
    r = R("POST", "/ai-interview/session", token=tok_a, json_body={})
    check("no interview_id -> 422", r.status == 422, repr(r))
    r = R("POST", "/ai-interview/session", token=tok_a,
          json_body={"interview_id": iv_a["interview_id"], "job_id": iv_b["job_id"]})
    check("the browser cannot name a job (extra field job_id -> 422)", r.status == 422, repr(r))
    r = R("POST", "/ai-interview/session", token=tok_a, json_body={"interview_id": "x"})
    check("non-integer interview_id -> 422", r.status == 422, repr(r))

    section("8. A's session: bound server-side, nothing about the job in LiveKit")
    sess = R("POST", "/ai-interview/session", token=tok_a, json_body={"interview_id": iv_a["interview_id"]})
    check("A opens their own interview -> 200", sess.ok, repr(sess))
    body = sess.body if sess.ok else {}
    room = body.get("room_name", "")
    ROOMS.append(room)
    check("the response names the job title the backend resolved",
          body.get("interview") == {"interview_id": iv_a["interview_id"], "job_title": JOB_A}, str(body.get("interview")))
    check("the response carries no description, requirements or application data",
          all(k not in sess.raw for k in ("requirements", "description", "application_id", "pipeline")))
    binding = db_exec("select interview_id, candidate_id, expires_at > created_at from ai_interview_sessions "
                      "where room_name = :r", r=room)
    cand_a = db_exec("""select a.candidate_id from interviews i join applications a on a.id = i.application_id
                        where i.id = :i""", i=iv_a["interview_id"])[0][0]
    check("the room is bound to A's interview and A's candidate row",
          binding and binding[0][0] == iv_a["interview_id"] and binding[0][1] == cand_a and binding[0][2], str(binding))

    from livekit import api
    claims = api.TokenVerifier(FAKE_KEY, FAKE_SECRET).verify(body.get("participant_token", ""))
    dispatch = claims.room_config.agents if claims.room_config else []
    everything = f"{claims.metadata!r}{claims.name!r}{claims.identity!r}{[d.metadata for d in dispatch]!r}"
    check("LiveKit token metadata is empty", not claims.metadata)
    check("agent dispatch metadata is empty", all(not d.metadata for d in dispatch))
    check("no job title, job id or interview id anywhere in the LiveKit token",
          JOB_A not in everything and "Engineering" not in everything
          and str(iv_a["interview_id"]) not in everything.replace(claims.identity, ""), everything)

    section("9. The agent's context endpoint: the room's own job, trimmed")
    status_, plan = plan_call(agent_bearer(room))
    check("agent token for A's room -> 200", status_ == 200, str(status_))
    plan = plan or {}
    job = plan.get("job") or {}
    check("the plan echoes the room", plan.get("room_name") == room)
    check("the job is A's job (resolved from the binding, not asked for)", job.get("title") == JOB_A, str(job))
    check("exactly the Job Context fields",
          set(job) == {"job_id", "title", "department", "employment_type", "description", "requirements"},
          str(sorted(job)))
    check("values are the database's, through job_context()", job == expected_context(JOB_A),
          f"{job} vs {expected_context(JOB_A)}")
    check("requirements are the posting's own phrases",
          job.get("requirements") == ["Python", "Machine Learning", "SQL", "Git"], str(job.get("requirements")))
    leaked = [f for f in INTERNAL_FIELDS if f in json.dumps(job)]
    check("no internal / candidate / application fields in the Job Context", not leaked, str(leaked))
    check("no applicant name or email anywhere in the plan",
          APPLICANT_A not in json.dumps(plan) and "Job Context A" not in json.dumps(plan))
    check("the Question Bank questions are still the plan's questions",
          plan.get("total") == len(plan.get("questions", [])) > 0)

    sess_b = R("POST", "/ai-interview/session", token=tok_b, json_body={"interview_id": iv_b["interview_id"]})
    ROOMS.append(sess_b.body.get("room_name", "") if sess_b.ok else "")
    _, plan_b = plan_call(agent_bearer(sess_b.body["room_name"])) if sess_b.ok else (0, {})
    check("B's room resolves to B's job - each room gets its own context",
          (plan_b or {}).get("job", {}).get("title") == JOB_B, str((plan_b or {}).get("job")))
    check("...with the same Question Bank questions (the bank is not per-job yet)",
          (plan_b or {}).get("questions") == plan.get("questions"))

    section("10. The agent endpoint refuses what it cannot resolve")
    unbound = "smarthr-ai-interview-" + secrets.token_hex(8)
    check("an unbound room -> 404 (the worker cannot pick an interview)", plan_call(agent_bearer(unbound))[0] == 404)
    check("an applicant's own room token -> 403",
          plan_call(f"Bearer {body.get('participant_token', '')}")[0] == 403)
    check("no token -> 401", plan_call(None)[0] == 401)

    exp = R("POST", "/ai-interview/session", token=tok_a, json_body={"interview_id": iv_a["interview_id"]})
    exp_room = exp.body["room_name"]
    ROOMS.append(exp_room)
    # The service writes and compares UTC (datetime.utcnow); Postgres now() is
    # the server's LOCAL time, so the row is aged with Python's UTC clock.
    from datetime import datetime, timedelta
    utc_now = datetime.utcnow()
    db_exec("update ai_interview_sessions set created_at = :c, expires_at = :e where room_name = :r",
            c=utc_now - timedelta(hours=2), e=utc_now - timedelta(seconds=1), r=exp_room)
    check("an expired binding -> 404", plan_call(agent_bearer(exp_room))[0] == 404)

    # Cancel A's interview: the live rows are re-read on every lookup.
    hr = staff[2]
    r = R("PATCH", f"/interviews/{iv_a['interview_id']}/status", token=hr, json_body={"status": "cancelled"})
    check("(HR cancels A's interview)", r.ok, repr(r))
    check("a cancelled interview's room -> 404 (re-checked, not remembered)",
          plan_call(agent_bearer(room))[0] == 404)
    r = R("POST", "/ai-interview/session", token=tok_a, json_body={"interview_id": iv_a["interview_id"]})
    check("a cancelled interview cannot start a session -> 404", r.status == 404, repr(r))
    listed = R("GET", "/ai-interview/interviews", token=tok_a).body.get("interviews", [])
    check("...and is no longer listed", iv_a["interview_id"] not in [i["interview_id"] for i in listed])
    r = R("PATCH", f"/interviews/{iv_a['interview_id']}/status", token=hr, json_body={"status": "scheduled"})
    check("(HR re-schedules it; the fixture is left usable)", r.ok, repr(r))
    check("the same room resolves again once the interview is scheduled",
          plan_call(agent_bearer(room))[0] == 200)

    r = R("GET", "/openapi.json")
    paths = r.body.get("paths", {}) if isinstance(r.body, dict) else {}
    check("openapi serves 128 paths (Phase 12 intelligence; Phase 11.5.3 analytics; Phase 4 adds /interviews, Phase 5 /agent/cv, Phase 6 /agent/matching, Phase 7 three, Phase 8 report, Phase 9 progress)", len(paths) == 128, str(len(paths)))


def cleanup() -> int:
    rooms = [r for r in ROOMS if r]
    if not rooms:
        return 0
    from sqlalchemy import text

    from app.database import engine
    with engine.begin() as conn:
        return conn.execute(text("delete from ai_interview_sessions where room_name = any(:r)"),
                            {"r": rooms}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 4 Job Context tests")
    test_parse_job()
    test_prompt()
    test_questions_stay_in_the_bank()
    test_containment()
    try:
        with Server(PORT):
            test_http()
    finally:
        print(f"\n  cleanup: removed {cleanup()} session binding(s)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
