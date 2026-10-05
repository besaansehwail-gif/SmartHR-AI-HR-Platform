"""AI Interview - Phase 12 Multi-Agent HR Intelligence. Deterministic, offline.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_multi_agent

No LiveKit, no real model, no interview. The model is a fake provider (the
Analysis Agent's one tool call); every other model path is pinned to
SMARTHR_LLM_PROVIDER=none so nothing can reach a real one. The REAL
orchestrator, report and recruitment agents, analysis service, report service
and matching service run in process against ONE temporary interview on
applicant10's fixture application (two answers stored through the real
answer service), deleted at the end. RBAC runs over HTTP on its own server
(port 8058, fake LiveKit credentials).
"""

import ast
import base64
import json
import logging
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Before anything reads a setting: no real model anywhere in this process.
os.environ["SMARTHR_LLM_PROVIDER"] = "none"

from scripts import test_ai_interview_cv_context as p5  # noqa: E402
from scripts import test_helpers as e2e  # noqa: E402
from scripts.test_ai_interview_report import FORBIDDEN_KEYS, keys_of  # noqa: E402

PORT = 8058
BASE = f"http://127.0.0.1:{PORT}"
MARK = "MULTI AGENT TEST"
CREATED: list[int] = []

passed = 0
failed: list[str] = []

TRANSCRIPT_SENTINEL = "synthetic-transcript-marker"
TRANSCRIPT_1 = f"I rebuilt the forecasting pipeline in Python after it failed, and I documented every step. {TRANSCRIPT_SENTINEL}"
TRANSCRIPT_2 = "I worked with the data team and we tested every change with SQL checks before release."
TRANSCRIPT_3 = "I usually plan my week on Monday and review it on Friday with my manager."
PAYLOAD_1 = {
    "addresses_question": "fully",
    "summary": "the applicant described rebuilding the forecasting pipeline in Python after it failed.",
    "evidence": [{"point": "rebuilt the forecasting pipeline", "quote": "I rebuilt the forecasting pipeline",
                  "type": "experience"},
                 {"point": "an invented claim", "quote": "I led a team of forty engineers", "type": "experience"}],
    "skills_mentioned": [{"skill": "Python", "quote": "in Python"}],
    "job_requirements_referenced": [], "cv_relation": [], "specificity": "specific", "clarity": "clear",
    "not_covered": ["how the result was measured"],
}


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


CAP = Capture()


class FakeProvider:
    name, model, configured = "fake", "fake-gpt-4o", True

    def __init__(self, payloads=None, error=None):
        self.payloads, self.error, self.calls = list(payloads or []), error, []

    def complete(self, system, messages, tools=None):
        from app.ai.provider import LlmReply, ToolCall
        self.calls.append({"system": system, "messages": messages})
        if self.error is not None:
            raise self.error
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        return LlmReply(tool_call=ToolCall(tools[0]["name"], json.loads(json.dumps(payload))))


def use_provider(provider) -> None:
    import app.ai.interview_analysis as analysis_mod
    analysis_mod.get_provider = lambda *_a, **_k: provider


