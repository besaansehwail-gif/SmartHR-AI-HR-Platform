"""Internal HR Agent tools - what a recruiter's agent is allowed to do.

Ten tools, registered on the **same** `smarthr_mcp` server as `get_my_leave`,
`parse_cv`, `search_hr_policies` and the Career Agent's eight. There is no
second MCP system and no second server: the HR Agent is a third *audience* for
the one server, and which tools it sees is decided by `tools_for_role(2)`
rather than by anything in the agent.

    requisitions   search_jobs, get_job, get_job_requirements
    people         search_candidates, get_candidate, get_candidate_cv
    pipeline       search_applications, get_application
    screening      match_candidate_to_job, rank_candidates_for_job

Three properties hold across all ten.

**Every one of them reads.** There is no HR Agent tool that writes anything,
which is the structural answer to "the agent must never hire or reject": it is
not a rule the model is asked to obey, it is a verb the model has no way to
express. Advancing, rejecting or scheduling remains `PATCH
/applications/{id}/status` and the Interviews screen - a recruiter's deliberate
act in a UI, not a sentence in a chat.

**Ids here are subjects, not identity claims.** The Career Agent's tools take
no ids at all, because they answer "my profile" and accepting a candidate_id
would be the whole vulnerability. These answer "that candidate", about
organisation-scoped recruitment data Admin and HR may already read in full
through `GET /candidates/`. So a job_id or candidate_id chosen by the model
selects *which record*; it never says who is asking. Who is asking comes from
the principal FastAPI bound from the verified JWT, and `authorise()` re-reads
`users.role_id` before any handler runs - a Manager, Employee or Applicant
reaching one of these is refused whatever id they pass.

**Every tool calls a service.** No SQL, no table names and no scoring rules
live in this file: `app/services/screening_service.py` owns those, and it in
turn imports the score itself from `app/services/matching_service.py`, which
the applicant side uses. One piece of arithmetic, three callers.
"""

import logging
from typing import Annotated, Any

from pydantic import Field

from app.database import SessionLocal
from app.mcp.identity import NoPrincipalBound, current_principal
from app.mcp.permissions import ToolNotPermitted, authorise
from app.mcp.server import smarthr_mcp
from app.services import screening_service
from app.services.screening_service import ScreeningError

logger = logging.getLogger("smarthr.mcp.tools")


def _error(code: str, message: str) -> dict[str, Any]:
    """A refusal the model can act on, rather than a protocol error."""
    return {"ok": False, "error_code": code, "error": message}


class _Refused(Exception):
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload


def _session(tool_name: str):
    """Authorise the caller from the database, then open a session.

    Returns `(db, principal)`; the caller closes `db`. Raises `_Refused`
    carrying the payload to return, so each tool's happy path stays readable -
    the same shape `app/mcp/tools/career.py` uses.
    """
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
        logger.warning("%s called with no principal bound", tool_name)
        raise _Refused(_error("no_principal", str(exc))) from exc

    db = SessionLocal()

    try:
        authorise(tool_name, principal.user_id, db)
    except ToolNotPermitted as exc:
        logger.info(
            "%s refused | user_id=%s code=%s", tool_name, principal.user_id, exc.code
        )
        db.close()
        raise _Refused(_error(exc.code, str(exc))) from exc

    return db, principal


# ===========================================================================
# Requisitions
# ===========================================================================

