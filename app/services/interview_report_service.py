"""AI Interview (Phase 8) - the Interview Report, assembled from what Phase 7 stored.

    interviews -> applications -> jobs            (A) interview information
    ai_interview_sessions  (ONE session)          (A) which conversation this is
    ai_interview_answers + _answer_analyses       (B) question-by-question, as stored
    counting and set logic over (B)               (C) factual aggregates

**Read-only and deterministic.** No model is called, nothing is written and
nothing is re-derived from a transcript: every value in the report is either a
stored column, a stored analysis field, or a count / union / difference of
those. The same database gives the same report.

**No verdict can be expressed.** There is no field for a score, a rating, a
percentage, a recommendation or a decision - the aggregates are counts of the
stored `addresses_question` tokens, the job's own requirement phrases, and
quotes. `is_hiring_decision` is always false.

**Missing is not negative.** An answer whose analysis failed or is still
pending contributes to no aggregate: it is counted as `failed` / `pending`,
never as "not addressed". If no answer has a completed analysis, the
requirements a report could call "not referenced" are unknowable, so the list
is empty and `requirements_basis` says why. When only some are analysed, the
list is marked `complete: false`.

**One session, never merged.** An interview can have several AI Interview
sessions (an applicant may start more than once). The report is for one of
them: the one asked for, or by default the latest session that has answers.
The others are listed by id so a caller can choose.

**What the report does not claim.** The number of questions PLANNED for a
session is not stored, and the current Question Bank may differ from the one
the interview used, so the report gives `answered_count` and
`highest_question_reached` and never "N of M".

**The interview as it actually ran (Phase 11.4)** - derived, never stored,
from the session's answers and their Question Bank ids:

* `question_flow` - one entry per MAIN question in the order it was heard
  (`question_number`, which is the order asked since Phase 11.2): the main
  question, the answers to it, and its predefined follow-up with ITS answers
  kept separate (Phase 11.1). Texts are the stored `question_text` of the
  answers; a main question known only through its follow-up's parent is shown
  with the bank row's text and `answered: false`. No question is ever
  reconstructed from model output, and nothing is shown for a question
  nobody answered.
* `coverage` - main questions answered (in order), follow-ups answered, the
  highest main question reached, and the main questions of the CURRENT
  Question Bank plan that were not reached - `not_reached_basis` says it is
  the current plan, because the plan a session used is not stored. Whether
  the order matched the current bank order is `order_matches_current_bank`
  (null when an answered question is no longer in the plan).
* `context` - whether the answer analyses had Job / CV / Matching context,
  read from each completed analysis's stored `meta.context` booleans (the
  only part of `meta` read; nothing else of it is exposed). Null with basis
  `no_completed_analyses` when nothing was analysed.

Access is the caller's business: the route that exposes this is Admin/HR
only, like `GET /ai-interview/answers/{interview_id}`. Candidate identity
is not included - the report is about the conversation. Logs carry ids and
counts, never a transcript or an analysis value.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.ai.interview_analysis import ANALYSIS_FIELDS
from app.models import AiInterviewSession, Application, Interview, InterviewQuestion, Job
from app.routers.interviews import read_status
from app.services import interview_answer_service, question_bank_service
from app.services.interview_context_service import job_context

logger = logging.getLogger("smarthr.interview.report")

ADDRESS_TOKENS = ("fully", "partially", "not_addressed", "unclear")
ANALYSIS_STATUSES = ("completed", "failed", "pending")

#: Aggregates are for reading, not for scanning every quote the interview
#: produced; the full list is in the per-answer section.
KEY_EVIDENCE_MAX = 20

#: The report's top-level keys - asserted by the tests, so adding one (a
#: "score", say) is a deliberate change rather than a side effect.
REPORT_FIELDS = ("interview", "session", "sessions", "answers", "question_flow", "coverage", "context",
                 "summary", "meta")
CONTEXT_KINDS = ("job", "cv", "matching")

DISCLAIMER = (
    "A factual summary of what the applicant said and how each answer was analysed. "
    "It is not a score, a rating or a hiring decision, and an analysis that failed or "
    "is pending is not a finding about the applicant."
)


class ReportError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _interview_info(db: Session, interview: Interview) -> tuple[dict[str, Any], list[str]]:
    """(A) and the job's requirement phrases - built field by field."""
    application = db.get(Application, interview.application_id)
    job = db.get(Job, application.job_id) if application else None
    context = job_context(job, db) if job else None
    info = {
        "interview_id": interview.id,
        "job_id": job.id if job else None,
        "job_title": job.title if job else None,
        "department": context["department"] if context else None,
        "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
        "status": read_status(interview.status),
    }
    return info, list(context["requirements"]) if context else []


