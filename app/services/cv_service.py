"""The CV analysis pipeline, in one place.

    bytes -> validate -> extract text -> LLM -> validate -> ParsedCv

Every caller that analyses a CV goes through `analyse_cv_bytes()`:

* `POST /cvs/upload`            (app/routers/cvs.py)   - a new upload
* the `parse_cv` MCP tool       (app/mcp/tools/cv.py)  - a CV already on file

That is the point of this module. The MCP tool must not be a second
implementation of CV parsing with its own prompt and its own idea of what a
valid result looks like; it is a different *entry point* to this function. The
same rule the leave feature follows, where `app/services/leave_service.py` is
shared by `GET /leave-requests/me` and `get_my_leave`.

This module deliberately knows nothing about HTTP, FastAPI, MCP or SQLAlchemy.
It takes bytes and a filename and returns a result object; deciding what
status code that becomes, or which candidate it belongs to, is the caller's
job.

**Privacy.** Nothing here logs CV text, names, emails, phone numbers or any
extracted value. The log lines carry counts and error codes only, because a
CV is personal data and a log file is the easiest place to leak it from.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.ai.config import llm_settings
from app.ai.cv_extraction import (
    MAX_FILE_BYTES,
    SUPPORTED_EXTENSIONS,
    CvExtractionError,
    extract_cv_text,
)
from app.ai.cv_parser import (
    CvParseError,
    ParsedCv,
    contact_details_from_text,
    parse_cv_text,
)

logger = logging.getLogger("smarthr.cv")

#: Extraction/validation failures that are the uploader's problem rather than
#: the server's. Listed so the mapping is a decision, not a default.
CLIENT_ERROR_CODES = frozenset(
    {
        "unsupported_type",
        "empty_file",
        "file_too_large",
        "corrupt_file",
        "encrypted_file",
        "no_text_layer",
    }
)

#: Analysis failures that mean "the model side is not usable right now". The
#: upload itself still succeeded in these cases.
ANALYSIS_ERROR_CODES = frozenset(
    {
        "llm_not_configured",
        "llm_error",
        "malformed_response",
        "invalid_structure",
        "empty_text",
        "analysis_failed",
        "not_requested",
    }
)


class CvServiceError(Exception):
    """The document could not be turned into text at all.

    Carries the code from `cv_extraction`, so the caller can decide between a
    422 (the file is wrong) and a 503 (we are wrong).
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code

    @property
    def is_client_error(self) -> bool:
        return self.code in CLIENT_ERROR_CODES


@dataclass
class CvAnalysis:
    """Everything the pipeline produced for one document."""

    #: Normalised plain text. Held so the caller can store the file and search
    #: the text; it is never logged and never returned to the browser in full.
    text: str
    file_type: str
    extraction: dict[str, Any]

    parsed: ParsedCv | None = None
    analysis_error: str | None = None
    analysis_error_code: str | None = None
    contact_found_in_text: dict[str, str | None] = field(default_factory=dict)

    llm_configured: bool = False
    provider: str = ""
    model: str | None = None

    @property
    def analysis_available(self) -> bool:
        return self.parsed is not None

    def analysis_dict(self) -> dict[str, Any] | None:
        return self.parsed.to_dict() if self.parsed else None


def validate_upload(filename: str, data: bytes) -> None:
    """Reject a file before anything tries to read it.

    Type is checked here by extension only as a fast rejection; the real check
    is `cv_extraction.detect_file_type`, which reads the file's signature, so a
    renamed executable is refused even though its name looks acceptable.
    """
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise CvServiceError(
            f"'{filename}' is not a supported CV. Upload a PDF or a DOCX file.",
            code="unsupported_type",
        )

    if not data:
        raise CvServiceError("The uploaded file is empty.", code="empty_file")

    if len(data) > MAX_FILE_BYTES:
        raise CvServiceError(
            f"The file is larger than the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
            code="file_too_large",
        )


def analyse_cv_bytes(
    filename: str,
    data: bytes,
    *,
    analyse: bool = True,
) -> CvAnalysis:
    """Validate, extract and (optionally) analyse one CV document.

    Raises `CvServiceError` when the document cannot be read at all - that is
    the only failure that stops the pipeline, because without text there is
    nothing to analyse and nothing worth storing.

    An *analysis* failure is not raised. The extraction still succeeded, so the
    result comes back with `parsed=None` and an `analysis_error_code`, and the
    caller can still store the file and show the recruiter what was found. A
    missing API key must not lose an upload.
    """
    validate_upload(filename, data)

    try:
        extracted = extract_cv_text(filename, data)
    except CvExtractionError as exc:
        logger.info("CV extraction failed | code=%s bytes=%s", exc.code, len(data))
        raise CvServiceError(str(exc), code=exc.code) from exc

    settings = llm_settings()

    result = CvAnalysis(
        text=extracted.text,
        file_type=extracted.file_type,
        extraction={
            "file_type": extracted.file_type,
            "unit_count": extracted.unit_count,
            "character_count": extracted.character_count,
            "word_count": extracted.word_count,
            "truncated": extracted.truncated,
        },
        contact_found_in_text=contact_details_from_text(extracted.text),
        llm_configured=settings.configured,
        provider=settings.provider,
        model=settings.model or None,
    )

    logger.info(
        "CV extracted | type=%s chars=%s words=%s truncated=%s",
        extracted.file_type,
        extracted.character_count,
        extracted.word_count,
        extracted.truncated,
    )

    if not analyse:
        result.analysis_error_code = "not_requested"
        return result

    try:
        result.parsed = parse_cv_text(extracted.text)
        logger.info(
            "CV parsed | provider=%s fields_found=%s skills=%s roles=%s",
            settings.provider,
            result.parsed.field_count,
            len(result.parsed.skills),
            len(result.parsed.experience),
        )
    except CvParseError as exc:
        # Expected, classified failures - missing key, bad model output.
        logger.info("CV analysis unavailable | code=%s", exc.code)
        result.analysis_error = str(exc)
        result.analysis_error_code = exc.code
    except Exception:
        # Anything unforeseen must not lose an upload that already worked.
        # exc_info carries the traceback, not the CV.
        logger.exception("CV analysis failed unexpectedly")
        result.analysis_error = "The CV analysis could not be completed."
        result.analysis_error_code = "analysis_failed"

    return result


def persistence_report(applied: dict[str, Any] | None = None) -> dict[str, Any]:
    """What of this analysis the SmartHR schema can and cannot hold.

    Said out loud in every response rather than left to be discovered. The
    `cvs` table has five columns and none of them hold parsed fields; the
    `candidates` table has `phone` and `location`, which is why those two are
    the only extracted values that can be written anywhere - and then only when
    a recruiter confirms them (see `POST /cvs/{cv_id}/apply-to-candidate`).
    """
    return {
        "stored_in_postgres": {
            "cvs": ["candidate_id", "file_name", "file_path", "uploaded_at"],
            "candidates_on_confirmation": ["phone", "location"],
        },
        "not_stored": [
            "extracted_text",
            "full_name", "email", "summary",
            "skills", "education", "experience", "certifications", "languages",
        ],
        "applied_to_candidate": applied,
        "note": (
            "The cvs table holds only (id, candidate_id, file_name, file_path, "
            "uploaded_at), so the analysis itself is not persisted - it is "
            "returned to the caller and re-derived on request. The schema was "
            "not changed to store it. The only extracted values with an "
            "existing home are phone and location on the candidates row, and "
            "those are written only when a recruiter explicitly confirms them."
        ),
    }