@smarthr_mcp.tool(
    name="search_jobs",
    title="Search job requisitions",
    description=(
        "Search SmartHR's job requisitions by words in the title, description "
        "or requirements. Returns real requisitions with their department, "
        "status, employment type, listed requirements and how many people "
        "have applied. Use this first when the recruiter names a position in "
        "words rather than by id. Unlike the applicant-facing catalogue this "
        "includes requisitions that are on hold, draft or closed, because HR "
        "screens against those too. If it returns nothing, SmartHR has no "
        "such requisition - say so rather than describing one."
    ),
)
def search_jobs(
    search: Annotated[
        str | None,
        Field(default=None, description=(
            "Words to look for, e.g. 'data analyst' or 'python'. Omit to list "
            "recent requisitions."
        )),
    ] = None,
    status: Annotated[
        str | None,
        Field(default=None, description=(
            "Restrict to one status: 'open', 'on_hold', 'closed' or 'draft'."
        )),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=50, description="How many to return. Default 10."),
    ] = None,
) -> dict[str, Any]:
    """Real requisitions from the jobs table."""
    try:
        db, principal = _session("search_jobs")
    except _Refused as refusal:
        return refusal.payload

    try:
        jobs = screening_service.find_jobs(
            db, search=search, status=status, limit=limit
        )

        logger.info(
            "search_jobs ok | user_id=%s found=%s", principal.user_id, len(jobs)
        )

        return {
            "ok": True,
            "jobs": jobs,
            "count": len(jobs),
            "note": (
                "No requisition in SmartHR matches those words."
                if not jobs else
                "Requirements are shown exactly as the recruiter typed them on "
                "the requisition."
            ),
        }
    except Exception:
        logger.exception("search_jobs failed | user_id=%s", principal.user_id)
        return _error("database_error", "The requisitions could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_job",
    title="Get one job requisition",
    description=(
        "Return one requisition in full: its title, department, description, "
        "the requirements it lists, its status, employment type, location, "
        "deadline, and the pipeline counts of how many applicants sit at each "
        "stage. Give a job_id, or a title when the recruiter named the "
        "position in words. An ambiguous title is refused with the list of "
        "matches so you can ask which one is meant - never pick one yourself."
    ),
)
def get_job(
    job_id: Annotated[
        int | None,
        Field(default=None, description="The requisition's id."),
    ] = None,
    title: Annotated[
        str | None,
        Field(default=None, description=(
            "The requisition's title, e.g. 'Data Analyst'. Used when job_id "
            "is not given."
        )),
    ] = None,
) -> dict[str, Any]:
    """One requisition, resolved by id or by an unambiguous title."""
    try:
        db, principal = _session("get_job")
    except _Refused as refusal:
        return refusal.payload

    try:
        job = screening_service.resolve_job(db, job_id=job_id, title=title)

        logger.info("get_job ok | user_id=%s job_id=%s", principal.user_id, job.id)

        return {"ok": True, "job": screening_service.job_view(job, db)}
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception("get_job failed | user_id=%s", principal.user_id)
        return _error("database_error", "The requisition could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_job_requirements",
    title="Get a job's requirements",
    description=(
        "Return just the requirement items one requisition lists, split into "
        "the individual items that matching compares against. Use it before "
        "comparing candidates so you are reasoning about the real "
        "requirements rather than what the title suggests. Every item is a "
        "literal piece of what the recruiter typed - nothing is interpreted, "
        "expanded or inferred. A requisition with no requirements returns an "
        "empty list, and that means no candidate can be scored against it."
    ),
)
def get_job_requirements(
    job_id: Annotated[
        int | None, Field(default=None, description="The requisition's id.")
    ] = None,
    title: Annotated[
        str | None,
        Field(default=None, description="The requisition's title, if job_id is unknown."),
    ] = None,
) -> dict[str, Any]:
    """The requirement items, in the job's own words."""
    try:
        db, principal = _session("get_job_requirements")
    except _Refused as refusal:
        return refusal.payload

    try:
        job = screening_service.resolve_job(db, job_id=job_id, title=title)
        view = screening_service.job_view(job, db, with_pipeline=False)

        logger.info(
            "get_job_requirements ok | user_id=%s job_id=%s items=%s",
            principal.user_id, job.id, view["requirement_count"],
        )

        return {
            "ok": True,
            "job_id": job.id,
            "title": job.title,
            "requirements": view["requirements"],
            "requirements_text": view["requirements_text"],
            "requirement_count": view["requirement_count"],
            "requirements_available": view["requirements_available"],
            "note": view.get("note"),
        }
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception("get_job_requirements failed | user_id=%s", principal.user_id)
        return _error("database_error", "The requirements could not be read just now.")
    finally:
        db.close()


# ===========================================================================
# Candidates
# ===========================================================================

