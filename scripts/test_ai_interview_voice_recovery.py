"""AI Interview - Phase 11.6.3 voice error recovery tests. Deterministic, offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_voice_recovery

No LiveKit, no model, no microphone. The real agent turn gate, controller,
QuestionProgress and state machine run against a fake session; LiveKit's
failures are the events it would deliver (or not deliver) - a reply that
never plays, a session that closes, a cancelled turn. The worker's backend
clients run against fake transports. Session replacement and "completed
cannot restart" run the REAL backend services in process against ONE
temporary interview on applicant10's fixture application, deleted at the
end. Every log line of the run is captured and searched for applicant
speech. The browser half (reconnecting, microphone failures) is checked by
frontend/scripts/check-ai-interview-voice-ux.ts.
"""

import asyncio
import logging
import secrets
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_ai_interview_turn_taking import LONG, plan, rig, settle, shown_number, turn  # noqa: E402

passed = 0
failed: list[str] = []
SPOKEN: set[str] = set()          # every applicant utterance used below - must never be logged
MARK = "VOICE RECOVERY TEST"
CREATED: list[int] = []


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


def say(text: str) -> str:
    SPOKEN.add(text)
    return text


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))


def invariants(label, c, committed, *, answers=None, current=None):
    """The recovery invariants every error path must keep."""
    texts = [r.text for r in committed]
    # Every stored answer is made only of what the applicant actually said
    # (one utterance, or several merged) - never empty, never invented.
    spoken_words = set(" ".join(SPOKEN).split())
    check(f"{label}: no fake or empty answer",
          all(t.strip() and (t in SPOKEN or set(t.split()) <= spoken_words) for t in texts), str(texts))
    check(f"{label}: no duplicated answer", len({r.sequence for r in committed}) == len(committed)
          and len(texts) == len(set(zip(texts, [r.question_id for r in committed]))))
    if answers is not None:
        check(f"{label}: answers stored = {answers}", len(committed) == answers, str(len(committed)))
    if current is not None:
        cur = c.progress.current
        check(f"{label}: the interview is on question id {current}", cur is not None and cur.id == current,
              str(cur and cur.id))
    check(f"{label}: at most one follow-up per main question",
          all(sum(1 for r in committed if r.question_id == q.follow_up.id) <= 1
              for q in c.progress.questions if q.follow_up) and len(c.progress.followed_up) <= len(c.progress.questions))
    check(f"{label}: no main question asked twice", len(c.progress.asked) == len(set(c.progress.asked)))


# -- 1. LiveKit connection -----------------------------------------------------------------

def test_connection() -> None:
    section("1. LiveKit connection: drop, reconnect, failed reconnect")
    from app.ai.interview.state import InterviewState as S

    async def drop_and_reconnect():
        m, s, c, a, committed, published = rig()
        await c.run_opening()
        said_before, state_before = len(s.said), m.state
        await settle()
        number_before = shown_number(published)
        # A network drop: LiveKit is reconnecting - the agent receives NO turn
        # and no state events for the applicant. Nothing is sent, nothing moves.
        await asyncio.sleep(0.01)
        # Reconnected: LiveKit delivers the pending state again (twice, as a
        # duplicate recovery event can) - the same state, no replay.
        c.on_agent_state("listening")
        c.on_agent_state("listening")
        await settle()
        return (m.state, state_before, len(s.said), said_before, shown_number(published), number_before,
                committed, c)
    (state, state_before, said, said_before, number, number_before, committed, c) = asyncio.run(drop_and_reconnect())
    check("temporary disconnect: state preserved, nothing committed", state == state_before == S.LISTENING
          and committed == [])
    check("reconnect: no welcome or question replayed", said == said_before == 2)
    check("reconnect: no question advance, number unchanged", number == number_before == 1 and c.progress.number == 1)
    check("duplicate recovery events change nothing", len(c.progress.answers) == 0)

    async def failed_reconnect():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, say(LONG))
        c.on_agent_state("speaking")                         # answer 1 heard -> final
        c.on_agent_state("listening")
        await turn(a, say("I paired with a colleague and traced the failing job."))   # answer 2, reply not yet heard
        c.on_close("participant_disconnected")               # the applicant never came back
        c.on_close("participant_disconnected")               # duplicate close event
        c.flush_answers()                                    # the worker's shutdown callback
        c.flush_answers()
        return m, c, committed
    m, c, committed = asyncio.run(failed_reconnect())
    check("failed reconnect: the session ends, NOT as a completed interview",
          m.state == S.COMPLETED and c.completed_normally is False)
    check("...the worker would report 'ended' (retriable), never 'completed'",
          ("completed" if c.completed_normally else "ended") == "ended")
    invariants("failed reconnect", c, committed, answers=2)
    check("...both answers kept, each once, in order", [(r.sequence, r.question_id) for r in committed]
          == [(1, 11), (2, 12)], str([(r.sequence, r.question_id) for r in committed]))


