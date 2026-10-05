"""Career Agent tools - what an Applicant's agent is allowed to do.

Eight tools, registered on the same `smarthr_mcp` server as `get_my_leave`,
`parse_cv` and `search_hr_policies`. The Career Agent is not a second tool
system: it is a second *audience* for the one MCP server, and which tools it
sees is decided by `tools_for_role(5)` rather than by anything in the agent.

    read    get_my_profile, get_my_cv, get_my_applications,
            get_my_application_status, search_opportunities, get_opportunity,
            match_my_profile_to_opportunity
    write   submit_application

Three rules hold across all eight, and they are structural rather than
conventional:

* **No tool takes an identity.** Not a candidate_id, not a user_id, not an
  email. The subject is the principal FastAPI bound from the verified JWT
  before the session opened. A model cannot ask about somebody else because
  there is no argument in which to name them.
* **Every tool authorises from the database.** `authorise()` re-reads
  `users.role_id`, so a stale or forged claim buys nothing, and a deactivated
  account is refused.
* **Every tool calls a service.** No SQL, no table names and no business rules
  live in this file - `app/services/` owns those, and the REST routes call the
  same functions. The MCP layer is protocol, not logic.

The write tool is the one worth reading closely. `submit_application` declares
`job_id` and `confirmed_by_applicant`, and the agent may only set the latter
when the applicant asked, in words, to apply. That is a prompt instruction, so
it is backed by something that is not: `app/ai/career_agent.py` does not even
offer this tool to the model unless the applicant's message expresses intent to
apply. A model that decides to be helpful mid-conversation cannot reach it.
"""

import logging
from typing import Annotated, Any

from pydantic import Field

from app.database import SessionLocal
from app.identity import resolve_candidate
from app.mcp.identity import NoPrincipalBound, current_principal
from app.mcp.permissions import ToolNotPermitted, authorise
from app.mcp.server import smarthr_mcp
from app.services import applicant_service, application_service
from app.services.application_service import ApplicationError
from app.services.matching_service import match_skills, rank_opportunities
from app.services.opportunity_service import (
    OPPORTUNITY_TYPES,
    OpportunityQuery,
    get_opportunity as get_opportunity_row,
    list_opportunities,
    parse_opportunity_id,
)

logger = logging.getLogger("smarthr.mcp.tools")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message}


class _Refused(Exception):
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload


def _candidate_session(tool_name: str):
    """Authorise the caller and resolve their candidate row.

    Returns `(db, candidate)`; the caller closes `db`. Raises `_Refused`
    carrying the payload to return, so each tool's happy path stays readable.
    """
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
        logger.warning("%s called with no principal bound", tool_name)
        raise _Refused(_error("no_principal", str(exc))) from exc

    db = SessionLocal()

    try:
        account = authorise(tool_name, principal.user_id, db)
    except ToolNotPermitted as exc:
        logger.info(
            "%s refused | user_id=%s code=%s", tool_name, principal.user_id, exc.code
        )
        db.close()
        raise _Refused(_error(exc.code, str(exc))) from exc

    candidate = resolve_candidate(account, db)

    if candidate is None:
        db.close()
        raise _Refused(_error(
            "no_applicant_profile",
            "This account is not linked to an applicant profile, so it has no "
            "profile, CV or applications to report.",
        ))

    return db, candidate


def _catalogue_session(tool_name: str):
    """Authorise the caller for a tool that reads only public listings."""
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
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
# Profile
# ===========================================================================

