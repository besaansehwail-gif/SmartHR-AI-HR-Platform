"""Turning CV text into structured candidate information.

    extracted text -> LLM (JSON schema tool) -> Pydantic validation -> ParsedCv

This module reuses the provider abstraction the assistant already uses
(`app/ai/provider.py`), so there is one place that holds an API key and one
place to add a provider.

The schema is passed to the model as a **tool**, which is how both Anthropic
and OpenAI express "reply in exactly this shape". That is far more reliable
than asking for JSON in prose and hoping.

**The model's output is never trusted.** Whatever comes back is run through the
Pydantic models below before anything else sees it. Validation is deliberately
*lenient about shape and strict about content*: a model that returns
`["Python"]` where a list of objects belongs is coerced rather than rejected,
because that is a formatting slip; but a response that cannot be read as a CV
at all raises `CvParseError` and nothing is persisted or displayed.

The prompt's single most important instruction is that every field must be
copied from the document or left empty. A CV parser that guesses a job title is
worse than one that returns null, because a recruiter cannot tell which fields
were read and which were invented.

**Extending this to CV -> job matching** (the next feature): `ParsedCv` is the
hand-off point. A matcher takes a `ParsedCv` plus a `Job` row and asks the same
provider for a score, matching skills and skill gaps. Nothing in this module
needs to change for that - add `app/ai/cv_matching.py` with its own schema and
call it with the `ParsedCv` this one returns. `experience[].technologies` and
`skills` exist partly to give that matcher something to match on.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ai.config import llm_settings
from app.ai.provider import LlmError, LlmNotConfigured, get_provider

# ---------------------------------------------------------------------------
# The shape the model is asked for
# ---------------------------------------------------------------------------

_NULLABLE_STRING = {"type": ["string", "null"]}

#: The exact shape the model must return. Everything is nullable or a list,
#: because "not stated in this CV" is the expected answer for many fields.
CV_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "full_name": _NULLABLE_STRING,
        "email": _NULLABLE_STRING,
        "phone": _NULLABLE_STRING,
        "location": _NULLABLE_STRING,
        "summary": {
            "type": ["string", "null"],
            "description": (
                "The candidate's own professional summary or profile section, "
                "copied from the CV. Do not compose one."
            ),
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Skills the CV itself names, as written. Do not add a skill "
                "because it is implied by a job title or by another skill."
            ),
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": _NULLABLE_STRING,
                    "field_of_study": _NULLABLE_STRING,
                    "institution": _NULLABLE_STRING,
                    "start_date": _NULLABLE_STRING,
                    "end_date": _NULLABLE_STRING,
                },
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_title": _NULLABLE_STRING,
                    "company": _NULLABLE_STRING,
                    "location": _NULLABLE_STRING,
                    "start_date": _NULLABLE_STRING,
                    "end_date": _NULLABLE_STRING,
                    "description": _NULLABLE_STRING,
                    "technologies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Tools or technologies this particular role names. "
                            "Leave empty unless the CV attaches them to this role."
                        ),
                    },
                },
            },
        },
        "certifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": _NULLABLE_STRING,
                    "issuer": _NULLABLE_STRING,
                    "date": _NULLABLE_STRING,
                },
            },
        },
        "languages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "language": _NULLABLE_STRING,
                    "proficiency": {
                        "type": ["string", "null"],
                        "description": (
                            "Only if the CV states a level. Null otherwise - "
                            "never estimate a proficiency."
                        ),
                    },
                },
            },
        },
    },
    "required": [
        "full_name", "email", "phone", "summary",
        "skills", "education", "experience", "certifications", "languages",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are an HR CV information extraction system. You are a parser, not a writer, and not a recruiter.

Absolute rules:

1. Every value you return must appear in the CV text you were given. Copy it;
   do not paraphrase job titles, employers, institutions, dates or skills.
2. If something is not in the document, return null for a field or [] for a
   list. An empty result is correct and expected. Never fill a gap with
   something plausible, typical or inferred.
3. Do not infer seniority. Do not expand an abbreviation into a qualification.
   Do not turn a tool mentioned in passing into a claimed skill, and do not add
   a skill because it commonly accompanies one that is listed.
4. Do not write a summary. Return the candidate's own summary or profile
   section if the CV has one, otherwise null.
5. Keep dates exactly as written in the CV ("2019", "Mar 2020", "2018-2021").
   Never convert, complete or guess a date.
6. Record a language proficiency only if the CV states one.
7. Do not evaluate the candidate. You do not score, rank, recommend, accept or
   reject anyone; a human recruiter reads your output and decides.
8. Do not infer sensitive characteristics - age, gender, nationality, religion,
   health, marital status - and do not return them even if they appear.
9. Return the result by calling the extract_cv tool exactly once.
"""

TOOL_NAME = "extract_cv"


# ---------------------------------------------------------------------------
# Validation: what the API and the UI are allowed to see
# ---------------------------------------------------------------------------