def strings_of(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from strings_of(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from strings_of(v)
    elif isinstance(value, str):
        yield value


def imports_of(rel: str) -> set[str]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


# -- 1. Roles ------------------------------------------------------------------------------------

def test_roles() -> None:
    section("1. Four roles, one live - responsibilities and model use stated and separated")
    from app.ai.hr_intelligence import roles as R

    check("four roles: interviewer, analysis, report, recruitment",
          [r.name for r in R.ROLES] == ["interviewer", "analysis", "report", "recruitment"])
    live = [r for r in R.ROLES if r.stage == R.LIVE]
    check("exactly one live role - the interviewer - and it alone uses the live conversation model",
          live == [R.INTERVIEWER] and [r for r in R.ROLES if r.model_use == R.LIVE_CONVERSATION] == [R.INTERVIEWER])
    check("the analysis role is the only post-interview model use",
          [r for r in R.ROLES if r.model_use == R.POST_INTERVIEW_ANALYSIS] == [R.ANALYST])
    check("report and recruitment make no model call", R.REPORTER.model_use == R.RECRUITER.model_use == R.NO_MODEL)
    check("report and recruitment write nothing; analysis writes only the analyses table",
          R.REPORTER.writes == R.RECRUITER.writes == () and R.ANALYST.writes == ("ai_interview_answer_analyses",))
    check("the post-interview order is analysis -> report -> recruitment (the interviewer is not in it)",
          R.POST_INTERVIEW_ORDER == ("analysis", "report", "recruitment"))
    check("every role states it never makes a hiring decision / score",
          all(any(w in " ".join(r.never) for w in ("hiring decision", "score")) for r in R.ROLES))
    check("the analysis role is never shown the match score; recruitment never recalculates it",
          "score" not in R.ANALYST.receives and "score" not in R.RECRUITER.receives
          and any("recalculate" in n for n in R.RECRUITER.never))


# -- 2. Boundaries, checked against the code --------------------------------------------------------

def test_boundaries() -> None:
    section("2. Boundaries enforced by the code, not by a prompt")
    interviewer = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "app/ai/interview").glob("*.py"))
    banned_live = ("app.ai.hr_intelligence", "app.ai.interview_analysis", "app.services", "app.models",
                   "app.database", "sqlalchemy")
    hits = [f"{f}: {m}" for f in interviewer for m in imports_of(f) if m.startswith(banned_live)]
    check("the interviewer (app/ai/interview/) imports no analysis, report, intelligence, service or DB code",
          not hits, "; ".join(hits[:3]))

    analysis_imports = imports_of("app/ai/interview_analysis.py")
    check("the Analysis Agent imports no live-interview control (agent, controller, worker, livekit)",
          not [m for m in analysis_imports if m.startswith(("app.ai.interview.agent", "app.ai.interview.controller",
                                                           "app.ai.interview.worker", "app.ai.interview.questions",
                                                           "app.ai.interview.state", "livekit"))])
    svc = (ROOT / "app/services/interview_analysis_service.py").read_text(encoding="utf-8")
    check("the analysis service never reports progress or writes an interview's status",
          "interview_progress_service" not in svc and "interview.status" not in svc and "Interview.status" not in svc)

    pure = ["app/ai/hr_intelligence/roles.py", "app/ai/hr_intelligence/contracts.py",
            "app/ai/hr_intelligence/report_agent.py", "app/ai/hr_intelligence/matching_agent.py"]
    banned_pure = ("app.ai.provider", "livekit", "app.models", "app.database", "sqlalchemy", "app.services",
                   "app.ai.interview.")
    hits = [f"{f}: {m}" for f in pure for m in imports_of(f) if m.startswith(banned_pure)]
    check("report / recruitment agents, contracts and roles: no model provider, no LiveKit, no DB, no service",
          not hits, "; ".join(hits[:3]))
    orch = imports_of("app/ai/hr_intelligence/orchestrator.py")
    check("the orchestrator reaches data through the existing services (and no model provider, no LiveKit)",
          {"app.services.interview_analysis_service", "app.services.interview_report_service",
           "app.services.interview_matching_service"} <= orch
          and not [m for m in orch if m.startswith(("app.ai.provider", "livekit", "app.ai.interview."))])

    live_sites = []
    for path in (ROOT / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "AgentSession(" in src or "rtc_session(" in src:
            live_sites.append(path.relative_to(ROOT).as_posix())
    check("the interviewer is the only live conversation agent (one AgentSession / rtc_session site)",
          live_sites == ["app/ai/interview/worker.py"], str(live_sites))
    providers = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "app/ai/hr_intelligence").glob("*.py")
                       if "get_provider" in p.read_text(encoding="utf-8"))
    check("no HR-intelligence module calls a model provider", providers == [], str(providers))
    router = (ROOT / "app/routers/ai_interview.py").read_text(encoding="utf-8")
    route = router[router.index('@router.post("/intelligence/{interview_id}"'):]
    check("the intelligence route is Admin/HR (require_roles(*REVIEW_ROLES)), REVIEW_ROLES = (1, 2)",
          route.startswith('@router.post("/intelligence/{interview_id}", dependencies=[Depends(require_roles(*REVIEW_ROLES))])')
          and "REVIEW_ROLES = (1, 2)" in router)