@smarthr_mcp.tool(
    name="get_my_profile",
    title="My applicant profile",
    description=(
        "Return the signed-in applicant's own profile: their name, contact "
        "details, location, the skills they have listed, and how complete the "
        "profile is. Use it before recommending opportunities, so suggestions "
        "are based on what this person actually says they can do. It always "
        "answers for the signed-in applicant and cannot return anyone else's "
        "profile. Skills come from what the applicant typed on their profile - "
        "if the list is empty, say so rather than guessing at their skills."
    ),
)
def get_my_profile() -> dict[str, Any]:
    """The signed-in applicant's own profile. Takes no identifier."""
    try:
        db, candidate = _candidate_session("get_my_profile")
    except _Refused as refusal:
        return refusal.payload

    try:
        profile = applicant_service.profile_dict(candidate, db)

        logger.info(
            "get_my_profile ok | candidate_id=%s skills=%s has_cv=%s",
            candidate.id, len(profile["skills"]), profile["has_cv"],
        )

        return {"ok": True, **profile}
    except Exception:
        logger.exception("get_my_profile failed | candidate_id=%s", candidate.id)
        return _error("database_error", "Your profile could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_my_cv",
    title="My CV",
    description=(
        "Report whether the signed-in applicant has a CV on file and when it "
        "was uploaded. Use it before helping them apply, because an "
        "application needs a CV. This returns the CV's status and filename, "
        "not its contents: SmartHR does not store parsed CV data, so do not "
        "claim to know what the CV says. The skills to reason about are the "
        "ones on the applicant's profile, from get_my_profile."
    ),
)
def get_my_cv() -> dict[str, Any]:
    """Whether this applicant has a CV, and which one is current."""
    try:
        db, candidate = _candidate_session("get_my_cv")
    except _Refused as refusal:
        return refusal.payload

    try:
        cvs = applicant_service.my_cvs(candidate, db)

        logger.info("get_my_cv ok | candidate_id=%s cvs=%s", candidate.id, len(cvs))

        return {
            "ok": True,
            "has_cv": bool(cvs),
            "current_cv": cvs[0] if cvs else None,
            "cv_count": len(cvs),
            # Said explicitly because it is the kind of thing a model would
            # otherwise assume: the `cvs` table holds five columns and none of
            # them is text, so nothing here knows what the document says.
            "contents_available": False,
            "note": (
                "SmartHR stores the CV file and its name, not its text or "
                "parsed fields. Upload a CV from the My CV page to have it "
                "analysed."
                if not cvs else
                "SmartHR stores the CV file, not its text. The skills to use "
                "for matching are the ones on the applicant's profile."
            ),
        }
    except Exception:
        logger.exception("get_my_cv failed | candidate_id=%s", candidate.id)
        return _error("database_error", "Your CV status could not be read just now.")
    finally:
        db.close()


# ===========================================================================
# Opportunities
# ===========================================================================

