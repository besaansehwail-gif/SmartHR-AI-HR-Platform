"""Applicant-to-opportunity matching, version one.

Two lists of strings are compared. That is genuinely all this is, and saying so
is the point: the score is a **skill-overlap ratio between text the applicant
typed and text the job posting says**, not a judgement about a person.

    applicant skills   candidates.skills, typed by the applicant
                       (optionally plus skills they accepted from their CV)
    requirements       jobs.requirements, split into its own items

Three rules this module is built to keep:

* **No invented candidate skills.** Every skill considered comes from the
  applicant's own profile. Nothing is inferred from their name, location,
  education or job titles.
* **No invented job requirements.** Every requirement is a literal substring of
  `jobs.requirements` (`requirement_tokens` splits, it never interprets).
* **It is not a hiring decision.** The result carries `label` -
  "AI Match / Recommendation" - and `is_hiring_decision: False`, and HR's own
  screens never read it. A match of 100% moves nobody to an offer, and a match
  of 0% rejects nobody.

Deliberately arithmetic rather than a language model: an applicant must be able
to see why the number is what it is, the answer must not change between two
identical questions, and it must work with no API key configured. The Career
Agent calls this as a tool and explains the result; it does not compute it.
"""

import logging
import re
from typing import Any

logger = logging.getLogger("smarthr.matching")

#: Shown with every score, everywhere it appears.
MATCH_LABEL = "AI Match / Recommendation"

MATCH_DISCLAIMER = (
    "This is an automated skill-overlap suggestion based on the skills on your "
    "profile and the requirements this opportunity lists. It is not a hiring "
    "decision, not a score SmartHR recruiters see, and not a measure of whether "
    "you should apply."
)


def _normalise(value: str) -> str:
    """Lowercase, collapse punctuation - for comparison only."""
    return re.sub(r"[^a-z0-9+#. ]+", " ", value.lower()).strip()


def _words(value: str) -> list[str]:
    return [w for w in _normalise(value).split() if w]


def _covers(skill: str, requirement: str) -> bool:
    """Does this applicant skill satisfy this requirement item?

    Word-boundary containment in either direction, so "SQL" covers "SQL" and
    "Advanced SQL", and "Microsoft Excel" covers "Excel". Substring matching
    without boundaries would let "R" match "Recruitment"; this will not.
    """
    skill_words = _words(skill)
    requirement_words = _words(requirement)

    if not skill_words or not requirement_words:
        return False

    def contains(haystack: list[str], needle: list[str]) -> bool:
        if len(needle) > len(haystack):
            return False
        return any(
            haystack[i:i + len(needle)] == needle
            for i in range(len(haystack) - len(needle) + 1)
        )

    return contains(requirement_words, skill_words) or contains(
        skill_words, requirement_words
    )


def mentions_requirements(text: str | None, requirements: list[str]) -> list[str]:
    """Which of these requirements does this passage literally mention?

    The public form of the same word-boundary rule `_covers` applies, exported
    because the AI interviewer needs it to say "this answer mentioned SQL"
    without re-deriving the matching arithmetic. Re-deriving it is how a
    recruiter and an interview report would come to disagree about whether the
    same sentence evidenced the same requirement.

    It reports mentions, not competence: a candidate who says "I have never
    used Power BI" has mentioned Power BI. The caller decides what that is
    worth, and the report says the basis out loud.
    """
    if not text or not text.strip():
        return []

    return [
        requirement
        for requirement in (requirements or [])
        if requirement and requirement.strip() and _covers(text, requirement)
    ]


def match_skills(
    applicant_skills: list[str],
    requirements: list[str],
) -> dict[str, Any]:
    """Compare one applicant's skills with one opportunity's requirements.

    `matching_skills` holds the applicant's own wording; `skill_gaps` holds the
    job's. Neither list ever contains a string that was not in one of the two
    inputs.
    """
    applicant_skills = [s for s in (applicant_skills or []) if s and s.strip()]
    requirements = [r for r in (requirements or []) if r and r.strip()]

    matched_requirements: list[str] = []
    gaps: list[str] = []
    matched_skills: list[str] = []

    for requirement in requirements:
        covering = [s for s in applicant_skills if _covers(s, requirement)]

        if covering:
            matched_requirements.append(requirement)
            for skill in covering:
                if skill not in matched_skills:
                    matched_skills.append(skill)
        else:
            gaps.append(requirement)

    # Score is coverage of the *job's* requirements, not of the applicant's
    # skills: an applicant who lists forty skills and meets two of four
    # requirements has met half of what the job asked for.
    if requirements:
        score = round(100 * len(matched_requirements) / len(requirements))
        scored = True
    else:
        # A posting with no requirements text cannot be scored. Saying so beats
        # returning 0% (reads as "unsuitable") or 100% (reads as "perfect fit").
        score = None
        scored = False

    extra = [s for s in applicant_skills if s not in matched_skills]

    return {
        "label": MATCH_LABEL,
        "is_hiring_decision": False,
        "score": score,
        "score_available": scored,
        "score_basis": (
            f"{len(matched_requirements)} of {len(requirements)} listed "
            f"requirements matched by the skills on your profile"
            if scored else
            "This opportunity lists no requirements, so there is nothing to "
            "compare your skills against."
        ),
        "matching_skills": matched_skills,
        "matched_requirements": matched_requirements,
        "skill_gaps": gaps,
        "additional_skills": extra,
        "applicant_skill_count": len(applicant_skills),
        "requirement_count": len(requirements),
        "disclaimer": MATCH_DISCLAIMER,
        "method": "skill-overlap",
        "skills_source": "the applicant's own profile (candidates.skills)",
    }


def rank_opportunities(
    applicant_skills: list[str],
    opportunities: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Score a list of opportunities and return the best ones first.

    Unscoreable opportunities (no requirements listed) sort last rather than
    being dropped: they are still real openings, and a job seeker with no
    skills on their profile yet would otherwise see an empty page.
    """
    scored: list[dict[str, Any]] = []

    for opportunity in opportunities:
        match = match_skills(applicant_skills, opportunity.get("skills") or [])
        scored.append({**opportunity, "match": match})

    scored.sort(
        key=lambda item: (
            item["match"]["score"] is None,
            -(item["match"]["score"] or 0),
            item.get("title") or "",
        )
    )

    return scored[:limit]
