"""An applicant's own account, profile and CV.

The applicant-side twin of `app/identity.py` plus the parts of the recruitment
workflow a job seeker drives themselves. Every function here takes a
`Candidate` that was resolved from a verified JWT by
`dependencies.get_current_candidate` - never a candidate id from a request -
so there is no function in this module that can be pointed at somebody else.

**Registration links, it does not duplicate.** `candidates` is shared with HR,
who have been keying candidates in by hand since before applicants could sign
in. If somebody registers with an address HR already recorded, their account is
attached to that existing row: their CV, their applications and their interview
history are one history, not two. A new `candidates` row is created only when
the address is genuinely new. This is the "do not create duplicate candidate
records" rule, and it is enforced here rather than trusted to the caller.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CV, Candidate, Role, User
from app.services.opportunity_service import split_skills

logger = logging.getLogger("smarthr.applicant")

#: roles.id 5, seeded by migrations/2026-09-14_applicant.sql.
ROLE_APPLICANT = 5

# candidates column widths, checked here so an over-long value is a clean
# validation error rather than a driver error from PostgreSQL.
MAX_NAME = 100
MAX_EMAIL = 255
MAX_PHONE = 30
MAX_LOCATION = 150


class ApplicantError(Exception):
    """Something the applicant can fix, with a code the router maps to HTTP."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


@dataclass
class Registration:
    full_name: str
    email: str
    password: str


def split_full_name(full_name: str) -> tuple[str, str]:
    """`candidates` stores first and last name separately; the form asks for one.

    A single-word name keeps the last name empty rather than guessing or
    duplicating - both columns are NOT NULL, so it becomes an empty string,
    and nothing downstream invents a surname.
    """
    parts = [p for p in (full_name or "").strip().split() if p]

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0][:MAX_NAME], ""

    return parts[0][:MAX_NAME], " ".join(parts[1:])[:MAX_NAME]


def name_from_email(email: str) -> tuple[str, str]:
    """A placeholder name derived from the account's own address.

    `candidates.first_name` and `last_name` are NOT NULL, but `users` stores no
    name at all, so an account created by an Admin through `POST /users/`
    arrives with nothing to put in them. The local part of the address is used
    - `sara.hamdan@...` becomes "Sara Hamdan" - because it is *derived from a
    value the account already has*, not invented personal data. The applicant
    changes it on My Profile, and `profile_dict()` counts the field as present
    either way, which is why registration should always pass a real name when
    it has one.
    """
    local = (email or "").split("@")[0]
    parts = [p for p in re.split(r"[._\-+]+", local) if p]

    if not parts:
        return "Applicant", ""

    words = [p[:1].upper() + p[1:] for p in parts]

    return words[0][:MAX_NAME], " ".join(words[1:])[:MAX_NAME]


def _normalised_email(raw: str) -> str:
    email = (raw or "").strip().lower()

    if not email or "@" not in email:
        raise ApplicantError("Enter a valid email address.", code="invalid_email")

    if len(email) > MAX_EMAIL:
        raise ApplicantError("That email address is too long.", code="invalid_email")

    return email


def register_applicant(data: Registration, db: Session) -> tuple[User, Candidate, bool]:
    """Create the account and attach it to a candidate row.

    Returns `(user, candidate, linked_existing)`. `linked_existing` is True when
    an existing HR-entered candidate was adopted rather than a new row created.

    Raises `ApplicantError` with code `email_taken` when an account already
    exists - the same message whether or not the address is known, so this
    endpoint cannot be used to enumerate who has an account.
    """
    email = _normalised_email(data.email)
    first_name, last_name = split_full_name(data.full_name)

    if not first_name:
        raise ApplicantError("Enter your full name.", code="invalid_name")

    if not data.password or len(data.password) < 8:
        raise ApplicantError(
            "Choose a password of at least 8 characters.", code="weak_password"
        )

    existing_account = (
        db.query(User).filter(func.lower(User.email) == email).first()
    )

    if existing_account is not None:
        raise ApplicantError(
            "An account with that email address already exists. Sign in instead.",
            code="email_taken",
        )

    # The Applicant role must exist before an account can reference it. This is
    # a clearer failure than a foreign-key violation.
    if db.query(Role).filter(Role.id == ROLE_APPLICANT).first() is None:
        raise ApplicantError(
            "The Applicant role is not present in this database. Run "
            "migrations/2026-09-14_applicant.sql.",
            code="role_missing",
        )

    # Imported here rather than at module scope: app/routers/auth.py is the
    # owner of the password hasher, and importing a router at import time from
    # a service would tie this module into the auth import chain for no reason.
    from app.routers.auth import password_hash

    account = User(
        email=email,
        password_hash=password_hash.hash(data.password),
        role_id=ROLE_APPLICANT,
        is_active=True,
    )
    db.add(account)
    db.flush()  # assigns account.id without ending the transaction

    candidate, outcome = link_candidate_profile(account, db, full_name=data.full_name)

    db.commit()
    db.refresh(account)
    db.refresh(candidate)

    logger.info(
        "Applicant registered | user_id=%s candidate_id=%s outcome=%s",
        account.id, candidate.id, outcome,
    )

    return account, candidate, outcome == LINKED_EXISTING


