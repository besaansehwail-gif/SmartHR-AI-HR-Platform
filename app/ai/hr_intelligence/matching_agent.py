"""The Recruitment / Matching Agent (Phase 12) - explains, never recalculates.

Input: SmartHR's EXISTING matching result for the interview's candidate and
job (`interview_matching_service.matching_for_candidate` - the same result the
interviewer and the Analysis Agent use), reduced to what an explanation
needs: the job title and requirement phrases, the status, the matching
skills (the candidate's wording) and the skill gaps (the job's wording).
**The score is not in the input**, so it cannot be restated, and nothing here
computes one.

Output: one fixed-template sentence per matching skill and per requirement
the evidence did not mention. No model call. A gap is always described as
missing evidence, never as something the applicant lacks.
"""

from dataclasses import dataclass, field
from typing import Any

from app.ai.hr_intelligence.contracts import assert_safe_input

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
ITEMS_MAX = 30

BASIS = ("SmartHR's existing matching: the applicant's own profile skills and latest CV compared with "
         "the job's listed requirements. Shown as it was computed - not recalculated here.")
DISCLAIMER = ("An explanation of text overlap between the applicant's evidence and the job posting. "
              "It is not a score, a ranking or a hiring decision.")
UNAVAILABLE_TEXT = ("SmartHR has no matching result for this applicant and job (no profile skills or "
                    "readable CV, or the job lists no requirements). Nothing is inferred in its place.")


@dataclass(frozen=True)
class MatchingInput:
    job_title: str | None
    status: str
    requirements: tuple[str, ...] = field(default_factory=tuple)
    matching_skills: tuple[str, ...] = field(default_factory=tuple)
    skill_gaps: tuple[str, ...] = field(default_factory=tuple)


def input_from(job_context: dict[str, Any] | None, status: str, context: dict[str, Any] | None) -> MatchingInput:
    """Built field by field from the existing results - the score is dropped."""
    context = context or {}
    available = status == STATUS_AVAILABLE and bool(context)
    return MatchingInput(
        job_title=(job_context or {}).get("title"),
        status=STATUS_AVAILABLE if available else STATUS_UNAVAILABLE,
        requirements=tuple(str(r) for r in ((job_context or {}).get("requirements") or [])),
        matching_skills=tuple(str(s) for s in (context.get("matching_skills") or [])) if available else (),
        skill_gaps=tuple(str(g) for g in (context.get("skill_gaps") or [])) if available else (),
    )


def explain(data: MatchingInput) -> dict[str, Any]:
    assert_safe_input(data, "recruitment")
    if data.status != STATUS_AVAILABLE:
        return {"status": STATUS_UNAVAILABLE, "job_title": data.job_title, "matching_skills": [],
                "requirements_not_evidenced": [], "explanation": [UNAVAILABLE_TEXT], "basis": BASIS,
                "disclaimer": DISCLAIMER, "is_hiring_decision": False, "model_calls": 0}
    matched = [{"skill": s,
                "explanation": f"“{s}” appears in the applicant's own profile skills or CV and "
                               f"corresponds to a requirement listed for this job."}
               for s in data.matching_skills[:ITEMS_MAX]]
    gaps = [{"requirement": g,
             "explanation": f"The job lists “{g}”; neither the applicant's profile skills nor "
                            f"their CV mentioned it. This is missing evidence, not a finding about the "
                            f"applicant - they may still have it."}
            for g in data.skill_gaps[:ITEMS_MAX]]
    summary = (f"{len(matched)} of the job's listed requirements were mentioned in the applicant's "
               f"evidence and {len(gaps)} were not mentioned.")
    return {"status": STATUS_AVAILABLE, "job_title": data.job_title, "matching_skills": matched,
            "requirements_not_evidenced": gaps, "explanation": [summary], "basis": BASIS,
            "disclaimer": DISCLAIMER, "is_hiring_decision": False, "model_calls": 0}
