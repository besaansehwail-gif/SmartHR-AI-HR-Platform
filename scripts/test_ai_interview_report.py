"""AI Interview - Phase 8 Interview Report service tests. No server, no model, no LiveKit.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_report

In process, against the real database, plus the HTTP route
`GET /ai-interview/report/{interview_id}` on a backend of its own (port 8051,
fake LiveKit credentials, no model, its log captured to a file). Fixture sessions are bound to an
EXISTING interview (applicant05's, the Phase 5-7 fixture) through the real
`bind_room`, answers are written through the real `record_answer`, and
analyses are stored as real validated Phase 7 payloads
(`validate_analysis`) - so the report reads exactly what Phase 7 writes.
Every session created here is deleted at the end (answers and analyses
cascade). The model is made unreachable for the whole run: any attempt to
call it fails the suite.

Checks: session choice (latest with answers by default, one session only,
never merged), the empty state, (A) interview information without a planned
total, (B) answers in order with stored fields only, (C) aggregates counted
from completed analyses only - failed / pending are never negative findings,
no score / rating / percentage / verdict field anywhere, determinism, no
writes, no model call, and no transcript in any log line. Over HTTP:
Admin and HR 200, Manager / Employee / Applicant 403, anonymous 401, session
selection and refusal, and the server's own log free of transcripts.
"""

import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

passed = 0
failed: list[str] = []
ROOMS: list[str] = []

FIXTURE_EMAIL = "applicant05@smarthr.test"
PORT = 8051
BASE = f"http://127.0.0.1:{PORT}"
STAFF = {1: "aiinterview.admin@smarthr.test", 2: "aiinterview.hr@smarthr.test",
         3: "aiinterview.manager@smarthr.test", 4: "aiinterview.employee@smarthr.test"}


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


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def scalar(sql: str, **p):
    from sqlalchemy import text
    from app.database import engine
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def counts() -> tuple:
    return tuple(scalar(f"select count(*) from {t}") for t in (
        "ai_interview_sessions", "ai_interview_answers", "ai_interview_answer_analyses",
        "interviews", "applications"))


TRANSCRIPTS = {
    # session 1 (older)
    (1, 1): "I studied data science and I enjoy building forecasting models in Python.",
    (1, 2): "Our pipeline broke before a release and I rebuilt it overnight with the team.",
    # session 2 (newer)
    (2, 1): "I work mostly in Python and I learned Git on every project I joined.",
    (2, 2): "A migration failed and I restored the data from backups within an hour.",
    (2, 3): "I prefer pairing with colleagues and reviewing code together every day.",
}


def stored_analysis(transcript: str, question: str, job: dict, **over):
    """A real Phase 7 analysis: the model's payload through validate_analysis."""
    from app.ai.interview_analysis import AnalysisInput, validate_analysis
    words = transcript.split()
    payload = {
        "addresses_question": "fully",
        "summary": "The applicant described their work.",
        "evidence": [{"point": "Describes relevant work.", "quote": " ".join(words[:6]), "type": "experience"}],
        "skills_mentioned": [{"skill": "Python", "quote": "in Python"}] if "Python" in transcript else [],
        "job_requirements_referenced": [r for r in job["requirements"] if r.lower() in transcript.lower()],
        "cv_relation": [],
        "specificity": "specific",
        "clarity": "clear",
        "not_covered": [],
    }
    payload.update(over)
    return validate_analysis(payload, AnalysisInput(question=question, transcript=transcript, job=job))


