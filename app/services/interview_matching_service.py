"""AI Interview (Phase 6) - the existing SmartHR matching result, as the interviewer may see it.

    room -> ai_interview_sessions -> interview -> application -> candidate + job
         -> screening_service.screen_candidate()      (the EXISTING HR matching)
              -> matching_service.match_skills()       (the one arithmetic)
         -> matching_context()                         (score, matching_skills, skill_gaps)

**Nothing is calculated here.** SmartHR stores no match result anywhere - every
score in the product is computed on request by `matching_service.match_skills()`
- so "the existing result" for a candidate and a job is whatever
`screening_service.screen_candidate()` returns for that pair. That is the
recruiter-side comparison: the same function HR's AI Screening Agent calls
through the `match_candidate_to_job` MCP tool, over the same evidence
(`candidate_evidence`: the candidate's own profile skills plus the skills of
their LATEST CV). An AI interview is HR's process about a candidate for a job,
so HR's comparison is the one it reuses. This module picks three fields out of
it and does not touch the arithmetic.

**The CV is not parsed twice.** `screen_candidate` would read the CV itself
(one model call). The interview has already parsed that same latest CV for its
CV Context (Phase 5), so the parse is taken from `interview_cv_service`'s
cache and handed to `candidate_evidence(parsed_cv=...)`. Same document, same
parser, same evidence - one model call.

**What reaches the interviewer** - the existing names, nothing else:

    score            match["score"]           int, 0-100, coverage of the job's
                                              listed requirements
    matching_skills  match["matching_skills"] the candidate's own wording
    skill_gaps       match["skill_gaps"]      the job's own wording

Deliberately not sent: `matched_requirements`, `additional_skills`, counts,
`score_basis`, `method`, `skills_source`, the disclaimers, the evidence dump
(which carries the CV id and file name), the candidate and job views,
relevant experience / education / certifications. None is needed to hold an
interview, and the candidate/job views carry contact details.

**When there is no result, there is no context** (`status: "unavailable"`,
`context: None`) - never a 0 and never an empty skills list standing in for
"unknown":

    no_evidence       the candidate has no profile skills and no readable CV;
                      screen_candidate itself refuses to score (score None) and
                      empties both lists
    no_requirements   the job lists no requirements; match_skills cannot score
    cv_unavailable    a CV is on file but could not be read or analysed just
                      now (model absent, timeout, unreadable file). HR's
                      screening would score such a candidate on profile skills
                      alone; the interview does not present that thinner
                      result as the match, because the evidence it normally
                      includes is missing for a reason that may be temporary.

The interview goes ahead without matching in every case, on the Question
Bank, the Job Context and whatever CV Context exists.

A real 0 is different and IS sent: evidence exists, the job lists
requirements, and none of them is covered. That is the result SmartHR's
matching gives, so it is the result the interviewer holds.

Logging is codes and counts only - never a skill, never a score.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Candidate, Job
from app.services import interview_cv_service, screening_service

logger = logging.getLogger("smarthr.interview.matching")

#: The whitelist, asserted by the tests. Adding a field is a decision.
MATCHING_CONTEXT_FIELDS = ("score", "matching_skills", "skill_gaps")

TEXT_MAX = 120
SKILLS_MAX = 30
GAPS_MAX = 20

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MatchingResult:
    status: str
    context: dict[str, Any] | None = None
    #: For logs and tests only - never sent to the worker.
    code: str | None = None


def _clip(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= TEXT_MAX else text[: TEXT_MAX - 1].rstrip() + "…"


def _strings(values: Any, cap: int) -> list[str]:
    return [s for s in (_clip(v) for v in (values or [])[:cap]) if s]


def matching_context(match: dict[str, Any]) -> dict[str, Any] | None:
    """The three existing fields of a scored `match`, trimmed - or None when
    the match carries no score."""
    score = match.get("score")
    if not match.get("score_available") or not isinstance(score, int) or isinstance(score, bool):
        return None
    return {
        "score": score,
        "matching_skills": _strings(match.get("matching_skills"), SKILLS_MAX),
        "skill_gaps": _strings(match.get("skill_gaps"), GAPS_MAX),
    }


def matching_for_candidate(
    db: Session, candidate_id: int, job: Job, wait_s: float = interview_cv_service.WAIT_S
) -> MatchingResult:
    """The existing SmartHR matching result for this candidate and this job."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        return MatchingResult(STATUS_UNAVAILABLE, code="no_candidate")

    cv = interview_cv_service.cv_for_candidate(db, candidate_id, wait_s)
    if cv.status == interview_cv_service.STATUS_UNAVAILABLE or (
        cv.status == interview_cv_service.STATUS_AVAILABLE and cv.parsed is None
    ):
        return MatchingResult(STATUS_UNAVAILABLE, code="cv_unavailable")

    evidence = screening_service.candidate_evidence(candidate, db, parsed_cv=cv.parsed)
    result = screening_service.screen_candidate(candidate, job, db, evidence=evidence)
    match = result["match"]

    context = matching_context(match)
    if context is None:
        code = "no_evidence" if not evidence.available else "no_requirements"
        return MatchingResult(STATUS_UNAVAILABLE, code=code)
    return MatchingResult(STATUS_AVAILABLE, context=context)