# -- 3. Contracts ----------------------------------------------------------------------------------

def test_contracts() -> None:
    section("3. Structured inputs: no credentials, no contact PII, no objects")
    from app.ai.hr_intelligence.contracts import AgentInputError, assert_safe_input, unsafe_paths
    from app.ai.interview_analysis import AnalysisInput

    ok = AnalysisInput(question="Tell me about yourself.", transcript=TRANSCRIPT_1,
                       job={"title": "Data Analyst", "requirements": ["Python"]},
                       cv={"skills": ["Python"], "certifications": [{"name": "AWS", "issuer": "Amazon"}]},
                       matching_skills=["Python"], skill_gaps=["SQL"])
    check("a real Analysis input (question, transcript, job, CV whitelist, skills) is accepted", unsafe_paths(ok) == [])
    jwt_sentinel = ".".join(
        base64.urlsafe_b64encode(part).decode("ascii").rstrip("=")
        for part in (b'{"alg":"none"}', b'{"test":true}', b"inert-signature")
    )
    bearer_sentinel = "Bearer " + ("x" * 24)
    cases = {
        "password": {"password": "x"}, "token": {"ctx_token": "x"}, "api key": {"job": {"api_key": "x"}},
        "livekit secret": {"livekit_api_secret": "x"}, "authorization": {"headers": {"Authorization": "x"}},
        "email": {"cv": {"email": "candidate@example.com"}}, "phone": {"phone": "+1-202-555-0101"},
        "full name": {"cv": {"full_name": "Samer Ali"}}, "bearer value": {"note": bearer_sentinel},
        "jwt value": {"x": [jwt_sentinel]},
        "an object (e.g. a DB session)": {"db": object()},
    }
    for label, value in cases.items():
        try:
            assert_safe_input(value, "analysis")
            check(f"refused: {label}", False)
        except AgentInputError as e:
            check(f"refused: {label} (reported by path, never by value)",
                  "x" != str(e) and "candidate@example.com" not in str(e) and "Samer" not in str(e))
    check("saying the word 'bearer' in an answer is not a token", unsafe_paths({"t": "the bearer of bad news"}) == [])


# -- 4. Recruitment agent ----------------------------------------------------------------------------

def test_recruitment() -> None:
    section("4. Recruitment agent: explains the existing match - no score, no recalculation, no decision")
    from app.ai.hr_intelligence import matching_agent as M
    from app.ai.interview.matching_context import decision_or_score_claim
    from app.ai.interview_analysis import verdict_claim

    job = {"title": "Data Analyst", "requirements": ["Python", "SQL", "Tableau"]}
    existing = {"score": 33, "matching_skills": ["Python"], "skill_gaps": ["SQL", "Tableau"]}
    data = M.input_from(job, "available", existing)
    check("the input carries the existing lists - and has no score field at all",
          data.matching_skills == ("Python",) and data.skill_gaps == ("SQL", "Tableau")
          and not hasattr(data, "score"))
    out = M.explain(data)
    check("one explanation per matching skill and per requirement not evidenced (the existing lists, as they are)",
          [m["skill"] for m in out["matching_skills"]] == ["Python"]
          and [g["requirement"] for g in out["requirements_not_evidenced"]] == ["SQL", "Tableau"])
    check("no score, rank, recommendation or decision key; the number 33 appears nowhere",
          not [p for p, k in keys_of(out) if FORBIDDEN_KEYS.search(k)] and "33" not in json.dumps(out))
    sentences = [s for s in strings_of(out) if s not in (out["disclaimer"], out["basis"])]
    check("no explanation is a verdict, a score or 'the applicant lacks ...'",
          not [s for s in sentences if verdict_claim(s) or decision_or_score_claim(s)])
    check("a gap is described as missing evidence", all("missing evidence" in g["explanation"]
                                                        for g in out["requirements_not_evidenced"]))
    check("labelled: is_hiring_decision false, no model call", out["is_hiring_decision"] is False
          and out["model_calls"] == 0)
    none = M.explain(M.input_from(job, "unavailable", existing))
    check("no matching result: nothing invented (no skills, no gaps), said plainly",
          none["status"] == "unavailable" and none["matching_skills"] == [] == none["requirements_not_evidenced"])