@smarthr_mcp.tool(
    name="search_candidates",
    title="Search candidates",
    description=(
        "Search SmartHR's candidate records by name, email, location or the "
        "skills on their profile, and optionally narrow to the people who "
        "applied to a particular job or who sit at a particular pipeline "
        "stage. Returns real candidate rows with whether each has a CV on "
        "file and what skills their profile lists. IMPORTANT: this searches "
        "the candidates table, not the text of CV documents - SmartHR stores "
        "CV files, not their contents, so a skill search only finds people "
        "whose profile names it. To know what a CV says, read it with "
        "get_candidate_cv. Say that plainly rather than implying the search "
        "covered every CV."
    ),
)
def search_candidates(
    search: Annotated[
        str | None,
        Field(default=None, description=(
            "Words to look for in the name, email, location or profile "
            "skills, e.g. 'Python, SQL'. Every word must appear."
        )),
    ] = None,
    job_id: Annotated[
        int | None,
        Field(default=None, description=(
            "Only candidates who have applied to this requisition."
        )),
    ] = None,
    stage: Annotated[
        str | None,
        Field(default=None, description=(
            "Only candidates at this pipeline stage: applied, screening, "
            "shortlisted, interview, assessment, offer, hired or rejected."
        )),
    ] = None,
    has_cv: Annotated[
        bool | None,
        Field(default=None, description="True for only candidates with a CV on file."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=50, description="How many to return. Default 10."),
    ] = None,
) -> dict[str, Any]:
    """Real candidate rows from the candidates table."""
    try:
        db, principal = _session("search_candidates")
    except _Refused as refusal:
        return refusal.payload

    try:
        candidates = screening_service.find_candidates(
            db, search=search, job_id=job_id, stage=stage,
            has_cv=has_cv, limit=limit,
        )

        without_evidence = [
            c["full_name"] for c in candidates
            if not c["profile_skills"] and not c["has_cv"]
        ]

        logger.info(
            "search_candidates ok | user_id=%s found=%s no_evidence=%s",
            principal.user_id, len(candidates), len(without_evidence),
        )

        return {
            "ok": True,
            "candidates": candidates,
            "count": len(candidates),
            "searched": "candidate records (name, email, location, profile skills)",
            "not_searched": (
                "CV document text - SmartHR stores CV files, not their text"
            ),
            "candidates_without_any_evidence": without_evidence,
            "note": (
                "No candidate in SmartHR matches those filters."
                if not candidates else
                "profile_skills is filled in only when the person registered "
                "through the Applicant portal and typed it. An empty list "
                "means SmartHR was not told, not that they lack the skill."
            ),
        }
    except Exception:
        logger.exception("search_candidates failed | user_id=%s", principal.user_id)
        return _error("database_error", "The candidates could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_candidate",
    title="Get a candidate's profile",
    description=(
        "Return one candidate's full SmartHR record: their name, contact "
        "details, location, the skills on their profile, whether they have a "
        "CV on file, and every application they have made with its job and "
        "current stage. This is the candidate profile - use it whenever you "
        "need to know who someone is or where they are in the pipeline. It "
        "does not include interviewer notes or any match score: a score "
        "belongs to a comparison with a specific job and comes from "
        "match_candidate_to_job."
    ),
)
def get_candidate(
    candidate_id: Annotated[
        int | None, Field(default=None, description="The candidate's id.")
    ] = None,
    name: Annotated[
        str | None,
        Field(default=None, description=(
            "The candidate's full name, used when candidate_id is not known."
        )),
    ] = None,
) -> dict[str, Any]:
    """One candidate's dossier, by id or by name."""
    try:
        db, principal = _session("get_candidate")
    except _Refused as refusal:
        return refusal.payload

    try:
        candidate = screening_service.resolve_candidate_row(
            db, candidate_id=candidate_id, name=name
        )

        logger.info(
            "get_candidate ok | user_id=%s candidate_id=%s",
            principal.user_id, candidate.id,
        )

        return {
            "ok": True,
            "candidate": screening_service.candidate_view(candidate, db),
        }
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception("get_candidate failed | user_id=%s", principal.user_id)
        return _error("database_error", "The candidate could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_candidate_cv",
    title="Read a candidate's CV",
    description=(
        "Read the structured contents of a candidate's most recent CV: "
        "skills, work experience, education, certifications and languages, "
        "extracted from the document itself. Use it when you need to know "
        "what someone can actually do and their profile lists nothing. Every "
        "value is copied from the document - a null field or an empty list "
        "means the CV did not state it, which is not the same as the "
        "candidate not having it, and you must say so that way. This reads a "
        "CV; it does not score, rank or recommend. If the candidate has no CV "
        "on file the tool says so and you should report that rather than "
        "reasoning about them anyway."
    ),
)
def get_candidate_cv(
    candidate_id: Annotated[
        int | None, Field(default=None, description="The candidate's id.")
    ] = None,
    name: Annotated[
        str | None,
        Field(default=None, description=(
            "The candidate's full name, used when candidate_id is not known."
        )),
    ] = None,
) -> dict[str, Any]:
    """The candidate's CV, through the shared CV pipeline.

    Reads via `screening_service.candidate_evidence(read_cv=True)`, which
    calls `analyse_cv_bytes()` - the same function `POST /cvs/upload` and the
    `parse_cv` MCP tool use. There is no second parser and no second prompt.
    """
    try:
        db, principal = _session("get_candidate_cv")
    except _Refused as refusal:
        return refusal.payload

    try:
        candidate = screening_service.resolve_candidate_row(
            db, candidate_id=candidate_id, name=name
        )
        evidence = screening_service.candidate_evidence(candidate, db, read_cv=True)

        if not evidence.has_cv:
            return _error(
                "no_cv",
                f"{candidate.first_name} {candidate.last_name} has no CV on "
                f"file in SmartHR, so there is nothing to read. Their skills "
                f"are unknown unless their profile lists some.",
            )

        if evidence.cv_error_code:
            return _error(evidence.cv_error_code, evidence.cv_error or "unreadable")

        logger.info(
            "get_candidate_cv ok | user_id=%s candidate_id=%s skills=%s roles=%s",
            principal.user_id, candidate.id,
            len(evidence.cv_skills), len(evidence.experience),
        )

        return {
            "ok": True,
            "candidate_id": candidate.id,
            "candidate_name": f"{candidate.first_name} {candidate.last_name}".strip(),
            "cv": {
                "id": evidence.cv_id,
                "file_name": evidence.cv_file_name,
            },
            "summary": evidence.summary,
            "skills": evidence.cv_skills,
            "experience": evidence.experience,
            "education": evidence.education,
            "certifications": evidence.certifications,
            "languages": evidence.languages,
            "note": (
                "Every field was copied from the CV document. SmartHR does not "
                "persist parsed CV contents - this was extracted on request "
                "and is for a recruiter to review. It is not a hiring decision."
            ),
        }
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception("get_candidate_cv failed | user_id=%s", principal.user_id)
        return _error("database_error", "The CV could not be read just now.")
    finally:
        db.close()