def _answer(view: dict[str, Any]) -> dict[str, Any]:
    """(B) one stored answer, with its stored analysis fields when completed."""
    analysis = view.get("analysis") or {"status": "pending"}
    status = analysis.get("status") if analysis.get("status") in ANALYSIS_STATUSES else "pending"
    stored = analysis.get("result") if status == "completed" else None
    return {
        "question_id": view["question_id"],
        "question_number": view["question_number"],
        "question_text": view["question_text"],
        "question_type": view.get("question_type", "main"),
        "sequence": view["sequence"],
        "answer_kind": view["answer_kind"],
        "transcript": view["transcript"],
        "word_count": view["word_count"],
        "answered_at": view["answered_at"],
        "analysis_status": status,
        # Only the analysis fields, by whitelist - never the stored `meta`.
        "analysis": {f: stored.get(f) for f in ANALYSIS_FIELDS} if isinstance(stored, dict) else None,
        "error_code": analysis.get("error_code") if status == "failed" else None,
    }


def _flow(
    db: Session, answers: list[dict[str, Any]], plan: list[dict], language: str = "en"
) -> list[dict[str, Any]]:
    """(Phase 11.4) The main questions in the order heard, each with its own
    answers and its follow-up's answers - from the stored answers only."""
    position = {q["id"]: i + 1 for i, q in enumerate(plan)}
    by_number: dict[int, dict[str, Any]] = {}
    for a in answers:
        entry = by_number.setdefault(a["question_number"], {
            "number": a["question_number"], "main": None, "follow_up": None})
        if a["question_type"] == "follow_up":
            fu = entry["follow_up"] or {"question_id": a["question_id"], "question_text": a["question_text"],
                                         "answer_sequences": []}
            fu["answer_sequences"].append(a["sequence"])
            entry["follow_up"] = fu
        else:
            main = entry["main"] or {"question_id": a["question_id"], "question_text": a["question_text"],
                                     "bank_position": position.get(a["question_id"]), "answered": True,
                                     "answer_sequences": []}
            main["answer_sequences"].append(a["sequence"])
            entry["main"] = main
    # A follow-up answered while its main question's own answer was not
    # stored: the main question WAS asked (a follow-up comes only after it),
    # so it is named from the follow-up's parent row - with no answer.
    for entry in by_number.values():
        if entry["main"] is None and entry["follow_up"] is not None:
            fu_row = db.get(InterviewQuestion, entry["follow_up"]["question_id"])
            parent = db.get(InterviewQuestion, fu_row.parent_question_id) if fu_row else None
            entry["main"] = {
                "question_id": parent.id if parent else None,
                "question_text": (
                    question_bank_service.planned_question(parent, language)
                    ["question_text"] if parent else None
                ),
                "bank_position": position.get(parent.id) if parent else None,
                "answered": False,
                "answer_sequences": [],
            }
    return [by_number[n] for n in sorted(by_number)]


def _coverage(flow: list[dict[str, Any]], plan: list[dict]) -> dict[str, Any]:
    asked = [e for e in flow if e["main"] and e["main"]["answered"]]
    asked_ids = {e["main"]["question_id"] for e in flow if e["main"]}
    positions = [e["main"]["bank_position"] for e in asked]
    if not asked:
        matches = None
    elif any(p is None for p in positions):
        matches = None          # a question no longer in the plan: cannot tell
    else:
        matches = positions == list(range(1, len(positions) + 1))
    return {
        "main_questions_answered": [{"number": e["number"], "question_id": e["main"]["question_id"]}
                                    for e in asked],
        "main_questions_answered_count": len(asked),
        "follow_ups_answered": [{"number": e["number"], "question_id": e["follow_up"]["question_id"]}
                                for e in flow if e["follow_up"]],
        "follow_ups_answered_count": sum(1 for e in flow if e["follow_up"]),
        "highest_main_question_reached": max((e["number"] for e in flow), default=None),
        "not_reached": [{"question_id": q["id"], "question_text": q["question_text"], "bank_position": i + 1}
                        for i, q in enumerate(plan) if q["id"] not in asked_ids],
        # The plan a session used is not stored; this is the plan TODAY.
        "not_reached_basis": "current_question_bank",
        "order_matches_current_bank": matches,
    }


def _context(views: list[dict[str, Any]]) -> dict[str, Any]:
    """Which contexts the COMPLETED answer analyses had - their stored
    `meta.context` booleans, and nothing else of `meta`."""
    seen = {k: False for k in CONTEXT_KINDS}
    analysed = 0
    for v in views:
        analysis = v.get("analysis") or {}
        result = analysis.get("result") if analysis.get("status") == "completed" else None
        flags = ((result or {}).get("meta") or {}).get("context") if isinstance(result, dict) else None
        if not isinstance(flags, dict):
            continue
        analysed += 1
        for k in CONTEXT_KINDS:
            seen[k] = seen[k] or flags.get(k) is True
    if analysed == 0:
        return {**{k: None for k in CONTEXT_KINDS}, "basis": "no_completed_analyses"}
    return {**seen, "basis": "completed_analyses"}


