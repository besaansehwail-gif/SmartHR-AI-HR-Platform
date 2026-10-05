"""AI Interview analytics (Phase 11.5.3) tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_analytics     # no model, no LiveKit

Temporary fixtures only, deleted at the end: six interviews created for this
run on applicant10's fixture application (notes "ANALYTICS TEST"), their AI
Interview sessions, answers and analysis rows written directly, with known
counts. The service is checked on exactly those interviews (its internal
`interview_ids` scope), and the endpoint on its own server (port 8057) for
access and shape. No real interview or session is read for an assertion.
"""

import json
import secrets
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_ai_interview_cv_context as p5  # noqa: E402
from scripts import test_helpers as e2e  # noqa: E402
from scripts.test_ai_interview_report import FORBIDDEN_KEYS, keys_of  # noqa: E402

PORT = 8057
BASE = f"http://127.0.0.1:{PORT}"
MARK = "ANALYTICS TEST"
CREATED: dict[str, list[int]] = {"interviews": []}

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


TRANSCRIPT = "ANALYTICS-TRANSCRIPT I rebuilt the forecasting pipeline in Python"


def build_fixtures(db):
    """Six temporary interviews with known contents:

    I1 scheduled    S1a: Q1 (completed: job+cv+matching), Q1's follow-up (failed),
                         Q2 short (pending) + Q2 elaboration (completed: job)
                    S1b: Q1 (completed: job+cv)
    I2 in_progress  S2 : bank Q4 asked 1st (pending), bank Q3 asked 2nd (failed)
    I3 completed    S3 : Q1's follow-up only (pending)
    I4 cancelled    S4 : no answers
    I5 scheduled    no session at all
    I6 scheduled    S6 : a main question outside today's plan (completed: nothing)
    """
    from app.models import AiInterviewAnswer, Application, Candidate, Interview, InterviewQuestion, User
    from app.services import interview_analysis_service as svc, interview_context_service as ctx
    from app.services import question_bank_service as qb

    plan = qb.interview_plan(db)
    if len(plan) < 4 or not plan[0]["follow_up"]:
        raise SystemExit("the fixture plan needs 4+ main questions and a follow-up on Q1 (seed_interview_questions)")
    outside = (db.query(InterviewQuestion).filter(InterviewQuestion.question_type == "main",
               InterviewQuestion.is_active.is_(True), ~InterviewQuestion.id.in_([p["id"] for p in plan]))
               .order_by(InterviewQuestion.id).first())
    if outside is None:
        raise SystemExit("the bank needs a main question beyond the plan (seed_interview_questions)")
    candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                 .filter(User.email == p5.APPLICANT_MANY_CVS).one())
    application = (db.query(Application).filter(Application.candidate_id == candidate.id)
                   .order_by(Application.id).first())

    interviews = {}
    for name, status in (("I1", "scheduled"), ("I2", "in_progress"), ("I3", "completed"),
                         ("I4", "cancelled"), ("I5", "scheduled"), ("I6", "scheduled")):
        iv = Interview(application_id=application.id, scheduled_at=datetime.now().replace(microsecond=0),
                       status=status, location=MARK, notes=MARK)
        db.add(iv)
        db.flush()
        interviews[name] = iv
        CREATED["interviews"].append(iv.id)
    db.commit()

    text = {q.id: q.question_text for q in db.query(InterviewQuestion).all()}
    q = [p["id"] for p in plan]
    fu = plan[0]["follow_up"]["id"]

    def session(iv_name, rows):
        room = f"smarthr-ai-interview-an{secrets.token_hex(6)}"
        binding = ctx.bind_room(db, room, interviews[iv_name], candidate, 10)
        for seq, (qid, number, kind, analysis) in enumerate(rows, 1):
            answer = AiInterviewAnswer(session_id=binding.id, interview_id=interviews[iv_name].id,
                                       question_id=qid, question_number=number, question_text=text[qid],
                                       sequence=seq, answer_kind=kind, transcript=TRANSCRIPT,
                                       word_count=len(TRANSCRIPT.split()), answered_at=datetime.utcnow(),
                                       created_at=datetime.utcnow())
            db.add(answer)
            db.commit()
            if isinstance(analysis, dict):
                svc._store(db, answer.id, "completed",
                           {"summary": "fixture", "meta": {"context": analysis, "is_hiring_decision": False}},
                           None, "fixture")
            elif analysis == "failed":
                svc._store(db, answer.id, "failed", None, "llm_error", None)

    session("I1", [(q[0], 1, "answer", {"job": True, "cv": True, "matching": True}),
                   (fu, 1, "answer", "failed"),
                   (q[1], 2, "short", "pending"),
                   (q[1], 2, "answer", {"job": True, "cv": False, "matching": False})])
    session("I1", [(q[0], 1, "answer", {"job": True, "cv": True, "matching": False})])
    session("I2", [(q[3], 1, "answer", "pending"), (q[2], 2, "answer", "failed")])
    session("I3", [(fu, 1, "answer", "pending")])
    session("I4", [])
    session("I6", [(outside.id, 1, "answer", {"job": False, "cv": False, "matching": False})])
    return {k: v.id for k, v in interviews.items()}, plan, candidate


