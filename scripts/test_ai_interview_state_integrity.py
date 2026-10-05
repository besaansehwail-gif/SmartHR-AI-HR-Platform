"""AI Interview - Phase 11.6.4 voice session state integrity. Deterministic, offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_state_integrity

The interview's status (`interviews.status`) is the one persisted state;
this suite drives it through the REAL backend services in process -
`ai_interview_service.start_voice_session` (which only signs a LiveKit token
locally - LiveKit is never contacted), `interview_progress_service.agent_event`,
`interview_answer_service.record_answer`, the applicant's interview list - on
TEMPORARY interviews created on applicant10's fixture application and
deleted at the end. The agent side runs the real controller / state machine
against a fake session; the page's state mapping is checked by running the
frontend's own check script. No model, no LiveKit, no real interview.
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_ai_interview_turn_taking import LONG, plan, rig, turn  # noqa: E402

MARK = "STATE INTEGRITY TEST"
CREATED: list[int] = []
SPOKEN = {LONG, "I rebuilt the forecasting pipeline after it failed, twice.", "It cut forecast errors by a third."}

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


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))


def backend_suite() -> None:
    from app.database import SessionLocal
    from app.models import AiInterviewSession, Application, Candidate, Interview, User
    from app.services import ai_interview_service as svc, interview_answer_service as ans
    from app.services import interview_context_service as ctx, interview_progress_service as prog
    from app.services import question_bank_service as qb
    from scripts.test_ai_interview_cv_context import APPLICANT_MANY_CVS

    db = SessionLocal()
    try:
        candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                     .filter(User.email == APPLICANT_MANY_CVS).one())
        application = (db.query(Application).filter(Application.candidate_id == candidate.id)
                       .order_by(Application.id).first())
        application.status = "interview"
        db.commit()
        plan_ = qb.interview_plan(db)
        fu = plan_[0]["follow_up"]

        def new_interview(status="scheduled", location=MARK):
            iv = Interview(application_id=application.id, scheduled_at=datetime.now().replace(microsecond=0),
                           status=status, location=location, notes=MARK)
            db.add(iv)
            db.commit()
            CREATED.append(iv.id)
            return iv

        def status(iv):
            db.expire_all()
            return db.get(Interview, iv.id).status

        def start(iv):
            """Start pressed: the real session creation (a locally signed token)."""
            return svc.start_voice_session(candidate, iv.id, db)["room_name"]

        def event(room, name):
            try:
                return prog.agent_event(db, room, name)["interview_status"]
            except prog.ProgressError as e:
                return e.code

        def answer(room, qid, number, seq, text=LONG):
            try:
                row, created = ans.record_answer(db, room, ans.AnswerSubmission(
                    question_id=qid, question_number=number, sequence=seq, kind="answer", transcript=text,
                    answered_at=datetime.utcnow()))
                return row, created
            except ans.AnswerError as e:
                return e.code, False

        def sessions(iv):
            return db.query(AiInterviewSession).filter(AiInterviewSession.interview_id == iv.id).count()

        def listed(iv):
            return next((i for i in ctx.my_interviews(candidate, db) if i["interview_id"] == iv.id), None)

        section("1. Status transitions: scheduled -> in_progress -> completed | scheduled (ended)")
        iv = new_interview()
        check("a new interview is scheduled, listed, not exhausted",
              status(iv) == "scheduled" and listed(iv) and listed(iv)["attempts_exhausted"] is False)
        before = sessions(iv)
        listed(iv)                                               # the page loading / refreshing
        check("loading or refreshing the page creates no session and no attempt",
              sessions(iv) == before and prog.started_attempts(db, iv.id) == 0)
        room = start(iv)
        check("pressing Start creates a session but does NOT consume an attempt, status unchanged",
              sessions(iv) == before + 1 and prog.started_attempts(db, iv.id) == 0 and status(iv) == "scheduled")
        check("an answer for a session whose agent never started is refused",
              answer(room, plan_[0]["id"], 1, 1)[0] == "not_started")
        check("an end report from a session that never started is refused (no transition)",
              event(room, "ended") == "not_started" and event(room, "completed") == "not_started"
              and status(iv) == "scheduled")
        check("scheduled -> in_progress when the agent starts", event(room, "started") == "in_progress"
              and prog.started_attempts(db, iv.id) == 1)
        check("a repeated 'started' is idempotent (still 1 attempt, still in_progress)",
              event(room, "started") == "in_progress" and prog.started_attempts(db, iv.id) == 1)
        row, created = answer(room, plan_[0]["id"], 1, 1)
        again, created_again = answer(room, plan_[0]["id"], 1, 1)
        check("a duplicate answer delivery stays ONE answer", created and not created_again and again.id == row.id)
        fu_row, _ = answer(room, fu["id"], 1, 2, "It cut forecast errors by a third.")
        check("a follow-up answer keeps its parent's question number", fu_row.question_number == 1
              and fu_row.question_id == fu["id"])
        check("...and cannot be filed under another number", answer(room, fu["id"], 2, 3)[0] == "question_mismatch")
        outside = next(q.id for q in db.query(ans.InterviewQuestion).filter(
            ans.InterviewQuestion.question_type == "main", ans.InterviewQuestion.is_active.is_(True))
            .order_by(ans.InterviewQuestion.id.desc()) if q.id not in {p["id"] for p in plan_})
        check("a main question outside the current plan is refused (adaptive stays within the plan)",
              answer(room, outside, 2, 3)[0] == "question_mismatch")
        check("an adaptively chosen plan question under the next number is accepted",
              not isinstance(answer(room, plan_[3]["id"], 2, 3)[0], str))
        check("in_progress -> completed", event(room, "completed") == "completed" and status(iv) == "completed")

        section("2. completed is terminal")
        check("a repeated 'completed' is harmless and still says completed", event(room, "completed") == "completed")
        check("a late 'ended' does not turn completed into scheduled", event(room, "ended") == "completed"
              and status(iv) == "completed")
        check("an answer after completion is refused", answer(room, plan_[1]["id"], 3, 9)[0] == "not_found")
        try:
            start(iv)
            check("a completed interview cannot be restarted", False)
        except svc.AiInterviewError as e:
            check("a completed interview cannot be restarted", e.code == "completed")
        check("...and after a refresh it is no longer offered at all", listed(iv) is None)
        check("the stored answers are still there", len(ans.answers_for_interview(db, iv.id)["sessions"][0]["answers"]) == 3)

        section("3. Early leave, stale sessions, attempts")
        iv2 = new_interview()
        a = start(iv2)
        event(a, "started")
        check("in_progress -> scheduled when the attempt ends early (retriable)", event(a, "ended") == "scheduled")
        check("an ended attempt's room cannot run again (re-join refused)", event(a, "started") == "attempt_finished")
        check("completed cannot follow an early end (invalid transition)", event(a, "completed") == "invalid_transition"
              and status(iv2) == "scheduled")
        b = start(iv2)                                          # a refresh + Start
        c = start(iv2)                                          # another tab: supersedes b
        check("sessions created by refreshes consume no attempt", prog.started_attempts(db, iv2.id) == 1)
        check("the replaced session cannot start", event(b, "started") == "superseded")
        check("...and holds no answers", answer(b, plan_[0]["id"], 1, 1)[0] == "not_started")
        check("the newest session starts the 2nd attempt", event(c, "started") == "in_progress"
              and prog.started_attempts(db, iv2.id) == 2)
        check("the stale session cannot end or complete the newest one's run",
              event(b, "ended") == "superseded" and event(b, "completed") == "superseded"
              and status(iv2) == "in_progress")
        check("the old, ended session cannot end it either", event(a, "ended") == "superseded"
              and status(iv2) == "in_progress")
        event(c, "ended")
        check("after 2 started attempts the list says exhausted (a refreshed page offers no Start)",
              listed(iv2)["attempts_exhausted"] is True)
        try:
            start(iv2)
            check("a third attempt is refused", False)
        except svc.AiInterviewError as e:
            check("a third attempt is refused", e.code == "attempts_exhausted")

        section("4. Permanent development test interview reuses one Interview row")
        test_iv = new_interview(
            status="TEST",
            location=ctx.DEVELOPMENT_TEST_INTERVIEW_LOCATION,
        )
        test_listing = listed(test_iv)
        check("test interview is listed beyond the normal application stage/time window",
              test_listing is not None and test_listing["is_test"] is True
              and test_listing["status"] == "test"
              and test_listing["scheduled_at"] is None
              and test_listing["attempts_exhausted"] is False)
        application.status = "screening"
        db.commit()
        room_a = start(test_iv)
        check("first test session starts against the existing interview row",
              event(room_a, "started") == "in_progress" and status(test_iv) == "in_progress")
        check("an early leave returns the persistent test record to TEST",
              event(room_a, "ended") == "TEST" and status(test_iv) == "TEST")
        check("an ended test room cannot be restarted",
              event(room_a, "started") == "attempt_finished")
        room_b = start(test_iv)
        check("re-entry issues a new room but reuses the same Interview ID",
              room_b != room_a and sessions(test_iv) == 2
              and listed(test_iv)["interview_id"] == test_iv.id)
        check("test re-entry bypasses the standard attempt cap",
              event(room_b, "started") == "in_progress"
              and prog.started_attempts(db, test_iv.id) == 2
              and listed(test_iv)["attempts_exhausted"] is False)
        check("completion is reported while the fixture remains marked as a test",
              event(room_b, "completed") == "completed"
              and listed(test_iv)["is_test"] is True)
        room_c = start(test_iv)
        check("a completed test interview can be entered again with its same ID",
              room_c != room_b and sessions(test_iv) == 3
              and status(test_iv) == "TEST"
              and test_iv.id == listed(test_iv)["interview_id"])
        event(room_c, "started")
        event(room_c, "ended")
        application.status = "interview"
        db.commit()

        section("4. A failed start consumes nothing")
        iv3 = new_interview()
        room3 = start(iv3)
        application.status = "screening"                        # HR moved the candidate on meanwhile
        db.commit()
        check("the agent's start is refused when the interview is no longer eligible",
              event(room3, "started") == "not_found" and status(iv3) == "scheduled")
        check("...and no attempt was counted", prog.started_attempts(db, iv3.id) == 0)
        application.status = "interview"
        db.commit()
    finally:
        db.close()


def agent_suite() -> None:
    section("5. Closing integrity (the agent)")
    from app.ai.interview.state import InterviewState as S

    async def last():
        m, s, c, a, committed, _ = rig(questions=plan()[1:2])
        await c.run_opening()
        d = await turn(a, LONG)
        decided = c.completed_normally
        c.on_agent_state("speaking")                    # the closing line starts playing
        state_ending, during = m.state, c.completed_normally
        c.on_agent_state("listening")                   # ...and has been heard
        return d, decided, state_ending, during, m.state, c.completed_normally, committed
    d, decided, ending, during, final, done, committed = asyncio.run(last())
    check("the last answer's decision is 'finish' - but deciding does not complete anything",
          d.kind == "finish" and decided is False)
    check("ENDING first, while the closing line plays (still not completed)", ending == S.ENDING and during is False)
    check("completed only after the closing line was heard", final == S.COMPLETED and done is True)
    check("the answer was made final before completion", len(committed) == 1)
    src = (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    body = src[src.index("async def _deliver_answers"):src.index("ctx.add_shutdown_callback(_deliver_answers)")]
    check("the answer drain happens before the completion report, which keeps its bounded retry",
          body.index("controller.flush_answers()") < body.index("await answers.drain()") < body.index("report_progress")
          and "attempts=END_ATTEMPTS" in body)

    section("6. Refresh in every state -> never a false completion, never a duplicate answer")

    async def refresh_at(stage):
        async def slow(*_):
            await asyncio.sleep(30)
        kw = {"decider": slow} if stage == "follow-up decision" else {"selector": slow} if stage == "adaptive selection" else {}
        qs = plan() if stage != "adaptive selection" else plan()[1:]
        m, s, c, a, committed, _ = rig(questions=qs, **kw)
        if stage != "connecting":
            await c.run_opening()
        if stage in ("follow-up decision", "adaptive selection"):
            task = asyncio.ensure_future(turn(a, LONG))
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        elif stage == "processing":
            await turn(a, LONG)
            c.on_agent_state("thinking")
        elif stage == "interviewer speaking":
            await turn(a, LONG)
            c.on_agent_state("speaking")
        elif stage == "applicant speaking":
            c.on_user_state("speaking")
        elif stage == "closing":
            m2, s2, c2, a2, committed2, _ = rig(questions=plan()[1:2])
            await c2.run_opening()
            await turn(a2, LONG)
            c2.on_agent_state("speaking")                      # closing playing, not yet heard
            m, c, committed = m2, c2, committed2
        c.on_close("participant_disconnected")                 # the page was refreshed / closed
        c.flush_answers()
        c.flush_answers()                                      # a duplicate shutdown
        return c.completed_normally, committed
    for stage in ("connecting", "interviewer speaking", "applicant speaking", "processing",
                  "follow-up decision", "adaptive selection", "closing"):
        done, committed = asyncio.run(refresh_at(stage))
        seqs = [r.sequence for r in committed]
        check(f"refresh during {stage}: reported 'ended' (never completed), answers unique",
              done is False and len(seqs) == len(set(seqs)) and all(r.text in SPOKEN for r in committed),
              f"{done} {seqs}")

    async def after_completed():
        m, s, c, a, committed, _ = rig(questions=plan()[1:2])
        await c.run_opening()
        await turn(a, LONG)
        c.on_agent_state("speaking")
        c.on_agent_state("listening")
        c.on_close("participant_disconnected")
        return c.completed_normally
    check("refresh after completion: it stays completed", asyncio.run(after_completed()) is True)


def frontend_mapping() -> None:
    section("7. The page's state mapping (frontend check script)")
    r = subprocess.run("npx tsx scripts/check-ai-interview-voice-ux.ts", cwd=str(ROOT / "frontend"),
                       capture_output=True, text=True, shell=True, timeout=300)
    check("check-ai-interview-voice-ux.ts passes: no 'Your turn' without listening, no 'Thinking' after the "
          "session ended, no 'Finishing' after completed, no Start when attempts are exhausted",
          r.returncode == 0 and "All AI Interview voice UX checks passed." in r.stdout, r.stdout[-400:])


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    if not CREATED:
        return 0
    with engine.begin() as conn:
        conn.execute(text("delete from ai_interview_sessions where interview_id = any(:i)"), {"i": CREATED})
        return conn.execute(text("delete from interviews where id = any(:i) and notes = :m"),
                            {"i": CREATED, "m": MARK}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 11.6.4 state integrity tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model

    capture = Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    try:
        backend_suite()
        agent_suite()
    finally:
        root.removeHandler(capture)
        print(f"\n  cleanup: removed {cleanup()} temporary interview(s) with their sessions and answers")
    frontend_mapping()
    section("8. Logs")
    leaked = [line for line in capture.lines for s in SPOKEN if s in line]
    check(f"{len(capture.lines)} log lines captured; none contains what the applicant said", not leaked, str(leaked[:2]))
    check("...and no LiveKit token or JWT", not any("eyJ" in line for line in capture.lines))
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
