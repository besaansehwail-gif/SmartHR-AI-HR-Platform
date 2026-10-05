"""AI Interview - Phase 11.4 Interview Report: the interview as it actually ran.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_report_flow     # no model, no LiveKit

Three throwaway sessions on applicant05's fixture interview (deleted at the
end), answers stored through the real `record_answer` (so every Question Bank
check applies), analyses stored by a FAKE provider or marked failed / left
pending - then the report is read and compared with what was stored:

* S1 sequential - Q1, Q2 in bank order; the rest not reached;
* S2 adaptive + follow-up - Q1, Q1's follow-up, then the bank's 4th question
  asked second, then the 2nd asked third (with a short answer and its
  elaboration); completed, failed and pending analyses side by side;
* S3 a follow-up whose main answer was never stored.

Plus the HTTP route on its own server (8056): Admin/HR only, Applicant 403.
"""

import json
import re
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

PORT = 8056
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


def setup(db):
    from app.models import Application, Candidate, Interview, User
    from app.services import interview_analysis_service as svc, interview_answer_service as ans
    from app.services import interview_context_service as ctx, question_bank_service as qb
    from scripts.test_ai_interview_answers import GOOD, FakeProvider

    plan = qb.interview_plan(db)
    if len(plan) < 4 or not plan[0]["follow_up"]:
        raise SystemExit("the fixture plan needs 4+ main questions and a follow-up on Q1 (seed_interview_questions)")
    candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                 .filter(User.email == p5.APPLICANT_ONE_CV).one())
    interview = (db.query(Interview).join(Application, Application.id == Interview.application_id)
                 .filter(Application.candidate_id == candidate.id,
                         Interview.location == e2e.AI_INTERVIEW_LOCATION)
                 .order_by(Interview.id.desc()).first())
    # Phase 9: an HR-approved interview in its window (fixture rows only).
    db.get(Application, interview.application_id).status = "interview"
    interview.status = "scheduled"
    interview.scheduled_at = datetime.now().replace(microsecond=0)
    db.commit()

    ids = [p["id"] for p in plan]
    fu = plan[0]["follow_up"]["id"]
    text = "our forecasting model drifted, so I retrained it in Python and I also deployed it on Kubernetes myself"
    sessions: dict[str, dict] = {}

    def session(name, rows):
        room = f"smarthr-ai-interview-rf{secrets.token_hex(6)}"
        ROOMS.append(room)
        binding = ctx.bind_room(db, room, interview, candidate, 10)
        e2e.mark_session_started(room)      # Phase 11.6.4: answers need a started session
        stored = []
        for seq, (qid, number, transcript, kind, analysis) in enumerate(rows, 1):
            row, _ = ans.record_answer(db, room, ans.AnswerSubmission(
                question_id=qid, question_number=number, sequence=seq, kind=kind, transcript=transcript,
                answered_at=datetime.utcnow()))
            if analysis == "completed":
                svc.analyse_answer(db, row.id, force=True, provider=FakeProvider(GOOD))
            elif analysis == "failed":
                svc._store(db, row.id, "failed", None, "llm_error", None)
            stored.append({"sequence": seq, "question_id": qid, "number": number, "transcript": transcript,
                           "analysis": analysis, "id": row.id, "question_text": row.question_text})
        sessions[name] = {"id": binding.id, "rows": stored}

    session("sequential", [(ids[0], 1, text, "answer", "completed"),
                           (ids[1], 2, "I paired with a colleague to fix it.", "answer", "pending")])
    session("adaptive", [(ids[0], 1, text, "answer", "completed"),
                         (fu, 1, "It cut forecast errors by a third within two months.", "answer", "failed"),
                         (ids[3], 2, "I would tell the team early and re-plan the scope.", "answer", "completed"),
                         (ids[1], 3, "Yes.", "short", "pending"),
                         (ids[1], 3, "I paired with a colleague and we traced the failing job.", "answer", "pending")])
    session("follow_up_only", [(fu, 1, "It cut forecast errors by a third.", "answer", "pending")])
    return interview, plan, sessions