def setup(db):
    """Three sessions on one existing interview: two answered, one not."""
    from app.models import Candidate, Interview, User
    from app.services import interview_answer_service as ans, interview_context_service as ctx
    from app.services import interview_analysis_service as ana, question_bank_service

    candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                 .filter(User.email == FIXTURE_EMAIL).first())
    if candidate is None:
        raise SystemExit(f"{FIXTURE_EMAIL} missing - run scripts.create_applicant_test_accounts")
    from datetime import datetime

    from app.models import Application
    from scripts.test_helpers import AI_INTERVIEW_LOCATION

    interview = (db.query(Interview).join(Application, Application.id == Interview.application_id)
                 .filter(Application.candidate_id == candidate.id,
                         Interview.location == AI_INTERVIEW_LOCATION)
                 .order_by(Interview.id.desc()).first())
    if interview is None:
        raise SystemExit("applicant05 has no AI Interview fixture interview - run the Phase 5 suite once")
    # Phase 9: answers are recorded only for a room of an HR-approved interview
    # started inside its window, so the fixture is made so (test rows only).
    db.get(Application, interview.application_id).status = "interview"
    interview.status = "scheduled"
    interview.scheduled_at = datetime.now().replace(microsecond=0)
    db.commit()
    plan = question_bank_service.interview_plan(db)

    sessions = {}
    for n in (1, 2, 3):
        room = f"smarthr-ai-interview-rpt{secrets.token_hex(6)}"
        ROOMS.append(room)
        sessions[n] = ctx.bind_room(db, room, interview, candidate, 10)
        from scripts.test_helpers import mark_session_started
        mark_session_started(room)          # Phase 11.6.4: answers need a started session

    from app.models import Application, Job
    job_row = db.get(Job, db.get(Application, interview.application_id).job_id)
    job = ctx.job_context(job_row, db)

    answers = {}
    for (s, number), transcript in TRANSCRIPTS.items():
        row, _ = ans.record_answer(db, sessions[s].room_name, ans.AnswerSubmission(
            question_id=plan[number - 1]["id"], question_number=number, sequence=number,
            kind="answer", transcript=transcript))
        answers[(s, number)] = row

    q = {n: plan[n - 1]["question_text"] for n in (1, 2, 3)}
    # Session 1: both completed.
    ana._store(db, answers[(1, 1)].id, "completed", stored_analysis(TRANSCRIPTS[(1, 1)], q[1], job), None, "gpt-4o")
    ana._store(db, answers[(1, 2)].id, "completed",
               stored_analysis(TRANSCRIPTS[(1, 2)], q[2], job, addresses_question="partially",
                               not_covered=["What the outcome was."]), None, "gpt-4o")
    # Session 2: one completed, one FAILED, one PENDING (no analysis row).
    ana._store(db, answers[(2, 1)].id, "completed", stored_analysis(TRANSCRIPTS[(2, 1)], q[1], job), None, "gpt-4o")
    ana._store(db, answers[(2, 2)].id, "failed", None, "llm_error", None)
    # Session 3: bound, never answered.
    return interview, sessions, answers, job, plan


FORBIDDEN_KEYS = re.compile(r"score|rating|rank|percent|pct|recommend|verdict|decision_|hire|reject|"
                            r"suitab|qualif|pass|fail_|grade|fit", re.I)


