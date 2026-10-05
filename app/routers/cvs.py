"""Candidate CVs, including AI analysis of an uploaded file.

    POST /cvs/upload                    file in, structured candidate information out
    POST /cvs/{cv_id}/analyse           re-analyse a CV already on file
    POST /cvs/{cv_id}/apply-to-candidate  write reviewed contact details to the candidate
    GET  /cvs/                          the stored rows
    POST /cvs/                          register a CV that already exists somewhere

Everything here is Admin + HR only (`require_roles(1, 2)`): a CV is a
candidate's personal document, and recruitment is an HR-owned tier. Managers
and Employees are refused by the same dependency the rest of the API uses, so
the rule is enforced server-side rather than by hiding a button.

The analysis itself lives in `app/services/cv_service.py`, which the `parse_cv`
MCP tool also calls - this router owns HTTP and persistence, not parsing.

**What is persisted.** `cvs` has exactly five columns - id, candidate_id,
file_name, file_path, uploaded_at - so the upload is stored and the *analysis
is not*. There is no column for extracted text or parsed fields and the schema
was not changed to invent one. The one exception is contact detail: the
`candidates` table already has `phone` and `location`, so those two extracted
values have an existing home - written only through
`/apply-to-candidate`, after a recruiter has reviewed them. Nothing the model
produced is ever written to the database automatically.
"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit import ACTION_CREATE, ACTION_UPDATE, ENTITY_CANDIDATE, ENTITY_CV, record_audit
from app.cv_storage import display_filename, store_cv_file
from app.database import SessionLocal
from app.dependencies import require_roles
from app.models import CV, Candidate, User
from app.services.cv_service import (
    CvServiceError,
    analyse_cv_bytes,
    persistence_report,
)

logger = logging.getLogger("smarthr.cv")

router = APIRouter(
    prefix="/cvs",
    tags=["CVs"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CVCreate(BaseModel):
    candidate_id: int
    file_name: str
    file_path: str


class ApplyToCandidate(BaseModel):
    """The reviewed values a recruiter chose to keep.

    Sent back explicitly rather than re-read from the analysis, because the
    recruiter may have corrected them. Omitting a field leaves the existing
    candidate value alone; sending an empty string clears it.
    """

    phone: str | None = None
    location: str | None = None


def cv_to_dict(cv: CV) -> dict:
    return {
        "id": cv.id,
        "candidate_id": cv.candidate_id,
        "file_name": cv.file_name,
        "file_path": cv.file_path,
        "uploaded_at": cv.uploaded_at.isoformat() if cv.uploaded_at else None,
    }


def _service_http_error(exc: CvServiceError) -> HTTPException:
    """Map a pipeline failure onto the right status code."""
    if exc.code == "file_too_large":
        return HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )

    return HTTPException(
        status_code=(
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if exc.is_client_error
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail=str(exc),
    )


def _require_candidate(candidate_id: int, db: Session) -> Candidate:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} does not exist.",
        )

    return candidate


def _analysis_envelope(analysis, cv_payload: dict, candidate: Candidate) -> dict:
    """The response shape both /upload and /analyse return."""
    return {
        "cv": cv_payload,
        "candidate": {
            "id": candidate.id,
            "full_name": f"{candidate.first_name} {candidate.last_name}",
            "email": candidate.email,
            "phone": candidate.phone,
            "location": candidate.location,
        },
        "extraction": analysis.extraction,
        "analysis": analysis.analysis_dict(),
        "analysis_available": analysis.analysis_available,
        "analysis_error": analysis.analysis_error,
        "analysis_error_code": analysis.analysis_error_code,
        "llm_configured": analysis.llm_configured,
        "provider": analysis.provider,
        "model": analysis.model,
        # Literal matches found in the document text, with no model involved.
        # Present so the upload is still useful before a key is configured;
        # anything here is verifiably a substring of the CV.
        "contact_found_in_text": analysis.contact_found_in_text,
        "persistence": persistence_report(),
        # AI output is a reading of the document, not a verified fact about a
        # person. The UI says so; the API says so too.
        "review_required": True,
        "analysed_at": datetime.utcnow().isoformat(),
    }


@router.get("/")
def get_cvs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    return [cv_to_dict(cv) for cv in db.query(CV).order_by(CV.id.desc()).all()]


@router.post("/")
def create_cv(
    cv_data: CVCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    _require_candidate(cv_data.candidate_id, db)

    cv = CV(
        candidate_id=cv_data.candidate_id,
        file_name=cv_data.file_name,
        file_path=cv_data.file_path,
    )

    db.add(cv)
    db.commit()
    db.refresh(cv)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_CV, cv.id)

    return cv_to_dict(cv)


@router.post("/upload")
async def upload_and_analyse_cv(
    file: UploadFile = File(...),
    # cvs.candidate_id is NOT NULL with a foreign key to candidates, so a CV
    # always belongs to a candidate that already exists. This endpoint does not
    # create candidates - that stays with the Candidates workflow, which owns
    # the duplicate rules.
    candidate_id: int = Form(...),
    analyse: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2)),
):
    """Upload a PDF or DOCX CV, store it, and return structured analysis.

        file -> extract text -> LLM (JSON schema) -> Pydantic -> result

    The file itself is never handed to the model; only the extracted text is.
    """
    candidate = _require_candidate(candidate_id, db)
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

    # ---- persistence -----------------------------------------------------
    # Written only after the file has proved to be a readable CV, so the table
    # never accumulates rows pointing at unusable uploads.
    try:
        stored_path = store_cv_file(data, analysis.file_type)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The CV could not be saved to disk.",
        ) from exc

    try:
        cv = CV(
            candidate_id=candidate_id,
            file_name=original_name,
            file_path=stored_path,
        )
        db.add(cv)
        db.commit()
        db.refresh(cv)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("CV row could not be written | candidate_id=%s", candidate_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The CV record could not be saved.",
        )

    cv_payload = cv_to_dict(cv)
    record_audit(db, current_user, ACTION_CREATE, ENTITY_CV, cv_payload["id"])

    # record_audit's commit expires the session, so the candidate is reloaded.
    candidate = _require_candidate(candidate_id, db)

    return _analysis_envelope(analysis, cv_payload, candidate)


@router.post("/{cv_id}/analyse")
def analyse_stored_cv(
    cv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2)),
):
    """Re-run the analysis for a CV already on file.

    The analysis is not persisted anywhere, so this is how a recruiter sees it
    again after closing the panel - and how it is produced once a model has
    been configured for a CV uploaded before that.
    """
    cv = db.query(CV).filter(CV.id == cv_id).first()

    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CV {cv_id} does not exist.",
        )

    path = Path(cv.file_path)

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "The stored file for this CV is no longer on disk, so it "
                "cannot be re-analysed. Upload it again."
            ),
        )

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The stored CV could not be read.",
        ) from exc

    try:
        analysis = analyse_cv_bytes(cv.file_name, data, analyse=True)
    except CvServiceError as exc:
        raise _service_http_error(exc) from exc

    candidate = _require_candidate(cv.candidate_id, db)

    return _analysis_envelope(analysis, cv_to_dict(cv), candidate)


@router.post("/{cv_id}/apply-to-candidate")
def apply_analysis_to_candidate(
    cv_id: int,
    payload: ApplyToCandidate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2)),
):
    """Write recruiter-reviewed contact details onto the candidate row.

    This is the only path by which anything derived from a CV reaches the
    candidates table, and it is driven by values the recruiter submitted after
    reading them - not by the model's output directly. `phone` and `location`
    are the only two extracted fields the existing schema has a column for;
    everything else the parser returns has nowhere to go and is not invented a
    home.
    """
    cv = db.query(CV).filter(CV.id == cv_id).first()

    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CV {cv_id} does not exist.",
        )

    candidate = _require_candidate(cv.candidate_id, db)

    # Column limits from the live schema: phone varchar(30), location
    # varchar(150). Checked here so an over-long value is a 422 rather than a
    # DataError from the driver.
    limits = {"phone": 30, "location": 150}
    applied: dict[str, str | None] = {}

    for column, limit in limits.items():
        value = getattr(payload, column)

        if value is None:
            continue  # not submitted: leave the existing value alone

        cleaned = value.strip() or None

        if cleaned is not None and len(cleaned) > limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{column} must be {limit} characters or fewer.",
            )

        setattr(candidate, column, cleaned)
        applied[column] = cleaned

    if not applied:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nothing to apply - send a phone or location value.",
        )

    try:
        db.commit()
        db.refresh(candidate)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Candidate update failed | candidate_id=%s", candidate.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The candidate record could not be updated.",
        )

    # Field names only - never the values, which are personal contact details.
    logger.info(
        "CV analysis applied to candidate | cv_id=%s candidate_id=%s fields=%s",
        cv_id,
        candidate.id,
        sorted(applied),
    )

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_CANDIDATE, candidate.id)

    return {
        "candidate": {
            "id": candidate.id,
            "full_name": f"{candidate.first_name} {candidate.last_name}",
            "email": candidate.email,
            "phone": candidate.phone,
            "location": candidate.location,
        },
        "applied_fields": sorted(applied),
        "persistence": persistence_report(applied=applied),
    }