def test_reports(db, interview, plan, sessions) -> dict:
    from app.models import AiInterviewAnswerAnalysis, InterviewQuestion
    from app.services.interview_report_service import REPORT_FIELDS, interview_report

    bank_text = {q.id: q.question_text for q in db.query(InterviewQuestion).all()}
    ids = [p["id"] for p in plan]
    fu = plan[0]["follow_up"]["id"]

    section("1. Structure")
    r = interview_report(db, interview.id, sessions["sequential"]["id"])
    check("top-level fields: the Phase 8 ones plus question_flow, coverage, context",
          tuple(r) == REPORT_FIELDS and {"question_flow", "coverage", "context"} <= set(r), str(tuple(r)))
    check("session carries first/last answer times; its length is declared NOT recorded",
          r["session"]["first_answer_at"] and r["session"]["last_answer_at"]
          and r["session"]["duration_recorded"] is False and "duration" not in r["session"])
    check("overview keeps job, department, scheduled time, status",
          {"job_title", "department", "scheduled_at", "status"} <= set(r["interview"]))

    section("2. Sequential interview (S1)")
    flow = r["question_flow"]
    check("flow = the two main questions, in order, numbered 1 and 2",
          [(e["number"], e["main"]["question_id"]) for e in flow] == [(1, ids[0]), (2, ids[1])])
    check("each main question's text is the stored (= Question Bank) text",
          all(e["main"]["question_text"] == bank_text[e["main"]["question_id"]] for e in flow))
    check("bank positions 1, 2; no follow-ups", [e["main"]["bank_position"] for e in flow] == [1, 2]
          and all(e["follow_up"] is None for e in flow))
    cov = r["coverage"]
    check("coverage: 2 main answered, 0 follow-ups, highest reached 2",
          (cov["main_questions_answered_count"], cov["follow_ups_answered_count"],
           cov["highest_main_question_reached"]) == (2, 0, 2))
    check("not reached = the CURRENT plan's other main questions, in bank order, with bank text",
          [q["question_id"] for q in cov["not_reached"]] == ids[2:]
          and all(q["question_text"] == bank_text[q["question_id"]] for q in cov["not_reached"])
          and cov["not_reached_basis"] == "current_question_bank")
    check("order matches the current bank", cov["order_matches_current_bank"] is True)

    section("3. Adaptive interview with a follow-up (S2)")
    r2 = interview_report(db, interview.id, sessions["adaptive"]["id"])
    flow = r2["question_flow"]
    check("main questions in the order ASKED: bank Q1, bank Q4, bank Q2",
          [(e["number"], e["main"]["question_id"], e["main"]["bank_position"]) for e in flow]
          == [(1, ids[0], 1), (2, ids[3], 4), (3, ids[1], 2)], str(flow))
    check("coverage says the order differs from the current bank", r2["coverage"]["order_matches_current_bank"] is False)
    check("the follow-up sits under Question 1, with its own id and bank text",
          flow[0]["follow_up"] and flow[0]["follow_up"]["question_id"] == fu
          and flow[0]["follow_up"]["question_text"] == bank_text[fu])
    rows = {row["sequence"]: row for row in sessions["adaptive"]["rows"]}
    check("the follow-up answer is SEPARATE from its main answer",
          flow[0]["main"]["answer_sequences"] == [1] and flow[0]["follow_up"]["answer_sequences"] == [2])
    check("a main question answered in two parts (short + elaboration) keeps both, in order",
          flow[2]["main"]["answer_sequences"] == [4, 5])
    cov = r2["coverage"]
    check("coverage: 3 main answered, 1 follow-up (under 1), highest reached 3",
          (cov["main_questions_answered_count"], cov["follow_ups_answered"], cov["highest_main_question_reached"])
          == (3, [{"number": 1, "question_id": fu}], 3), str(cov))
    check("not reached excludes every asked question", {q["question_id"] for q in cov["not_reached"]}
          == set(ids) - {ids[0], ids[1], ids[3]})
    answers = {a["sequence"]: a for a in r2["answers"]}
    check("exact transcripts, as stored", all(answers[s]["transcript"] == rows[s]["transcript"] for s in rows))
    check("each answer typed main / follow_up",
          [answers[s]["question_type"] for s in sorted(answers)] == ["main", "follow_up", "main", "main", "main"])
    check("analysis statuses as stored: completed, failed, completed, pending, pending",
          [answers[s]["analysis_status"] for s in sorted(answers)]
          == ["completed", "failed", "completed", "pending", "pending"])
    check("a failed analysis keeps its code and contributes no analysis fields",
          answers[2]["error_code"] == "llm_error" and answers[2]["analysis"] is None)
    check("the summary counts only completed analyses; incomplete is flagged",
          r2["summary"]["analysis_status_counts"] == {"completed": 2, "failed": 1, "pending": 2}
          and r2["summary"]["complete"] is False)

    section("4. Follow-up whose main answer was not stored (S3)")
    r3 = interview_report(db, interview.id, sessions["follow_up_only"]["id"])
    e = r3["question_flow"][0]
    check("the main question is named from the follow-up's parent row, marked answered: false, no answers",
          e["main"]["question_id"] == ids[0] and e["main"]["question_text"] == bank_text[ids[0]]
          and e["main"]["answered"] is False and e["main"]["answer_sequences"] == [])
    check("...and no answer is invented for it", [a["question_type"] for a in r3["answers"]] == ["follow_up"])
    check("coverage: 0 main answered, 1 follow-up, highest reached 1; Q1 not listed as 'not reached'",
          r3["coverage"]["main_questions_answered_count"] == 0 and r3["coverage"]["follow_ups_answered_count"] == 1
          and r3["coverage"]["highest_main_question_reached"] == 1
          and ids[0] not in [q["question_id"] for q in r3["coverage"]["not_reached"]])
    check("context unknown when nothing was analysed", r3["context"] == {
        "job": None, "cv": None, "matching": None, "basis": "no_completed_analyses"})

    section("5. Context indicators and what the report never contains")
    metas = [a.analysis["meta"]["context"] for a in db.query(AiInterviewAnswerAnalysis).filter(
        AiInterviewAnswerAnalysis.answer_id.in_([row["id"] for row in sessions["adaptive"]["rows"]]),
        AiInterviewAnswerAnalysis.status == "completed").all()]
    expected = {k: any(m.get(k) is True for m in metas) for k in ("job", "cv", "matching")}
    check("context = the stored analyses' meta.context booleans", r2["context"] == {**expected, "basis": "completed_analyses"},
          f"{r2['context']} vs {expected}")
    for label, report in (("S1", r), ("S2", r2), ("S3", r3)):
        bad = [pth for pth, k in keys_of(report) if FORBIDDEN_KEYS.search(k) and k != "is_hiring_decision"]
        check(f"{label}: no score / rating / rank / recommendation / decision key anywhere", not bad, str(bad))
        blob = json.dumps(report)
        check(f"{label}: no stored meta, prompt, token, LiveKit or model reasoning in the report",
              '"meta": {"version' not in blob and not re.search(r"prompt|token|livekit|reasoning|smarthr-ai-interview",
                                                                   blob, re.I))
        check(f"{label}: is_hiring_decision is false", report["meta"]["is_hiring_decision"] is False)
    every = [q for rep_ in (r, r2, r3) for e in rep_["question_flow"]
             for q in (e["main"], e["follow_up"]) if q]
    check("no invented questions: every flow question is a Question Bank row, with its text",
          all(q["question_id"] in bank_text and q["question_text"] == bank_text[q["question_id"]] for q in every))
    return r2


