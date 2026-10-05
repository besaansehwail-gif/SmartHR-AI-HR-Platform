"""The opportunity catalogue, as an external job seeker may see it.

An "opportunity" is not a new table. It is a **public projection** over two
tables SmartHR already had:

    jobs       -> job, internship        (employment_type tells them apart)
    trainings  -> training, free_course  (category tells them apart)

That is the whole design. An internship is a `jobs` row whose
`employment_type` is `internship`, so an applicant applying to one creates an
ordinary `applications` row and HR sees it on the recruitment board they
already use. No parallel pipeline, no second applications table.

**What this module exists to guarantee is what it leaves out.** `job_to_dict()`
in `app/routers/jobs.py` returns `created_by`, `created_by_email`,
`applications_count` and a full `pipeline_counts` breakdown - who opened the
requisition and how many rivals are at each stage. None of that is an
applicant's business. `public_job()` below builds its dictionary field by
field from scratch rather than filtering the HR one, because a projection that
starts from everything and removes the private parts leaks the next field
somebody adds. Starting from nothing does not.

Only `status = 'open'` jobs are listed. A draft, on-hold or closed requisition
is internal planning, and its existence is itself information.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Department, Job, Training

logger = logging.getLogger("smarthr.opportunities")

#: The organisation these opportunities belong to. SmartHR is a single-tenant
#: HR system - there is no company or tenant table - so this is presentation,
#: stated here rather than implied by a hardcoded string in a React component.
ORGANISATION_NAME = "SmartHR"

# ---------------------------------------------------------------------------
# Opportunity types
#
# The four an applicant browses. `job` and `internship` are `jobs` rows and can
# be applied to through SmartHR; `training` and `free_course` are `trainings`
# rows and cannot, because enrolment lives in `employee_trainings`, which keys
# on `employees.id` - and an applicant is not an employee. That is a real
# limit of the schema and the payload says so out loud rather than offering an
# Apply button that could not work.
# ---------------------------------------------------------------------------

TYPE_JOB = "job"
TYPE_INTERNSHIP = "internship"
TYPE_TRAINING = "training"
TYPE_FREE_COURSE = "free_course"

OPPORTUNITY_TYPES = (TYPE_JOB, TYPE_INTERNSHIP, TYPE_TRAINING, TYPE_FREE_COURSE)

#: Which types accept an application through SmartHR.
APPLICABLE_TYPES = (TYPE_JOB, TYPE_INTERNSHIP)

TYPE_LABELS = {
    TYPE_JOB: "Job",
    TYPE_INTERNSHIP: "Internship",
    TYPE_TRAINING: "Training Opportunity",
    TYPE_FREE_COURSE: "Free Course",
}

# ---------------------------------------------------------------------------
# jobs.employment_type
#
# Free text varchar(30), same strict-on-write / lenient-on-read pattern the
# rest of SmartHR uses for status columns (jobs.status, applications.status,
# interviews.status).
# ---------------------------------------------------------------------------

EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "temporary", "internship")

EMPLOYMENT_TYPE_ALIASES = {value: value for value in EMPLOYMENT_TYPES}
EMPLOYMENT_TYPE_ALIASES.update({
    "full time": "full_time", "full-time": "full_time", "fulltime": "full_time",
    "permanent": "full_time",
    "part time": "part_time", "part-time": "part_time", "parttime": "part_time",
    "intern": "internship", "internships": "internship", "trainee": "internship",
    "temp": "temporary",
})

EMPLOYMENT_TYPE_LABELS = {
    "full_time": "Full time",
    "part_time": "Part time",
    "contract": "Contract",
    "temporary": "Temporary",
    "internship": "Internship",
}

#: trainings.category, same pattern.
TRAINING_CATEGORIES = ("training", "free_course")

TRAINING_CATEGORY_ALIASES = {value: value for value in TRAINING_CATEGORIES}
TRAINING_CATEGORY_ALIASES.update({
    "free course": "free_course", "free-course": "free_course",
    "course": "free_course", "free": "free_course",
})


def normalize_employment_type(value: str | None) -> str:
    """Strict: used on write."""
    if value is None:
        return "full_time"

    normalized = EMPLOYMENT_TYPE_ALIASES.get(str(value).strip().lower())

    if normalized is None:
        raise ValueError(
            f"Invalid employment type '{value}'. "
            f"Allowed values: {', '.join(EMPLOYMENT_TYPES)}"
        )

    return normalized


def read_employment_type(value: str | None) -> str:
    """Lenient: used on read, so a legacy row never breaks a listing."""
    return EMPLOYMENT_TYPE_ALIASES.get((value or "").strip().lower(), "full_time")


def read_training_category(value: str | None) -> str:
    return TRAINING_CATEGORY_ALIASES.get((value or "").strip().lower(), "training")


# ---------------------------------------------------------------------------
# Requirement tokens
#
# `jobs.requirements` is free text. Every token below is a literal substring of
# it - the text is split, never interpreted - so a requirement shown to an
# applicant, or counted as a skill gap, is always something the job itself
# says. Nothing is added, expanded or inferred from a skills taxonomy, because
# SmartHR has no skills taxonomy and inventing one would be inventing data.
#
# On the seeded rows ("Python, SQL, Excel, Power BI") this yields exactly the
# four skills. On prose it yields whole clauses, which simply match less often
# - a weaker result, never a wrong one.
# ---------------------------------------------------------------------------

_SPLIT = re.compile(r"[,;\n\r،]|(?:^|\s)[-*•]\s+")

#: Longer than this and it is a sentence rather than a named skill. Kept and
#: shown, but flagged so the UI can present it as a requirement line.
PHRASE_LENGTH = 60


def requirement_tokens(requirements: str | None) -> list[str]:
    """The requirement items a job lists, in the job's own words."""
    if not requirements:
        return []

    seen: set[str] = set()
    tokens: list[str] = []

    for piece in _SPLIT.split(requirements):
        if piece is None:
            continue

        cleaned = re.sub(r"\s+", " ", piece).strip(" \t.-*•")

        if not cleaned:
            continue

        key = cleaned.lower()

        if key in seen:
            continue

        seen.add(key)
        tokens.append(cleaned)

    return tokens