# ---------------------------------------------------------------------------
# Linking an account to its profile
# ---------------------------------------------------------------------------

#: What `link_candidate_profile` did, for callers that report it.
ALREADY_LINKED = "already_linked"
LINKED_EXISTING = "linked_existing"
CREATED = "created"


def link_candidate_profile(
    account: User, db: Session, full_name: str | None = None
) -> tuple[Candidate, str]:
    """Give this account the `candidates` row it signs in as. Idempotent.

    **This is the single definition of what links a user to an applicant
    profile**, and every path that can produce a role 5 account goes through
    it: self-registration, an Admin creating or promoting an account through
    `POST /users/` and `PUT /users/{id}`, and the backfill in
    `scripts/link_applicant_profiles.py`. Without one shared implementation the
    rule holds only on the path somebody remembered, leaving an applicant
    account without a linked profile.

    Three outcomes, in priority order, and the first two never write a new row:

    * `already_linked` - `candidates.user_id` already points here. Returned
      unchanged, which is what makes calling this twice harmless.
    * `linked_existing` - an unlinked candidate HR keyed in by hand carries the
      same address, so it is adopted. Their CV, applications and interview
      history stay one history rather than being duplicated.
    * `created` - the address is genuinely new.

    `full_name` overwrites the name when it is supplied, because the person
    themselves typed it. When it is absent the existing row keeps whatever a
    recruiter recorded, and a new row is named from the address by
    `name_from_email()` - the NOT NULL columns have to hold something, and a
    value derived from the account beats a guess. Nothing else on an adopted
    row is ever touched.

    Does not commit: the caller owns the transaction, so registration can
    create the account and link it in one.
    """
    if account.role_id != ROLE_APPLICANT:
        raise ApplicantError(
            f"Account {account.email} is not an Applicant (role {account.role_id}), "
            f"so it has no applicant profile.",
            code="not_an_applicant",
        )

    if account.id is None:
        raise ApplicantError(
            "The account must be saved before it can be linked to a profile.",
            code="unsaved_account",
        )

    email = _normalised_email(account.email)

    linked = db.query(Candidate).filter(Candidate.user_id == account.id).first()

    if linked is not None:
        if full_name:
            linked.first_name, linked.last_name = split_full_name(full_name)

        return linked, ALREADY_LINKED

    # Adopt the candidate HR already has for this address, if there is one.
    # `user_id IS NULL` matters: a row already claimed by another account is
    # not ours to take, and candidates.user_id is UNIQUE, so trying would be a
    # constraint violation rather than a silent hijack.
    candidate = (
        db.query(Candidate)
        .filter(func.lower(Candidate.email) == email)
        .filter(Candidate.user_id.is_(None))
        .order_by(Candidate.id)
        .first()
    )

    if candidate is not None:
        candidate.user_id = account.id

        if full_name:
            candidate.first_name, candidate.last_name = split_full_name(full_name)

        db.flush()

        return candidate, LINKED_EXISTING

    first_name, last_name = (
        split_full_name(full_name) if full_name else name_from_email(email)
    )

    candidate = Candidate(
        first_name=first_name,
        last_name=last_name,
        email=email,
        user_id=account.id,
    )
    db.add(candidate)
    db.flush()

    return candidate, CREATED


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def profile_dict(candidate: Candidate, db: Session) -> dict[str, Any]:
    """The applicant's own profile, plus their CV status.

    `completeness` drives the dashboard's "finish your profile" prompt. It
    counts fields that are actually present, so it can never claim a profile is
    complete when matching would have nothing to work with.
    """
    latest = latest_cv(candidate, db)
    skills = split_skills(candidate.skills)

    fields = {
        "name": bool(candidate.first_name),
        "email": bool(candidate.email),
        "phone": bool(candidate.phone),
        "location": bool(candidate.location),
        "skills": bool(skills),
        "cv": latest is not None,
    }
    complete = sum(1 for present in fields.values() if present)

    return {
        "candidate_id": candidate.id,
        "user_id": candidate.user_id,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "full_name": f"{candidate.first_name} {candidate.last_name}".strip(),
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "skills": skills,
        "skills_raw": candidate.skills,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "cv": cv_dict(latest) if latest else None,
        "has_cv": latest is not None,
        "completeness": {
            "fields": fields,
            "complete": complete,
            "total": len(fields),
            "percent": round(100 * complete / len(fields)),
        },
    }