# -- 5. Report agent -------------------------------------------------------------------------------

def _report(answers, completed=True):
    counts = {"completed": sum(a["analysis_status"] == "completed" for a in answers),
              "failed": sum(a["analysis_status"] == "failed" for a in answers),
              "pending": sum(a["analysis_status"] == "pending" for a in answers)}
    return {"interview": {"job_title": "Data Analyst"}, "session": {"session_id": 1},
            "answers": answers, "meta": {"state": "ready" if answers else "no_answers"},
            "summary": {"answered_count": len(answers), "analysis_status_counts": counts,
                        "addresses_question_counts": {"addressed": 1, "partially_addressed": 0,
                                                      "not_addressed": 0, "unclear": 0},
                        "requirements_referenced": ["Python"], "requirements_not_referenced": ["SQL"],
                        "requirements_basis": "completed_analyses", "complete": completed,
                        "skills_mentioned": [{"skill": "Python"}]}}


def _answer(seq, status, transcript, qid=11, analysis=None):
    return {"question_id": qid, "question_number": 1, "question_text": "Tell me about yourself.",
            "question_type": "main", "sequence": seq, "transcript": transcript, "analysis_status": status,
            "analysis": analysis}


def test_report_agent() -> None:
    section("5. Report agent: composed from stored analysis - never invents, never judges")
    from app.ai.hr_intelligence.report_agent import build_brief
    from app.ai.interview_analysis import verdict_claim

    analysis = {**PAYLOAD_1, "evidence": PAYLOAD_1["evidence"] + [
        {"point": "earlier part", "quote": "Yes, briefly", "type": "other"}]}
    report = _report([_answer(1, "completed", "Yes, briefly.", analysis=None) | {"analysis_status": "failed"},
                      _answer(2, "completed", TRANSCRIPT_1, analysis=analysis),
                      _answer(3, "pending", TRANSCRIPT_3, qid=12)], completed=False)
    brief = build_brief(report)
    a2 = brief["answers"][1]
    check("a stored quote found in what was said is kept, with its answer sequence",
          {"quote": "I rebuilt the forecasting pipeline", "sequence": 2} ==
          {k: a2["evidence"][0][k] for k in ("quote", "sequence")})
    check("a quote that is NOT in the transcript is dropped and counted (never shown)",
          all("forty engineers" not in e["quote"] for e in a2["evidence"]) and brief["unverified_quotes_dropped"] == 1)
    check("a quote from an earlier part of the same answer is still kept", any(e["quote"] == "Yes, briefly"
                                                                                for e in a2["evidence"]))
    check("the summary and skills are the stored ones, copied", a2["summary"] == PAYLOAD_1["summary"]
          and a2["skills_mentioned"] == ["Python"])
    check("failed / pending answers are 'not analysed' - no evidence, no negative claim",
          brief["answers"][0]["evidence"] == [] and "could not be analysed" in brief["answers"][0]["headline"]
          and "not been analysed" in brief["answers"][2]["headline"])
    check("partial analysis is said to be partial",
          any("describe the analysed answers only" in s for s in brief["overview"]))
    check("the brief carries no transcript (no key, no transcript text), no score / rank / decision key",
          not [k for _, k in keys_of(brief) if k == "transcript"] and TRANSCRIPT_SENTINEL not in json.dumps(brief)
          and TRANSCRIPT_1 not in json.dumps(brief) and TRANSCRIPT_3 not in json.dumps(brief)
          and not [p for p, k in keys_of(brief) if FORBIDDEN_KEYS.search(k)])
    composed = brief["overview"] + [a["headline"] for a in brief["answers"]]
    check("no composed sentence is a verdict or recommendation", not [s for s in composed if verdict_claim(s)])
    check("labelled: stored analyses, no model call, not a hiring decision",
          brief["provenance"] == "stored_analyses" and brief["model_calls"] == 0 and brief["is_hiring_decision"] is False)
    empty = build_brief(_report([]))
    check("no answers: says so, invents nothing", empty["answers"] == [] and "No AI Interview answers" in empty["overview"][0])


