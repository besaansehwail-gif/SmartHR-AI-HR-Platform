"""The Applicant / Job Seeker surface.

    POST /applicant/register                 public - the only unauthenticated
                                             write in SmartHR
    GET  /applicant/dashboard                everything the landing page shows
    GET  /applicant/me                       my profile
    PUT  /applicant/me                       update my profile
    GET  /applicant/opportunities            browse
    GET  /applicant/opportunities/recommended  matched to my skills
    GET  /applicant/opportunities/{id}       one listing, e.g. "job-3"
    GET  /applicant/cv                       my CVs
    POST /applicant/cv                       upload / replace my CV
    GET  /applicant/applications             my applications
    POST /applicant/applications             apply
    GET  /applicant/applications/{id}        one of my applications

Every route except registration depends on `get_current_candidate`, which
resolves the `candidates` row from the verified JWT. **No route on this router
accepts a candidate id, a user id or a role**, so an applicant cannot widen
their scope by editing a request - there is no field to edit. That is the same
rule the `/me` routes on the employee side follow.

Registration is the one deliberate exception to "every route requires
authentication": somebody who does not have an account cannot present a token
for it. It creates an account with role 5 and nothing else, and it refuses a
duplicate address with the same message whether or not that address is known,
so it cannot be used to find out who has an account here.

`/applicant/*` deliberately does not reuse `/candidates/*`. Those are HR's
endpoints over the same table, and they return the whole dossier - every
candidate, their pipeline stage, their interview notes. This router returns one
person's own row, so the two are separate surfaces over shared data rather than
one surface with a role switch inside it.
"""

import logging

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status,
)
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit import (
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_APPLICATION,
    ENTITY_CANDIDATE,
    ENTITY_CV,
    ENTITY_USER,
    record_audit,
)
from app.cv_storage import display_filename, store_cv_file
from app.dependencies import get_current_candidate, get_db, require_applicant
from app.models import CV, Candidate, User
from app.routers.cvs import _analysis_envelope, _service_http_error, cv_to_dict
from app.services import applicant_service, application_service
from app.services.applicant_service import (
    ApplicantError,
    ProfileUpdate,
    Registration,
)
from app.services.application_service import ApplicationError
from app.services.cv_service import CvServiceError, analyse_cv_bytes
from app.services.matching_service import match_skills, rank_opportunities
from app.services.opportunity_service import (
    OPPORTUNITY_TYPES,
    OpportunityQuery,
    counts_by_type,
    get_opportunity,
    list_opportunities,
    parse_opportunity_id,
)

logger = logging.getLogger("smarthr.applicant")

router = APIRouter(
    prefix="/applicant",
    tags=["Applicant"]
)




#: ApplicantError / ApplicationError codes -> HTTP status.
ERROR_STATUS = {
    "email_taken": status.HTTP_409_CONFLICT,
    "already_applied": status.HTTP_409_CONFLICT,
    "not_found": status.HTTP_404_NOT_FOUND,
    "role_missing": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: ApplicantError | ApplicationError) -> HTTPException:
    return HTTPException(
        status_code=ERROR_STATUS.get(
            exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        detail=str(exc),
    )


# ===========================================================================
# Registration
# ===========================================================================

class ApplicantRegistration(BaseModel):
    """Exactly the three fields the brief asks for.

    There is no `role_id` here, and there could not usefully be one: the role
    is set to Applicant by the service. A registration form that accepted a
    role would be a privilege-escalation endpoint.
    """

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: ApplicantRegistration, db: Session = Depends(get_db)):
    """Create an applicant account. The only public write endpoint."""
    try:
        account, candidate, linked = applicant_service.register_applicant(
            Registration(
                full_name=payload.full_name,
                email=payload.email,
                password=payload.password,
            ),
            db,
        )
    except ApplicantError as exc:
        raise _http_error(exc) from exc
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Applicant registration failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The account could not be created. Please try again.",
        )

    # Recorded like any other account creation, with the new account as actor -
    # there is no signed-in user to attribute it to.
    record_audit(db, account, ACTION_CREATE, ENTITY_USER, account.id)

    return {
        "message": "Your applicant account has been created. You can sign in now.",
        "user_id": account.id,
        "candidate_id": candidate.id,
        "role_id": account.role_id,
        # True when HR already had this person on file and the account was
        # attached to that row rather than a second one being created.
        "linked_to_existing_candidate": linked,
    }


