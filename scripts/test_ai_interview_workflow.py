"""AI Interview - Phase 9 workflow controls tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_workflow     # no model, no LiveKit

The three rules, each checked in process and over HTTP:

* **HR approval** - an AI Interview starts only for an application at the
  `interview` stage; moving it away closes the open room too (agent calls 404).
* **Start window** - 15 min before to 30 min after `scheduled_at` by default
  (`SMARTHR_INTERVIEW_EARLY_MINUTES` / `_LATE_MINUTES`); outside it the start
  is a 409 naming the time, and a room started before a reschedule is closed.
* **Status** - the agent's reports move `interviews.status`: started ->
  in_progress, completed -> completed (never startable again), ended ->
  scheduled; opening the page or a refused start changes nothing; a second
  start while one runs is refused; only the newest room may report.

Plus the worker's side: when the controller counts an interview as completed,
and the progress client against the real endpoint.

Uses the EXISTING fixture applicant applicant10 and its fixture interview
(`test_helpers.ensure_ai_interview`, reused - rescheduled to now). Its own
server on port 8052 with throwaway LiveKit credentials and
`SMARTHR_LLM_PROVIDER=none`. Session bindings created here are deleted at the
end, and the fixture interview is left scheduled for now.
"""

import ast
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_ai_interview_cv_context as p5  # noqa: E402
from scripts import test_helpers as e2e  # noqa: E402

PORT = 8052
BASE = f"http://127.0.0.1:{PORT}"
ROOMS: list[str] = []

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


# -- 1-2. In process: configuration and the one eligibility rule -------------------

def test_window_settings() -> None:
    section("1. The start window is configuration, not a constant")
    from app.ai.interview.config import interview_window

    saved = {k: os.environ.pop(k, None) for k in ("SMARTHR_INTERVIEW_EARLY_MINUTES",
                                                   "SMARTHR_INTERVIEW_LATE_MINUTES")}
    try:
        w = interview_window(local_file=None)
        check("default: 15 minutes before, 30 after", (w.early_minutes, w.late_minutes) == (15, 30), str(w))
        os.environ["SMARTHR_INTERVIEW_EARLY_MINUTES"] = "5"
        os.environ["SMARTHR_INTERVIEW_LATE_MINUTES"] = "60"
        w = interview_window(local_file=None)
        check("environment overrides both", (w.early_minutes, w.late_minutes) == (5, 60), str(w))
        os.environ["SMARTHR_INTERVIEW_EARLY_MINUTES"] = "0"
        check("0 is allowed (no early start)", interview_window(local_file=None).early_minutes == 0)
        os.environ["SMARTHR_INTERVIEW_EARLY_MINUTES"] = "-3"
        os.environ["SMARTHR_INTERVIEW_LATE_MINUTES"] = "soon"
        w = interview_window(local_file=None)
        check("negative / non-numeric fall back to the defaults",
              (w.early_minutes, w.late_minutes) == (15, 30), str(w))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_eligibility_rule() -> None:
    section("2. ineligibility(): status, HR approval, window - in that order")
    from app.models import Application, Interview, Job
    from app.services import interview_context_service as ctx

    at = datetime(2026, 10, 5, 9, 0)

    def verdict(status="scheduled", stage="interview", when=at, now=at):
        return ctx.ineligibility(Interview(status=status, scheduled_at=when), Application(status=stage), now)

    check("scheduled, stage interview, at the time -> eligible", verdict() is None)
    check("in_progress is eligible (the running interview's own calls)", verdict("in_progress") is None)
    check("completed -> completed (cannot be started again)", verdict("completed") == ctx.COMPLETED)
    check("cancelled -> not open", verdict("cancelled") == ctx.NOT_OPEN)
    for stage in ("applied", "screening", "shortlisted", "assessment", "offer", "hired", "rejected"):
        check(f"stage {stage} -> not approved", verdict(stage=stage) == ctx.NOT_APPROVED)
    check("stage written in another case ('Interview') still counts as approved",
          verdict(stage="Interview") is None)
    check("status is checked before stage (completed + rejected -> completed)",
          verdict("completed", "rejected") == ctx.COMPLETED)
    check("stage is checked before time (applied + too early -> not approved)",
          verdict(stage="applied", now=at - timedelta(hours=2)) == ctx.NOT_APPROVED)
    check("16 min early -> too early", verdict(now=at - timedelta(minutes=16)) == ctx.TOO_EARLY)
    check("exactly 15 min early -> open", verdict(now=at - timedelta(minutes=15)) is None)
    check("exactly 30 min late -> open", verdict(now=at + timedelta(minutes=30)) is None)
    check("30 min 1 s late -> too late", verdict(now=at + timedelta(minutes=30, seconds=1)) == ctx.TOO_LATE)
    opens, closes = ctx.start_window(Interview(status="scheduled", scheduled_at=at))
    check("start_window() = (-15 min, +30 min)",
          (opens, closes) == (at - timedelta(minutes=15), at + timedelta(minutes=30)), f"{opens} {closes}")
    stamp = datetime.utcnow()
    check("a UTC session time is compared on the local clock",
          abs((ctx.utc_to_local(stamp) - datetime.now()).total_seconds()) < 5)

    section("3. Permanent development test interview stays reusable and isolated")
    test_location = ctx.DEVELOPMENT_TEST_INTERVIEW_LOCATION
    test_interview = Interview(status="TEST", scheduled_at=at, location=test_location)
    check("the exact fixture marker is recognized in development",
          ctx.is_development_test_interview(test_interview))
    check("TEST, scheduled, and in_progress states are startable outside normal stage/time rules",
          all(ctx.ineligibility(
              Interview(status=state, scheduled_at=at, location=test_location),
              Application(status="screening"),
              at + timedelta(days=30),
          ) is None for state in ("TEST", "scheduled", "in_progress")))
    check("completed test interview remains terminal until Start explicitly reopens it",
          ctx.ineligibility(
              Interview(status="completed", scheduled_at=at, location=test_location),
              Application(status="screening"),
              at,
          ) == ctx.COMPLETED)
    test_listing = ctx.interview_summary(test_interview, Job(title="Data Analyst"))
    check("the applicant listing labels the fixture and omits schedule-window values",
          test_listing["status"] == "test" and test_listing["is_test"] is True
          and test_listing["scheduled_at"] is None
          and test_listing["opens_at"] is None and test_listing["closes_at"] is None)

    saved_env = os.environ.get("SMARTHR_ENV")
    try:
        os.environ["SMARTHR_ENV"] = "production"
        check("the permanent-test marker is ignored in production",
              not ctx.is_development_test_interview(test_interview)
              and ctx.ineligibility(test_interview, Application(status="interview"), at) == ctx.NOT_OPEN)
    finally:
        if saved_env is None:
            os.environ.pop("SMARTHR_ENV", None)
        else:
            os.environ["SMARTHR_ENV"] = saved_env