def test_http(interview, report) -> None:
    section("6. HTTP: Admin / HR only - the Applicant cannot read the HR report")
    e2e.BASE = BASE
    p5.BASE = BASE
    R = e2e.request
    path = f"/ai-interview/report/{interview.id}?session_id={report['session']['session_id']}"
    tokens = {}
    for role, email in ((2, e2e.AI_INTERVIEW_HR), (3, "reportflow.manager@smarthr.test"),
                        (4, "reportflow.employee@smarthr.test")):
        e2e.ensure_staff_account(email, role)
        tokens[role] = e2e.login(email)
    tokens[5] = p5.fixture_login(p5.APPLICANT_ONE_CV)
    hr = R("GET", path, token=tokens[2])
    check("HR -> 200 with question_flow, coverage and context",
          hr.status == 200 and {"question_flow", "coverage", "context"} <= set(hr.body))
    check("...the same report as the service (served, not re-derived)",
          hr.body["question_flow"] == report["question_flow"] and hr.body["coverage"] == report["coverage"])
    for role, label in ((3, "Manager"), (4, "Employee"), (5, "Applicant - even for their own interview")):
        check(f"{label} -> 403", R("GET", path, token=tokens[role]).status == 403)
    check("anonymous -> 401", R("GET", path).status == 401)


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    if not ROOMS:
        return 0
    with engine.begin() as conn:
        return conn.execute(text("delete from ai_interview_sessions where room_name = any(:r)"),
                            {"r": ROOMS}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 11.4 Interview Report tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider
    from app.database import SessionLocal
    from app.services import interview_cv_service as cvsvc
    from scripts.test_ai_interview_matching_context import FakeAnalysis

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model
    cvsvc.analyse_cv_bytes = lambda *a, **k: FakeAnalysis(p5.sample_parsed())
    cvsvc.clear_cache()

    db = SessionLocal()
    try:
        interview, plan, sessions = setup(db)
        report = test_reports(db, interview, plan, sessions)
        db.close()
        with p5.Server(PORT, False):
            test_http(interview, report)
    finally:
        db.close()
        print(f"\n  cleanup: removed {cleanup()} session binding(s) (answers and analyses cascade)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