# ===========================================================================
# Profile
# ===========================================================================

class ApplicantProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=150)
    #: Comma-separated, in the applicant's own words.
    skills: str | None = Field(default=None, max_length=2000)


@router.get("/me")
def my_profile(
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    return applicant_service.profile_dict(candidate, db)


@router.put("/me")
def update_my_profile(
    payload: ApplicantProfileUpdate,
    candidate: Candidate = Depends(get_current_candidate),
    current_user: User = Depends(require_applicant),
    db: Session = Depends(get_db),
):
    try:
        profile = applicant_service.update_profile(
            candidate,
            ProfileUpdate(
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                location=payload.location,
                skills=payload.skills,
            ),
            db,
        )
    except ApplicantError as exc:
        raise _http_error(exc) from exc

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_CANDIDATE, candidate.id)

    return profile


# ===========================================================================
# Opportunities
#
# `/recommended` is declared before `/{opportunity_id}` so the literal path
# wins the route match - the same ordering rule as /interviews/interviewers
# and /employees/roster.
# ===========================================================================

@router.get("/opportunities")
def browse_opportunities(
    search: str | None = Query(default=None, max_length=200),
    opportunity_type: str | None = Query(default=None),
    location: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=50, ge=1, le=200),
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Browse everything on offer. Real rows only - nothing is seeded here."""
    if opportunity_type is not None and opportunity_type not in OPPORTUNITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown opportunity type '{opportunity_type}'. "
                f"Allowed: {', '.join(OPPORTUNITY_TYPES)}"
            ),
        )

    opportunities = list_opportunities(
        db,
        OpportunityQuery(
            search=search,
            opportunity_type=opportunity_type,
            location=location,
            limit=limit,
        ),
    )

    return {
        "opportunities": opportunities,
        "count": len(opportunities),
        "counts_by_type": counts_by_type(db),
    }


@router.get("/opportunities/recommended")
def recommended_opportunities(
    limit: int = Query(default=5, ge=1, le=20),
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Opportunities ranked against the skills on the applicant's profile.

    With no skills on the profile there is nothing to rank against, so this
    says so and returns the newest openings unranked rather than inventing a
    preference.
    """
    skills = applicant_service.applicant_skills(candidate)
    openings = list_opportunities(db, OpportunityQuery(limit=200))

    return {
        "skills_available": bool(skills),
        "skills_used": skills,
        "recommendations": rank_opportunities(skills, openings, limit=limit),
        "note": (
            None if skills else
            "Add your skills on My Profile to get matched suggestions. Until "
            "then these are simply the most recent opportunities."
        ),
    }


@router.get("/opportunities/{opportunity_id}")
def view_opportunity(
    opportunity_id: str,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """One opportunity, with this applicant's match against it."""
    reference = parse_opportunity_id(opportunity_id)

    if reference is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That opportunity does not exist.",
        )

    opportunity = get_opportunity(db, reference[0], reference[1])

    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That opportunity does not exist or is no longer open.",
        )

    already = None

    if opportunity["source"] == "job":
        existing = application_service.existing_open_application(
            candidate, opportunity["id"], db
        )
        already = application_service.stage_view(existing.status) if existing else None

    return {
        "opportunity": opportunity,
        "match": match_skills(
            applicant_service.applicant_skills(candidate),
            opportunity.get("skills") or [],
        ),
        "my_application": already,
        "has_cv": applicant_service.latest_cv(candidate, db) is not None,
    }


# ===========================================================================
# CV
#
# The same pipeline HR uses. `analyse_cv_bytes()` is called here exactly as
# `POST /cvs/upload` calls it - there is no second parser, no second prompt and
# no second idea of what a valid result looks like.
#
# The difference is ownership: HR names a candidate_id, and this takes the
# candidate from the JWT. An applicant cannot upload a CV onto somebody else's
# record.
# ===========================================================================