# ===========================================================================
# Pipeline
# ===========================================================================

@smarthr_mcp.tool(
    name="search_applications",
    title="Search applications",
    description=(
        "Return real application rows, optionally narrowed to one "
        "requisition, one candidate or one pipeline stage. Each row carries "
        "the candidate, the job, the current stage, when it was submitted and "
        "how many interviews are scheduled. Use it to answer questions about "
        "the pipeline itself - who applied to what, and where they are. "
        "Interviewer notes and interviewer identities are never included."
    ),
)
def search_applications(
    job_id: Annotated[
        int | None, Field(default=None, description="Only this requisition's applications.")
    ] = None,
    candidate_id: Annotated[
        int | None, Field(default=None, description="Only this candidate's applications.")
    ] = None,
    status: Annotated[
        str | None,
        Field(default=None, description=(
            "Only this stage: applied, screening, shortlisted, interview, "
            "assessment, offer, hired or rejected."
        )),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=50, description="How many to return. Default 10."),
    ] = None,
) -> dict[str, Any]:
    """Real rows from the applications table."""
    try:
        db, principal = _session("search_applications")
    except _Refused as refusal:
        return refusal.payload

    try:
        applications = screening_service.find_applications(
            db, job_id=job_id, candidate_id=candidate_id, status=status, limit=limit
        )

        logger.info(
            "search_applications ok | user_id=%s found=%s",
            principal.user_id, len(applications),
        )

        return {
            "ok": True,
            "applications": applications,
            "count": len(applications),
            "note": (
                "No application matches those filters."
                if not applications else
                "Stage names are SmartHR's recruitment vocabulary, read from "
                "applications.status."
            ),
        }
    except Exception:
        logger.exception("search_applications failed | user_id=%s", principal.user_id)
        return _error("database_error", "The applications could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_application",
    title="Get one application",
    description=(
        "Return one application in full: the candidate, the requisition, the "
        "current pipeline stage, when it was submitted and its scheduled "
        "interviews. Interviewer notes and interviewer identities are never "
        "included. You cannot change an application's stage - there is no "
        "tool for it, because advancing or rejecting a candidate is the "
        "recruiter's decision to make in the Recruitment screens."
    ),
)
def get_application(
    application_id: Annotated[int, Field(description="The application's id.")],
) -> dict[str, Any]:
    """One application row."""
    try:
        db, principal = _session("get_application")
    except _Refused as refusal:
        return refusal.payload

    try:
        application = screening_service.get_application(application_id, db)

        logger.info(
            "get_application ok | user_id=%s application_id=%s",
            principal.user_id, application.id,
        )

        return {
            "ok": True,
            "application": screening_service.application_view(application, db),
        }
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception("get_application failed | user_id=%s", principal.user_id)
        return _error("database_error", "The application could not be read just now.")
    finally:
        db.close()


# ===========================================================================
# Screening
# ===========================================================================

