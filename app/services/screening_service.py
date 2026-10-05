"""HR-side screening: comparing real candidates against a real requisition.

The recruiter-facing counterpart to `app/services/matching_service.py`, which
is the applicant-facing one. They are deliberately **not** the same module and
deliberately **not** two implementations of matching:

    matching_service.match_skills()   the arithmetic - shared by both sides
    matching_service                  applicant -> opportunity (their view)
    screening_service                 candidate -> job         (HR's view)

The arithmetic is imported, never re-derived. What this module adds is the
part HR needs and an applicant does not: **where a candidate's evidence comes
from**, and what to say when there is none.

Evidence, and nothing but evidence
----------------------------------

An applicant matching themselves has one source of skills - the ones they
typed on their own profile. A recruiter screening five candidates usually has
neither: `candidates` holds a name, an email, a phone and a location, and
`candidates.skills` is filled in only when the person registered through the
Applicant portal and typed it.

So this module reads exactly two sources, names which one every fact came
from, and reports an empty hand as an empty hand:

    profile   `candidates.skills` - the candidate's own words, when they have
              an account and filled it in
    cv        the stored CV, parsed by `app/services/cv_service.py` - the
              **same** `analyse_cv_bytes()` that `POST /cvs/upload` and the
              `parse_cv` MCP tool call. There is no second CV parser here.

A candidate with neither gets `evidence_available: False`, `score: None` and a
sentence saying what is missing. It does **not** get 0%, which reads as
"unsuitable" when it means "we know nothing about this person yet" - the same
rule `matching_service` applies to an applicant with no skills listed, for the
same reason. Nothing in this file infers a skill from a job title, a name, a
location or an education line; every string in `matching_skills` came from the
profile or the CV, and every string in `skill_gaps` is a literal item of
`jobs.requirements`.

Reading a CV costs a real model call
------------------------------------

Parsing is an LLM round-trip per document, so it is opt-in per call rather
than implicit. `search_candidates` is cheap and says who has a CV worth
reading; `screen_candidate` and `rank_candidates` read them. `rank_candidates`
is bounded by `MAX_CV_READS` so one question cannot turn into forty model
calls.

Not a decision
--------------

Every payload carries `label`, `is_hiring_decision: False` and a disclaimer,
and there is no function here that writes. Advancing, rejecting or hiring a
candidate is `PATCH /applications/{id}/status`, which is a recruiter's
deliberate act in the Recruitment UI - it is not reachable from this module
and not exposed as a tool.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import CV, Application, Candidate, Department, Interview, Job
from app.services.cv_service import CvServiceError, analyse_cv_bytes
from app.services.matching_service import (
    MATCH_LABEL,
    _covers,
    match_skills,
)
from app.services.opportunity_service import requirement_tokens, split_skills

logger = logging.getLogger("smarthr.screening")

#: How many CVs one ranking request may parse. Each is a model call, so this
#: is a cost ceiling, not a data limit - candidates beyond it are still
#: returned and still ranked on their profile skills, with `cv_read: False`
#: saying why their evidence is thinner.
MAX_CV_READS = 8

#: The most candidates one search returns without being asked for more.
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

SCREENING_DISCLAIMER = (
    "This is an automated skill-overlap suggestion comparing evidence SmartHR "
    "holds for this candidate against the requirements this job lists. It is "
    "not a hiring decision, not a ranking of people, and not a substitute for "
    "a recruiter reading the CV. A low score most often means SmartHR holds "
    "little evidence, not that the candidate is unsuitable."
)


class ScreeningError(Exception):
    """Something the caller can act on, with a code the tool layer maps."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


# ===========================================================================
# Jobs
# ===========================================================================

def _department_name(department_id: int | None, db: Session) -> str | None:
    if department_id is None:
        return None

    row = db.query(Department).filter(Department.id == department_id).first()

    return row.name if row else None