# -- 2. Microphone and STT -----------------------------------------------------------------------

def test_mic_and_stt() -> None:
    section("2. Microphone / speech-to-text failures produce no answer")
    calls: list = []

    async def decider(*args):
        calls.append(args)
        return True

    async def run():
        m, s, c, a, committed, published = rig(decider=decider)
        await c.run_opening()
        # A dead or blocked microphone delivers no audio: no turn at all.
        # Speech-to-text that fails delivers an EMPTY transcript, or none.
        results = [await turn(a, t) for t in ("", "   ", "\n")]
        c.flush_answers()
        await settle()
        return results, c, committed, m, published
    results, c, committed, m, published = asyncio.run(run())
    check("empty / blank transcripts are refused (no answer, no reply)", results == [None, None, None])
    check("...no follow-up or adaptive decision was asked about them", calls == [])
    check("...the question did not advance", c.progress.current.id == 11 and shown_number(published) == 1)
    check("...nothing was stored, even at shutdown", committed == [])
    check("...and the interview is still waiting for the applicant", m.state.value == "listening")


# -- 3. Model (decision) failures --------------------------------------------------------------------

def test_decision_failures() -> None:
    section("3. GPT decision failures fall back - never stuck, never duplicated")
    from app.ai.interview.state import InterviewState as S

    async def boom(*_a):
        raise RuntimeError("model unavailable")

    async def follow_up_fails():
        m, s, c, a, committed, _ = rig(decider=boom)
        await c.run_opening()
        d = await turn(a, say(LONG))
        c.on_agent_state("speaking")
        return d, m, c, committed
    d, m, c, committed = asyncio.run(follow_up_fails())
    check("follow-up decision fails -> no follow-up, the next bank question", d.kind == "advance"
          and d.say_after == plan()[1].text and not c.progress.followed_up)
    check("...not stuck in FOLLOW_UP_DECISION: the next question is being asked", m.state == S.ASKING)
    invariants("follow-up failure", c, committed, answers=1, current=12)

    async def adaptive_fails():
        m, s, c, a, committed, _ = rig(questions=plan()[1:], selector=boom)
        await c.run_opening()
        d = await turn(a, say(LONG))
        c.on_agent_state("speaking")
        return d, m, c, committed
    d, m, c, committed = asyncio.run(adaptive_fails())
    check("adaptive selection fails -> first not-yet-asked main question (bank order)",
          d.say_after == plan()[2].text and m.state == S.ASKING)
    invariants("adaptive failure", c, committed, answers=1, current=13)


# -- 4. TTS failure -----------------------------------------------------------------------------------

def test_tts_failure() -> None:
    section("4. TTS failure: nothing is treated as spoken")
    from app.ai.interview.state import InterviewState as S

    async def run():
        m, s, c, a, committed, published = rig()
        await c.run_opening()
        await turn(a, say(LONG))
        c.on_agent_state("thinking")
        # TTS failed: LiveKit never reaches "speaking" and returns to listening.
        c.on_agent_state("listening")
        await settle()
        after_failure = (list(committed), shown_number(published), c.progress.current.id, m.state)
        # The applicant speaks again (e.g. "hello?"): it joins the same answer.
        await turn(a, say("Hello, can you hear me?"))
        c.on_agent_state("speaking")                         # this time the reply plays
        await settle()
        return after_failure, committed, shown_number(published), c
    (after, committed, number, c) = asyncio.run(run())
    stored, shown, current, state = after
    check("the generated reply was never heard: no answer stored for it", stored == [])
    check("...the question number was not advanced by generated text", shown == 1)
    check("...question 1 stays open, the interview listening", current == 11 and state == S.LISTENING)
    check("once a reply plays, ONE answer is stored (the merged turn) and question 2 is shown",
          len(committed) == 1 and committed[0].text == f"{LONG} Hello, can you hear me?" and number == 2)
    invariants("TTS failure", c, committed, answers=1, current=12)