def split_skills(raw: str | None) -> list[str]:
    """An applicant's comma-separated skills, as they typed them."""
    return requirement_tokens(raw)


# ---------------------------------------------------------------------------
# Public projections
# ---------------------------------------------------------------------------

def _department_name(department_id: int | None, db: Session) -> str | None:
    if department_id is None:
        return None

    department = (
        db.query(Department).filter(Department.id == department_id).first()
    )

    return department.name if department else None


def public_job(job: Job, db: Session) -> dict[str, Any]:
    """One `jobs` row as an opportunity listing.

    Built field by field. Everything internal - created_by, the pipeline
    counts, the raw status - is absent because it was never added, not because
    it was removed afterwards.
    """
    employment_type = read_employment_type(job.employment_type)
    opportunity_type = (
        TYPE_INTERNSHIP if employment_type == "internship" else TYPE_JOB
    )
    department_name = _department_name(job.department_id, db)
    tokens = requirement_tokens(job.requirements)

    return {
        "opportunity_id": f"job-{job.id}",
        "source": "job",
        "id": job.id,
        "title": job.title,
        "organization": ORGANISATION_NAME,
        "department_name": department_name,
        "opportunity_type": opportunity_type,
        "opportunity_type_label": TYPE_LABELS[opportunity_type],
        "employment_type": employment_type,
        "employment_type_label": EMPLOYMENT_TYPE_LABELS[employment_type],
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "skills": tokens,
        "requirement_phrases": [t for t in tokens if len(t) > PHRASE_LENGTH],
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "is_expired": bool(job.deadline and job.deadline < date.today()),
        "posted_at": job.created_at.isoformat() if job.created_at else None,
        "can_apply": True,
        "how_to_apply": (
            "Apply through SmartHR: open the opportunity and submit your "
            "application with the CV on your profile."
        ),
        "external_url": None,
    }


def public_training(training: Training) -> dict[str, Any]:
    """One `trainings` row as a learning opportunity.

    `can_apply` is False and says why: enrolment is `employee_trainings`, which
    keys on `employees.id`. An applicant has no employees row, so SmartHR
    genuinely cannot enrol them, and the payload states that instead of
    offering an action that would fail.
    """
    category = read_training_category(training.category)
    tokens = requirement_tokens(training.description)

    return {
        "opportunity_id": f"training-{training.id}",
        "source": "training",
        "id": training.id,
        "title": training.title,
        "organization": training.provider or ORGANISATION_NAME,
        "department_name": None,
        "opportunity_type": category,
        "opportunity_type_label": TYPE_LABELS[category],
        "employment_type": None,
        "employment_type_label": None,
        "location": None,
        "description": training.description,
        "requirements": None,
        "skills": tokens if len(tokens) > 1 else [],
        "requirement_phrases": [],
        "duration_hours": training.duration_hours,
        "deadline": None,
        "is_expired": False,
        "posted_at": training.created_at.isoformat() if training.created_at else None,
        "can_apply": False,
        "how_to_apply": (
            f"Enrol with the provider{f' ({training.provider})' if training.provider else ''}. "
            "SmartHR records course enrolment for employees only, so an "
            "applicant account cannot be enrolled here."
        ),
        "external_url": training.url,
    }


@dataclass
class OpportunityQuery:
    """What an applicant (or the Career Agent) asked for."""

    search: str | None = None
    opportunity_type: str | None = None
    location: str | None = None
    limit: int = 50