# -- HTTP helpers -----------------------------------------------------------------------

def agent_call(path: str, room: str | None, body: dict | None = None, bearer: str | None = None):
    headers = {"Content-Type": "application/json"}
    if bearer or room:
        headers["Authorization"] = bearer or p5.agent_bearer(room)
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(BASE + path, method="POST", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read())
        except Exception:
            return err.code, None


def progress(room: str, event: str):
    return agent_call("/ai-interview/agent/progress", room, {"event": event})


def plan_status(room: str) -> int:
    return agent_call("/ai-interview/agent/plan", room)[0]


def db_write(sql: str, **params) -> int:
    from sqlalchemy import text

    from app.database import engine
    with engine.begin() as conn:
        return conn.execute(text(sql), params).rowcount


def iv_status(interview_id: int) -> str:
    return p5.db_scalar("select status from interviews where id = :i", i=interview_id)


def test_http() -> None:
    e2e.BASE = BASE
    p5.BASE = BASE
    R = e2e.request

    tok = p5.fixture_login(p5.APPLICANT_MANY_CVS)
    fixture = e2e.ensure_ai_interview(tok)
    iv, app_id = fixture["interview_id"], fixture["application_id"]
    e2e.ensure_staff_account(e2e.AI_INTERVIEW_HR, 2)
    hr = e2e.login(e2e.AI_INTERVIEW_HR)

    def start():
        r = R("POST", "/ai-interview/session", token=tok, json_body={"interview_id": iv})
        if r.ok:
            ROOMS.append(r.body["room_name"])
        return r

    def listed() -> bool:
        rows = R("GET", "/ai-interview/interviews", token=tok).body["interviews"]
        return any(i["interview_id"] == iv for i in rows)

    def set_stage(stage: str) -> None:
        r = R("PATCH", f"/applications/{app_id}/status", token=hr, json_body={"status": stage})
        assert r.ok, r

    def reschedule(at: datetime) -> None:
        r = R("PUT", f"/interviews/{iv}", token=hr, json_body={
            "application_id": app_id, "scheduled_at": at.replace(microsecond=0).isoformat(),
            "location": e2e.AI_INTERVIEW_LOCATION, "status": "scheduled"})
        assert r.ok, r

    section("3. HR approval gate: the application must be at the interview stage")
    check("fixture: HR-approved, scheduled now -> listed", listed())
    s1 = start()
    check("start -> 200", s1.ok, repr(s1))
    room1 = s1.body["room_name"]
    check("the agent may fetch the plan", plan_status(room1) == 200)
    check("creating a session changes no status (still scheduled)", iv_status(iv) == "scheduled")

    set_stage("screening")
    check("stage screening -> no longer listed", not listed())
    r = start()
    check("stage screening -> start refused 409 not_approved",
          r.status == 409 and "interview stage" in (r.body or {}).get("detail", ""), repr(r))
    check("...and the OPEN room is closed too: plan -> 404", plan_status(room1) == 404)
    check("...CV -> 404", agent_call("/ai-interview/agent/cv", room1)[0] == 404)
    check("...matching -> 404", agent_call("/ai-interview/agent/matching", room1)[0] == 404)
    check("...progress started -> 404", progress(room1, "started")[0] == 404)
    set_stage("rejected")
    check("stage rejected -> start refused 409", start().status == 409)
    check("refused starts changed no status", iv_status(iv) == "scheduled")
    set_stage("interview")
    check("back at the interview stage -> listed again and the room reopens",
          listed() and plan_status(room1) == 200)

    section("4. Start window around scheduled_at (default -15 / +30 minutes)")
    now = datetime.now()
    reschedule(now + timedelta(minutes=20))
    check("20 min ahead -> still listed (upcoming)", listed())
    r = start()
    detail = (r.body or {}).get("detail", "")
    opens = (now + timedelta(minutes=5)).strftime("%H:%M")
    check("20 min ahead -> 409 too early, naming when it opens",
          r.status == 409 and "opens at" in detail and opens in detail, f"{r.status} {detail}")
    check("a room started before the reschedule is closed (plan -> 404)", plan_status(room1) == 404)
    reschedule(now + timedelta(minutes=14))
    r = start()
    check("14 min ahead -> inside the window -> 200", r.ok, repr(r))
    reschedule(now - timedelta(minutes=29))
    r = start()
    check("29 min ago -> inside the window -> 200", r.ok, repr(r))
    reschedule(now - timedelta(minutes=31))
    r = start()
    detail = (r.body or {}).get("detail", "")
    check("31 min ago -> 409 too late, naming when it closed",
          r.status == 409 and "ended at" in detail, f"{r.status} {detail}")
    check("window refusals changed no status", iv_status(iv) == "scheduled")
    reschedule(datetime.now())

    section("5. Status follows the agent: started / ended / completed")
    audit = lambda: p5.db_scalar(  # noqa: E731
        "select count(*) from audit_logs where entity_type = 'Interview' and entity_id = :i "
        "and action = 'STATUS_CHANGE' and user_id is null", i=iv)
    audit0 = audit()
    R("GET", "/ai-interview/interviews", token=tok)
    check("opening the page (listing) changes nothing", iv_status(iv) == "scheduled")
    sa = start()
    room_a = sa.body["room_name"]
    check("session created, agent not joined -> still scheduled", iv_status(iv) == "scheduled")
    code, body = progress(room_a, "started")
    check("agent reports started -> 200, interview in_progress",
          code == 200 and body["interview_status"] == "in_progress" and iv_status(iv) == "in_progress",
          f"{code} {body}")
    check("the change is audited (STATUS_CHANGE, system actor)", audit() == audit0 + 1)
    r = start()
    check("a second start while it runs -> 409 session_active",
          r.status == 409 and "already running" in (r.body or {}).get("detail", ""), repr(r))
    code, _ = progress(room_a, "started")
    check("a repeated started report is harmless (200, no second audit row)",
          code == 200 and iv_status(iv) == "in_progress" and audit() == audit0 + 1)
    plan = agent_call("/ai-interview/agent/plan", room_a)[1]["questions"]
    answer = {"question_id": plan[0]["id"], "question_number": 1, "sequence": 1, "kind": "answer",
              "transcript": "Phase nine workflow test answer.", "answered_at": datetime.utcnow().isoformat() + "Z"}
    check("answers are recorded while in progress",
          agent_call("/ai-interview/agent/answers", room_a, answer)[0] == 200)
    code, body = progress(room_a, "ended")
    check("ended early -> back to scheduled (can be started again)",
          code == 200 and iv_status(iv) == "scheduled", f"{code} {body}")
    check("the early-ended attempt's answer is kept",
          p5.db_scalar("""select count(*) from ai_interview_answers a join ai_interview_sessions s
                          on s.id = a.session_id where s.room_name = :r""", r=room_a) == 1)

    sb = start()
    check("restart after an early end -> 200", sb.ok, repr(sb))
    sc = start()
    check("a second start before the first agent joined -> 200 (supersedes it)", sc.ok, repr(sc))
    room_b, room_c = sb.body["room_name"], sc.body["room_name"]
    code, _ = progress(room_b, "started")
    check("the superseded room cannot start -> 409, status unchanged",
          code == 409 and iv_status(iv) == "scheduled", str(code))
    check("the newest room starts -> in_progress",
          progress(room_c, "started")[0] == 200 and iv_status(iv) == "in_progress")
    check("an older room cannot complete it -> 409", progress(room_a, "completed")[0] == 409)
    code, body = progress(room_c, "completed")
    check("completed -> 200, interview completed",
          code == 200 and iv_status(iv) == "completed", f"{code} {body}")
    r = start()
    check("a completed interview cannot be started again -> 409 completed",
          r.status == 409 and "already been completed" in (r.body or {}).get("detail", ""), repr(r))
    check("...and is no longer listed", not listed())
    check("...its room gets no plan (404)", plan_status(room_c) == 404)
    answer2 = {**answer, "sequence": 1, "transcript": "Too late."}
    check("...and records no more answers (404)",
          agent_call("/ai-interview/agent/answers", room_c, answer2)[0] == 404)

    def reset_attempts() -> None:
        """Phase 10: an interview allows 2 STARTED attempts, and this suite
        starts more than that on purpose. Deleting this run's own session
        rows (test data, removed at the end anyway) gives a clean count."""
        p5.cleanup()
        ROOMS.clear()
        e2e.ready_ai_interview(hr, app_id)

    section("6. A crashed agent does not lock the interview forever")
    reset_attempts()
    se = start()
    room_e = se.body["room_name"]
    check("a started agent -> in_progress", progress(room_e, "started")[0] == 200 and iv_status(iv) == "in_progress")
    check("in_progress with a recent session -> start refused", start().status == 409)
    db_write("""update ai_interview_sessions set created_at = created_at - interval '2 hours',
                expires_at = expires_at - interval '2 hours' where room_name = :r""", r=room_e)
    r = start()
    check("in_progress but its newest session is past the answer grace -> start allowed", r.ok, repr(r))

    section("7. /agent/progress: agent only, one field")
    room_x = ROOMS[-1]
    check("no token -> 401", agent_call("/ai-interview/agent/progress", None, {"event": "started"})[0] == 401)
    check("an applicant's JWT -> 403",
          agent_call("/ai-interview/agent/progress", None, {"event": "started"}, bearer=f"Bearer {tok}")[0] == 403)
    check("unknown event -> 422", progress(room_x, "finished")[0] == 422)
    check("extra field -> 422", agent_call("/ai-interview/agent/progress", room_x,
                                           {"event": "started", "interview_id": iv})[0] == 422)
    check("unbound room -> 404", progress("smarthr-ai-interview-00000000deadbeef", "started")[0] == 404)
    r = R("GET", "/openapi.json")
    paths = r.body.get("paths", {})
    check("openapi serves 128 paths (Phase 12 intelligence; Phase 11.5.3 analytics; Phase 9 adds /ai-interview/agent/progress)",
          len(paths) == 128 and "/ai-interview/agent/progress" in paths, str(len(paths)))

    section("8. The worker's progress client against the real endpoint")
    reset_attempts()
    from app.ai.interview.progress_client import report_progress
    os.environ.update({"LIVEKIT_URL": p5.FAKE_URL, "LIVEKIT_API_KEY": p5.FAKE_KEY,
                       "LIVEKIT_API_SECRET": p5.FAKE_SECRET, "SMARTHR_INTERVIEW_BACKEND_URL": BASE})
    sd = start()
    room_d = sd.body["room_name"]
    check("report_progress(started) -> True, in_progress",
          asyncio.run(report_progress(room_d, "started", timeout=10)) is True and iv_status(iv) == "in_progress")
    check("report_progress(ended) -> True, scheduled",
          asyncio.run(report_progress(room_d, "ended", timeout=10)) is True and iv_status(iv) == "scheduled")
    check("a refused report -> False", asyncio.run(report_progress(
        "smarthr-ai-interview-00000000deadbeef", "started", timeout=10)) is False)
    os.environ["SMARTHR_INTERVIEW_BACKEND_URL"] = "http://127.0.0.1:9"
    check("backend unreachable -> False, never raises",
          asyncio.run(report_progress(room_d, "started", timeout=2)) is False)
    os.environ["SMARTHR_INTERVIEW_BACKEND_URL"] = BASE

    section("10. At most 2 STARTED attempts per interview (Phase 10)")
    from app.services.interview_progress_service import MAX_STARTED_ATTEMPTS
    reset_attempts()
    used = lambda: p5.db_scalar(  # noqa: E731
        """select count(*) from ai_interview_sessions s where s.interview_id = :i and exists (
             select 1 from audit_logs l where l.action = 'STATUS_CHANGE'
             and l.entity_type = 'AiInterviewSession' and l.entity_id = s.id)""", i=iv)
    check("the limit is 2", MAX_STARTED_ATTEMPTS == 2)
    check("fresh: 0 started attempts", used() == 0)

    s1 = start()
    check("0 started -> start allowed", s1.ok, repr(s1))
    extra = [start() for _ in range(3)]
    check("sessions created but never joined -> all allowed (none is an attempt)",
          all(r.ok for r in extra), str([r.status for r in extra]))
    check("...and they count as 0 attempts", used() == 0, str(used()))
    room_1 = extra[-1].body["room_name"]
    check("the newest room's agent starts -> attempt 1", progress(room_1, "started")[0] == 200 and used() == 1)
    check("a repeated started report while it runs is the SAME attempt (still 1)",
          progress(room_1, "started")[0] == 200 and used() == 1)
    r = start()
    check("concurrent start while attempt 1 runs -> 409 session_active (unchanged)",
          r.status == 409 and (r.body or {}).get("code") == "session_active", repr(r))
    check("attempt 1 ends early -> scheduled", progress(room_1, "ended")[0] == 200 and iv_status(iv) == "scheduled")
    code, body = progress(room_1, "started")
    check("re-joining the ENDED attempt's room cannot run it again -> 409 attempt_finished",
          code == 409 and used() == 1 and iv_status(iv) == "scheduled", f"{code} {body}")

    s2 = start()
    check("1 started attempt -> start allowed", s2.ok, repr(s2))
    room_2 = s2.body["room_name"]
    check("its agent starts -> attempt 2", progress(room_2, "started")[0] == 200 and used() == 2)
    r = start()
    check("concurrent start while attempt 2 runs -> still 409 session_active",
          r.status == 409 and (r.body or {}).get("code") == "session_active", repr(r))
    check("attempt 2 ends early -> scheduled", progress(room_2, "ended")[0] == 200 and iv_status(iv) == "scheduled")

    r = start()
    body = r.body or {}
    check("2 started attempts -> start refused 409 with code attempts_exhausted",
          r.status == 409 and body.get("code") == "attempts_exhausted", repr(r))
    check("...and a clear message the page can show (detail)",
          "used all 2 attempts" in body.get("detail", ""), body.get("detail", ""))
    retry = [start() for _ in range(3)]
    check("refreshing / pressing Start again cannot bypass it (all 409 attempts_exhausted)",
          all(x.status == 409 and (x.body or {}).get("code") == "attempts_exhausted" for x in retry))
    check("the refusals created no room", used() == 2 and not any(x.ok for x in retry))
    check("an older, never-started room cannot become a 3rd attempt (409)",
          progress(s1.body["room_name"], "started")[0] == 409 and used() == 2)
    check("the interview stays scheduled (nothing marked completed)", iv_status(iv) == "scheduled")

    # Defence in depth: the AGENT's start is checked against the limit too.
    # Reach "newest room, never started, 2 attempts used" the only way it can
    # happen - a room created while 1 attempt was used, then another attempt
    # recorded - by writing the second attempt's record directly (test rows).
    reset_attempts()
    first = start()
    progress(first.body["room_name"], "started")
    progress(first.body["room_name"], "ended")
    other = start()                                  # created with 1 attempt used
    late = start()                                   # likewise - and the newest
    db_write("""insert into audit_logs (user_id, action, entity_type, entity_id)
                values (null, 'STATUS_CHANGE', 'AiInterviewSession', :s)""",
             s=p5.db_scalar("select id from ai_interview_sessions where room_name = :r",
                            r=other.body["room_name"]))
    code, body = progress(late.body["room_name"], "started")
    check("a room created before the limit was reached cannot start once it is -> 409 attempts_exhausted",
          code == 409 and used() == 2 and iv_status(iv) == "scheduled", f"{code} {body}")

    reset_attempts()
    check("fixture left scheduled for now, at the interview stage", iv_status(iv) == "scheduled")