# -- 5. Backend failures -------------------------------------------------------------------------------

def test_backend_clients() -> None:
    section("5. Backend failures: answers and progress retried, never duplicated")
    from app.ai.interview import progress_client as pc
    from app.ai.interview.answer_client import DRAIN_TIMEOUT_S, AnswerSink
    from app.ai.interview.questions import AnswerRecord

    def record(seq, text):
        r = AnswerRecord(11, 1, say(text), "answer", len(text.split()))
        r.sequence = seq
        return r

    async def answers(statuses):
        posted: list[dict] = []
        queue = list(statuses)

        async def post(payload):
            posted.append(payload)
            status = queue.pop(0)
            if isinstance(status, Exception):
                raise status
            return status
        sink = AnswerSink("room", post=post)
        import app.ai.interview.answer_client as ac
        saved = ac.RETRY_DELAYS_S
        ac.RETRY_DELAYS_S = (0.0, 0.0)
        try:
            sink.submit([record(1, "I rebuilt the forecasting pipeline after it failed.")])
            await sink.drain(5)
        finally:
            ac.RETRY_DELAYS_S = saved
        return sink, posted

    sink, posted = asyncio.run(answers([503, ConnectionError("down"), 200]))
    check("answer save: transient 503 / network error retried, then delivered once", sink.delivered == [1]
          and len(posted) == 3 and all(p == posted[0] for p in posted))
    check("...every retry is the SAME payload (sequence 1) - the backend keeps one row",
          {p["sequence"] for p in posted} == {1})
    sink, posted = asyncio.run(answers([409]))
    check("answer save: a refusal (4xx) is not retried", sink.refused == [(1, 409)] and len(posted) == 1)
    sink, posted = asyncio.run(answers([ConnectionError("down")] * 3))
    check("answer save: still failing -> reported undelivered, never faked", sink.undelivered == [1]
          and sink.delivered == [])

    async def progress(statuses, **kw):
        sent: list[str] = []
        queue = list(statuses)

        async def fake_send(room, event, timeout):
            sent.append(event)
            s = queue.pop(0)
            if isinstance(s, Exception):
                raise s
            return s
        real = pc._send
        pc._send = fake_send
        try:
            ok = await pc.report_progress("room", kw.pop("event", "completed"), **kw)
        finally:
            pc._send = real
        return ok, sent

    ok, sent = asyncio.run(progress([503, 200], attempts=pc.END_ATTEMPTS, pause=0))
    check("progress: a transient failure of 'completed' is retried and delivered", ok is True and sent == ["completed"] * 2)
    ok, sent = asyncio.run(progress([404], attempts=pc.END_ATTEMPTS, pause=0))
    check("progress: a refusal (4xx) is final - not retried, no duplicate transition", ok is False and len(sent) == 1)
    ok, sent = asyncio.run(progress([TimeoutError(), TimeoutError()], attempts=pc.END_ATTEMPTS, pause=0))
    check("progress: still failing -> False (the interview is NOT reported completed)", ok is False and len(sent) == 2)
    ok, sent = asyncio.run(progress([ConnectionError(), 200], event="started",
                                    attempts=pc.STARTED_ATTEMPTS, pause=0))
    check("progress: a transient failure of 'started' is retried once", ok is True and sent == ["started"] * 2)
    budget = DRAIN_TIMEOUT_S + pc.END_ATTEMPTS * pc.TIMEOUT_S + (pc.END_ATTEMPTS - 1) * pc.END_PAUSE_S
    check(f"shutdown: answer drain + end report with retry = {budget:.1f} s, inside LiveKit's 10 s", budget < 10.0)
    src = (ROOT / "app/ai/interview/worker.py").read_text(encoding="utf-8")
    body = src[src.index("async def _deliver_answers"):src.index("ctx.add_shutdown_callback(_deliver_answers)")]
    check("the worker reports the end AFTER the answers are drained, with the bounded retry",
          body.index("await answers.drain()") < body.index("report_progress")
          and "attempts=END_ATTEMPTS" in body and "if started:" in body)