# -- 6-8. Orchestration against the real services ---------------------------------------------------

def make_fixture(db):
    from app.models import Application, Candidate, Interview, User
    from app.services import interview_answer_service as ans, interview_context_service as ctx
    from app.services import question_bank_service as qb

    candidate = (db.query(Candidate).join(User, User.id == Candidate.user_id)
                 .filter(User.email == p5.APPLICANT_MANY_CVS).one())
    application = (db.query(Application).filter(Application.candidate_id == candidate.id)
                   .order_by(Application.id).first())
    application.status = "interview"
    interview = Interview(application_id=application.id, scheduled_at=datetime.now().replace(microsecond=0),
                          status="scheduled", location=MARK, notes=MARK)
    db.add(interview)
    db.commit()
    CREATED.append(interview.id)
    room = ctx.bind_room(db, f"smarthr-ai-interview-ma{secrets.token_hex(6)}", interview, candidate, 10).room_name
    e2e.mark_session_started(room)
    plan = qb.interview_plan(db)
    for seq, (number, text) in enumerate([(1, TRANSCRIPT_1), (2, TRANSCRIPT_2)], start=1):
        ans.record_answer(db, room, ans.AnswerSubmission(
            question_id=plan[number - 1]["id"], question_number=number, sequence=seq, kind="answer",
            transcript=text, answered_at=datetime.utcnow()))
    interview = db.get(Interview, interview.id)
    interview.status = "completed"          # the interview is over
    db.commit()
    user = db.query(User).filter(User.id == candidate.user_id).one()
    return interview.id, room, plan, {"email": user.email, "first": candidate.first_name,
                                      "last": candidate.last_name, "phone": candidate.phone}


def analyses_of(db, interview_id):
    from sqlalchemy import text
    return db.execute(text("""select n.answer_id, n.status, n.error_code from ai_interview_answer_analyses n
                              join ai_interview_answers a on a.id = n.answer_id
                              where a.interview_id = :i order by n.answer_id"""), {"i": interview_id}).all()


def answers_of(db, interview_id):
    from sqlalchemy import text
    return db.execute(text("select id, sequence, question_id, transcript from ai_interview_answers "
                           "where interview_id = :i order by id"), {"i": interview_id}).all()


