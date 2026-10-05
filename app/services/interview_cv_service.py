"""AI Interview (Phase 5) - the candidate's CV, as the interviewer may see it.

    room -> ai_interview_sessions -> interview -> application -> candidate
         -> the candidate's LATEST cv (SmartHR's existing rule)
         -> analyse_cv_bytes()  (the one CV pipeline: extraction + ParsedCv)
         -> cv_context()        (a whitelisted projection of ParsedCv)

**Nothing new about CVs is invented here.** `cvs` stores only file metadata
(id, candidate_id, file_name, file_path, uploaded_at) - no text and no parsed
fields - so the structured CV is re-derived from the stored file by the same
`analyse_cv_bytes()` that `POST /cvs/upload`, `POST /applicant/cv`, the
`parse_cv` MCP tool and HR screening use. There is no second parser.

**Which CV.** A candidate may have several `cvs` rows (applications carry no
cv_id). Every existing reader - `applicant_service.latest_cv`,
`screening_service.latest_cv`, the `parse_cv` tool - takes the most recent:
`ORDER BY uploaded_at DESC, id DESC`. The interview uses exactly that rule, by
calling `screening_service.latest_cv` (the id-taking twin of
`applicant_service.latest_cv`), so the CV the interviewer knows is the
one the applicant's own CV page shows as current and the one HR screens.

**What reaches the interviewer** (`cv_context`), built field by field from
ParsedCv - never the raw text, never the row:

    summary, skills, experience[job_title, company, start_date, end_date,
    description, technologies], education[degree, field_of_study,
    institution, start_date, end_date], certifications[name, issuer, date],
    languages[language, proficiency]

**Deliberately left out:** full_name, email, phone and home location (contact
PII the interview does not need; the interviewer does not address the
applicant by a name read from a document), each role's location, the file
name, the storage path, the cv id, upload time, and anything from the
candidate / application / interview rows. ParsedCv has no "projects" field,
so there is none here either - a project appears only where the CV put it
(usually a role's description).

**Cost and latency.** Parsing is a model call. It starts when the applicant
presses Start (`prewarm`, in a small thread pool, off the request) and the
agent's request waits for that same computation. Results are kept in memory,
keyed by the CV row AND the file's size/mtime, for `CACHE_TTL_S` - never
written to the database, never logged. A process restart forgets them.

**Phase 6 reuses the same parse.** Matching (`interview_matching_service`)
needs the candidate's CV skills, and asking the model to read the document a
second time would cost a second call and could disagree with the first. So
the cached result also keeps the ParsedCv itself (`CvResult.parsed`), with
its contact fields (name, email, phone, home location) cleared first. It lives
only in this process's memory, beside the context it was built from, and is
never sent to the worker - the agent endpoint returns `status` and `context`
only.

Logging is codes and counts only - never a CV value.
"""

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.cv_storage import CV_UPLOAD_DIR, PROJECT_ROOT
from app.models import CV
from app.services.screening_service import latest_cv
from app.services.cv_service import CvServiceError, analyse_cv_bytes

logger = logging.getLogger("smarthr.interview.cv")

#: How long a parsed CV is reused. Long enough for one interview and a retry.
CACHE_TTL_S = 30 * 60
CACHE_MAX = 64
#: How long the agent's request waits for a parse already running.
WAIT_S = 45

SUMMARY_MAX = 800
TEXT_MAX = 160
DESCRIPTION_MAX = 400
SKILLS_MAX = 30
EXPERIENCE_MAX = 6
EDUCATION_MAX = 4
CERTIFICATIONS_MAX = 8
LANGUAGES_MAX = 6
TECHNOLOGIES_MAX = 12

#: The whitelist, asserted by the tests. Adding a field is a decision.
CV_CONTEXT_FIELDS = {
    "summary": None,
    "skills": None,
    "experience": ("job_title", "company", "start_date", "end_date", "description", "technologies"),
    "education": ("degree", "field_of_study", "institution", "start_date", "end_date"),
    "certifications": ("name", "issuer", "date"),
    "languages": ("language", "proficiency"),
}

STATUS_AVAILABLE = "available"
STATUS_NONE = "none"                # the candidate has no CV on file
STATUS_UNAVAILABLE = "unavailable"  # a CV exists but could not be read / analysed


@dataclass(frozen=True)
class CvResult:
    status: str
    context: dict[str, Any] | None = None
    #: For logs and tests only - never sent to the worker.
    code: str | None = None
    #: The ParsedCv the context came from, contact fields cleared - for
    #: Phase 6 matching in this process only. Never serialised.
    parsed: Any = field(default=None, repr=False, compare=False)

#: ParsedCv fields cleared before a parse is kept in memory. Matching reads
#: skills; nothing in the interview needs who the document says it belongs to.
CONTACT_FIELDS = ("full_name", "email", "phone", "location")