def job_view(job: Job, db: Session, *, with_pipeline: bool = True) -> dict[str, Any]:
    """One requisition as the HR agent sees it.

    Built field by field rather than by filtering `jobs.job_to_dict()`. That
    is the same rule `opportunity_service.public_job()` follows and it is here
    for the opposite reason: this projection is allowed *more* than the public
    one, so it should still be an explicit list rather than "everything on the
    row", or the next column added to `jobs` silently joins every agent
    answer.
    """
    requirements = requirement_tokens(job.requirements)

    view: dict[str, Any] = {
        "job_id": job.id,
        "title": job.title,
        "department_id": job.department_id,
        "department_name": _department_name(job.department_id, db),
        "description": job.description,
        "employment_type": job.employment_type,
        "location": job.location,
        "status": job.status,
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        # The requirements, split into the items matching compares against.
        # `requirement_tokens` splits and never interprets, so each one is a
        # literal substring of what the recruiter typed.
        "requirements_text": job.requirements,
        "requirements": requirements,
        "requirement_count": len(requirements),
        "requirements_available": bool(requirements),
    }

    if not requirements:
        view["note"] = (
            "This job lists no requirements, so there is nothing to compare a "
            "candidate's skills against and no match score can be produced "
            "for it. Add requirements to the requisition first."
        )

    if with_pipeline:
        applications = (
            db.query(Application).filter(Application.job_id == job.id).all()
        )
        counts: dict[str, int] = {}

        for application in applications:
            stage = (application.status or "unknown").strip().lower()
            counts[stage] = counts.get(stage, 0) + 1

        view["applications_count"] = len(applications)
        view["pipeline_counts"] = counts

    return view