@smarthr_mcp.tool(
    name="search_opportunities",
    title="Search opportunities",
    description=(
        "Search the opportunities SmartHR currently has on offer: jobs, "
        "internships, training opportunities and free courses. Returns real "
        "open listings with their title, department, location, description, "
        "requirements and deadline. Use it for any question about what is "
        "available, in any language. If it returns nothing, there is nothing "
        "on offer that matches - say so. Never describe an opportunity that "
        "did not come back from this tool."
    ),
)
def search_opportunities(
    search: Annotated[
        str | None,
        Field(default=None, description=(
            "Words to look for in the title, description or requirements, "
            "e.g. 'data analyst' or 'python'. Omit to list everything."
        )),
    ] = None,
    opportunity_type: Annotated[
        str | None,
        Field(default=None, description=(
            "Restrict to one kind: 'job', 'internship', 'training' or "
            "'free_course'. Omit for all four."
        )),
    ] = None,
    location: Annotated[
        str | None,
        Field(default=None, description="Restrict to listings in this location."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=25, description="How many to return. Default 10."),
    ] = None,
) -> dict[str, Any]:
    """Real open opportunities, as an applicant may see them."""
    try:
        db, principal = _catalogue_session("search_opportunities")
    except _Refused as refusal:
        return refusal.payload

    try:
        if opportunity_type and opportunity_type not in OPPORTUNITY_TYPES:
            return _error(
                "invalid_type",
                f"'{opportunity_type}' is not an opportunity type. "
                f"Use one of: {', '.join(OPPORTUNITY_TYPES)}.",
            )

        results = list_opportunities(
            db,
            OpportunityQuery(
                search=search,
                opportunity_type=opportunity_type,
                location=location,
                limit=limit or 10,
            ),
        )

        logger.info(
            "search_opportunities ok | user_id=%s type=%s results=%s",
            principal.user_id, opportunity_type or "all", len(results),
        )

        return {
            "ok": True,
            "found": bool(results),
            "count": len(results),
            "opportunities": results,
            "guidance": (
                "Describe only the opportunities listed above, using their own "
                "wording for requirements. If none fit what was asked for, say "
                "SmartHR has nothing matching right now."
                if results else
                "SmartHR has no open opportunity matching that search. Tell the "
                "applicant so plainly. Do not invent an opportunity, and do not "
                "suggest one from general knowledge."
            ),
        }
    except Exception:
        logger.exception("search_opportunities failed | user_id=%s", principal.user_id)
        return _error("database_error", "Opportunities could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_opportunity",
    title="Opportunity details",
    description=(
        "Return the full public details of one opportunity by its id, as given "
        "by search_opportunities - for example 'job-3'. Use it to read the "
        "requirements of a specific opportunity before discussing whether it "
        "suits the applicant, or before applying to it."
    ),
)
def get_opportunity(
    opportunity_id: Annotated[
        str,
        Field(description=(
            "The opportunity_id from search_opportunities, such as 'job-3' or "
            "'training-2'."
        )),
    ],
) -> dict[str, Any]:
    """One opportunity's public detail."""
    try:
        db, principal = _catalogue_session("get_opportunity")
    except _Refused as refusal:
        return refusal.payload

    try:
        reference = parse_opportunity_id(opportunity_id)

        if reference is None:
            return _error(
                "invalid_id",
                f"'{opportunity_id}' is not an opportunity id. Use the "
                f"opportunity_id from search_opportunities, e.g. 'job-3'.",
            )

        opportunity = get_opportunity_row(db, reference[0], reference[1])

        if opportunity is None:
            return _error(
                "not_found",
                "There is no open opportunity with that id. It may have closed.",
            )

        logger.info(
            "get_opportunity ok | user_id=%s opportunity=%s",
            principal.user_id, opportunity_id,
        )

        return {"ok": True, "opportunity": opportunity}
    except Exception:
        logger.exception("get_opportunity failed | user_id=%s", principal.user_id)
        return _error("database_error", "That opportunity could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="match_my_profile_to_opportunity",
    title="Match my profile to an opportunity",
    description=(
        "Compare the skills on the signed-in applicant's profile with the "
        "requirements one opportunity lists, and return a match score, the "
        "matching skills and the skill gaps. Give an opportunity_id to match "
        "one opportunity, or omit it to rank the best current opportunities "
        "for this applicant. The score is a skill-overlap suggestion labelled "
        "'AI Match / Recommendation' - it is NOT a hiring decision, not a "
        "measure of the person, and must never be presented as one. Explain "
        "which skills matched and which are missing; never add a skill the "
        "applicant did not list or a requirement the opportunity did not state."
    ),
)
def match_my_profile_to_opportunity(
    opportunity_id: Annotated[
        str | None,
        Field(default=None, description=(
            "The opportunity to match against, e.g. 'job-3'. Omit to rank the "
            "best current opportunities instead."
        )),
    ] = None,
    limit: Annotated[
        int | None,
        Field(default=None, ge=1, le=10,
              description="When ranking, how many to return. Default 5."),
    ] = None,
) -> dict[str, Any]:
    """Skill overlap between this applicant's profile and an opportunity."""
    try:
        db, candidate = _candidate_session("match_my_profile_to_opportunity")
    except _Refused as refusal:
        return refusal.payload

    try:
        skills = applicant_service.applicant_skills(candidate)

        if not skills:
            # Honest refusal rather than a 0% score, which would read as
            # "unsuitable" when it actually means "we know nothing yet".
            return {
                "ok": True,
                "scored": False,
                "skills_available": False,
                "matches": [],
                "guidance": (
                    "This applicant has no skills on their profile, so there is "
                    "nothing to match against and no score can be given. Ask "
                    "them to add their skills on the My Profile page. Do not "
                    "guess their skills from anything else."
                ),
            }

        if opportunity_id:
            reference = parse_opportunity_id(opportunity_id)

            if reference is None:
                return _error("invalid_id", f"'{opportunity_id}' is not an opportunity id.")

            opportunity = get_opportunity_row(db, reference[0], reference[1])

            if opportunity is None:
                return _error("not_found", "There is no open opportunity with that id.")

            match = match_skills(skills, opportunity.get("skills") or [])

            logger.info(
                "match ok | candidate_id=%s opportunity=%s score=%s",
                candidate.id, opportunity_id, match["score"],
            )

            return {
                "ok": True,
                "scored": match["score_available"],
                "skills_available": True,
                "matches": [{**opportunity, "match": match}],
                "guidance": (
                    "Report the score as an AI match suggestion, name the "
                    "matching skills and the gaps using the exact wording "
                    "returned, and state that it is not a hiring decision."
                ),
            }

        ranked = rank_opportunities(
            skills,
            list_opportunities(db, OpportunityQuery(limit=200)),
            limit=limit or 5,
        )

        logger.info(
            "match ranked | candidate_id=%s skills=%s results=%s",
            candidate.id, len(skills), len(ranked),
        )

        return {
            "ok": True,
            "scored": True,
            "skills_available": True,
            "matches": ranked,
            "guidance": (
                "Recommend these in the order given and say why each one fits, "
                "naming the matching skills and the gaps. These are AI match "
                "suggestions, not hiring decisions."
                if ranked else
                "SmartHR has no open opportunities to rank right now."
            ),
        }
    except Exception:
        logger.exception("match failed | candidate_id=%s", candidate.id)
        return _error("database_error", "The match could not be computed just now.")
    finally:
        db.close()