# -- 6. Leaving, recovery mid-decision / mid-speech ----------------------------------------------------

def test_leaving() -> None:
    section("6. The applicant leaves - early, mid-decision, mid-speech, after completion")
    from app.ai.interview.state import InterviewState as S

    async def early():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, say(LONG))
        c.on_agent_state("speaking")
        c.on_agent_state("listening")
        c.on_close("participant_disconnected")
        c.flush_answers()
        return c, committed
    c, committed = asyncio.run(early())
    check("early leave: reported 'ended' (retriable), not completed", c.completed_normally is False)
    invariants("early leave", c, committed, answers=1)

    async def after_completion():
        m, s, c, a, committed, _ = rig(questions=plan()[1:2])
        await c.run_opening()
        await turn(a, say(LONG))
        c.on_agent_state("speaking")
        c.on_agent_state("listening")                        # closing heard -> COMPLETED
        c.on_close("participant_disconnected")               # then the applicant leaves
        c.flush_answers()
        return m, c, committed
    m, c, committed = asyncio.run(after_completion())
    check("leaving AFTER completion keeps it completed (a later close does not undo it)",
          m.state == S.COMPLETED and c.completed_normally is True)
    invariants("after completion", c, committed, answers=1)

    for label, kind in (("follow-up decision", "decider"), ("adaptive selection", "selector")):
        async def mid_decision(kind=kind):
            asked: list = []

            async def slow(*args):
                asked.append(args)
                await asyncio.sleep(30)
            m, s, c, a, committed, _ = rig(questions=plan() if kind == "decider" else plan()[1:],
                                           **{kind: slow})
            await c.run_opening()
            task = asyncio.ensure_future(turn(a, say("I lead the data team and build forecasting tools.")))
            await asyncio.sleep(0.01)
            task.cancel()                                     # the connection dropped mid-decision
            try:
                await task
            except asyncio.CancelledError:
                pass
            c.on_close("participant_disconnected")
            c.flush_answers()
            return asked, c, committed
        asked, c, committed = asyncio.run(mid_decision())
        check(f"recovery during the {label}: asked once, the answer kept once, nothing advanced",
              len(asked) == 1 and len(committed) == 1 and c.completed_normally is False)
        invariants(f"during the {label}", c, committed, answers=1)

    async def while_ai_speaking():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, say(LONG))
        c.on_agent_state("speaking")                          # reply playing
        c.on_close("participant_disconnected")
        c.flush_answers()
        return c, committed
    c, committed = asyncio.run(while_ai_speaking())
    check("drop while the AI is speaking: the heard answer stays stored once", len(committed) == 1)
    invariants("while AI speaking", c, committed, answers=1)

    async def while_applicant_speaking():
        m, s, c, a, committed, _ = rig()
        await c.run_opening()
        await turn(a, say("At my last job I"))
        c.on_agent_state("thinking")
        c.on_agent_state("listening")                         # still talking: reopened
        c.on_close("participant_disconnected")                # ...and then the line dropped
        c.flush_answers()
        return c, committed
    c, committed = asyncio.run(while_applicant_speaking())
    check("drop while the applicant is mid-answer: the part they gave is kept once, as said",
          [r.text for r in committed] == ["At my last job I"])
    invariants("while applicant speaking", c, committed, answers=1)


# -- 7. Session replacement and completed interviews (real backend services) ------------------------------

