"""The HR Report Agent (Phase 12) - an HR-readable brief, from stored data only.

Input: the existing Interview Report (`interview_report_service`, Phases 8 and
11.4) - the stored answers and their stored analyses, unchanged. Output: a
brief an HR reviewer can read top to bottom. Its sentences are fixed
templates filled with stored values; every summary, evidence point, quote,
skill and requirement is COPIED from a stored analysis and carries the
answer sequence it came from.

No model call: a report that is composed rather than generated cannot
invent evidence. As a second net, an evidence quote is kept only if it is
found in that answer's stored transcript. Missing analyses are said to be
missing - never counted as a negative. There is no score, rank or
recommendation field.
"""

from typing import Any

from app.ai.hr_intelligence.contracts import assert_safe_input
from app.ai.interview_analysis import quoted_in

DISCLAIMER = ("A readable summary of the stored AI Interview analysis. Every quote and summary is "
              "copied from the stored analysis of the answer it names. It is not a score, a ranking, "
              "a recommendation or a hiring decision; an answer that was not analysed is not a "
              "finding about the applicant.")

_ADDRESS = {
    "fully": "The answer addresses the question.",
    "partially": "The answer addresses part of the question.",
    "not_addressed": "The answer does not address the question as it was asked.",
    "unclear": "Whether the answer addresses the question is unclear.",
}
_SPECIFIC = {"specific": "specific", "general": "general", "vague": "vague"}
_CLEAR = {"clear": "clear", "partly_clear": "partly clear", "unclear": "unclear"}
_NOT_ANALYSED = {
    "failed": "This answer could not be analysed. Its transcript is stored and the analysis can be re-run.",
    "pending": "This answer has not been analysed yet.",
}


def _answer_brief(a: dict[str, Any], said: str) -> tuple[dict[str, Any], int]:
    """`said`: this answer's transcript plus the earlier parts of the same
    question's answer - exactly what its analysis was allowed to quote."""
    base = {"sequence": a["sequence"], "question_number": a["question_number"],
            "question_type": a.get("question_type", "main"), "question_text": a["question_text"],
            "analysis_status": a["analysis_status"]}
    result = a.get("analysis")
    if a["analysis_status"] != "completed" or not isinstance(result, dict):
        return {**base, "headline": _NOT_ANALYSED.get(a["analysis_status"], _NOT_ANALYSED["pending"]),
                "summary": None, "evidence": [], "skills_mentioned": [], "requirements_referenced": [],
                "not_covered": []}, 0

    headline = _ADDRESS.get(result.get("addresses_question"), _ADDRESS["unclear"])
    spec, clear = _SPECIFIC.get(result.get("specificity")), _CLEAR.get(result.get("clarity"))
    if spec and clear:
        headline += f" It is {spec} and {clear}."
    evidence, dropped = [], 0
    for e in result.get("evidence") or []:
        if not isinstance(e, dict) or not e.get("quote"):
            continue
        if not quoted_in(e["quote"], said):
            dropped += 1                # not in what was said: never shown
            continue
        evidence.append({"point": e.get("point"), "quote": e["quote"], "type": e.get("type"),
                         "sequence": a["sequence"]})
    skills = [s["skill"] for s in (result.get("skills_mentioned") or []) if isinstance(s, dict) and s.get("skill")]
    return {**base, "headline": headline, "summary": result.get("summary"), "evidence": evidence,
            "skills_mentioned": skills,
            "requirements_referenced": [r for r in (result.get("job_requirements_referenced") or [])
                                        if isinstance(r, str)],
            "not_covered": [i for i in (result.get("not_covered") or []) if isinstance(i, str)]}, dropped


def _overview(report: dict[str, Any]) -> list[str]:
    info, summary = report.get("interview") or {}, report.get("summary") or {}
    counts = summary.get("analysis_status_counts") or {}
    n = summary.get("answered_count", 0)
    if n == 0:
        return ["No AI Interview answers are recorded for this interview."]
    lines = [f"{n} answer(s) were recorded for the {info.get('job_title') or 'interview'} role."]
    lines.append(f"{counts.get('completed', 0)} analysed, {counts.get('failed', 0)} could not be "
                 f"analysed, {counts.get('pending', 0)} not analysed yet.")
    if counts.get("completed", 0):
        a = summary.get("addresses_question_counts") or {}
        lines.append(f"Of the analysed answers, {a.get('addressed', 0)} addressed the question, "
                     f"{a.get('partially_addressed', 0)} partly, {a.get('not_addressed', 0)} did not "
                     f"address it as asked and {a.get('unclear', 0)} are unclear.")
        referenced = summary.get("requirements_referenced") or []
        missing = summary.get("requirements_not_referenced") or []
        lines.append(f"The analysed answers referred to {len(referenced)} of the job's listed requirements"
                     + (f"; {len(missing)} were not referred to." if missing else "."))
        if not summary.get("complete"):
            lines.append("Not every answer was analysed, so these figures describe the analysed answers only.")
    else:
        lines.append("No answer has been analysed yet, so nothing is said about requirement coverage.")
    return lines


def build_brief(report: dict[str, Any]) -> dict[str, Any]:
    """The HR brief for one stored Interview Report. Pure, deterministic."""
    assert_safe_input(report, "report")
    answers, dropped = [], 0
    stored = report.get("answers") or []
    for a in stored:
        said = "\n".join(x.get("transcript") or "" for x in stored
                         if x["question_id"] == a["question_id"] and x["sequence"] <= a["sequence"])
        brief, lost = _answer_brief(a, said)
        answers.append(brief)
        dropped += lost
    summary = report.get("summary") or {}
    return {
        "state": (report.get("meta") or {}).get("state", "no_answers"),
        "job_title": (report.get("interview") or {}).get("job_title"),
        "session_id": (report.get("session") or {}).get("session_id"),
        "overview": _overview(report),
        "answers": answers,
        "requirements": {
            "referenced": list(summary.get("requirements_referenced") or []),
            "not_referenced": list(summary.get("requirements_not_referenced") or []),
            "basis": summary.get("requirements_basis"),
        },
        "skills_mentioned": [s.get("skill") for s in (summary.get("skills_mentioned") or []) if isinstance(s, dict)],
        "unverified_quotes_dropped": dropped,
        "provenance": "stored_analyses",
        "model_calls": 0,
        "disclaimer": DISCLAIMER,
        "is_hiring_decision": False,
    }