def _summary(answers: list[dict[str, Any]], requirements: list[str]) -> dict[str, Any]:
    """(C) counts, unions and differences over the COMPLETED analyses only."""
    statuses = {s: 0 for s in ANALYSIS_STATUSES}
    addressed = {t: 0 for t in ADDRESS_TOKENS}
    referenced: set[str] = set()
    skills: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    not_covered: list[dict[str, Any]] = []

    for a in answers:
        statuses[a["analysis_status"]] += 1
        result = a["analysis"]
        if a["analysis_status"] != "completed" or result is None:
            continue
        if result.get("addresses_question") in addressed:
            addressed[result["addresses_question"]] += 1
        referenced.update(r for r in (result.get("job_requirements_referenced") or []) if isinstance(r, str))
        for s in result.get("skills_mentioned") or []:
            if not isinstance(s, dict) or not s.get("skill"):
                continue
            entry = skills.setdefault(s["skill"].lower(), {
                "skill": s["skill"], "source": "applicant_statement", "mentions": []})
            entry["mentions"].append({"sequence": a["sequence"], "question_number": a["question_number"],
                                      "quote": s.get("quote")})
        for e in result.get("evidence") or []:
            if isinstance(e, dict) and e.get("quote"):
                evidence.append({"sequence": a["sequence"], "question_number": a["question_number"],
                                 "type": e.get("type"), "point": e.get("point"), "quote": e["quote"]})
        items = [i for i in (result.get("not_covered") or []) if isinstance(i, str) and i]
        if items:
            not_covered.append({"sequence": a["sequence"], "question_number": a["question_number"],
                                "items": items})

    analysed = statuses["completed"]
    if analysed == 0:
        # Nothing was analysed: "not referenced" would be a claim made from
        # missing data. Say so instead of listing every requirement.
        not_referenced: list[str] = []
        basis = "no_completed_analyses"
    else:
        not_referenced = [r for r in requirements if r not in referenced]
        basis = "completed_analyses"

    return {
        "answered_count": len(answers),
        "analysis_status_counts": statuses,
        "addresses_question_counts": {
            "addressed": addressed["fully"],
            "partially_addressed": addressed["partially"],
            "not_addressed": addressed["not_addressed"],
            "unclear": addressed["unclear"],
        },
        # In the job's own order, so the list reads like the posting.
        "requirements_referenced": [r for r in requirements if r in referenced]
                                   + sorted(r for r in referenced if r not in requirements),
        "requirements_not_referenced": not_referenced,
        "requirements_basis": basis,
        # False when some answers have no completed analysis: the lists above
        # describe the analysed answers only.
        "complete": analysed == len(answers) and analysed > 0,
        "skills_mentioned": list(skills.values()),
        "key_evidence": evidence[:KEY_EVIDENCE_MAX],
        "key_evidence_total": len(evidence),
        "not_covered": not_covered,
    }


def interview_report(db: Session, interview_id: int, session_id: int | None = None) -> dict[str, Any]:
    """The Interview Report for one interview and one of its AI sessions.

    Raises ReportError `interview_not_found`, or `session_not_found` when a
    `session_id` is given that is not one of THIS interview's sessions with
    answers. An interview with no answered session is a valid, empty report.
    """
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise ReportError("Interview not found.", "interview_not_found")
    stored = interview_answer_service.answers_for_interview(db, interview_id) or {"sessions": []}
    sessions = stored["sessions"]  # only sessions with answers, oldest first

    if session_id is not None:
        chosen = next((s for s in sessions if s["session_id"] == session_id), None)
        if chosen is None:
            raise ReportError("No answered AI Interview session with that id for this interview.",
                              "session_not_found")
    else:
        chosen = sessions[-1] if sessions else None

    info, requirements = _interview_info(db, interview)
    views = chosen["answers"] if chosen else []
    answers = [_answer(v) for v in views]
    summary = _summary(answers, requirements)
    binding = db.get(AiInterviewSession, chosen["session_id"]) if chosen else None
    report_language = question_bank_service.question_language(binding.language if binding else None)
    plan = question_bank_service.interview_plan(db, language=report_language)
    flow = _flow(db, answers, plan, report_language)
    info["answered_count"] = len(answers)
    info["highest_question_reached"] = max((a["question_number"] for a in answers), default=None)

    logger.info("interview report built: interview=%s session=%s answers=%d analysed=%d",
                interview_id, chosen["session_id"] if chosen else None, len(answers),
                summary["analysis_status_counts"]["completed"])
    return {
        "interview": info,
        "session": ({"session_id": chosen["session_id"], "started_at": chosen["started_at"],
                     # Phase 11.4: when the first and last answers were given.
                     # The interview's own length is not recorded.
                     "first_answer_at": answers[0]["answered_at"] if answers else None,
                     "last_answer_at": max(a["answered_at"] for a in answers) if answers else None,
                     "duration_recorded": False}
                    if chosen else None),
        # Every answered session of this interview, newest first - for choosing.
        "sessions": [{"session_id": s["session_id"], "started_at": s["started_at"],
                      "answered_count": len(s["answers"])} for s in reversed(sessions)],
        "answers": answers,
        "question_flow": flow,
        "coverage": _coverage(flow, plan) if chosen else None,
        "context": _context(views) if chosen else None,
        "summary": summary,
        "meta": {
            "state": "ready" if chosen else "no_answers",
            "label": "AI Interview report - for review",
            "disclaimer": DISCLAIMER,
            "is_hiring_decision": False,
            "planned_question_count_recorded": False,
            "generated_by": "stored_analyses",
        },
    }