def test_sessions() -> None:
    section("7. Newest room only; a completed interview cannot restart (backend, in process)")
    from app.database import SessionLocal
    from app.models import Application, Candidate, Interview, User
    from app.services import ai_interview_service, interview_answer_service as ans
    from app.services import interview_context_service as ctx, interview_progress_service as prog
    from app.services import question_bank_service as qb
    from scripts.test_ai_interview_cv_context import APPLICANT_MANY_CVS

    db = SessionLocal()
    try:
        candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                     .filter(User.email == APPLICANT_MANY_CVS).one())
        application = (db.query(Application).filter(Application.candidate_id == candidate.id)
                       .order_by(Application.id).first())
        application.status = "interview"                      # HR-approved (fixture application)
        interview = Interview(application_id=application.id, scheduled_at=datetime.now().replace(microsecond=0),
                              status="scheduled", location=MARK, notes=MARK)
        db.add(interview)
        db.commit()
        CREATED.append(interview.id)
        old = ctx.bind_room(db, f"smarthr-ai-interview-vr{secrets.token_hex(6)}", interview, candidate, 10)
        new = ctx.bind_room(db, f"smarthr-ai-interview-vr{secrets.token_hex(6)}", interview, candidate, 10)
        old_room, new_room = old.room_name, new.room_name

        try:
            prog.agent_event(db, old_room, prog.STARTED)
            check("the replaced (older) room cannot start the interview", False)
        except prog.ProgressError as e:
            check("the replaced (older) room cannot start the interview", e.code == "superseded")
        check("...and the status is untouched", db.get(Interview, interview.id).status == "scheduled")
        check("the newest room starts it", prog.agent_event(db, new_room, prog.STARTED)["interview_status"]
              == "in_progress")
        for event in (prog.ENDED, prog.COMPLETED):
            try:
                prog.agent_event(db, old_room, event)
                check(f"the older room cannot report '{event}' for the newest session", False)
            except prog.ProgressError as e:
                check(f"the older room cannot report '{event}' for the newest session", e.code == "superseded")
        check("...the newest session's status was not overwritten",
              db.get(Interview, interview.id).status == "in_progress")

        plan_ = qb.interview_plan(db)
        row, created = ans.record_answer(db, new_room, ans.AnswerSubmission(
            question_id=plan_[0]["id"], question_number=1, sequence=1, kind="answer",
            transcript=say("I rebuilt the forecasting pipeline after it failed."), answered_at=datetime.utcnow()))
        again, created_again = ans.record_answer(db, new_room, ans.AnswerSubmission(
            question_id=plan_[0]["id"], question_number=1, sequence=1, kind="answer",
            transcript="I rebuilt the forecasting pipeline after it failed.", answered_at=datetime.utcnow()))
        check("a retried answer (same sequence) is the same row - no duplicate", created and not created_again
              and again.id == row.id)
        check("the answer belongs to the room's OWN session", row.session_id == new.id)

        check("a transient progress failure is simply repeated: 'ended' twice = one transition",
              prog.agent_event(db, new_room, prog.ENDED)["interview_status"] == "scheduled"
              and prog.agent_event(db, new_room, prog.ENDED)["interview_status"] == "scheduled")
        check("...the stored answer survives the early end", ans.answers_for_interview(db, interview.id)
              ["sessions"][0]["answers"][0]["answer_id"] == row.id)

        third = ctx.bind_room(db, f"smarthr-ai-interview-vr{secrets.token_hex(6)}", interview, candidate, 10)
        prog.agent_event(db, third.room_name, prog.STARTED)
        prog.agent_event(db, third.room_name, prog.COMPLETED)
        check("completed only by a completion report from the newest room",
              db.get(Interview, interview.id).status == "completed")
        try:
            ai_interview_service.start_voice_session(candidate, interview.id, db)
            check("a completed interview cannot be started again", False)
        except ai_interview_service.AiInterviewError as e:
            check("a completed interview cannot be started again", e.code == "completed")
    finally:
        db.close()


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
    print("SmartHR - AI Interview Phase 11.6.3 voice error recovery tests")
    import app.ai.interview_analysis as analysis_mod
    from app.ai import provider

    def no_model(*_a, **_k):
        raise RuntimeError("no model may be called in this suite")
    provider.get_provider = no_model
    analysis_mod.get_provider = no_model

    capture = LogCapture()
    root = logging.getLogger()
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    try:
        test_connection()
        test_mic_and_stt()
        test_decision_failures()
        test_tts_failure()
        test_backend_clients()
        test_leaving()
        test_sessions()
    finally:
        root.removeHandler(capture)
        removed = cleanup()
        print(f"\n  cleanup: removed {removed} temporary interview(s) with their sessions and answers")
    section("8. No applicant transcript in any log line")
    leaked = [line for line in capture.lines for s in SPOKEN if len(s) > 12 and s in line]
    check(f"{len(capture.lines)} log lines captured; none contains what the applicant said", not leaked,
          str(leaked[:2]))
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