def find_jobs(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Requisitions matching a recruiter's words.

    Unlike the applicant-facing catalogue this does **not** restrict to
    `status = 'open'`: HR legitimately screens against a job that is on hold
    or closed, and hiding it would make the agent claim a real requisition
    does not exist. `status` narrows it when the recruiter asks.
    """
    query = db.query(Job)

    if status:
        query = query.filter(func.lower(Job.status) == status.strip().lower())

    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Job.title).like(like),
                func.lower(func.coalesce(Job.description, "")).like(like),
                func.lower(func.coalesce(Job.requirements, "")).like(like),
            )
        )

    rows = query.order_by(Job.created_at.desc(), Job.id.desc()).limit(
        _bounded(limit)
    ).all()

    return [job_view(job, db) for job in rows]


def get_job(job_id: int, db: Session) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise ScreeningError(f"There is no job with id {job_id}.", code="not_found")

    return job


def resolve_job(db: Session, *, job_id: int | None, title: str | None) -> Job:
    """Turn what the recruiter said into one requisition, or refuse clearly.

    A title is how a person names a job ("the Data Analyst position"), so the
    agent is allowed to pass one - but an ambiguous title must not be guessed
    at, because screening the wrong requisition produces a confident answer
    about the wrong requirements. An exact match wins; otherwise a single
    partial match is accepted and several are refused with the list, so the
    agent can ask which one.
    """
    if job_id is not None:
        return get_job(job_id, db)

    if not title or not title.strip():
        raise ScreeningError(
            "Give either a job_id or a job title to say which requisition "
            "this is about.",
            code="missing_argument",
        )

    wanted = title.strip().lower()

    exact = [
        job for job in db.query(Job).all()
        if (job.title or "").strip().lower() == wanted
    ]

    if len(exact) == 1:
        return exact[0]

    partial = [
        job for job in db.query(Job).all()
        if wanted in (job.title or "").strip().lower()
    ]

    if len(partial) == 1:
        return partial[0]

    if not partial:
        raise ScreeningError(
            f"No job in SmartHR has a title matching '{title}'. Use "
            f"search_jobs to see what requisitions exist.",
            code="not_found",
        )

    names = ", ".join(f"{job.title} (id {job.id})" for job in partial[:8])
    raise ScreeningError(
        f"'{title}' matches more than one requisition: {names}. Ask which one "
        f"is meant, then call again with its job_id.",
        code="ambiguous",
    )


# ===========================================================================
# Candidate evidence
# ===========================================================================

@dataclass
class Evidence:
    """What SmartHR actually knows about one candidate's skills.

    `sources` names where each fact came from. It exists so an answer can say
    "from their CV" or "from the profile they filled in" rather than asserting
    a skill with no provenance - and so that "we hold nothing" is a state the
    caller has to handle rather than one that silently looks like zero.
    """

    skills: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    profile_skills: list[str] = field(default_factory=list)
    cv_skills: list[str] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[dict[str, Any]] = field(default_factory=list)
    languages: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None

    has_cv: bool = False
    cv_read: bool = False
    cv_id: int | None = None
    cv_file_name: str | None = None
    cv_error_code: str | None = None
    cv_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.skills)

    def describe(self) -> str:
        """One sentence a model can relay verbatim about provenance."""
        if self.skills:
            return (
                f"{len(self.skills)} skill(s) from "
                f"{' and '.join(self.sources)}."
            )

        if self.has_cv and not self.cv_read:
            return (
                "This candidate has a CV on file that has not been read in "
                "this request, so SmartHR holds no skills for them yet."
            )

        if self.has_cv and self.cv_error_code:
            return (
                f"This candidate has a CV on file but it could not be read "
                f"({self.cv_error_code}), so no skills are available."
            )

        return (
            "SmartHR holds no skills for this candidate: they have no CV on "
            "file and no skills on their profile. Nothing can be inferred "
            "from their name, location or application history."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_available": self.available,
            "skills": self.skills,
            "skills_sources": self.sources,
            "profile_skills": self.profile_skills,
            "cv_skills": self.cv_skills,
            "summary": self.summary,
            "experience": self.experience,
            "education": self.education,
            "certifications": self.certifications,
            "languages": self.languages,
            "has_cv": self.has_cv,
            "cv_read": self.cv_read,
            "cv_id": self.cv_id,
            "cv_file_name": self.cv_file_name,
            "cv_error_code": self.cv_error_code,
            "cv_error": self.cv_error,
            "evidence_note": self.describe(),
        }


def latest_cv(candidate_id: int, db: Session) -> CV | None:
    return (
        db.query(CV)
        .filter(CV.candidate_id == candidate_id)
        .order_by(CV.uploaded_at.desc(), CV.id.desc())
        .first()
    )


def _read_cv(cv: CV) -> tuple[Any | None, str | None, str | None]:
    """Parse one stored CV through the shared pipeline.

    Returns `(parsed, error_code, error)`. This is the **only** place in the
    HR agent that touches a CV document, and it calls the same
    `analyse_cv_bytes()` as `POST /cvs/upload`. A failure here is reported,
    never substituted for: a CV that cannot be read means no skills, not
    guessed skills.
    """
    path = Path(cv.file_path)

    if not path.is_file():
        return None, "file_missing", (
            "The stored file for this CV is no longer on disk."
        )

    try:
        data = path.read_bytes()
    except OSError:
        logger.exception("Screening could not read stored CV | cv_id=%s", cv.id)
        return None, "file_unreadable", "The stored CV could not be read."

    try:
        analysis = analyse_cv_bytes(cv.file_name, data, analyse=True)
    except CvServiceError as exc:
        return None, exc.code, str(exc)

    if not analysis.analysis_available:
        return None, (
            analysis.analysis_error_code or "analysis_failed"
        ), (
            analysis.analysis_error or "The CV could not be analysed just now."
        )

    return analysis.parsed, None, None


def candidate_evidence(
    candidate: Candidate,
    db: Session,
    *,
    read_cv: bool = False,
    parsed_cv: Any | None = None,
) -> Evidence:
    """Everything SmartHR can say about this candidate's skills, with sources.

    `parsed_cv` is the candidate's LATEST CV already parsed by the same
    `analyse_cv_bytes()` - passed by a caller that has just parsed it (the AI
    Interview, `interview_cv_service`) so the document is not sent to the
    model a second time. It is used exactly where `_read_cv`'s result would
    be; the evidence and everything derived from it are otherwise identical.

    Counts and codes are logged; no skill, name or CV value ever is.
    """
    evidence = Evidence()

    profile_skills = split_skills(candidate.skills)

    if profile_skills:
        evidence.profile_skills = profile_skills
        evidence.skills.extend(profile_skills)
        evidence.sources.append("the candidate's own profile")

    cv = latest_cv(candidate.id, db)

    if cv is not None:
        evidence.has_cv = True
        evidence.cv_id = cv.id
        evidence.cv_file_name = cv.file_name

    if cv is not None and (read_cv or parsed_cv is not None):
        if parsed_cv is not None:
            parsed, code, message = parsed_cv, None, None
        else:
            parsed, code, message = _read_cv(cv)

        if parsed is None:
            evidence.cv_error_code = code
            evidence.cv_error = message
        else:
            evidence.cv_read = True
            evidence.summary = parsed.summary
            evidence.cv_skills = list(parsed.skills)
            evidence.experience = [row.model_dump() for row in parsed.experience]
            evidence.education = [row.model_dump() for row in parsed.education]
            evidence.certifications = [
                row.model_dump() for row in parsed.certifications
            ]
            evidence.languages = [row.model_dump() for row in parsed.languages]

            known = {s.lower() for s in evidence.skills}
            for skill in parsed.skills:
                if skill.lower() not in known:
                    evidence.skills.append(skill)
                    known.add(skill.lower())

            if parsed.skills:
                evidence.sources.append("their CV")

    logger.info(
        "Candidate evidence | candidate_id=%s skills=%s has_cv=%s cv_read=%s code=%s",
        candidate.id, len(evidence.skills), evidence.has_cv,
        evidence.cv_read, evidence.cv_error_code,
    )

    return evidence


# ===========================================================================
# Relevant experience, education, certifications
#
# Each of these is *derived from overlap with this job's requirements* and
# reports the basis alongside the verdict. None of them is a judgement the
# model is asked to make up: "strong" here means a counted number of roles
# mentioned a requirement, and the count is returned so the sentence can be
# checked.
# ===========================================================================

def _mentions_any(text_parts: list[str | None], requirements: list[str]) -> list[str]:
    """Which of these requirements appear in this block of CV text."""
    haystack = " ".join(part for part in text_parts if part)

    if not haystack.strip():
        return []

    return [req for req in requirements if _covers(haystack, req)]


def relevant_experience(
    evidence: Evidence, requirements: list[str]
) -> dict[str, Any]:
    """Which roles on the CV touch this job's requirements, and how many.

    `relevance` is a band over a counted number, never an impression. It is
    `unknown` whenever the CV was not read - which is the honest answer, and
    distinct from `none`, which means the CV was read and mentioned nothing.
    """
    if not evidence.cv_read:
        return {
            "relevance": "unknown",
            "basis": (
                "No CV was read for this candidate, so their work experience "
                "is unknown to SmartHR."
            ),
            "matching_roles": [],
            "roles_considered": 0,
            "roles_matching": 0,
        }

    if not requirements:
        return {
            "relevance": "unknown",
            "basis": (
                "This job lists no requirements, so there is nothing to judge "
                "experience against."
            ),
            "matching_roles": [],
            "roles_considered": len(evidence.experience),
            "roles_matching": 0,
        }

    matching: list[dict[str, Any]] = []

    for role in evidence.experience:
        hits = _mentions_any(
            [
                role.get("title"),
                role.get("company"),
                role.get("description"),
                ", ".join(role.get("technologies") or []),
            ],
            requirements,
        )

        if hits:
            matching.append({
                "title": role.get("title"),
                "company": role.get("company"),
                "start_date": role.get("start_date"),
                "end_date": role.get("end_date"),
                "requirements_mentioned": hits,
            })

    considered = len(evidence.experience)
    count = len(matching)

    if considered == 0:
        relevance = "none_stated"
        basis = "The CV was read but lists no work experience."
    elif count == 0:
        relevance = "none_evidenced"
        basis = (
            f"None of the {considered} role(s) on the CV mention any of this "
            f"job's requirements."
        )
    elif count >= 2 or count == considered:
        relevance = "strong"
        basis = (
            f"{count} of {considered} role(s) on the CV mention this job's "
            f"requirements."
        )
    else:
        relevance = "some"
        basis = (
            f"{count} of {considered} role(s) on the CV mention this job's "
            f"requirements."
        )

    return {
        "relevance": relevance,
        "basis": basis,
        "matching_roles": matching,
        "roles_considered": considered,
        "roles_matching": count,
    }


def relevant_education(
    evidence: Evidence, requirements: list[str]
) -> dict[str, Any]:
    """Education, and whether any of it names a requirement. Often neither."""
    if not evidence.cv_read:
        return {
            "available": False,
            "basis": "No CV was read, so education is unknown to SmartHR.",
            "entries": [],
            "matching_entries": [],
        }

    if not evidence.education:
        return {
            "available": False,
            "basis": "The CV was read but states no education.",
            "entries": [],
            "matching_entries": [],
        }

    matching = []

    for entry in evidence.education:
        hits = _mentions_any(
            [entry.get("degree"), entry.get("field"), entry.get("institution")],
            requirements,
        )
        if hits:
            matching.append({**entry, "requirements_mentioned": hits})

    return {
        "available": True,
        "basis": (
            f"{len(evidence.education)} education entry(ies) on the CV; "
            f"{len(matching)} mention this job's requirements."
        ),
        "entries": evidence.education,
        "matching_entries": matching,
    }


def relevant_certifications(
    evidence: Evidence, requirements: list[str]
) -> dict[str, Any]:
    if not evidence.cv_read:
        return {
            "available": False,
            "basis": "No CV was read, so certifications are unknown to SmartHR.",
            "entries": [],
            "matching_entries": [],
        }

    if not evidence.certifications:
        return {
            "available": False,
            "basis": "The CV was read but states no certifications.",
            "entries": [],
            "matching_entries": [],
        }

    matching = []

    for entry in evidence.certifications:
        hits = _mentions_any([entry.get("name"), entry.get("issuer")], requirements)
        if hits:
            matching.append({**entry, "requirements_mentioned": hits})

    return {
        "available": True,
        "basis": (
            f"{len(evidence.certifications)} certification(s) on the CV; "
            f"{len(matching)} mention this job's requirements."
        ),
        "entries": evidence.certifications,
        "matching_entries": matching,
    }


# ===========================================================================
# Candidates
# ===========================================================================

def _bounded(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT

    return max(1, min(int(limit), MAX_LIMIT))


def candidate_view(
    candidate: Candidate, db: Session, *, with_applications: bool = True
) -> dict[str, Any]:
    """One candidate as HR's agent sees them: identity, pipeline, CV status.

    This is the dossier - it answers both "get_candidate" and "the candidate's
    profile", which is why there is one tool rather than two that would return
    the same row. Deliberately absent: `interviews.notes`, which is a private
    interviewer record, and anything resembling a score. A score belongs to a
    comparison with a specific job and is produced by `screen_candidate`,
    never carried around on the person.
    """
    applications = (
        db.query(Application)
        .filter(Application.candidate_id == candidate.id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .all()
    )

    cv = latest_cv(candidate.id, db)

    view: dict[str, Any] = {
        "candidate_id": candidate.id,
        "full_name": f"{candidate.first_name} {candidate.last_name}".strip(),
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        # True when this person registered through the Applicant portal, which
        # is also the only way `profile_skills` gets filled in.
        "has_applicant_account": candidate.user_id is not None,
        "profile_skills": split_skills(candidate.skills),
        "has_cv": cv is not None,
        "cv_id": cv.id if cv else None,
        "cv_file_name": cv.file_name if cv else None,
        "cv_uploaded_at": cv.uploaded_at.isoformat() if cv and cv.uploaded_at else None,
        "applications_count": len(applications),
    }

    if with_applications:
        view["applications"] = [
            application_view(application, db) for application in applications
        ]

    if not view["profile_skills"] and not view["has_cv"]:
        view["evidence_note"] = (
            "SmartHR holds no CV and no profile skills for this candidate, so "
            "there is nothing to match against a job's requirements."
        )

    return view


def get_candidate(candidate_id: int, db: Session) -> Candidate:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()

    if candidate is None:
        raise ScreeningError(
            f"There is no candidate with id {candidate_id}.", code="not_found"
        )

    return candidate


def resolve_candidate_row(
    db: Session, *, candidate_id: int | None, name: str | None
) -> Candidate:
    """Turn what the recruiter said into one candidate, or refuse clearly.

    The twin of `resolve_job`, and it exists for the same reason: a recruiter
    names a person in words ("why is Samer Ali a match?"), not by id. Without
    it the agent had to search, read the result, and only then call the tool -
    three steps for a lookup, which is how a multi-step turn runs out of steps
    before it gets to the actual question.

    An exact full-name match wins; otherwise a single partial match is
    accepted and several are refused **with the list**, so the agent asks
    rather than picking. Screening the wrong person produces a confident
    answer about somebody else, which is the one failure mode worth spending a
    round trip to avoid.
    """
    if candidate_id is not None:
        return get_candidate(candidate_id, db)

    if not name or not name.strip():
        raise ScreeningError(
            "Give either a candidate_id or a candidate name to say who this "
            "is about.",
            code="missing_argument",
        )

    wanted = " ".join(name.strip().lower().split())
    rows = db.query(Candidate).all()

    def full(row: Candidate) -> str:
        return " ".join(f"{row.first_name} {row.last_name}".lower().split())

    exact = [row for row in rows if full(row) == wanted]

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        ids = ", ".join(f"id {row.id}" for row in exact[:8])
        raise ScreeningError(
            f"More than one candidate is called '{name}' ({ids}). Ask which "
            f"one is meant, then call again with their candidate_id.",
            code="ambiguous",
        )

    partial = [
        row for row in rows
        if wanted in full(row) or wanted in (row.email or "").lower()
    ]

    if len(partial) == 1:
        return partial[0]

    if not partial:
        raise ScreeningError(
            f"No candidate in SmartHR matches '{name}'. Use search_candidates "
            f"to see who is on file.",
            code="not_found",
        )

    names = ", ".join(f"{full(row).title()} (id {row.id})" for row in partial[:8])
    raise ScreeningError(
        f"'{name}' matches more than one candidate: {names}. Ask which one is "
        f"meant, then call again with their candidate_id.",
        code="ambiguous",
    )


def find_candidates(
    db: Session,
    *,
    search: str | None = None,
    job_id: int | None = None,
    stage: str | None = None,
    has_cv: bool | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Candidates matching a recruiter's filters.

    `search` looks at the name, the email, the location and the profile skills
    - the columns `candidates` actually has. It does **not** search CV text,
    because SmartHR stores the CV file and not its text; a question like "show
    me candidates with Python and SQL" therefore finds people whose *profile*
    says so, and the caller is told that the rest need their CV read. Claiming
    to search inside documents that are not indexed would be the easiest lie
    to tell here.
    """
    query = db.query(Candidate)

    if job_id is not None or stage:
        query = query.join(Application, Application.candidate_id == Candidate.id)

        if job_id is not None:
            query = query.filter(Application.job_id == job_id)

        if stage:
            query = query.filter(
                func.lower(Application.status) == stage.strip().lower()
            )

    if search and search.strip():
        terms = [t for t in split_skills(search) if t] or [search.strip()]
        clauses = []

        # `candidates` stores the name in two columns, so a recruiter typing
        # a full name ("Samer Ali") matches neither of them on its own. The
        # concatenation is matched too, or asking the agent about somebody by
        # name returns nothing and it correctly - but uselessly - reports that
        # SmartHR has no such person.
        full_name = func.lower(
            Candidate.first_name + " " + func.coalesce(Candidate.last_name, "")
        )

        for term in terms:
            like = f"%{term.lower()}%"
            clauses.append(
                or_(
                    func.lower(Candidate.first_name).like(like),
                    func.lower(Candidate.last_name).like(like),
                    full_name.like(like),
                    func.lower(Candidate.email).like(like),
                    func.lower(func.coalesce(Candidate.location, "")).like(like),
                    func.lower(func.coalesce(Candidate.skills, "")).like(like),
                )
            )

        # Every term must appear somewhere, the same rule the applicant-facing
        # search uses: matching on *any* term makes an absent topic look
        # answered.
        for clause in clauses:
            query = query.filter(clause)

    rows = (
        query.distinct()
        .order_by(Candidate.created_at.desc(), Candidate.id.desc())
        .limit(_bounded(limit))
        .all()
    )

    if has_cv is not None:
        rows = [
            row for row in rows
            if (latest_cv(row.id, db) is not None) == has_cv
        ]

    return [candidate_view(row, db, with_applications=False) for row in rows]


# ===========================================================================
# Applications
# ===========================================================================

def application_view(application: Application, db: Session) -> dict[str, Any]:
    """One application, recruiter-facing.

    Richer than `application_service.application_view()`, which is the
    applicant's view of their own row - but still without `interviews.notes`.
    An interviewer's written note is a private record; the agent has no reason
    to quote one into a chat answer, and a screening conversation is not where
    it should surface.
    """
    job = db.query(Job).filter(Job.id == application.job_id).first()
    candidate = (
        db.query(Candidate).filter(Candidate.id == application.candidate_id).first()
    )

    interviews = (
        db.query(Interview)
        .filter(Interview.application_id == application.id)
        .order_by(Interview.scheduled_at.desc(), Interview.id.desc())
        .all()
    )

    return {
        "application_id": application.id,
        "candidate_id": application.candidate_id,
        "candidate_name": (
            f"{candidate.first_name} {candidate.last_name}".strip()
            if candidate else None
        ),
        "job_id": application.job_id,
        "job_title": job.title if job else None,
        "department_name": _department_name(job.department_id, db) if job else None,
        "status": application.status,
        "applied_at": (
            application.applied_at.isoformat() if application.applied_at else None
        ),
        "interviews": [
            {
                "id": row.id,
                "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
                "status": row.status,
                # Deliberately no `notes` and no interviewer identity.
            }
            for row in interviews
        ],
        "interviews_count": len(interviews),
    }


def get_application(application_id: int, db: Session) -> Application:
    application = (
        db.query(Application).filter(Application.id == application_id).first()
    )

    if application is None:
        raise ScreeningError(
            f"There is no application with id {application_id}.", code="not_found"
        )

    return application


def find_applications(
    db: Session,
    *,
    job_id: int | None = None,
    candidate_id: int | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    query = db.query(Application)

    if job_id is not None:
        query = query.filter(Application.job_id == job_id)

    if candidate_id is not None:
        query = query.filter(Application.candidate_id == candidate_id)

    if status:
        query = query.filter(func.lower(Application.status) == status.strip().lower())

    rows = (
        query.order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(_bounded(limit))
        .all()
    )

    return [application_view(row, db) for row in rows]


# ===========================================================================
# Screening: one candidate against one job
# ===========================================================================

def screen_candidate(
    candidate: Candidate,
    job: Job,
    db: Session,
    *,
    read_cv: bool = True,
    evidence: Evidence | None = None,
) -> dict[str, Any]:
    """Compare one real candidate with one real requisition.

    The score itself is `matching_service.match_skills()` - the identical
    arithmetic the applicant side uses, imported rather than reimplemented, so
    a recruiter and a candidate looking at the same pair see the same number.
    What this adds is provenance, experience, education and certifications,
    and an explicit statement when there is nothing to go on.
    """
    requirements = requirement_tokens(job.requirements)

    if evidence is None:
        evidence = candidate_evidence(candidate, db, read_cv=read_cv)

    match = match_skills(evidence.skills, requirements)

    # `match_skills` phrases itself for an applicant reading about themselves
    # ("the skills on your profile"). HR is a different reader with a
    # different risk - taking a low number as a verdict on a person - so the
    # disclaimer and the basis are rewritten for them. The arithmetic is
    # untouched; only the sentences around it change.
    match = {**match, "disclaimer": SCREENING_DISCLAIMER}

    if match["score_available"]:
        match["score_basis"] = (
            f"{len(match['matched_requirements'])} of {len(requirements)} "
            f"requirement(s) this job lists are evidenced by "
            f"{' and '.join(evidence.sources)}."
        )

    if not evidence.available:
        # Refuse to score rather than return 0%. An unknown is not a zero, and
        # a zero beside somebody's name reads as a judgement of them.
        match["score"] = None
        match["score_available"] = False
        match["score_basis"] = evidence.describe()
        match["matching_skills"] = []
        # Every requirement is unevidenced rather than "missing" - SmartHR has
        # not established that the candidate lacks them.
        match["skill_gaps"] = []
        match["unevidenced_requirements"] = requirements

    return {
        "label": MATCH_LABEL,
        "is_hiring_decision": False,
        "candidate": candidate_view(candidate, db, with_applications=False),
        "job": job_view(job, db, with_pipeline=False),
        "match": match,
        "evidence": evidence.as_dict(),
        "relevant_experience": relevant_experience(evidence, requirements),
        "education": relevant_education(evidence, requirements),
        "certifications": relevant_certifications(evidence, requirements),
        "decision_note": (
            "The hiring decision belongs to HR. This comparison advances no "
            "candidate, rejects nobody, and changes no application status."
        ),
    }


def rank_candidates(
    job: Job,
    db: Session,
    *,
    candidates: list[Candidate] | None = None,
    applied_only: bool = True,
    read_cvs: bool = True,
    limit: int | None = None,
    min_score: int | None = None,
) -> dict[str, Any]:
    """Score a pool of candidates against one job, best evidenced first.

    `applied_only` defaults to True: the people who applied for *this* job are
    who a recruiter means by "the candidates for this position". Setting it
    False widens the pool to everybody SmartHR holds, which is a different and
    more intrusive question, so the caller has to ask for it.

    Candidates with no evidence are **not dropped**. They sort last with
    `score: None` and a reason, because "we hold nothing for this person" is
    information a recruiter needs - it usually means ask them for a CV, not
    that they are unsuitable.
    """
    requirements = requirement_tokens(job.requirements)
    wanted = _bounded(limit)

    if candidates is None:
        if applied_only:
            candidates = (
                db.query(Candidate)
                .join(Application, Application.candidate_id == Candidate.id)
                .filter(Application.job_id == job.id)
                .distinct()
                .all()
            )
        else:
            candidates = (
                db.query(Candidate)
                .order_by(Candidate.created_at.desc(), Candidate.id.desc())
                .limit(MAX_LIMIT)
                .all()
            )

    if not candidates:
        return {
            "job": job_view(job, db),
            "label": MATCH_LABEL,
            "is_hiring_decision": False,
            "pool": "applicants to this job" if applied_only else "all candidates",
            "candidates_considered": 0,
            "results": [],
            "cvs_read": 0,
            "note": (
                f"No candidate has applied to '{job.title}' yet."
                if applied_only else
                "SmartHR holds no candidate records."
            ),
            "disclaimer": SCREENING_DISCLAIMER,
        }

    # Read CVs for the candidates most likely to need it, newest first, and
    # stop at the ceiling. Each read is a model call.
    reads = 0
    results: list[dict[str, Any]] = []

    for candidate in candidates:
        may_read = read_cvs and reads < MAX_CV_READS
        evidence = candidate_evidence(candidate, db, read_cv=may_read)

        if evidence.cv_read:
            reads += 1

        results.append(
            screen_candidate(
                candidate, job, db, read_cv=False, evidence=evidence
            )
        )

    # Unscoreable last, then by score, then by name - deterministic, so the
    # same question twice gives the same order.
    results.sort(
        key=lambda row: (
            row["match"]["score"] is None,
            -(row["match"]["score"] or 0),
            row["candidate"]["full_name"] or "",
        )
    )

    if min_score is not None:
        kept = [
            row for row in results
            if row["match"]["score"] is not None and row["match"]["score"] >= min_score
        ]
        excluded = len(results) - len(kept)
        results = kept
    else:
        excluded = 0

    logger.info(
        "Ranked candidates | job_id=%s pool=%s considered=%s cvs_read=%s returned=%s",
        job.id, "applied" if applied_only else "all",
        len(candidates), reads, min(len(results), wanted),
    )

    payload = {
        "job": job_view(job, db),
        "label": MATCH_LABEL,
        "is_hiring_decision": False,
        "pool": "applicants to this job" if applied_only else "all candidates",
        "candidates_considered": len(candidates),
        "cvs_read": reads,
        "cv_read_limit": MAX_CV_READS,
        "results": results[:wanted],
        "disclaimer": SCREENING_DISCLAIMER,
        "decision_note": (
            "This is a suggested reading order for a recruiter, not a "
            "shortlist and not a decision. Nothing here has changed any "
            "application."
        ),
    }

    if min_score is not None:
        payload["min_score"] = min_score
        payload["excluded_below_min_score"] = excluded

    if not requirements:
        payload["note"] = (
            f"'{job.title}' lists no requirements, so no candidate can be "
            f"scored against it. Add requirements to the requisition."
        )

    unevidenced = [
        row["candidate"]["full_name"]
        for row in results if row["match"]["score"] is None
    ]

    if unevidenced:
        payload["unevidenced_candidates"] = unevidenced
        payload["unevidenced_note"] = (
            f"{len(unevidenced)} candidate(s) could not be scored because "
            f"SmartHR holds no CV and no profile skills for them. That is "
            f"missing evidence, not a low match."
        )

    return payload
