"""CV tools.

`parse_cv` re-reads a CV that is already stored against a candidate and returns
its structured contents. It exists so the assistant can answer "what does
Tareq's CV say about his experience?" without a recruiter opening the file.

**It is not a second CV parser.** The handler resolves a `cvs` row, reads the
stored file and calls `analyse_cv_bytes()` - the same
`app/services/cv_service.py` function `POST /cvs/upload` calls, with the same
extraction, the same prompt and the same Pydantic validation. If the parser
changes, both change together. A duplicate implementation here would be the
one thing guaranteed to drift.

**Why this tool takes an id and `get_my_leave` does not.** Leave is *self*
scope: the answer must be about the caller, so accepting an employee id would
be the whole vulnerability. A CV is *organisation* scope - recruitment data
that Admin and HR are entitled to read across all candidates, exactly as
`GET /cvs/` already lets them. So a candidate id here is a legitimate subject,
not an identity claim: it selects which CV to read, it never says who is
asking. Who is asking still comes from the principal, and `authorise()` still
re-reads the role from `users` before any file is opened - a Manager or
Employee reaching this tool is refused whatever id they pass.
"""

import logging
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from app.database import SessionLocal
from app.mcp.identity import NoPrincipalBound, current_principal
from app.mcp.permissions import ToolNotPermitted, authorise
from app.mcp.server import smarthr_mcp
from app.models import CV, Candidate
from app.services.cv_service import CvServiceError, analyse_cv_bytes

logger = logging.getLogger("smarthr.mcp.tools")


def _error(code: str, message: str) -> dict[str, Any]:
    """A refusal the model can act on, rather than a protocol error."""
    return {"ok": False, "error_code": code, "error": message}


@smarthr_mcp.tool(
    name="parse_cv",
    title="Read a candidate's CV",
    description=(
        "Return the structured contents of a CV already stored in SmartHR: "
        "skills, work experience, education, certifications and languages, "
        "extracted from the document itself. Give either a cv_id or a "
        "candidate_id; with a candidate_id the most recently uploaded CV is "
        "used. Only Admin and HR may use this. Every value comes from the "
        "document - if the CV does not state something, the field is null or "
        "the list is empty, and that means the CV did not say it rather than "
        "that it is not true. This reads CVs; it does not score, rank or "
        "recommend candidates."
    ),
)
def parse_cv(
    cv_id: Annotated[
        int | None,
        Field(default=None, description="The id of a specific stored CV."),
    ] = None,
    candidate_id: Annotated[
        int | None,
        Field(
            default=None,
            description=(
                "A candidate id; their most recently uploaded CV is read. "
                "Ignored when cv_id is given."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Structured contents of one stored CV, via the shared CV service."""
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
        logger.warning("parse_cv called with no principal bound")
        return _error("no_principal", str(exc))

    if cv_id is None and candidate_id is None:
        return _error(
            "missing_argument",
            "Give either a cv_id or a candidate_id to say which CV to read.",
        )

    logger.info(
        "MCP tool parse_cv invoked | user_id=%s cv_id=%s candidate_id=%s",
        principal.user_id,
        cv_id,
        candidate_id,
    )

    db = SessionLocal()
    try:
        # Authorisation first, from the database - not from the principal's
        # cached role and not from anything the browser or the model sent.
        try:
            authorise("parse_cv", principal.user_id, db)
        except ToolNotPermitted as exc:
            logger.info(
                "MCP tool parse_cv refused | user_id=%s code=%s",
                principal.user_id,
                exc.code,
            )
            return _error(exc.code, str(exc))

        if cv_id is not None:
            cv = db.query(CV).filter(CV.id == cv_id).first()
            if cv is None:
                return _error("not_found", f"There is no CV with id {cv_id}.")
        else:
            cv = (
                db.query(CV)
                .filter(CV.candidate_id == candidate_id)
                .order_by(CV.uploaded_at.desc(), CV.id.desc())
                .first()
            )
            if cv is None:
                return _error(
                    "not_found",
                    f"Candidate {candidate_id} has no CV on file in SmartHR.",
                )

        candidate = db.query(Candidate).filter(Candidate.id == cv.candidate_id).first()

        path = Path(cv.file_path)
        if not path.is_file():
            return _error(
                "file_missing",
                "The stored file for this CV is no longer on disk, so its "
                "contents cannot be read.",
            )

        try:
            data = path.read_bytes()
        except OSError:
            logger.exception("parse_cv could not read stored file | cv_id=%s", cv.id)
            return _error("file_unreadable", "The stored CV could not be read.")

        # The shared pipeline - identical to what POST /cvs/upload runs.
        try:
            analysis = analyse_cv_bytes(cv.file_name, data, analyse=True)
        except CvServiceError as exc:
            return _error(exc.code, str(exc))

        if not analysis.analysis_available:
            return _error(
                analysis.analysis_error_code or "analysis_failed",
                analysis.analysis_error
                or "The CV could not be analysed just now.",
            )

        # Counts only. The CV's contents are returned to the caller but never
        # written to the log.
        logger.info(
            "MCP tool parse_cv ok | user_id=%s cv_id=%s skills=%s roles=%s",
            principal.user_id,
            cv.id,
            len(analysis.parsed.skills),
            len(analysis.parsed.experience),
        )

        return {
            "ok": True,
            "cv": {
                "id": cv.id,
                "file_name": cv.file_name,
                "uploaded_at": cv.uploaded_at.isoformat() if cv.uploaded_at else None,
            },
            "candidate": (
                {
                    "id": candidate.id,
                    "full_name": f"{candidate.first_name} {candidate.last_name}",
                }
                if candidate
                else None
            ),
            "extraction": analysis.extraction,
            "analysis": analysis.analysis_dict(),
            "notes": (
                "Every field was copied from the CV document. A null field or "
                "an empty list means the CV did not state it. This extraction "
                "is for a recruiter to review; it is not a hiring decision and "
                "is not persisted - SmartHR stores the file, not the parsed "
                "contents."
            ),
        }

    except Exception:
        logger.exception("MCP tool parse_cv failed | user_id=%s", principal.user_id)
        return _error(
            "database_error", "The SmartHR database could not be read just now."
        )
    finally:
        db.close()