def _clip(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _rows(items, fields: tuple[str, ...], limits: dict[str, int], cap: int) -> list[dict[str, Any]]:
    out = []
    for item in items[:cap]:
        row: dict[str, Any] = {}
        for name in fields:
            value = getattr(item, name, None)
            if name == "technologies":
                techs = [t for t in (_clip(v, TEXT_MAX) for v in (value or [])[:TECHNOLOGIES_MAX]) if t]
                if techs:
                    row[name] = techs
                continue
            clipped = _clip(value, limits.get(name, TEXT_MAX))
            if clipped:
                row[name] = clipped
        if row:
            out.append(row)
    return out


def cv_context(parsed) -> dict[str, Any]:
    """The whitelisted, trimmed view of a ParsedCv. Empty values are omitted
    rather than sent as null, so the model never reads an absent fact as one."""
    context: dict[str, Any] = {}
    summary = _clip(parsed.summary, SUMMARY_MAX)
    if summary:
        context["summary"] = summary
    skills = [s for s in (_clip(v, TEXT_MAX) for v in parsed.skills[:SKILLS_MAX]) if s]
    if skills:
        context["skills"] = skills
    sections = (
        ("experience", parsed.experience, {"description": DESCRIPTION_MAX}, EXPERIENCE_MAX),
        ("education", parsed.education, {}, EDUCATION_MAX),
        ("certifications", parsed.certifications, {}, CERTIFICATIONS_MAX),
        ("languages", parsed.languages, {}, LANGUAGES_MAX),
    )
    for key, items, limits, cap in sections:
        rows = _rows(items, CV_CONTEXT_FIELDS[key], limits, cap)
        if rows:
            context[key] = rows
    return context


# --- reading the stored file ---------------------------------------------------

def _stored_file(cv: CV):
    """The CV's file, only if it resolves INSIDE the CV upload directory."""
    path = (PROJECT_ROOT / cv.file_path).resolve()
    root = CV_UPLOAD_DIR.resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def _analyse(file_name: str, data: bytes) -> CvResult:
    try:
        analysis = analyse_cv_bytes(file_name, data, analyse=True)
    except CvServiceError as exc:
        return CvResult(STATUS_UNAVAILABLE, code=exc.code)
    except Exception:
        logger.exception("interview CV analysis failed unexpectedly")
        return CvResult(STATUS_UNAVAILABLE, code="analysis_failed")
    if not analysis.analysis_available:
        return CvResult(STATUS_UNAVAILABLE, code=analysis.analysis_error_code or "analysis_failed")
    context = cv_context(analysis.parsed.pruned())
    if not context:
        return CvResult(STATUS_UNAVAILABLE, code="nothing_extracted")
    kept = analysis.parsed.model_copy(update={name: None for name in CONTACT_FIELDS})
    return CvResult(STATUS_AVAILABLE, context=context, parsed=kept)


# --- the cache: one computation per CV version, shared by prewarm and agent ----

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="interview-cv")
_lock = threading.Lock()
_cache: dict[tuple, tuple[float, Future]] = {}


def _key(cv: CV, path) -> tuple:
    stat = path.stat()
    return (cv.id, stat.st_size, stat.st_mtime_ns)


def _submit(key: tuple, file_name: str, path) -> Future:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            started, future = hit
            failed = future.done() and future.result().status != STATUS_AVAILABLE
            if now - started < CACHE_TTL_S and not failed:
                return future
        for stale in [k for k, (t, _) in _cache.items() if now - t >= CACHE_TTL_S]:
            _cache.pop(stale, None)
        while len(_cache) >= CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        future = _executor.submit(lambda: _analyse(file_name, path.read_bytes()))
        _cache[key] = (now, future)
        return future


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _candidate_cv(db: Session, candidate_id: int) -> CV | None:
    return latest_cv(candidate_id, db)


def prewarm(db: Session, candidate_id: int) -> None:
    """Start parsing the candidate's current CV now, off the request thread,
    so it is usually ready by the time the agent asks. Never raises."""
    try:
        cv = _candidate_cv(db, candidate_id)
        path = _stored_file(cv) if cv else None
        if path is not None:
            _submit(_key(cv, path), cv.file_name, path)
    except Exception:
        logger.exception("interview CV prewarm failed")


def cv_for_candidate(db: Session, candidate_id: int, wait_s: float = WAIT_S) -> CvResult:
    """The CV Context of this candidate's current CV."""
    cv = _candidate_cv(db, candidate_id)
    if cv is None:
        return CvResult(STATUS_NONE, code="no_cv")
    path = _stored_file(cv)
    if path is None:
        return CvResult(STATUS_UNAVAILABLE, code="file_missing")
    future = _submit(_key(cv, path), cv.file_name, path)
    try:
        return future.result(timeout=wait_s)
    except FutureTimeout:
        return CvResult(STATUS_UNAVAILABLE, code="timeout")