# ===========================================================================
# Applications
# ===========================================================================

@smarthr_mcp.tool(
    name="get_my_applications",
    title="My applications",
    description=(
        "Return every application the signed-in applicant has submitted, with "
        "the opportunity, the date and the current stage (Applied, Under "
        "Review, Shortlisted, Interview, Assessment, Offer, Hired, Not "
        "selected), plus any interview that has been scheduled. Use it for any "
        "question about what they have applied to or how an application is "
        "going. It always answers for the signed-in applicant and cannot "
        "return anyone else's applications."
    ),
)
def get_my_applications() -> dict[str, Any]:
    """The signed-in applicant's own applications. Takes no identifier."""
    try:
        db, candidate = _candidate_session("get_my_applications")
    except _Refused as refusal:
        return refusal.payload

    try:
        applications = application_service.my_applications(candidate, db)
        summary = application_service.application_summary(candidate, db)

        logger.info(
            "get_my_applications ok | candidate_id=%s total=%s",
            candidate.id, summary["total"],
        )

        return {
            "ok": True,
            "applications": applications,
            "summary": summary,
            "guidance": (
                "Report the stages exactly as given. SmartHR does not record "
                "why an application is at a stage, so do not speculate about "
                "the reason or predict the outcome."
            ),
        }
    except Exception:
        logger.exception("get_my_applications failed | candidate_id=%s", candidate.id)
        return _error("database_error", "Your applications could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="get_my_application_status",
    title="Status of one of my applications",
    description=(
        "Return the current stage of one application belonging to the "
        "signed-in applicant, by its application id. Use it to answer a "
        "question about one specific application. An id that is not theirs is "
        "reported as not found."
    ),
)
def get_my_application_status(
    application_id: Annotated[
        int,
        Field(description="The application id, as given by get_my_applications."),
    ],
) -> dict[str, Any]:
    """One of this applicant's own applications."""
    try:
        db, candidate = _candidate_session("get_my_application_status")
    except _Refused as refusal:
        return refusal.payload

    try:
        application = application_service.application_for_candidate(
            candidate, application_id, db
        )

        if application is None:
            # Ownership is in the query, so "not yours" and "does not exist"
            # are the same answer. That is deliberate.
            return _error(
                "not_found",
                "You have no application with that id.",
            )

        logger.info(
            "get_my_application_status ok | candidate_id=%s application_id=%s",
            candidate.id, application_id,
        )

        return {"ok": True, "application": application}
    except Exception:
        logger.exception(
            "get_my_application_status failed | candidate_id=%s", candidate.id
        )
        return _error("database_error", "That application could not be read just now.")
    finally:
        db.close()