# -- 9. Worker side, offline ------------------------------------------------------------

def test_worker() -> None:
    section("9. Worker: what counts as a completed interview, and the order of reports")
    from scripts.test_ai_interview_answers import _plan, _rig, _turn
    from app.ai.interview.questions import PlannedQuestion

    async def all_questions():
        m, s, c, a = _rig([PlannedQuestion(11, 1, "general", "Tell me about yourself.")], lambda r: None)
        await c.run_opening()
        await _turn(a, "I am a data engineer and I build reliable pipelines for analytics teams.")
        c.on_agent_state("thinking")
        c.on_agent_state("speaking")
        before = c.completed_normally
        c.on_agent_state("listening")
        return before, c.completed_normally, m.state.value

    before, after, state = asyncio.run(all_questions())
    check("last question answered, closing heard -> completed_normally",
          before is False and after is True and state == "completed", f"{before} {after} {state}")

    async def time_limit():
        m, s, c, a = _rig(_plan(), lambda r: None)
        await c.run_opening()
        await c.end("time_limit")
        return c.completed_normally

    check("time limit reached, closing spoken -> completed_normally", asyncio.run(time_limit()) is True)

    async def left_early():
        m, s, c, a = _rig(_plan(), lambda r: None)
        await c.run_opening()
        c.on_close("participant_disconnected")
        return c.completed_normally, m.state.value

    done, state = asyncio.run(left_early())
    check("applicant left mid-interview -> NOT completed (reported as ended)",
          done is False and state == "completed", f"{done} {state}")

    async def no_plan():
        m, s, c, a = _rig([], lambda r: None)
        await c.run_opening()
        return c.completed_normally

    check("no plan (start refused / questions unavailable) -> NOT completed", asyncio.run(no_plan()) is False)

    src = (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    check("the worker reports started BEFORE asking for the plan",
          src.index('report_progress(room_name, "started"') < src.index("await fetch_plan(room_name)"))
    body = src[src.index("async def _deliver_answers"):src.index("ctx.add_shutdown_callback(_deliver_answers)")]
    check("...and reports the end AFTER the answers are drained, only if its start was accepted",
          body.index("await answers.drain()") < body.index("report_progress")
          and "if started:" in body)
    tree = ast.parse((ROOT / "app/ai/interview/progress_client.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    check("the progress client does not touch the database",
          not any(m.startswith(("app.models", "app.database", "sqlalchemy")) for m in imported), str(imported))


def main() -> int:
    print("SmartHR - AI Interview Phase 9 workflow controls tests")
    test_window_settings()
    test_eligibility_rule()
    test_worker()
    p5.ROOMS = ROOMS
    try:
        with p5.Server(PORT, False):
            test_http()
    finally:
        print(f"\n  cleanup: removed {p5.cleanup()} session binding(s)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