def table_counts():
    tables = ("interviews", "ai_interview_sessions", "ai_interview_answers", "ai_interview_answer_analyses",
              "interview_questions", "audit_logs")
    return {t: p5.db_scalar(f"select count(*) from {t}") for t in tables}


def leaves(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from leaves(v)
    else:
        yield value


def test_service(db, ids, plan, candidate):
    from app.services.ai_interview_analytics_service import ANALYTICS_FIELDS, interview_analytics

    main_set = [ids[k] for k in ("I1", "I2", "I3", "I4", "I5")]
    section("1. Shape - and nothing but counts")
    before = table_counts()
    r = interview_analytics(db, main_set)
    check("sections and fields are exactly the designed ones",
          {k: tuple(v) for k, v in r.items()} == ANALYTICS_FIELDS, str({k: tuple(v) for k, v in r.items()}))
    check("every value is an integer, a boolean or null - no text can be in it",
          all(v is None or isinstance(v, (int, bool)) for v in leaves(r)))
    bad = [p for p, k in keys_of(r) if FORBIDDEN_KEYS.search(k)]
    check("no score / rating / rank / percentage / recommendation / decision key", not bad, str(bad))
    blob = json.dumps(r).lower()
    check("no transcript, name, email, prompt, token or LiveKit data",
          not any(x.lower() in blob for x in (TRANSCRIPT, candidate.first_name, candidate.email or "@",
                                               "prompt", "token", "livekit", "room")))

    section("2. Interview status counts (interviews with an AI Interview session)")
    ov = r["overview"]
    check("total = the 4 interviews with a session (I5 has none, so it is not counted)", ov["total_interviews"] == 4,
          str(ov))
    check("scheduled 1, in progress 1, completed 1 - the cancelled one is in the total, not a bucket",
          (ov["scheduled"], ov["in_progress"], ov["completed"]) == (1, 1, 1), str(ov))

    section("3. Activity: answers, main vs follow-up, highest question")
    act = r["activity"]
    check("answers recorded = every stored answer (8)", act["answers_recorded"] == 8, str(act))
    check("main questions reached = distinct main ids per session, summed (5: a two-part answer counts once)",
          act["main_questions_reached"] == 5, str(act))
    check("follow-ups answered = stored follow-up answers (2)", act["follow_ups_answered"] == 2, str(act))
    check("highest question reached = largest MAIN question_number (2)", act["highest_question_reached"] == 2)

    section("4. Analysis states and context indicators - as persisted")
    check("completed 3, failed 2, pending (no analysis row) 3",
          r["analysis"] == {"completed": 3, "pending": 3, "failed": 2}, str(r["analysis"]))
    check("context = completed analyses whose stored meta.context flag is true: job 3, cv 2, matching 1",
          r["context"] == {"job": 3, "cv": 2, "matching": 1}, str(r["context"]))
    check("failed / pending analyses add nothing to context", sum(r["context"].values()) == 6)

    section("5. Question flow and not-reached (against today's plan)")
    qf = r["question_flow"]
    check("main questions = distinct main Question Bank ids answered (4)", qf["main_questions"] == 4, str(qf))
    check("follow-ups = distinct follow-up Question Bank ids answered (1)", qf["follow_ups"] == 1)
    check("not reached = today's plan minus those reached (a count, no planned total claimed)",
          qf["not_reached"] == len(plan) - 4 and "planned" not in json.dumps(r))
    check("order comparable: every answered main question is in today's plan", qf["order_comparable"] is True)
    outside = interview_analytics(db, [ids["I6"]])
    check("a main question no longer in the plan -> order not comparable; it does not count as reaching the plan",
          outside["question_flow"]["order_comparable"] is False
          and outside["question_flow"]["not_reached"] == len(plan) and outside["question_flow"]["main_questions"] == 1)

    section("6. Empty and zero data")
    for label, scope in (("an interview with no session", [ids["I5"]]), ("an empty scope", [])):
        e = interview_analytics(db, scope)
        check(f"{label}: all counts zero, highest null, nothing comparable",
              e["overview"] == {"total_interviews": 0, "scheduled": 0, "in_progress": 0, "completed": 0}
              and e["activity"] == {"answers_recorded": 0, "main_questions_reached": 0,
                                    "follow_ups_answered": 0, "highest_question_reached": None}
              and e["analysis"] == {"completed": 0, "pending": 0, "failed": 0}
              and e["context"] == {"job": 0, "cv": 0, "matching": 0}
              and e["question_flow"] == {"main_questions": 0, "follow_ups": 0, "not_reached": len(plan),
                                         "order_comparable": False}, str(e))

    section("7. Read-only and deterministic")
    check("the same data gives the same answer", interview_analytics(db, main_set) == r)
    check("nothing was written by any of these calls (row counts unchanged)", table_counts() == before)


def test_http(ids) -> None:
    section("8. HTTP: Admin and HR only")
    from app.database import SessionLocal
    from app.services.ai_interview_analytics_service import interview_analytics

    e2e.BASE = BASE
    p5.BASE = BASE
    R = e2e.request
    tokens = {}
    for role, email in ((1, "analytics.admin@smarthr.test"), (2, e2e.AI_INTERVIEW_HR),
                        (3, "analytics.manager@smarthr.test"), (4, "analytics.employee@smarthr.test")):
        e2e.ensure_staff_account(email, role)
        tokens[role] = e2e.login(email)
    tokens[5] = p5.fixture_login(p5.APPLICANT_ONE_CV)
    for role, label in ((1, "Admin"), (2, "HR")):
        r = R("GET", "/ai-interview/analytics", token=tokens[role])
        check(f"{label} -> 200", r.status == 200, str(r.status))
    db = SessionLocal()
    try:
        expected = interview_analytics(db)
    finally:
        db.close()
    check("the endpoint serves the service's figures for everything stored (no scope over HTTP)",
          r.body == expected, f"{r.body} vs {expected}")
    check("...and they include this run's fixtures", r.body["activity"]["answers_recorded"] >= 9)
    for role, label in ((3, "Manager"), (4, "Employee"), (5, "Applicant")):
        check(f"{label} -> 403", R("GET", "/ai-interview/analytics", token=tokens[role]).status == 403)
    check("anonymous -> 401", R("GET", "/ai-interview/analytics").status == 401)
    check("a scope cannot be passed over HTTP (the parameter is ignored)",
          R("GET", f"/ai-interview/analytics?interview_ids={ids['I5']}", token=tokens[2]).body == expected)
    paths = R("GET", "/openapi.json").body.get("paths", {})
    check("openapi serves 128 paths (Phase 12 intelligence; Phase 11.5.3 adds /ai-interview/analytics)",
          len(paths) == 128 and "/ai-interview/analytics" in paths, str(len(paths)))


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    ids = CREATED["interviews"]
    if not ids:
        return 0
    with engine.begin() as conn:
        conn.execute(text("delete from ai_interview_sessions where interview_id = any(:i)"), {"i": ids})
        return conn.execute(text("delete from interviews where id = any(:i) and notes = :m"),
                            {"i": ids, "m": MARK}).rowcount


def main() -> int:
    print("SmartHR - AI Interview analytics (Phase 11.5.3) tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider
    from app.database import SessionLocal

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model

    db = SessionLocal()
    try:
        ids, plan, candidate = build_fixtures(db)
        test_service(db, ids, plan, candidate)
        db.close()
        with p5.Server(PORT, False):
            test_http(ids)
    finally:
        db.close()
        removed = cleanup()
        left = p5.db_scalar("select count(*) from interviews where notes = :m", m=MARK)
        print(f"\n  cleanup: removed {removed} temporary interview(s) with their sessions, answers and analyses;"
              f" {left} left")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