@smarthr_mcp.tool(
    name="submit_application",
    title="Apply to an opportunity",
    description=(
        "Submit an application to one opportunity on behalf of the signed-in "
        "applicant. THIS WRITES TO THE DATABASE AND IS VISIBLE TO RECRUITERS. "
        "Call it ONLY when the applicant has asked, in words, to apply to a "
        "specific opportunity - for example 'apply me to the Data Analyst "
        "internship'. Never call it because an opportunity looks like a good "
        "fit, never to be helpful, and never while merely searching or "
        "comparing. If you are not certain which opportunity they mean, ask "
        "them instead of guessing. The applicant must have a CV on file. It "
        "applies only for the signed-in applicant and cannot apply for anyone "
        "else."
    ),
)
def submit_application(
    opportunity_id: Annotated[
        str,
        Field(description=(
            "The opportunity to apply to, e.g. 'job-3'. Only jobs and "
            "internships accept applications."
        )),
    ],
    confirmed_by_applicant: Annotated[
        bool,
        Field(description=(
            "Set true only if the applicant explicitly asked to apply to this "
            "opportunity in their message. If they only asked to find, compare "
            "or explain opportunities, this must be false."
        )),
    ] = False,
) -> dict[str, Any]:
    """Create one application for the signed-in applicant."""
    try:
        db, candidate = _candidate_session("submit_application")
    except _Refused as refusal:
        return refusal.payload

    try:
        if not confirmed_by_applicant:
            # The model said so itself. Refused rather than assumed - and the
            # agent would not have offered this tool at all without apply
            # intent in the message, so this is the second of two gates.
            logger.info(
                "submit_application refused, not confirmed | candidate_id=%s",
                candidate.id,
            )
            return _error(
                "not_confirmed",
                "An application is only submitted when the applicant explicitly "
                "asks to apply. Ask them to confirm which opportunity they want "
                "to apply to.",
            )

        reference = parse_opportunity_id(opportunity_id)

        if reference is None:
            return _error("invalid_id", f"'{opportunity_id}' is not an opportunity id.")

        source, row_id = reference

        if source != "job":
            return _error(
                "not_applicable",
                "Training opportunities and free courses are not applied to "
                "through SmartHR - enrol with the provider instead.",
            )

        try:
            result = application_service.submit(candidate, row_id, db)
        except ApplicationError as exc:
            logger.info(
                "submit_application refused | candidate_id=%s code=%s",
                candidate.id, exc.code,
            )
            return _error(exc.code, str(exc))

        # Audited exactly like the REST route, so an application filed through
        # the agent is indistinguishable in the trail from one filed by hand.
        from app.audit import ACTION_CREATE, ENTITY_APPLICATION, record_audit
        from app.models import User

        account = db.query(User).filter(User.id == candidate.user_id).first()
        record_audit(
            db, account, ACTION_CREATE, ENTITY_APPLICATION, result.application["id"]
        )

        logger.info(
            "submit_application ok | candidate_id=%s job_id=%s application_id=%s",
            candidate.id, row_id, result.application["id"],
        )

        return {
            "ok": True,
            "submitted": True,
            "application": result.application,
            "warnings": result.warnings,
            "guidance": (
                "Confirm to the applicant that the application was submitted, "
                "name the opportunity, and tell them they can follow it on My "
                "Applications. Do not predict the outcome."
            ),
        }
    except Exception:
        db.rollback()
        logger.exception("submit_application failed | candidate_id=%s", candidate.id)
        return _error("database_error", "Your application could not be submitted just now.")
    finally:
        db.close()