def _as_optional_str(value: Any) -> str | None:
    """Any scalar the model might send, as a trimmed string or None."""
    if value is None or isinstance(value, (list, dict)):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return None
    return str(value)


#: Keys a model tends to use when it returns objects where strings belong.
_NAME_KEYS = ("name", "skill", "title", "value", "language", "certification", "technology")


def _flatten_to_strings(value: Any) -> list[str]:
    """Coerce a loose list into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        # A model occasionally returns "Python, SQL, FastAPI" for a list.
        return [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list):
        return []

    out: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            if entry.strip():
                out.append(entry.strip())
        elif isinstance(entry, dict):
            for key in _NAME_KEYS:
                text = _as_optional_str(entry.get(key))
                if text:
                    out.append(text)
                    break
    return out


def _objectify(value: Any, primary_key: str) -> list[dict[str, Any]]:
    """Coerce a loose list into a list of dicts keyed for an object model.

    `["AWS Certified"]` becomes `[{"name": "AWS Certified"}]` so a model that
    flattened an object list still validates instead of losing the data.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    rows: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            rows.append(entry)
        elif isinstance(entry, str) and entry.strip():
            rows.append({primary_key: entry.strip()})
    return rows


class _CvModel(BaseModel):
    """Shared config: ignore anything the model invented beyond the schema."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class CvExperience(_CvModel):
    job_title: str | None = None
    company: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    #: Technologies this role names. Kept per-role because that is what a
    #: future job matcher needs - "React, 2022-2024" is a stronger signal
    #: than "React" sitting loose in a skills list.
    technologies: list[str] = Field(default_factory=list)

    @field_validator(
        "job_title", "company", "location", "start_date", "end_date", "description",
        mode="before",
    )
    @classmethod
    def _scalar(cls, value: Any) -> str | None:
        return _as_optional_str(value)

    @field_validator("technologies", mode="before")
    @classmethod
    def _list(cls, value: Any) -> list[str]:
        return _flatten_to_strings(value)

    @property
    def is_empty(self) -> bool:
        return not any(
            [self.job_title, self.company, self.location, self.start_date,
             self.end_date, self.description, self.technologies]
        )


class CvEducation(_CvModel):
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    @field_validator(
        "degree", "field_of_study", "institution", "start_date", "end_date",
        mode="before",
    )
    @classmethod
    def _scalar(cls, value: Any) -> str | None:
        return _as_optional_str(value)

    @property
    def is_empty(self) -> bool:
        return not any(
            [self.degree, self.field_of_study, self.institution,
             self.start_date, self.end_date]
        )


class CvCertification(_CvModel):
    name: str | None = None
    issuer: str | None = None
    date: str | None = None

    @field_validator("name", "issuer", "date", mode="before")
    @classmethod
    def _scalar(cls, value: Any) -> str | None:
        return _as_optional_str(value)

    @property
    def is_empty(self) -> bool:
        return not any([self.name, self.issuer, self.date])


class CvLanguage(_CvModel):
    language: str | None = None
    #: Null unless the CV states a level. The prompt forbids estimating one,
    #: and nothing downstream fills it in.
    proficiency: str | None = None

    @field_validator("language", "proficiency", mode="before")
    @classmethod
    def _scalar(cls, value: Any) -> str | None:
        return _as_optional_str(value)

    @property
    def is_empty(self) -> bool:
        return not any([self.language, self.proficiency])


class ParsedCv(_CvModel):
    """The validated structured result.

    This is the type every caller receives - the REST endpoint, the MCP tool
    and, in a later phase, the job matcher. Nothing hands round the raw model
    response.
    """

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    education: list[CvEducation] = Field(default_factory=list)
    experience: list[CvExperience] = Field(default_factory=list)
    certifications: list[CvCertification] = Field(default_factory=list)
    languages: list[CvLanguage] = Field(default_factory=list)

    @field_validator("full_name", "email", "phone", "location", "summary", mode="before")
    @classmethod
    def _scalar(cls, value: Any) -> str | None:
        return _as_optional_str(value)

    @field_validator("skills", mode="before")
    @classmethod
    def _skills(cls, value: Any) -> list[str]:
        return _flatten_to_strings(value)

    @field_validator("education", mode="before")
    @classmethod
    def _education(cls, value: Any) -> list[dict[str, Any]]:
        return _objectify(value, "degree")

    @field_validator("experience", mode="before")
    @classmethod
    def _experience(cls, value: Any) -> list[dict[str, Any]]:
        return _objectify(value, "job_title")

    @field_validator("certifications", mode="before")
    @classmethod
    def _certifications(cls, value: Any) -> list[dict[str, Any]]:
        return _objectify(value, "name")

    @field_validator("languages", mode="before")
    @classmethod
    def _languages(cls, value: Any) -> list[dict[str, Any]]:
        return _objectify(value, "language")

    def pruned(self) -> "ParsedCv":
        """Drop rows the model emitted with every field empty.

        A model asked for a list sometimes returns one blank object rather than
        an empty list. Showing a recruiter an empty experience card would imply
        the CV contained a job it does not.
        """
        self.education = [row for row in self.education if not row.is_empty]
        self.experience = [row for row in self.experience if not row.is_empty]
        self.certifications = [row for row in self.certifications if not row.is_empty]
        self.languages = [row for row in self.languages if not row.is_empty]
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @property
    def field_count(self) -> int:
        """How many top-level fields the CV actually yielded.

        Used for logging, so a parse can be traced without recording anything
        the CV said.
        """
        scalars = [self.full_name, self.email, self.phone, self.location, self.summary]
        lists = [self.skills, self.education, self.experience,
                 self.certifications, self.languages]
        return sum(1 for v in scalars if v) + sum(1 for v in lists if v)


class CvParseError(Exception):
    """Parsing failed for a reason worth telling the user about.

    Codes: `empty_text`, `llm_not_configured`, `llm_error`,
    `malformed_response`, `invalid_structure`.
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def validate_parsed_cv(payload: dict[str, Any]) -> ParsedCv:
    """Validate a model response into `ParsedCv`, or refuse it.

    This is the only way a `ParsedCv` is built from model output. If Pydantic
    cannot make sense of the payload the result is discarded - a half-read CV
    is worse than a reported failure, because the recruiter cannot see which
    half is missing.
    """
    if not isinstance(payload, dict):
        raise CvParseError(
            "The model returned structured data of the wrong shape.",
            code="invalid_structure",
        )

    try:
        return ParsedCv.model_validate(payload).pruned()
    except ValidationError as exc:
        # The message names fields, never values - a validation error must not
        # become a channel for CV contents to reach the logs.
        fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in exc.errors()[:5])
        raise CvParseError(
            f"The model's response did not match the CV schema ({fields}).",
            code="invalid_structure",
        ) from exc