def test_orchestration() -> int | None:
    section("6. Orchestration: analysis -> report -> recruitment, over the real services")
    from app.ai.hr_intelligence import orchestrator as O
    from app.ai.interview_analysis import verdict_claim
    from app.database import SessionLocal
    from app.models import Interview

    db = SessionLocal()
    try:
        iid, room, plan, who = make_fixture(db)
        payload_2 = {**PAYLOAD_1, "summary": "the applicant described testing changes with SQL checks.",
                     "evidence": [{"point": "tested changes", "quote": "we tested every change with SQL checks",
                                   "type": "approach"}],
                     "skills_mentioned": [{"skill": "SQL", "quote": "SQL checks"}], "not_covered": []}
        fake = FakeProvider([PAYLOAD_1, payload_2])
        use_provider(fake)
        answers_before = answers_of(db, iid)
        result = O.run_post_interview(db, iid)
        agents = result["agents"]
        check("the order is explicit and fixed", result["order"] == ["analysis", "report", "recruitment"]
              and list(agents) == ["analysis", "report", "recruitment"])
        check("analysis: both stored answers analysed through the existing service (one model call each)",
              agents["analysis"] == {"status": "completed", "attempted": 2} and len(fake.calls) == 2
              and [r[1] for r in analyses_of(db, iid)] == ["completed", "completed"])
        brief = agents["report"].get("brief") or {}
        check("report: built from the stored analyses just written",
              agents["report"]["status"] == "completed" and len(brief.get("answers", [])) == 2
              and brief["answers"][0]["summary"] == PAYLOAD_1["summary"])
        check("report: the invented quote in the model output was already dropped by analysis validation",
              all("forty engineers" not in e["quote"] for a in brief["answers"] for e in a["evidence"]))
        check("recruitment: explains the existing matching result (no CV readable here -> unavailable, nothing invented)",
              agents["recruitment"]["status"] == "completed"
              and agents["recruitment"]["explanation"]["status"] in ("available", "unavailable")
              and not [k for _, k in keys_of(agents["recruitment"]) if "score" in k.lower()])
        check("the interview is untouched: status still completed, answers byte-identical",
              result["interview_unchanged"] is True and db.get(Interview, iid).status == "completed"
              and answers_of(db, iid) == answers_before)

        prompt = json.dumps([c["messages"] for c in fake.calls])
        check("the Analysis Agent's input carries no candidate identity (email, name, phone)",
              all(v and v not in prompt for v in (who["email"], f"{who['first']} {who['last']}"))
              and (not who["phone"] or who["phone"] not in prompt))
        check("...and never the match score", "score" not in prompt.lower())
        out = json.dumps(result)
        check("the orchestrator's output carries no candidate identity and no transcript",
              who["email"] not in out and f"{who['first']} {who['last']}" not in out
              and TRANSCRIPT_SENTINEL not in out
              and TRANSCRIPT_2 not in out)
        check("no score / rank / decision key anywhere in the output",
              not [p for p, k in keys_of(result) if FORBIDDEN_KEYS.search(k)])
        composed = brief["overview"] + [a["headline"] for a in brief["answers"]] + \
            agents["recruitment"]["explanation"]["explanation"]
        check("no agent sentence is a hiring verdict", not [s for s in composed if verdict_claim(s)])
        check("labelled: not a hiring decision", result["is_hiring_decision"] is False)

        again = O.run_post_interview(db, iid)
        check("a second run makes NO model call (completed analyses are reused)",
              again["agents"]["analysis"]["attempted"] == 0 and len(fake.calls) == 2)
        skip = O.run_post_interview(db, iid, analyse=False)
        check("analyse=false skips the Analysis Agent entirely", skip["agents"]["analysis"]["status"] == "skipped")
        return iid
    finally:
        db.close()