def keys_of(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield f"{path}.{k}", k
            yield from keys_of(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from keys_of(v, f"{path}[{i}]")


def main() -> int:
    print("SmartHR - AI Interview Phase 8 Interview Report service tests")
    from app.database import SessionLocal
    from app.services import interview_cv_service, interview_report_service as rpt
    from app.services.interview_report_service import REPORT_FIELDS, ReportError, interview_report
    import app.ai.provider as provider
    import app.ai.interview_analysis as analysis_mod

    def no_model(*_a, **_k):
        raise AssertionError("the report must not call a model")

    provider.get_provider = no_model
    analysis_mod.get_provider = no_model
    interview_cv_service.analyse_cv_bytes = no_model

    capture = LogCapture()
    logging.getLogger("smarthr").addHandler(capture)
    logging.getLogger("smarthr").setLevel(logging.DEBUG)

    db = SessionLocal()
    try:
        section("1. Fixture: three sessions on one existing interview")
        interview, sessions, answers, job, plan = setup(db)
        check("two answered sessions + one unanswered, on the same interview",
              len(answers) == 5 and len(sessions) == 3)
        print(f"        interview {interview.id}, sessions {[s.id for s in sessions.values()]}")

        before = counts()
        capture.lines.clear()

        section("2. Session choice: one session, never merged")
        report = interview_report(db, interview.id)
        check("top-level fields are exactly the report fields", tuple(report) == REPORT_FIELDS, str(tuple(report)))
        check("default = the LATEST session that has answers (not the newer unanswered one)",
              report["session"]["session_id"] == sessions[2].id, str(report["session"]))
        check("only that session's answers", [a["transcript"] for a in report["answers"]]
              == [TRANSCRIPTS[(2, n)] for n in (1, 2, 3)])
        older = interview_report(db, interview.id, session_id=sessions[1].id)
        check("session_id selects the older session - its answers only",
              [a["transcript"] for a in older["answers"]] == [TRANSCRIPTS[(1, n)] for n in (1, 2)])
        check("no answer appears in both reports (not merged)",
              not {a["transcript"] for a in older["answers"]} & {a["transcript"] for a in report["answers"]})
        listed = [(s["session_id"], s["answered_count"]) for s in report["sessions"]]
        check("sessions listed for choosing, newest first, with answer counts; unanswered session absent",
              (sessions[2].id, 3) in listed and (sessions[1].id, 2) in listed
              and sessions[3].id not in [s for s, _ in listed]
              and listed.index((sessions[2].id, 3)) < listed.index((sessions[1].id, 2)), str(listed))
        for label, sid in (("an unanswered session", sessions[3].id), ("a session id that does not exist", 10**9)):
            try:
                interview_report(db, interview.id, session_id=sid)
                check(f"{label} -> session_not_found", False)
            except ReportError as e:
                check(f"{label} -> session_not_found", e.code == "session_not_found")
        other = scalar("""select s.id from ai_interview_sessions s join ai_interview_answers a on a.session_id = s.id
                          where s.interview_id <> :i limit 1""", i=interview.id)
        if other:
            try:
                interview_report(db, interview.id, session_id=other)
                check("another interview's session -> session_not_found", False)
            except ReportError as e:
                check("another interview's session -> session_not_found", e.code == "session_not_found")
        try:
            interview_report(db, 10**9)
            check("unknown interview -> interview_not_found", False)
        except ReportError as e:
            check("unknown interview -> interview_not_found", e.code == "interview_not_found")

        section("3. (A) Interview information - no planned total")
        info = report["interview"]
        check("interview id, job title, department, scheduled_at, status",
              info["interview_id"] == interview.id and info["job_title"] == job["title"]
              and info["department"] == job["department"] and info["scheduled_at"]
              and info["status"] in ("scheduled", "in_progress", "completed", "cancelled"), str(info))
        check("answered_count and highest_question_reached", info["answered_count"] == 3
              and info["highest_question_reached"] == 3, str(info))
        blob = json.dumps(report)
        check("no planned total anywhere (no 'N of M', no total/planned count key)",
              not any(k.lower() in ("total", "total_questions", "planned", "planned_questions", "question_count")
                      for _, k in keys_of(report))
              and report["meta"]["planned_question_count_recorded"] is False
              and not re.search(r"\b\d+\s+of\s+\d+\b", blob))
        check("no candidate identity in the report",
              not any(w in blob for w in ("applicant05", "@smarthr", "candidate_name", "email", "phone")))

        section("4. (B) Answers in order, stored fields only")
        a1, a2, a3 = report["answers"]
        check("in answer order", [a["sequence"] for a in report["answers"]] == [1, 2, 3])
        check("question id / number / bank text as stored",
              all(a["question_id"] == plan[a["question_number"] - 1]["id"]
                  and a["question_text"] == plan[a["question_number"] - 1]["question_text"] for a in report["answers"]))
        check("transcript and word count exactly as stored", a1["transcript"] == answers[(2, 1)].transcript
              and a1["word_count"] == answers[(2, 1)].word_count)
        check("completed: status + the nine stored analysis fields, and nothing else",
              a1["analysis_status"] == "completed" and set(a1["analysis"]) == {
                  "addresses_question", "summary", "evidence", "skills_mentioned", "job_requirements_referenced",
                  "cv_relation", "specificity", "clarity", "not_covered"} and a1["error_code"] is None)
        check("the stored meta block is not passed through", "guards" not in json.dumps(a1))
        check("failed: status + error_code, no analysis", a2["analysis_status"] == "failed"
              and a2["analysis"] is None and a2["error_code"] == "llm_error")
        check("pending: status only, no analysis, no error", a3["analysis_status"] == "pending"
              and a3["analysis"] is None and a3["error_code"] is None)

        section("5. (C) Aggregates - from completed analyses only; missing is not negative")
        s = report["summary"]
        check("analysis status counts: 1 completed, 1 failed, 1 pending",
              s["analysis_status_counts"] == {"completed": 1, "failed": 1, "pending": 1}, str(s["analysis_status_counts"]))
        check("failed / pending are NOT counted as not addressed",
              s["addresses_question_counts"] == {"addressed": 1, "partially_addressed": 0,
                                                 "not_addressed": 0, "unclear": 0}, str(s["addresses_question_counts"]))
        check("the summary is marked incomplete", s["complete"] is False)
        expect_ref = [r for r in job["requirements"] if r.lower() in TRANSCRIPTS[(2, 1)].lower()]
        check("requirements referenced = union of the stored lists, in the job's order",
              s["requirements_referenced"] == expect_ref, str(s["requirements_referenced"]))
        check("requirements not referenced = the job's other phrases (basis: completed analyses)",
              s["requirements_not_referenced"] == [r for r in job["requirements"] if r not in expect_ref]
              and s["requirements_basis"] == "completed_analyses", str(s["requirements_not_referenced"]))
        check("skills mentioned: the applicant's statement, with where it was said",
              [(k["skill"], k["source"], [m["sequence"] for m in k["mentions"]]) for k in s["skills_mentioned"]]
              == [("Python", "applicant_statement", [1])], str(s["skills_mentioned"]))
        check("key evidence: stored quotes, each found in its answer's transcript",
              s["key_evidence"] and all(e["quote"] in report["answers"][e["sequence"] - 1]["transcript"]
                                        for e in s["key_evidence"]))
        o = older["summary"]
        check("older session: partially addressed counted, its not-covered items grouped by question",
              o["addresses_question_counts"]["partially_addressed"] == 1 and o["complete"] is True
              and o["not_covered"] == [{"sequence": 2, "question_number": 2, "items": ["What the outcome was."]}],
              str(o["not_covered"]))

        from app.services.interview_report_service import _summary
        unanalysed = [{**a, "analysis_status": st, "analysis": None} for a, st in
                      zip(report["answers"], ("failed", "pending", "failed"))]
        u = _summary(unanalysed, job["requirements"])
        check("NOTHING analysed -> no requirement is listed as not referenced (basis says why)",
              u["requirements_not_referenced"] == [] and u["requirements_basis"] == "no_completed_analyses"
              and u["addresses_question_counts"] == {"addressed": 0, "partially_addressed": 0,
                                                     "not_addressed": 0, "unclear": 0}
              and u["complete"] is False, str(u))

        section("6. No score, rating, percentage, recommendation or decision")
        for label, r in (("default report", report), ("older session", older)):
            bad = [p for p, k in keys_of(r) if FORBIDDEN_KEYS.search(k) and k != "is_hiring_decision"]
            check(f"{label}: no key can hold a score / rating / verdict", not bad, str(bad))
            check(f"{label}: is_hiring_decision is false", r["meta"]["is_hiring_decision"] is False)
            # Phase 11.4 adds two order-like numbers: `answer_sequences` (answer
            # sequence numbers) and `bank_position` (a place in the bank's order).
            numbers = [(p, v) for p, v in _numbers(r) if not re.search(
                r"(_id|_count|count|sequence|sequences|number|reached|_total|bank_position|"
                r"\.(completed|failed|pending|addressed|partially_addressed|not_addressed|unclear))$", p)]
            check(f"{label}: every number is an id, a count, an order or a question number", not numbers, str(numbers))
            check(f"{label}: no percentage sign", "%" not in json.dumps(r))

        section("7. Empty state: an interview with no answered session")
        empty_id = scalar("""select i.id from interviews i where not exists
                             (select 1 from ai_interview_answers a where a.interview_id = i.id) order by i.id limit 1""")
        e = interview_report(db, empty_id)
        check("valid report, state 'no_answers', no session, no answers",
              e["meta"]["state"] == "no_answers" and e["session"] is None and e["answers"] == [], str(e["meta"]))
        check("empty aggregates, no requirement listed as not referenced",
              e["summary"]["answered_count"] == 0 and e["summary"]["requirements_not_referenced"] == []
              and e["summary"]["requirements_basis"] == "no_completed_analyses"
              and e["interview"]["highest_question_reached"] is None)

        section("8. Read-only, deterministic, no model, nothing logged but ids and counts")
        check("deterministic: the same report twice", interview_report(db, interview.id) == report)
        check("no row written or removed by any report call", counts() == before, f"{before} -> {counts()}")
        check("no model was called (any call would have raised)", True)
        logged = " ".join(capture.lines)
        check("the report logs something (ids and counts)", "interview report built" in logged)
        leaked = [t for t in TRANSCRIPTS.values() if t in logged or t[:30] in logged]
        check("no transcript in any log line", not leaked, str(leaked))
        check("no analysis text in any log line", "The applicant described" not in logged)
        src = (ROOT / "app" / "services" / "interview_report_service.py").read_text(encoding="utf-8")
        check("the service has no write, no model call, no user/role parameter",
              not any(w in src for w in ("db.add", "db.commit", "db.delete", "get_provider", "analyse(",
                                         "current_user", "require_roles")))

        test_http(interview, sessions, report, older, empty_id)
    finally:
        db.close()
        logging.getLogger("smarthr").removeHandler(capture)
        print(f"\n  cleanup: removed {cleanup()} session binding(s) (answers and analyses cascade)")

    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


class Server:
    """A backend of its own: fake LiveKit credentials, no model, log to a file."""

    def __init__(self, port: int):
        self.port, self._p = port, None
        self.log = Path(tempfile.gettempdir()) / f"smarthr_report_server_{port}.log"

    def __enter__(self):
        env = {**os.environ, "LIVEKIT_URL": "wss://smarthr-test.invalid",
               "LIVEKIT_API_KEY": "APItest" + secrets.token_hex(4),
               "LIVEKIT_API_SECRET": secrets.token_urlsafe(32), "SMARTHR_LLM_PROVIDER": "none"}
        self._out = open(self.log, "w", encoding="utf-8")
        self._p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "info"],
            cwd=str(ROOT), stdout=self._out, stderr=subprocess.STDOUT, env=env)
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
        self._out.close()