@router.get("/cv")
def my_cvs(
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    cvs = applicant_service.my_cvs(candidate, db)

    return {
        "cvs": cvs,
        "current": cvs[0] if cvs else None,
        "has_cv": bool(cvs),
        "note": (
            "Uploading again adds a newer CV and it becomes the one recruiters "
            "read. Earlier versions stay on file."
        ),
    }


@router.post("/cv")
async def upload_my_cv(
    file: UploadFile = File(...),
    analyse: bool = Form(True),
    candidate: Candidate = Depends(get_current_candidate),
    current_user: User = Depends(require_applicant),
    db: Session = Depends(get_db),
):
    """Upload or replace my CV, and get the AI analysis of it.

    Note there is no `candidate_id` parameter. HR's equivalent has one because
    a recruiter uploads on somebody's behalf; here the owner is the caller, so
    accepting one would only create a way to get it wrong.
    """
    original_name = display_filename(file.filename)

    try:
        data = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The upload could not be read.",
        ) from exc
    finally:
        await file.close()

    try:
        analysis = analyse_cv_bytes(original_name, data, analyse=analyse)
    except CvServiceError as exc:
        raise _service_http_error(exc) from exc

    try:
        stored_path = store_cv_file(data, analysis.file_type)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your CV could not be saved.",
        ) from exc

    try:
        cv = CV(
            candidate_id=candidate.id,
            file_name=original_name,
            file_path=stored_path,
        )
        db.add(cv)
        db.commit()
        db.refresh(cv)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Applicant CV row failed | candidate_id=%s", candidate.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your CV could not be saved.",
        )

    cv_payload = cv_to_dict(cv)
    record_audit(db, current_user, ACTION_CREATE, ENTITY_CV, cv_payload["id"])

    # record_audit's commit expires the session; reload before reading.
    candidate = db.query(Candidate).filter(Candidate.id == cv.candidate_id).first()

    envelope = _analysis_envelope(analysis, cv_payload, candidate)

    # Skills the CV mentions are offered as a *suggestion*, never written.
    # `candidates.skills` changes only when the applicant saves their profile,
    # which is what keeps matching free of model-invented skills.
    suggested = list(analysis.parsed.skills) if analysis.parsed else []

    envelope["suggested_skills"] = {
        "skills": suggested,
        "applied": False,
        "note": (
            "These skills were read from your CV by AI. They have not been "
            "saved. Review them and add the ones you want on My Profile."
        ),
    }

    return envelope


# ===========================================================================
# Applications
# ===========================================================================

class ApplicationSubmission(BaseModel):
    """`job_id` and nothing else.

    No candidate_id: the applicant is the caller. No status: a new application
    starts at 'applied' and only HR can move it, exactly as
    `MyLeaveRequestCreate` forbids self-approval on the employee side.
    """

    job_id: int
    #: The applicant must mean it. The Apply button sets this; the Career Agent
    #: sets it only when the applicant asked in words to apply.
    confirm: bool = True


@router.get("/applications")
def my_applications(
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    return {
        "applications": application_service.my_applications(candidate, db),
        "summary": application_service.application_summary(candidate, db),
    }


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def apply(
    payload: ApplicationSubmission,
    candidate: Candidate = Depends(get_current_candidate),
    current_user: User = Depends(require_applicant),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Confirm that you want to apply before submitting.",
        )

    try:
        result = application_service.submit(candidate, payload.job_id, db)
    except ApplicationError as exc:
        raise _http_error(exc) from exc
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Application failed | candidate_id=%s job_id=%s",
            candidate.id, payload.job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your application could not be submitted. Please try again.",
        )

    record_audit(
        db, current_user, ACTION_CREATE, ENTITY_APPLICATION,
        result.application["id"],
    )

    return {
        "message": "Your application has been submitted.",
        "application": result.application,
        "cv_id": result.cv_id,
        "warnings": result.warnings,
    }


@router.get("/applications/{application_id}")
def my_application(
    application_id: int,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    application = application_service.application_for_candidate(
        candidate, application_id, db
    )

    if application is None:
        # Deliberately the same response as a non-existent id: an applicant
        # must not be able to discover that somebody else's application exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    return application


# ===========================================================================
# Dashboard
# ===========================================================================

@router.get("/dashboard")
def applicant_dashboard(
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """One read for the landing page. Every figure is counted from real rows."""
    profile = applicant_service.profile_dict(candidate, db)
    skills = applicant_service.applicant_skills(candidate)
    openings = list_opportunities(db, OpportunityQuery(limit=200))

    applications = application_service.my_applications(candidate, db)

    return {
        "profile": profile,
        "cv": profile["cv"],
        "recommended": {
            "skills_available": bool(skills),
            "items": rank_opportunities(skills, openings, limit=3),
        },
        "applications": {
            "recent": applications[:5],
            "summary": application_service.application_summary(candidate, db),
        },
        "opportunity_counts": counts_by_type(db),
    }