# ---------------------------------------------------------------------------
# Free-text search
#
# The query is often a whole sentence rather than keywords, because the Career
# Agent passes the applicant's own words straight through ("find me AI
# internships"). So the filler is dropped and what is left must *all* appear.
#
# "All of them must appear" is the important half. Matching on *any* word would
# make "quantum cryptography jobs in Antarctica" return every job through the
# word "jobs", and an applicant reading that list would reasonably conclude
# SmartHR had quantum cryptography roles. Requiring every content word means an
# absent topic returns nothing, which is the truthful answer.
# ---------------------------------------------------------------------------

_SEARCH_STOPWORDS = frozenset({
    # asking words
    "find", "show", "get", "give", "search", "look", "looking", "list", "want",
    "need", "seeking", "tell", "please", "any", "some", "available", "open",
    "opportunity", "opportunities", "opening", "openings", "position",
    "positions", "role", "roles", "vacancy", "vacancies",
    # grammar
    "me", "my", "i", "a", "an", "the", "for", "to", "in", "on", "at", "of",
    "with", "and", "or", "is", "are", "am", "do", "does", "can", "could",
    "would", "should", "that", "this", "there", "here", "about", "as", "by",
    "from", "you", "your", "it", "its", "all",
})


def _stem(word: str) -> str:
    """Crude plural trimming, so "internships" finds an "Internship"."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"

    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]

    return word


def _search_terms(needle: str) -> list[str]:
    words = re.findall(r"[a-z0-9+#.]+", needle.lower())
    terms = [_stem(w) for w in words if w not in _SEARCH_STOPWORDS and len(w) > 1]

    # A query made entirely of filler ("show me anything") has no terms, and
    # returning everything is then the right answer rather than nothing.
    return terms


def _matches_search(opportunity: dict[str, Any], needle: str) -> bool:
    haystack = " ".join(
        str(opportunity.get(field) or "")
        for field in ("title", "description", "requirements", "department_name",
                      "location", "organization", "opportunity_type",
                      "opportunity_type_label", "employment_type_label")
    ).lower()

    # Stemmed on both sides so "internship" matches "Internships" and back.
    hay_words = {_stem(w) for w in re.findall(r"[a-z0-9+#.]+", haystack)}

    return all(
        term in hay_words or term in haystack
        for term in _search_terms(needle)
    )


def list_opportunities(
    db: Session, query: OpportunityQuery | None = None
) -> list[dict[str, Any]]:
    """Every opportunity an applicant may see, newest first.

    Reads real rows only. There is no seeded, sample or placeholder
    opportunity anywhere in this module: an empty database returns an empty
    list, and the UI says so.
    """
    query = query or OpportunityQuery()
    wanted = query.opportunity_type

    results: list[dict[str, Any]] = []

    if wanted in (None, TYPE_JOB, TYPE_INTERNSHIP):
        jobs = (
            db.query(Job)
            .filter(Job.status == "open")
            .order_by(Job.created_at.desc(), Job.id.desc())
            .all()
        )
        results.extend(public_job(job, db) for job in jobs)

    if wanted in (None, TYPE_TRAINING, TYPE_FREE_COURSE):
        trainings = (
            db.query(Training)
            .order_by(Training.created_at.desc(), Training.id.desc())
            .all()
        )
        results.extend(public_training(training) for training in trainings)

    if wanted is not None:
        results = [o for o in results if o["opportunity_type"] == wanted]

    if query.location:
        needle = query.location.strip().lower()
        results = [
            o for o in results if needle in str(o.get("location") or "").lower()
        ]

    if query.search and query.search.strip():
        results = [o for o in results if _matches_search(o, query.search.strip())]

    return results[: max(1, min(query.limit, 200))]


def get_opportunity(
    db: Session, source: str, row_id: int
) -> dict[str, Any] | None:
    """One opportunity by source and row id, or None."""
    if source == "job":
        job = db.query(Job).filter(Job.id == row_id).first()

        # An applicant may only open an opportunity that is actually on offer.
        # A closed or draft requisition is internal, so this is a 404 for them
        # exactly as a non-existent id would be.
        if job is None or job.status != "open":
            return None

        return public_job(job, db)

    if source == "training":
        training = db.query(Training).filter(Training.id == row_id).first()

        if training is None:
            return None

        return public_training(training)

    return None


def parse_opportunity_id(opportunity_id: str) -> tuple[str, int] | None:
    """Turn "job-3" into ("job", 3). None if it is not a valid reference."""
    if not opportunity_id or "-" not in opportunity_id:
        return None

    source, _, raw_id = opportunity_id.partition("-")

    if source not in ("job", "training"):
        return None

    try:
        return source, int(raw_id)
    except ValueError:
        return None


def counts_by_type(db: Session) -> dict[str, int]:
    """How many of each type are on offer, for the dashboard."""
    everything = list_opportunities(db, OpportunityQuery(limit=200))

    counts = {opportunity_type: 0 for opportunity_type in OPPORTUNITY_TYPES}

    for opportunity in everything:
        counts[opportunity["opportunity_type"]] += 1

    return counts