def test_http(interview, sessions, report, older, empty_id) -> None:
    from scripts import test_helpers as e2e
    e2e.BASE = BASE
    R = e2e.request
    path = f"/ai-interview/report/{interview.id}"

    with Server(PORT) as server:
        section("9. HTTP: GET /ai-interview/report/{interview_id} - Admin and HR only")
        tokens = {}
        for role, email in STAFF.items():
            e2e.ensure_staff_account(email, role)
            tokens[role] = e2e.login(email)
        tokens[5] = e2e.login(FIXTURE_EMAIL)
        check("fixture sign-ins", all(tokens.values()), str({k: bool(v) for k, v in tokens.items()}))

        before = counts()
        check("anonymous -> 401", R("GET", path).status == 401)
        for role, expected in ((1, 200), (2, 200), (3, 403), (4, 403), (5, 403)):
            r = R("GET", path, token=tokens[role])
            check(f"role {role} -> {expected}", r.status == expected, str(r.status))
        check("the applicant cannot read their OWN interview's report either",
              R("GET", path + f"?session_id={sessions[2].id}", token=tokens[5]).status == 403)

        section("10. HTTP: the route returns the service's report, unchanged")
        admin = R("GET", path, token=tokens[1]).body
        hr = R("GET", path, token=tokens[2]).body
        check("Admin and HR get the same report", admin == hr)
        check("== the service's report (default session)", hr == report)
        check("default = the latest session with answers", hr["session"]["session_id"] == sessions[2].id)
        explicit = R("GET", path + f"?session_id={sessions[1].id}", token=tokens[2])
        check("explicit session_id -> that session's report", explicit.ok and explicit.body == older)
        check("never merged: no transcript is in both",
              not {a["transcript"] for a in explicit.body["answers"]} & {a["transcript"] for a in hr["answers"]})
        for label, q in (("a session with no answers", sessions[3].id), ("a session id that does not exist", 10**9)):
            r = R("GET", path + f"?session_id={q}", token=tokens[2])
            check(f"{label} -> 404", r.status == 404, str(r.status))
        other = scalar("select min(id) from interviews where id <> :i", i=interview.id)
        r = R("GET", f"/ai-interview/report/{other}?session_id={sessions[2].id}", token=tokens[2])
        check("this interview's session asked for under ANOTHER interview -> 404", r.status == 404, str(r.status))
        check("unknown interview -> 404", R("GET", "/ai-interview/report/999999999", token=tokens[2]).status == 404)
        check("a non-numeric session_id -> 422", R("GET", path + "?session_id=abc", token=tokens[2]).status == 422)
        e = R("GET", f"/ai-interview/report/{empty_id}", token=tokens[2])
        check("an interview with no answers -> 200, state 'no_answers'", e.ok and e.body["meta"]["state"] == "no_answers"
              and e.body["answers"] == [] and e.body["summary"]["requirements_not_referenced"] == [])

        section("11. HTTP: factual only; failed / pending are not findings; nothing written")
        check("is_hiring_decision is false", hr["meta"]["is_hiring_decision"] is False)
        bad = [p for p, k in keys_of(hr) if FORBIDDEN_KEYS.search(k) and k != "is_hiring_decision"]
        check("no key can hold a score / rating / verdict", not bad, str(bad))
        check("failed and pending answers carry no analysis and are not counted as not addressed",
              [a["analysis_status"] for a in hr["answers"]] == ["completed", "failed", "pending"]
              and hr["summary"]["addresses_question_counts"]["not_addressed"] == 0
              and all(a["analysis"] is None for a in hr["answers"][1:]))
        check("deterministic over HTTP", R("GET", path, token=tokens[2]).body == hr)
        check("no row written or removed by any request", counts() == before, f"{before} -> {counts()}")

        r = R("GET", "/openapi.json")
        check("openapi serves 128 paths (Phase 12 intelligence; Phase 11.5.3 analytics; Phase 8 adds /ai-interview/report/{interview_id}, Phase 9 /agent/progress)",
              len(r.body.get("paths", {})) == 128, str(len(r.body.get("paths", {}))))

    log = server.log.read_text(encoding="utf-8", errors="replace")
    check("the server log has the report requests", "/ai-interview/report/" in log)
    check("no transcript in the server's log",
          not any(t in log or t[:30] in log for t in TRANSCRIPTS.values()))
    check("no analysis text in the server's log", "The applicant described" not in log)


def _numbers(value, path=""):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _numbers(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _numbers(v, path)


def cleanup() -> int:
    if not ROOMS:
        return 0
    from sqlalchemy import text
    from app.database import engine
    with engine.begin() as conn:
        return conn.execute(text("delete from ai_interview_sessions where room_name = any(:r)"),
                            {"r": ROOMS}).rowcount


if __name__ == "__main__":
    sys.exit(main())