def _json_from_text(text: str) -> dict[str, Any]:
    """Last resort when a model answers in prose instead of calling the tool."""
    candidate = text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise CvParseError(
                "The model did not return structured CV data.",
                code="malformed_response",
            )
        candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CvParseError(
            "The model returned data that was not valid JSON.",
            code="malformed_response",
        ) from exc

    if not isinstance(parsed, dict):
        raise CvParseError(
            "The model returned structured data of the wrong shape.",
            code="malformed_response",
        )

    return parsed


def parse_cv_text(text: str) -> ParsedCv:
    """Ask the configured model to extract structured data from CV text.

    Raises `CvParseError` with a code: `empty_text`, `llm_not_configured`,
    `llm_error`, `malformed_response`, `invalid_structure`.
    """
    if not text or not text.strip():
        raise CvParseError("There is no CV text to analyse.", code="empty_text")

    provider = get_provider(llm_settings())

    tools = [
        {
            "name": TOOL_NAME,
            "description": (
                "Return the structured contents of this CV. Copy values from "
                "the document; never invent them."
            ),
            "parameters": CV_SCHEMA,
        }
    ]

    messages = [
        {
            "role": "user",
            "content": (
                "Extract the structured contents of the CV below by calling the "
                "extract_cv tool. Use only what the document actually says.\n\n"
                "--- BEGIN CV TEXT ---\n"
                f"{text}\n"
                "--- END CV TEXT ---"
            ),
        }
    ]

    try:
        reply = provider.complete(SYSTEM_PROMPT, messages, tools)
    except LlmNotConfigured as exc:
        raise CvParseError(str(exc), code="llm_not_configured") from exc
    except LlmError as exc:
        raise CvParseError(str(exc), code="llm_error") from exc

    if reply.tool_call is not None and reply.tool_call.name == TOOL_NAME:
        payload = reply.tool_call.arguments or {}
    elif reply.text:
        payload = _json_from_text(reply.text)
    else:
        raise CvParseError(
            "The model returned an empty response.", code="malformed_response"
        )

    return validate_parsed_cv(payload)


# =========================
# Deterministic fallback
# =========================

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}")


def contact_details_from_text(text: str) -> dict[str, str | None]:
    """Email and phone read straight out of the document, with no model.

    This is not AI and is not presented as such - it is a literal search of the
    CV text, so anything it returns is verifiably a substring of the document.
    It exists so the upload is still useful before a model is configured; every
    other field stays empty rather than being guessed.
    """
    email_match = EMAIL_RE.search(text or "")

    phone: str | None = None
    for candidate in PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", candidate)
        # Long enough to be a phone number, short enough not to be a date range
        # or an ID number swept up by the pattern.
        if 7 <= len(digits) <= 15:
            phone = candidate.strip()
            break

    return {
        "email": email_match.group(0) if email_match else None,
        "phone": phone,
    }