def test_failures(iid: int) -> None:
    section("7. Failures are contained: the interview and its stored data are never altered")
    from app.ai.hr_intelligence import orchestrator as O
    from app.ai.provider import LlmError
    from app.database import SessionLocal
    from app.models import AiInterviewAnswer, Interview
    from app.services import interview_analysis_service, interview_context_service, interview_matching_service
    from app.services import interview_answer_service as ans, interview_report_service

    db = SessionLocal()
    try:
        # A third answer whose analysis will fail.
        interview = db.get(Interview, iid)
        interview.status = "scheduled"
        db.commit()
        from sqlalchemy import text
        room = db.execute(text("select room_name from ai_interview_sessions where interview_id = :i"),
                          {"i": iid}).scalar()
        plan_ = __import__("app.services.question_bank_service", fromlist=["x"]).interview_plan(db)
        ans.record_answer(db, room, ans.AnswerSubmission(question_id=plan_[2]["id"], question_number=3, sequence=3,
                                                         kind="answer", transcript=TRANSCRIPT_3,
                                                         answered_at=datetime.utcnow()))
        interview = db.get(Interview, iid)
        interview.status = "completed"
        db.commit()

        failing = FakeProvider(error=LlmError(f"provider down while reading {TRANSCRIPT_SENTINEL}"))
        use_provider(failing)
        before = answers_of(db, iid)
        result = O.run_post_interview(db, iid)
        rows = analyses_of(db, iid)
        check("failed analysis: stored as failed (existing behaviour), the others kept completed",
              [r[1] for r in rows] == ["completed", "completed", "failed"] and rows[-1][2] == "llm_error")
        check("...the interview is still completed and its answers unchanged",
              result["interview_unchanged"] and db.get(Interview, iid).status == "completed"
              and answers_of(db, iid) == before)
        brief = result["agents"]["report"]["brief"]
        check("...the report still builds, and says the answer could not be analysed (no fake content)",
              brief["answers"][2]["analysis_status"] == "failed" and brief["answers"][2]["evidence"] == []
              and brief["answers"][2]["summary"] is None)

        analyses_before = analyses_of(db, iid)
        real = interview_report_service.interview_report

        def broken(*_a, **_k):
            raise RuntimeError(f"report store down {TRANSCRIPT_SENTINEL}")
        interview_report_service.interview_report = broken
        try:
            result = O.run_post_interview(db, iid, analyse=False)
        finally:
            interview_report_service.interview_report = real
        check("failed report: status failed, NO brief produced (nothing fake in its place)",
              result["agents"]["report"] == {"status": "failed", "error_code": "internal_error"})
        check("...the next role still ran", result["agents"]["recruitment"]["status"] == "completed")
        check("...stored answers and analyses untouched", answers_of(db, iid) == before
              and analyses_of(db, iid) == analyses_before and db.get(Interview, iid).status == "completed")
        check("an unknown session is a report failure with its own code",
              O.run_post_interview(db, iid, analyse=False, session_id=987654321)["agents"]["report"]
              == {"status": "failed", "error_code": "session_not_found"})

        real_m = interview_matching_service.matching_for_candidate
        interview_matching_service.matching_for_candidate = broken
        try:
            result = O.run_post_interview(db, iid, analyse=False)
        finally:
            interview_matching_service.matching_for_candidate = real_m
        check("failed recruitment agent: failed with a code; the report is unaffected",
              result["agents"]["recruitment"]["status"] == "failed" and result["agents"]["report"]["status"] == "completed")

        try:
            O.run_post_interview(db, 987654321)
            check("an unknown interview is not_found", False)
        except O.IntelligenceError as e:
            check("an unknown interview is not_found", e.code == "not_found")

        real_job = interview_context_service.job_context
        interview_context_service.job_context = lambda job, db_: {**real_job(job, db_), "api_key": "leak"}
        counted = len(failing.calls)
        third = db.query(AiInterviewAnswer).filter(AiInterviewAnswer.interview_id == iid,
                                                   AiInterviewAnswer.sequence == 3).one().id
        try:
            row = interview_analysis_service.analyse_answer(db, third, force=True)
        finally:
            interview_context_service.job_context = real_job
        check("an unsafe Analysis input is refused by its contract before any model call (stored failed: unsafe_input)",
              row.status == "failed" and row.error_code == "unsafe_input" and len(failing.calls) == counted)
    finally:
        db.close()