@dataclass
class ProfileUpdate:
    """Only fields an applicant owns. Notice what is absent: no email (it is
    the account identifier), no id, no user_id, and nothing about their
    applications or their stage in anybody's pipeline."""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    location: str | None = None
    skills: str | None = None


def _checked(value: str | None, limit: int, label: str) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    if len(cleaned) > limit:
        raise ApplicantError(
            f"{label} must be {limit} characters or fewer.", code="too_long"
        )

    return cleaned


def update_profile(
    candidate: Candidate, update: ProfileUpdate, db: Session
) -> dict[str, Any]:
    """Write the applicant's own profile fields."""
    if update.first_name is not None:
        first = _checked(update.first_name, MAX_NAME, "First name")

        if not first:
            raise ApplicantError("Your first name cannot be empty.", code="invalid_name")

        candidate.first_name = first

    if update.last_name is not None:
        candidate.last_name = _checked(update.last_name, MAX_NAME, "Last name") or ""

    if update.phone is not None:
        candidate.phone = _checked(update.phone, MAX_PHONE, "Phone")

    if update.location is not None:
        candidate.location = _checked(update.location, MAX_LOCATION, "Location")

    if update.skills is not None:
        # Normalised to a clean comma-separated list so the same skill typed
        # with odd spacing matches. The words stay exactly as typed.
        skills = split_skills(update.skills)
        candidate.skills = ", ".join(skills) if skills else None

    db.commit()
    db.refresh(candidate)

    logger.info(
        "Applicant profile updated | candidate_id=%s skills=%s",
        candidate.id, len(split_skills(candidate.skills)),
    )

    return profile_dict(candidate, db)


def applicant_skills(candidate: Candidate) -> list[str]:
    """The skills matching is allowed to use: the applicant's own, only."""
    return split_skills(candidate.skills)


# ---------------------------------------------------------------------------
# CV
# ---------------------------------------------------------------------------

def latest_cv(candidate: Candidate, db: Session) -> CV | None:
    """The CV an application should be read against: the most recent one."""
    return (
        db.query(CV)
        .filter(CV.candidate_id == candidate.id)
        .order_by(CV.uploaded_at.desc(), CV.id.desc())
        .first()
    )


def cv_dict(cv: CV) -> dict[str, Any]:
    """A CV row as its owner may see it.

    `file_path` is deliberately absent: it is a server path, it is of no use to
    a browser, and nothing serves files out of `uploads/`.
    """
    return {
        "id": cv.id,
        "file_name": cv.file_name,
        "uploaded_at": cv.uploaded_at.isoformat() if cv.uploaded_at else None,
    }


def my_cvs(candidate: Candidate, db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(CV)
        .filter(CV.candidate_id == candidate.id)
        .order_by(CV.uploaded_at.desc(), CV.id.desc())
        .all()
    )

    return [cv_dict(cv) for cv in rows]