@smarthr_mcp.tool(
    name="match_candidate_to_job",
    title="Match one candidate to one job",
    description=(
        "Compare one real candidate with one real requisition and return a "
        "match score, the matching skills, the skill gaps, their relevant "
        "experience, education and certifications. Skills come from the "
        "candidate's profile and from reading their CV; requirements come "
        "from the requisition. Every skill and every gap is a literal string "
        "from one of those sources - nothing is inferred. When SmartHR holds "
        "no CV and no profile skills the score is null with a reason, NOT "
        "zero: that means the evidence is missing, not that the candidate is "
        "unsuitable, and you must present it that way. The result is labelled "
        "'AI Match / Recommendation'. It is not a hiring decision and it "
        "changes nothing in the pipeline."
    ),
)
def match_candidate_to_job(
    candidate_id: Annotated[
        int | None, Field(default=None, description="The candidate's id.")
    ] = None,
    candidate_name: Annotated[
        str | None,
        Field(default=None, description=(
            "The candidate's full name, e.g. 'Samer Ali'. Used when "
            "candidate_id is not known, so you do not have to search first. "
            "An ambiguous name is refused with the matches listed."
        )),
    ] = None,
    job_id: Annotated[
        int | None, Field(default=None, description="The requisition's id.")
    ] = None,
    job_title: Annotated[
        str | None,
        Field(default=None, description="The requisition's title, if job_id is unknown."),
    ] = None,
    read_cv: Annotated[
        bool | None,
        Field(default=None, description=(
            "Read the candidate's CV for skills and experience. Default true. "
            "Set false only to compare on profile skills alone."
        )),
    ] = None,
) -> dict[str, Any]:
    """One candidate against one requisition, with provenance."""
    try:
        db, principal = _session("match_candidate_to_job")
    except _Refused as refusal:
        return refusal.payload

    try:
        candidate = screening_service.resolve_candidate_row(
            db, candidate_id=candidate_id, name=candidate_name
        )
        job = screening_service.resolve_job(db, job_id=job_id, title=job_title)

        result = screening_service.screen_candidate(
            candidate, job, db, read_cv=True if read_cv is None else read_cv
        )

        logger.info(
            "match_candidate_to_job ok | user_id=%s candidate_id=%s job_id=%s score=%s",
            principal.user_id, candidate.id, job.id, result["match"]["score"],
        )

        return {"ok": True, **result}
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception(
            "match_candidate_to_job failed | user_id=%s", principal.user_id
        )
        return _error("database_error", "The comparison could not be made just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="rank_candidates_for_job",
    title="Rank candidates for a job",
    description=(
        "Score every candidate against one requisition and return them best "
        "evidenced first, each with their match score, matching skills, skill "
        "gaps and relevant experience. By default the pool is the people who "
        "actually applied to that requisition, which is what a recruiter "
        "normally means; set include_all_candidates to widen it to everyone "
        "SmartHR holds. CVs are read for up to eight candidates per call. "
        "Candidates SmartHR holds no evidence for are returned last with a "
        "null score and a reason - they are not dropped, because 'we have no "
        "CV for this person' is something the recruiter needs to know. This "
        "is a suggested reading order, not a shortlist and not a decision: it "
        "advances nobody and rejects nobody."
    ),
)
def rank_candidates_for_job(
    job_id: Annotated[
        int | None, Field(default=None, description="The requisition's id.")
    ] = None,
    job_title: Annotated[
        str | None,
        Field(default=None, description=(
            "The requisition's title, e.g. 'Data Analyst', if job_id is unknown."
        )),
    ] = None,
    include_all_candidates: Annotated[
        bool | None,
        Field(default=None, description=(
            "False (default) ranks only those who applied to this "
            "requisition. True ranks every candidate in SmartHR."
        )),
    ] = None,
    min_score: Annotated[
        int | None,
        Field(default=None, ge=0, le=100, description=(
            "Return only candidates scoring at least this percentage. "
            "Candidates with no evidence are excluded by this filter and the "
            "count of them is reported."
        )),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=50, description="How many to return. Default 10."),
    ] = None,
) -> dict[str, Any]:
    """Real candidates scored against one real requisition."""
    try:
        db, principal = _session("rank_candidates_for_job")
    except _Refused as refusal:
        return refusal.payload

    try:
        job = screening_service.resolve_job(db, job_id=job_id, title=job_title)

        result = screening_service.rank_candidates(
            job, db,
            applied_only=not bool(include_all_candidates),
            read_cvs=True,
            limit=limit,
            min_score=min_score,
        )

        logger.info(
            "rank_candidates_for_job ok | user_id=%s job_id=%s considered=%s returned=%s",
            principal.user_id, job.id,
            result["candidates_considered"], len(result["results"]),
        )

        return {"ok": True, **result}
    except ScreeningError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        logger.exception(
            "rank_candidates_for_job failed | user_id=%s", principal.user_id
        )
        return _error("database_error", "The candidates could not be ranked just now.")
    finally:
        db.close()