def test_http() -> None:
    section("8. RBAC over HTTP: Admin and HR only; the agents have no other door")
    from app.database import SessionLocal
    from app.models import Interview

    e2e.BASE = BASE
    p5.BASE = BASE
    R = e2e.request
    tokens = {}
    for role, email in ((1, "analytics.admin@smarthr.test"), (2, e2e.AI_INTERVIEW_HR),
                        (3, "analytics.manager@smarthr.test"), (4, "analytics.employee@smarthr.test")):
        e2e.ensure_staff_account(email, role)
        tokens[role] = e2e.login(email)
    tokens[5] = p5.fixture_login(p5.APPLICANT_ONE_CV)
    iid = CREATED[0]
    path = f"/ai-interview/intelligence/{iid}?analyse=false"
    for role, label in ((1, "Admin"), (2, "HR")):
        r = R("POST", path, token=tokens[role])
        check(f"{label} -> 200 with the three roles' results", r.status == 200
              and list(r.body.get("agents", {})) == ["analysis", "report", "recruitment"], str(r.status))
    for role, label in ((3, "Manager"), (4, "Employee"), (5, "Applicant - even for their own interview")):
        r = R("POST", path, token=tokens[role])
        check(f"{label} -> 403", r.status == 403, str(r.status))
    check("anonymous -> 401", R("POST", path).status == 401)
    check("an unknown interview -> 404", R("POST", "/ai-interview/intelligence/987654321?analyse=false",
                                           token=tokens[2]).status == 404)
    db = SessionLocal()
    try:
        check("after every HTTP call the interview is still completed", db.get(Interview, iid).status == "completed")
    finally:
        db.close()


def test_question_bank() -> None:
    section("9. Question Bank policy intact")
    from app.database import SessionLocal
    from app.models import InterviewQuestion
    from app.services import question_bank_service as qb

    db = SessionLocal()
    try:
        a, b = qb.interview_plan(db), qb.interview_plan(db)
        rows = {q.id: q for q in db.query(InterviewQuestion).filter(InterviewQuestion.id.in_([p["id"] for p in a])).all()}
        check("the plan is deterministic and only active MAIN questions",
              a == b and all(rows[p["id"]].question_type == "main" and rows[p["id"]].is_active for p in a))
    finally:
        db.close()


def cleanup() -> int:
    from sqlalchemy import text

    from app.database import engine
    if not CREATED:
        return 0
    with engine.begin() as conn:
        conn.execute(text("""delete from ai_interview_answer_analyses where answer_id in
                             (select id from ai_interview_answers where interview_id = any(:i))"""), {"i": CREATED})
        conn.execute(text("delete from ai_interview_answers where interview_id = any(:i)"), {"i": CREATED})
        conn.execute(text("delete from ai_interview_sessions where interview_id = any(:i)"), {"i": CREATED})
        return conn.execute(text("delete from interviews where id = any(:i) and notes = :m"),
                            {"i": CREATED, "m": MARK}).rowcount


def main() -> int:
    print("SmartHR - AI Interview Phase 12 multi-agent HR intelligence tests")
    from app.services import interview_analysis_service
    interview_analysis_service.schedule = lambda _answer_id: None     # analysis runs only when the tests ask

    root = logging.getLogger()
    root.addHandler(CAP)
    level = root.level
    root.setLevel(logging.DEBUG)
    try:
        test_roles()
        test_boundaries()
        test_contracts()
        test_recruitment()
        test_report_agent()
        iid = test_orchestration()
        if iid:
            test_failures(iid)
            with p5.Server(PORT, False):
                test_http()
        test_question_bank()
    finally:
        root.removeHandler(CAP)
        root.setLevel(level)
        removed = cleanup()
        print(f"\n  cleanup: removed {removed} temporary interview(s) with their sessions, answers and analyses")

    section("10. Privacy: no transcript, secret or candidate text in any log line")
    leaked = [l for l in CAP.lines for s in (TRANSCRIPT_SENTINEL, TRANSCRIPT_1[:30], TRANSCRIPT_2[:30], TRANSCRIPT_3[:30],
                                             PAYLOAD_1["summary"][:30], "forty engineers") if s in l]
    check(f"{len(CAP.lines)} log lines captured; none carries a transcript, analysis text or secret",
          not leaked, leaked[0][:120] if leaked else "")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
