"""The Social Hub: feed, stories, profiles, people, connections, messages.

`app/routers/social.py` is a thin HTTP layer over this module, following the
same split the rest of SmartHR uses (`application_service`, `interview_service`,
`screening_service`): the router authenticates and maps errors to status codes,
everything else happens here.

Three rules run through all of it.

**The participant is the account, not the employee row.** Every table keys on
`users.id`. `employees.user_id` is nullable and mostly unlinked in this
database, so keying on `employees.id` would lock an active HR account out of
the module entirely. The *person* - name, department, position - is still read
from the linked employees row wherever one exists, through `actor_map()`,
falling back to the email exactly as `describe_user()` already does.

**Ownership goes in the query, and a miss is a 404.** `post_for_author()`,
`conversation_for_member()` and friends filter on the caller inside the query
rather than loading a row and comparing afterwards. Somebody else's id returns
None and the router turns that into 404 rather than 403, so ids cannot be
probed - the rule `application_for_candidate()` and `interview_for_candidate()`
already follow.

**A social projection is built field by field.** `actor_map()` assembles the
person from scratch and carries name, department, position, avatar and
headline - and nothing else. It is never a filtered `employee_identity()`,
because a projection that starts from everything and removes the private parts
leaks the next field somebody adds. Salary has no column in SmartHR at all;
attendance, leave, performance ratings, reviews and hire-date-derived HR status
are simply never read here, and the two places that touch anything adjacent
(`achievements()`) are documented where they are.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Department,
    Employee,
    EmployeeTraining,
    Notification,
    Position,
    Role,
    SocialComment,
    SocialConnection,
    SocialConversation,
    SocialConversationMember,
    SocialMessage,
    SocialPost,
    SocialProfile,
    SocialReaction,
    SocialStory,
    SocialStoryView,
    Training,
    User,
)
from app.audit import (
    ACTION_STATUS_CHANGE,
    ENTITY_SOCIAL_MODERATION,
    record_audit,
)
from app.services import social_moderation_service as moderation
from app.social_storage import media_url

logger = logging.getLogger("smarthr.social")


class SocialError(Exception):
    """Something the caller asked for that SmartHR will not do.

    `code` is what the router maps to a status; the message is what the person
    reads.
    """

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Moderation visibility
#
# One rule, written once and applied to posts, comments and stories alike:
#
#   published      -> everybody sees it
#   pending_review -> ONLY its author sees it, labelled as awaiting review
#   removed        -> nobody sees it on the feed, and the row still exists
#
# The author keeps sight of their own held content on purpose. Content that
# simply vanishes after somebody presses Post reads as a bug, and they would
# post it again; seeing it marked "pending review" is both honest and the
# thing that stops a second copy arriving in the queue.
#
# The author is told the STATUS and nothing else. No category, no severity, no
# confidence and no model reasoning ever crosses into an author-facing
# payload - those live only on the HR review, which is a different projection
# built by `social_moderation_service.review_view()`.
# ---------------------------------------------------------------------------

def _audit_flagged(db: Session, user: User, review) -> None:
    """Record that a piece of content was held for review.

    Called *after* the business commit, like every other `record_audit` call
    in SmartHR, and a no-op when nothing was flagged - so an ordinary post
    writes no moderation row and the trail stays readable.

    The acting user is the author: the audit row says "this person's content
    entered moderation", which is the event. Who then decided is a separate
    row written by the review endpoint under the reviewer's own identity.
    """
    if review is None:
        return

    record_audit(
        db,
        user,
        ACTION_STATUS_CHANGE,
        ENTITY_SOCIAL_MODERATION,
        review.id,
    )


def _visible_to(query, model, viewer_id: int):
    """Narrow a content query to what this viewer may see."""
    return query.filter(
        or_(
            model.moderation_status == moderation.CONTENT_PUBLISHED,
            and_(
                model.moderation_status == moderation.CONTENT_PENDING,
                model.author_user_id == viewer_id,
            ),
        )
    )


def _can_see(row, viewer_id: int) -> bool:
    """The same rule, for a row already in hand."""
    status = getattr(row, "moderation_status", moderation.CONTENT_PUBLISHED)

    if status == moderation.CONTENT_PUBLISHED:
        return True

    if status == moderation.CONTENT_PENDING:
        return row.author_user_id == viewer_id

    return False


def _moderation_fields(row, viewer_id: int) -> dict:
    """The author-facing moderation block. Status only - never the reasons."""
    status = getattr(row, "moderation_status", moderation.CONTENT_PUBLISHED)
    mine = row.author_user_id == viewer_id

    return {
        "moderation_status": status,
        # True only for the author, so a colleague's payload cannot even
        # imply that something of theirs is being reviewed.
        "pending_review": mine and status == moderation.CONTENT_PENDING,
    }


# ---------------------------------------------------------------------------
# Vocabulary
#
# Small, closed and strict on write / lenient on read, matching how `jobs`,
# `applications` and `interviews` treat their own status columns.
# ---------------------------------------------------------------------------

#: Roles that may use the Social Hub at all. Role 5 (Applicant) is external and
#: is refused by `require_staff` on the router; this constant exists so the
#: People directory does not *list* them either.
INTERNAL_ROLES = (1, 2, 3, 4)

#: A reserved domain for fixture accounts. `test_social_hub.py` and
#: `scripts/test_helpers.py` create real,
#: signed-in accounts under it, and they persist between runs by design - which
#: left the People directory listing `e2e.employee@smarthr.test` as a colleague
#: to connect to. They are hidden from the *social* surfaces only: nothing about
#: authentication, RBAC or any other module changes, and the accounts still work.
TEST_ACCOUNT_DOMAIN = "@smarthr.test"

#: Set SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS=true to list them anyway. That is what
#: `test_social_hub.py` does for its own server, because asserting that a
#: fixture appears in the directory is precisely what that test is for. It is
#: read per request like every other setting, so it needs no restart.
SHOW_TEST_ACCOUNTS_VARIABLE = "SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS"


def hides_test_accounts() -> bool:
    """False only where a deployment has explicitly asked to see fixtures."""
    from app.ai.config import bool_setting

    return not bool_setting(SHOW_TEST_ACCOUNTS_VARIABLE, False)


def is_test_account(email: str | None) -> bool:
    return bool(email) and email.strip().lower().endswith(TEST_ACCOUNT_DOMAIN)


#: Roles whose posts are "Company Updates". HR and Admin are the accounts that
#: speak for the organisation, so the filter is derived from who posted rather
#: than from a flag somebody has to remember to tick - which would also have
#: meant a column nobody could verify.
ANNOUNCER_ROLES = (1, 2)

FEED_FILTERS = ("all", "department", "following", "company")

POST_AUDIENCES = ("company", "department")

CONNECTION_STATUSES = ("pending", "accepted", "rejected")

#: A story stops being visible 24 hours after it is posted.
STORY_LIFETIME = timedelta(hours=24)

MAX_POST_CHARS = 5000
MAX_COMMENT_CHARS = 2000
MAX_MESSAGE_CHARS = 4000
MAX_STORY_CAPTION_CHARS = 300

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

#: Notification types written by this module. All of them are ordinary
#: `notifications` rows, so they reach the existing bell and the existing
#: per-role notification pages with no change to either.
NOTIFY_CONNECTION_REQUEST = "social_connection_request"
NOTIFY_CONNECTION_ACCEPTED = "social_connection_accepted"
NOTIFY_COMMENT = "social_comment"
NOTIFY_REACTION = "social_reaction"
NOTIFY_MESSAGE = "social_message"

SOCIAL_NOTIFICATION_TYPES = (
    NOTIFY_CONNECTION_REQUEST,
    NOTIFY_CONNECTION_ACCEPTED,
    NOTIFY_COMMENT,
    NOTIFY_REACTION,
    NOTIFY_MESSAGE,
)


# ---------------------------------------------------------------------------
# Who somebody is, on a social surface
# ---------------------------------------------------------------------------

def _initials(name: str) -> str:
    parts = [p for p in name.replace("@", " ").split() if p]
    if not parts:
        return "--"
    letters = "".join(p[0] for p in parts[:2])
    return (letters or name[0]).upper()


def actor_map(user_ids, db: Session) -> dict[int, dict]:
    """The social identity of each of these accounts, in four queries.

    Built field by field and deliberately narrow: id, name, email, role,
    department, position, avatar, headline. Nothing about attendance, leave,
    performance, reviews or employment status is read, and SmartHR has no
    salary column anywhere.

    An account with no `employees` row is a normal state, not an error - it
    gets its email as a display name, exactly as `describe_user()` does, and
    a null department and position.
    """
    ids = sorted({int(uid) for uid in user_ids if uid is not None})

    if not ids:
        return {}

    users = db.query(User).filter(User.id.in_(ids)).all()
    employees = db.query(Employee).filter(Employee.user_id.in_(ids)).all()

    employee_by_user = {e.user_id: e for e in employees}

    department_ids = {e.department_id for e in employees if e.department_id}
    position_ids = {e.position_id for e in employees if e.position_id}
    role_ids = {u.role_id for u in users}

    departments = (
        {
            d.id: d.name
            for d in db.query(Department).filter(Department.id.in_(department_ids)).all()
        }
        if department_ids
        else {}
    )

    positions = (
        {
            p.id: p.title
            for p in db.query(Position).filter(Position.id.in_(position_ids)).all()
        }
        if position_ids
        else {}
    )

    roles = (
        {r.id: r.name for r in db.query(Role).filter(Role.id.in_(role_ids)).all()}
        if role_ids
        else {}
    )

    profiles = {
        p.user_id: p
        for p in db.query(SocialProfile).filter(SocialProfile.user_id.in_(ids)).all()
    }

    result: dict[int, dict] = {}

    for user in users:
        employee = employee_by_user.get(user.id)
        profile = profiles.get(user.id)

        name = (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else user.email
        )

        result[user.id] = {
            "user_id": user.id,
            "name": name,
            "initials": _initials(name),
            "email": user.email,
            "role_id": user.role_id,
            "role_name": roles.get(user.role_id),
            # Null rather than invented when the account has no employees row.
            "employee_id": employee.id if employee else None,
            "department_id": employee.department_id if employee else None,
            "department_name": (
                departments.get(employee.department_id) if employee else None
            ),
            "position_title": (
                positions.get(employee.position_id) if employee else None
            ),
            "headline": profile.headline if profile else None,
            "avatar_url": media_url(profile.avatar_path) if profile else None,
        }

    return result


def actor(user_id: int, db: Session) -> dict | None:
    return actor_map([user_id], db).get(user_id)


def department_of(user: User, db: Session) -> int | None:
    """The caller's department id, or None when their account has no employee
    row. Used to stamp a post and to answer the "My Department" filter."""
    employee = db.query(Employee).filter(Employee.user_id == user.id).first()

    return employee.department_id if employee else None


# ---------------------------------------------------------------------------
# Notifications - the existing table, not a second one
# ---------------------------------------------------------------------------

def notify(db: Session, user_id: int, kind: str, title: str, message: str) -> None:
    """Write one `notifications` row.

    Best-effort in the same spirit as `record_audit`: a notification is
    secondary to the action it describes, so a failure here rolls itself back
    and is logged rather than failing the post, the like or the message.

    Never notifies the actor about their own action - liking your own post is
    allowed, being told about it is noise.

    The text is stored in English, following the existing rule that database
    values are shown as stored and only the labels around them are translated.
    The UI localises the *category* (from `type`) and the surrounding chrome;
    the sentence itself is a stored value like every other notification in
    SmartHR.
    """
    try:
        db.add(
            Notification(
                user_id=user_id,
                title=title[:150],
                message=message,
                type=kind,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover - defensive, same as record_audit
        db.rollback()
        logger.warning("social notification failed", extra={"kind": kind})


def list_notifications(user: User, db: Session, limit: int = 50) -> list[dict]:
    """The caller's Social Hub notifications.

    Scoped to the caller by `user_id` and narrowed to the `social_*` types, so
    this is a view of the same inbox the bell shows rather than a second one.
    """
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .filter(Notification.type.in_(SOCIAL_NOTIFICATION_TYPES))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(min(limit, 200))
        .all()
    )

    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": bool(n.is_read),
            "created_at": n.created_at,
        }
        for n in rows
    ]


def mark_notification_read(user: User, notification_id: int, db: Session) -> dict:
    """Mark one of the caller's own notifications read.

    Ownership is in the query, so another user's notification id is a 404 and
    not a 403 - it must not be possible to learn that a row exists.
    """
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .filter(Notification.user_id == user.id)
        .first()
    )

    if row is None:
        raise SocialError("That notification does not exist.", "not_found")

    row.is_read = True
    db.commit()

    return {"id": row.id, "is_read": True}


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def _profile_row(user_id: int, db: Session) -> SocialProfile | None:
    return db.query(SocialProfile).filter(SocialProfile.user_id == user_id).first()


def ensure_profile(user_id: int, db: Session) -> SocialProfile:
    """The caller's profile row, created empty on first use.

    Created rather than required: an account is a Social Hub participant the
    moment it signs in, and a person who has not written a bio has an empty
    profile, not a missing one. Every field stays null until they type
    something, so nothing is ever invented on their behalf.
    """
    profile = _profile_row(user_id, db)

    if profile is not None:
        return profile

    profile = SocialProfile(user_id=user_id)
    db.add(profile)

    try:
        db.commit()
    except IntegrityError:
        # Two concurrent first-visits; the other one won, which is fine.
        db.rollback()
        profile = _profile_row(user_id, db)

        if profile is None:  # pragma: no cover - only if the row vanished
            raise SocialError("The profile could not be created.", "conflict")

        return profile

    db.refresh(profile)
    return profile


def _skill_list(raw: str | None) -> list[str]:
    """Split the free-text skills field, never interpret it.

    Same treatment `matching_service.requirement_tokens()` gives job
    requirements: every skill shown is a literal substring of what the person
    typed.
    """
    if not raw:
        return []

    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]

    return [p for p in parts if p][:40]


def achievements(user_id: int, db: Session) -> list[dict]:
    """Professional milestones, from real rows only.

    Two sources, both chosen because they are about somebody's professional
    development rather than their HR record:

      * completed `employee_trainings` - a course finished, with its date;
      * the `employees.hire_date` anniversary - how long they have been here,
        which is ordinary colleague-facing information.

    **Deliberately not included:** performance ratings and review feedback,
    attendance, leave, employment status, manager, and anything derived from
    them. Those are HR records, and this is a social profile. SmartHR has no
    salary column at all, so there is nothing there to exclude.

    An empty list is a correct answer and renders as an empty state - nothing
    is generated to fill the tab.
    """
    employee = db.query(Employee).filter(Employee.user_id == user_id).first()

    if employee is None:
        return []

    items: list[dict] = []

    if employee.hire_date:
        years = (datetime.utcnow().date() - employee.hire_date).days // 365
        items.append(
            {
                "kind": "tenure",
                "title": None,
                "date": employee.hire_date.isoformat(),
                "years": max(years, 0),
            }
        )

    rows = (
        db.query(EmployeeTraining, Training)
        .join(Training, Training.id == EmployeeTraining.training_id)
        .filter(EmployeeTraining.employee_id == employee.id)
        .filter(EmployeeTraining.status == "completed")
        .order_by(EmployeeTraining.completed_at.desc().nullslast())
        .limit(20)
        .all()
    )

    for assignment, training in rows:
        items.append(
            {
                "kind": "training",
                # A database value, shown exactly as stored.
                "title": training.title,
                "date": (
                    assignment.completed_at.isoformat()
                    if assignment.completed_at
                    else None
                ),
                "years": None,
            }
        )

    return items


def profile_view(
    target_user_id: int,
    viewer: User,
    db: Session,
    *,
    include_posts: bool = True,
) -> dict:
    """One person's social profile, as another internal user sees it.

    The same shape whoever is looking: there is no richer variant for HR, and
    no field appears here that is not on every other profile. `is_me` says
    whether the profile is the viewer's own, which is what the UI uses to swap
    Connect/Message for Edit.
    """
    target = db.query(User).filter(User.id == target_user_id).first()

    if target is None or target.role_id not in INTERNAL_ROLES:
        # Applicants are not in the directory and neither is a missing id, and
        # the two are answered identically so neither can be told from the
        # other.
        raise SocialError("That person is not in the SmartHR directory.", "not_found")

    if not target.is_active and target.id != viewer.id:
        raise SocialError("That person is not in the SmartHR directory.", "not_found")

    profile = ensure_profile(target.id, db) if target.id == viewer.id else _profile_row(
        target.id, db
    )

    person = actor(target.id, db) or {}

    connection = connection_state(viewer.id, target.id, db)

    counts = connection_counts(target.id, db)

    payload = {
        **person,
        "is_me": target.id == viewer.id,
        "headline": profile.headline if profile else None,
        "bio": profile.bio if profile else None,
        "skills": _skill_list(profile.skills if profile else None),
        "interests": _skill_list(profile.interests if profile else None),
        "location": (profile.location if profile else None),
        "avatar_url": media_url(profile.avatar_path) if profile else None,
        "cover_url": media_url(profile.cover_path) if profile else None,
        "connection": connection,
        "connections_count": counts["accepted"],
        "achievements": achievements(target.id, db),
    }

    if include_posts:
        payload["posts"] = [
            post_view(post, viewer, db)
            for post in (
                db.query(SocialPost)
                .filter(SocialPost.author_user_id == target.id)
                .order_by(SocialPost.created_at.desc(), SocialPost.id.desc())
                .limit(20)
                .all()
            )
        ]

    return payload


def update_my_profile(user: User, data: dict, db: Session) -> dict:
    """Write the caller's own profile. There is no id in the request.

    Like `PUT /applicant/me`, the row is resolved from the verified token, so
    "my profile" cannot be widened by editing the body - there is no parameter
    naming whose profile this is.
    """
    profile = ensure_profile(user.id, db)

    if "headline" in data:
        value = (data["headline"] or "").strip()
        # varchar(150) in the database; refused here so it is a 422 rather
        # than a driver error.
        if len(value) > 150:
            raise SocialError("Headline must be 150 characters or fewer.", "too_long")
        profile.headline = value or None

    if "bio" in data:
        value = (data["bio"] or "").strip()
        if len(value) > 2000:
            raise SocialError("Bio must be 2000 characters or fewer.", "too_long")
        profile.bio = value or None

    if "skills" in data:
        profile.skills = (data["skills"] or "").strip() or None

    if "interests" in data:
        profile.interests = (data["interests"] or "").strip() or None

    if "location" in data:
        value = (data["location"] or "").strip()
        if len(value) > 150:
            raise SocialError("Location must be 150 characters or fewer.", "too_long")
        profile.location = value or None

    profile.updated_at = datetime.utcnow()

    db.commit()

    return profile_view(user.id, user, db)


def set_avatar(user: User, stored_path: str, db: Session) -> dict:
    profile = ensure_profile(user.id, db)
    profile.avatar_path = stored_path
    profile.updated_at = datetime.utcnow()
    db.commit()

    return profile_view(user.id, user, db)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def _pair_row(a: int, b: int, db: Session) -> SocialConnection | None:
    """The one row for this pair, in whichever direction it was created.

    There is exactly one, always: the unique index on (LEAST, GREATEST)
    guarantees it.
    """
    return (
        db.query(SocialConnection)
        .filter(
            or_(
                and_(
                    SocialConnection.requester_user_id == a,
                    SocialConnection.receiver_user_id == b,
                ),
                and_(
                    SocialConnection.requester_user_id == b,
                    SocialConnection.receiver_user_id == a,
                ),
            )
        )
        .first()
    )


def connection_state(viewer_id: int, other_id: int, db: Session) -> dict:
    """How the viewer stands with this person, from the viewer's side.

    `state` is one of: self, none, pending_outgoing, pending_incoming,
    connected, rejected. The direction matters to the UI - an incoming request
    offers Accept/Reject, an outgoing one offers nothing but a label.
    """
    if viewer_id == other_id:
        return {"state": "self", "connection_id": None}

    row = _pair_row(viewer_id, other_id, db)

    if row is None:
        return {"state": "none", "connection_id": None}

    if row.status == "accepted":
        return {"state": "connected", "connection_id": row.id}

    if row.status == "pending":
        outgoing = row.requester_user_id == viewer_id
        return {
            "state": "pending_outgoing" if outgoing else "pending_incoming",
            "connection_id": row.id,
        }

    return {"state": "rejected", "connection_id": row.id}


def connection_counts(user_id: int, db: Session) -> dict:
    accepted = (
        db.query(func.count(SocialConnection.id))
        .filter(SocialConnection.status == "accepted")
        .filter(
            or_(
                SocialConnection.requester_user_id == user_id,
                SocialConnection.receiver_user_id == user_id,
            )
        )
        .scalar()
        or 0
    )

    incoming = (
        db.query(func.count(SocialConnection.id))
        .filter(SocialConnection.status == "pending")
        .filter(SocialConnection.receiver_user_id == user_id)
        .scalar()
        or 0
    )

    return {"accepted": int(accepted), "pending_incoming": int(incoming)}


def connected_user_ids(user_id: int, db: Session) -> list[int]:
    rows = (
        db.query(SocialConnection)
        .filter(SocialConnection.status == "accepted")
        .filter(
            or_(
                SocialConnection.requester_user_id == user_id,
                SocialConnection.receiver_user_id == user_id,
            )
        )
        .all()
    )

    return [
        r.receiver_user_id if r.requester_user_id == user_id else r.requester_user_id
        for r in rows
    ]


def request_connection(user: User, target_user_id: int, db: Session) -> dict:
    """Ask to connect.

    Three refusals, and the first two are structural rather than trusted to
    this function: the CHECK constraint makes a self-connection unstorable and
    the unique pair index makes a duplicate unstorable. They are checked here
    as well so the caller gets a sentence instead of an IntegrityError.
    """
    if target_user_id == user.id:
        raise SocialError("You cannot connect with yourself.", "self_connection")

    target = db.query(User).filter(User.id == target_user_id).first()

    if target is None or target.role_id not in INTERNAL_ROLES or not target.is_active:
        raise SocialError("That person is not in the SmartHR directory.", "not_found")

    row = _pair_row(user.id, target_user_id, db)

    if row is not None:
        if row.status == "accepted":
            raise SocialError("You are already connected.", "already_connected")

        if row.status == "pending":
            if row.requester_user_id == user.id:
                raise SocialError("You have already sent a request.", "already_pending")

            # They asked first. Accepting is the sensible reading of both
            # people wanting this, and it avoids two rows the schema forbids.
            return respond_to_connection(user, row.id, "accepted", db)

        # A previously rejected pair: revive the same row rather than leaving
        # a tombstone that blocks these two forever.
        row.requester_user_id = user.id
        row.receiver_user_id = target_user_id
        row.status = "pending"
        row.updated_at = datetime.utcnow()
        db.commit()
    else:
        row = SocialConnection(
            requester_user_id=user.id,
            receiver_user_id=target_user_id,
            status="pending",
        )
        db.add(row)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise SocialError(
                "There is already a connection request between you.",
                "already_pending",
            )

        db.refresh(row)

    me = actor(user.id, db) or {}
    notify(
        db,
        target_user_id,
        NOTIFY_CONNECTION_REQUEST,
        "New connection request",
        f"{me.get('name', 'A colleague')} would like to connect with you on the Social Hub.",
    )

    return connection_view(row, user, db)


def respond_to_connection(
    user: User,
    connection_id: int,
    decision: str,
    db: Session,
) -> dict:
    """Accept or reject a request **addressed to the caller**.

    The receiver is in the query, so a request between two other people is a
    404: there is no id to find, and no way to learn that one exists.
    """
    if decision not in ("accepted", "rejected"):
        raise SocialError("Unknown decision.", "invalid")

    row = (
        db.query(SocialConnection)
        .filter(SocialConnection.id == connection_id)
        .filter(SocialConnection.receiver_user_id == user.id)
        .first()
    )

    if row is None:
        raise SocialError("That connection request does not exist.", "not_found")

    if row.status != "pending":
        raise SocialError(
            "That request has already been answered.",
            "already_answered",
        )

    row.status = decision
    row.updated_at = datetime.utcnow()
    db.commit()

    if decision == "accepted":
        me = actor(user.id, db) or {}
        notify(
            db,
            row.requester_user_id,
            NOTIFY_CONNECTION_ACCEPTED,
            "Connection accepted",
            f"{me.get('name', 'A colleague')} accepted your connection request.",
        )

    return connection_view(row, user, db)


def remove_connection(user: User, connection_id: int, db: Session) -> dict:
    """Disconnect, or withdraw a request the caller sent.

    Either party may do this, so the filter is "the caller is one of the two",
    which is still ownership in the query - a third person's connection is a
    404.
    """
    row = (
        db.query(SocialConnection)
        .filter(SocialConnection.id == connection_id)
        .filter(
            or_(
                SocialConnection.requester_user_id == user.id,
                SocialConnection.receiver_user_id == user.id,
            )
        )
        .first()
    )

    if row is None:
        raise SocialError("That connection does not exist.", "not_found")

    db.delete(row)
    db.commit()

    return {"id": connection_id, "removed": True}


def connection_view(row: SocialConnection, viewer: User, db: Session) -> dict:
    other_id = (
        row.receiver_user_id
        if row.requester_user_id == viewer.id
        else row.requester_user_id
    )

    return {
        "id": row.id,
        "status": row.status,
        "direction": "outgoing" if row.requester_user_id == viewer.id else "incoming",
        "person": actor(other_id, db),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_connections(user: User, db: Session) -> dict:
    """Everything the caller has going on: accepted, incoming, outgoing."""
    rows = (
        db.query(SocialConnection)
        .filter(
            or_(
                SocialConnection.requester_user_id == user.id,
                SocialConnection.receiver_user_id == user.id,
            )
        )
        .order_by(SocialConnection.updated_at.desc())
        .all()
    )

    accepted, incoming, outgoing = [], [], []

    for row in rows:
        view = connection_view(row, user, db)

        if row.status == "accepted":
            accepted.append(view)
        elif row.status == "pending" and row.receiver_user_id == user.id:
            incoming.append(view)
        elif row.status == "pending":
            outgoing.append(view)

    return {
        "connections": accepted,
        "incoming_requests": incoming,
        "outgoing_requests": outgoing,
        "counts": {
            "connections": len(accepted),
            "incoming": len(incoming),
            "outgoing": len(outgoing),
        },
    }


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

def search_people(
    user: User,
    db: Session,
    *,
    query: str = "",
    department_id: int | None = None,
    limit: int = 50,
) -> dict:
    """The internal directory, as a social surface sees it.

    **Lists accounts, not employee records**, and that is a deliberate
    narrowing: a connection request or a message needs a recipient who can sign
    in and answer. An `employees` row with no account cannot accept, reply or
    post, so listing it would offer two buttons that can never complete - the
    same reasoning that makes a training listing say `can_apply: false` rather
    than showing a button that would fail.

    Search matches name, email, department and position. Matching on *any*
    word would make every query return everybody, so each search term must
    appear somewhere in the person's text.
    """
    users = (
        db.query(User)
        .filter(User.role_id.in_(INTERNAL_ROLES))
        .filter(User.is_active.is_(True))
        .all()
    )

    people = actor_map([u.id for u in users], db)

    terms = [t for t in (query or "").lower().split() if t]

    results = []

    hide_fixtures = hides_test_accounts()

    for person in people.values():
        if person["user_id"] == user.id:
            continue

        # A fixture account is not a colleague. Excluded here rather than in
        # the browser so the count, the pages and the suggestions all agree -
        # `suggestions()` reads this function, so it is covered by the same
        # line.
        if hide_fixtures and is_test_account(person["email"]):
            continue

        if department_id is not None and person["department_id"] != department_id:
            continue

        if terms:
            haystack = " ".join(
                str(part or "").lower()
                for part in (
                    person["name"],
                    person["email"],
                    person["department_name"],
                    person["position_title"],
                    person["headline"],
                )
            )

            if not all(term in haystack for term in terms):
                continue

        results.append(
            {
                **person,
                "connection": connection_state(user.id, person["user_id"], db),
            }
        )

    results.sort(key=lambda p: (p["name"] or "").lower())

    return {
        "people": results[:limit],
        "total": len(results),
        "query": query,
        "department_id": department_id,
    }


def suggestions(user: User, db: Session, limit: int = 5) -> list[dict]:
    """People the caller is not connected to yet.

    No scoring and no ranking: these are colleagues with no connection row,
    nearest department first. Ranking colleagues by an invented affinity
    number is exactly the kind of thing this module should not do.
    """
    mine = department_of(user, db)

    found = search_people(user, db, limit=200)["people"]

    open_people = [
        p for p in found if p["connection"]["state"] == "none"
    ]

    open_people.sort(
        key=lambda p: (
            0 if (mine is not None and p["department_id"] == mine) else 1,
            (p["name"] or "").lower(),
        )
    )

    return open_people[:limit]


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def post_for_author(post_id: int, user: User, db: Session) -> SocialPost | None:
    """A post the caller wrote. Ownership in the query.

    Note there is no Admin override: deleting a colleague's post is moderation,
    and V1 has no moderation surface, so it is not smuggled in as a side effect
    of being an Admin.
    """
    return (
        db.query(SocialPost)
        .filter(SocialPost.id == post_id)
        .filter(SocialPost.author_user_id == user.id)
        .first()
    )


def _post_counts(post_ids: list[int], viewer_id: int, db: Session):
    """Reactions, comments and "did I like it" for a page of posts.

    Three grouped queries for the whole page rather than three per post: the
    feed renders ten posts and would otherwise issue thirty round trips.
    """
    if not post_ids:
        return {}, {}, set()

    reactions = dict(
        db.query(SocialReaction.post_id, func.count(SocialReaction.id))
        .filter(SocialReaction.post_id.in_(post_ids))
        .group_by(SocialReaction.post_id)
        .all()
    )

    # Counted with the same visibility rule the list uses, so the number on
    # the card is the number of comments that open underneath it.
    comments = dict(
        _visible_to(
            db.query(SocialComment.post_id, func.count(SocialComment.id)),
            SocialComment,
            viewer_id,
        )
        .filter(SocialComment.post_id.in_(post_ids))
        .group_by(SocialComment.post_id)
        .all()
    )

    mine = {
        row[0]
        for row in db.query(SocialReaction.post_id)
        .filter(SocialReaction.post_id.in_(post_ids))
        .filter(SocialReaction.user_id == viewer_id)
        .all()
    }

    return reactions, comments, mine


def post_view(post: SocialPost, viewer: User, db: Session) -> dict:
    reactions, comments, mine = _post_counts([post.id], viewer.id, db)

    return _assemble_post(post, viewer, actor_map([post.author_user_id], db),
                          reactions, comments, mine, db)


def _assemble_post(post, viewer, people, reactions, comments, mine, db):
    return {
        "id": post.id,
        "author": people.get(post.author_user_id),
        # The post's own words, shown exactly as written - a database value,
        # never translated.
        "content": post.content,
        "image_url": media_url(post.image_path),
        "audience": post.audience,
        "department_id": post.department_id,
        "created_at": post.created_at,
        "edited_at": post.edited_at,
        "like_count": int(reactions.get(post.id, 0)),
        "comment_count": int(comments.get(post.id, 0)),
        "liked_by_me": post.id in mine,
        "is_mine": post.author_user_id == viewer.id,
        **_moderation_fields(post, viewer.id),
    }


def feed(
    user: User,
    db: Session,
    *,
    scope: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """A page of the feed.

    Four scopes, all of them real queries over real rows:

      * `all`        - everything, newest first;
      * `department` - posts stamped with the caller's own department;
      * `following`  - posts by the caller's accepted connections, plus their
                       own, which is what makes the filter useful on day one;
      * `company`    - posts by HR and Admin accounts, i.e. the people who
                       speak for the organisation. Derived from the author's
                       role rather than from a flag, so it cannot drift out of
                       step with who actually posted.

    Paginated, never unbounded: `page_size` is clamped and the response carries
    the total so the UI can page rather than scroll forever.
    """
    if scope not in FEED_FILTERS:
        scope = "all"

    page = max(int(page or 1), 1)
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))

    # Held and removed posts are not on anybody's feed; the author still
    # sees their own while it waits.
    query = _visible_to(db.query(SocialPost), SocialPost, user.id)

    if scope == "department":
        mine = department_of(user, db)

        if mine is None:
            # An account with no employees row has no department. Saying so is
            # the honest answer; filtering on NULL would silently show every
            # other department-less post.
            return {
                "posts": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "pages": 0,
                "scope": scope,
                "department_available": False,
            }

        query = query.filter(SocialPost.department_id == mine)

    elif scope == "following":
        ids = connected_user_ids(user.id, db) + [user.id]
        query = query.filter(SocialPost.author_user_id.in_(ids))

    elif scope == "company":
        announcer_ids = [
            row[0]
            for row in db.query(User.id).filter(User.role_id.in_(ANNOUNCER_ROLES)).all()
        ]
        query = query.filter(SocialPost.author_user_id.in_(announcer_ids or [0]))

    total = query.count()

    rows = (
        query.order_by(SocialPost.created_at.desc(), SocialPost.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    people = actor_map([r.author_user_id for r in rows], db)
    reactions, comments, mine_likes = _post_counts([r.id for r in rows], user.id, db)

    return {
        "posts": [
            _assemble_post(r, user, people, reactions, comments, mine_likes, db)
            for r in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
        "scope": scope,
        "department_available": True,
    }


def create_post(
    user: User,
    db: Session,
    *,
    content: str,
    image_path: str | None = None,
    audience: str = "company",
) -> dict:
    content = (content or "").strip()

    if not content:
        raise SocialError("A post needs something to say.", "empty")

    if len(content) > MAX_POST_CHARS:
        raise SocialError(
            f"A post must be {MAX_POST_CHARS} characters or fewer.",
            "too_long",
        )

    if audience not in POST_AUDIENCES:
        audience = "company"

    department_id = department_of(user, db)

    if audience == "department" and department_id is None:
        raise SocialError(
            "Your account is not linked to a department, so it cannot post to one.",
            "no_department",
        )

    post = SocialPost(
        author_user_id=user.id,
        content=content,
        image_path=image_path,
        audience=audience,
        department_id=department_id,
    )

    db.add(post)
    # Flushed rather than committed: the moderation record references the
    # post's id, and both the post's visibility and its review row are
    # written in ONE transaction. A crash between them would otherwise leave
    # a post nobody is reviewing or a review pointing at nothing.
    db.flush()

    status, review, _ = moderation.moderate_and_record(
        db,
        content_type="post",
        content_id=post.id,
        author_user_id=user.id,
        text=content,
    )

    post.moderation_status = status
    db.commit()
    db.refresh(post)

    _audit_flagged(db, user, review)

    return post_view(post, user, db)


def update_post(user: User, post_id: int, content: str, db: Session) -> dict:
    post = post_for_author(post_id, user, db)

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    content = (content or "").strip()

    if not content:
        raise SocialError("A post needs something to say.", "empty")

    if len(content) > MAX_POST_CHARS:
        raise SocialError(
            f"A post must be {MAX_POST_CHARS} characters or fewer.",
            "too_long",
        )

    changed = content != post.content

    post.content = content
    post.updated_at = datetime.utcnow()
    # Set only on a real edit, so "edited" on screen always means edited.
    post.edited_at = datetime.utcnow()

    review = None

    # Re-moderated only when the words actually changed. Saving a post
    # unchanged, or any other write, must not spend a model call - and an
    # edit that alters nothing has not created anything new to judge.
    if changed:
        status, review, _ = moderation.moderate_and_record(
            db,
            content_type="post",
            content_id=post.id,
            author_user_id=user.id,
            text=content,
        )
        post.moderation_status = status

    db.commit()

    _audit_flagged(db, user, review)

    return post_view(post, user, db)


def delete_post(user: User, post_id: int, db: Session) -> dict:
    post = post_for_author(post_id, user, db)

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    # Comments and reactions go with it, by ON DELETE CASCADE in the schema.
    db.delete(post)
    db.commit()

    return {"id": post_id, "deleted": True}


def get_post(user: User, post_id: int, db: Session) -> dict:
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    # Held or removed content is a 404 to everybody but its author - the same
    # "ownership in the query" rule the rest of the module follows, so an id
    # cannot be probed to learn that something is under review.
    if not _can_see(post, user.id):
        raise SocialError("That post does not exist.", "not_found")

    return post_view(post, user, db)


# ---------------------------------------------------------------------------
# Comments and reactions
# ---------------------------------------------------------------------------

def list_comments(user: User, post_id: int, db: Session) -> dict:
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    rows = (
        _visible_to(db.query(SocialComment), SocialComment, user.id)
        .filter(SocialComment.post_id == post_id)
        .order_by(SocialComment.created_at, SocialComment.id)
        .all()
    )

    people = actor_map([r.author_user_id for r in rows], db)

    return {
        "post_id": post_id,
        "comments": [
            {
                "id": r.id,
                "author": people.get(r.author_user_id),
                "content": r.content,
                "created_at": r.created_at,
                "is_mine": r.author_user_id == user.id,
                **_moderation_fields(r, user.id),
            }
            for r in rows
        ],
        "total": len(rows),
    }


def add_comment(user: User, post_id: int, content: str, db: Session) -> dict:
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    content = (content or "").strip()

    if not content:
        raise SocialError("A comment needs something in it.", "empty")

    if len(content) > MAX_COMMENT_CHARS:
        raise SocialError(
            f"A comment must be {MAX_COMMENT_CHARS} characters or fewer.",
            "too_long",
        )

    comment = SocialComment(
        post_id=post_id,
        author_user_id=user.id,
        content=content,
    )

    db.add(comment)
    db.flush()

    status, review, _ = moderation.moderate_and_record(
        db,
        content_type="comment",
        content_id=comment.id,
        author_user_id=user.id,
        text=content,
    )

    comment.moderation_status = status
    db.commit()
    db.refresh(comment)

    _audit_flagged(db, user, review)

    # A held comment notifies nobody. The post's author has not received a
    # comment yet - one is waiting to be reviewed - and telling them now would
    # send them to a post where nothing had appeared.
    if status == moderation.CONTENT_PUBLISHED and post.author_user_id != user.id:
        me = actor(user.id, db) or {}
        notify(
            db,
            post.author_user_id,
            NOTIFY_COMMENT,
            "New comment on your post",
            f"{me.get('name', 'A colleague')} commented on your post.",
        )

    return {
        "id": comment.id,
        "author": actor(user.id, db),
        "content": comment.content,
        "created_at": comment.created_at,
        "is_mine": True,
        **_moderation_fields(comment, user.id),
    }


def delete_comment(user: User, comment_id: int, db: Session) -> dict:
    """Delete a comment the caller wrote.

    Ownership is in the query. A post author cannot delete somebody else's
    comment on their post either: that is moderation, and V1 has none.
    """
    comment = (
        db.query(SocialComment)
        .filter(SocialComment.id == comment_id)
        .filter(SocialComment.author_user_id == user.id)
        .first()
    )

    if comment is None:
        raise SocialError("That comment does not exist.", "not_found")

    db.delete(comment)
    db.commit()

    return {"id": comment_id, "deleted": True}


def like_post(user: User, post_id: int, db: Session) -> dict:
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    existing = (
        db.query(SocialReaction)
        .filter(SocialReaction.post_id == post_id)
        .filter(SocialReaction.user_id == user.id)
        .first()
    )

    if existing is None:
        db.add(SocialReaction(post_id=post_id, user_id=user.id, kind="like"))

        try:
            db.commit()
        except IntegrityError:
            # The UNIQUE constraint won a race. Liking twice is still one
            # like, so this is success, not an error.
            db.rollback()
        else:
            if post.author_user_id != user.id:
                me = actor(user.id, db) or {}
                notify(
                    db,
                    post.author_user_id,
                    NOTIFY_REACTION,
                    "Someone liked your post",
                    f"{me.get('name', 'A colleague')} liked your post.",
                )

    return post_view(post, user, db)


def unlike_post(user: User, post_id: int, db: Session) -> dict:
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

    if post is None:
        raise SocialError("That post does not exist.", "not_found")

    (
        db.query(SocialReaction)
        .filter(SocialReaction.post_id == post_id)
        .filter(SocialReaction.user_id == user.id)
        .delete()
    )

    db.commit()

    return post_view(post, user, db)


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

def active_stories(user: User, db: Session) -> dict:
    """Stories that have not expired, grouped by author.

    Expiry is a WHERE clause on a stored column, so an expired story is not
    "hidden" - it is not selected. Nothing deletes it; the row stays as a
    record of what was posted, exactly as a completed interview session does.
    """
    now = datetime.utcnow()

    rows = (
        _visible_to(db.query(SocialStory), SocialStory, user.id)
        .filter(SocialStory.expires_at > now)
        .order_by(SocialStory.created_at.desc(), SocialStory.id.desc())
        .all()
    )

    people = actor_map([r.author_user_id for r in rows], db)

    seen_ids = {
        row[0]
        for row in db.query(SocialStoryView.story_id)
        .filter(SocialStoryView.viewer_user_id == user.id)
        .all()
    }

    grouped: dict[int, dict] = {}

    for row in rows:
        entry = grouped.setdefault(
            row.author_user_id,
            {
                "author": people.get(row.author_user_id),
                "stories": [],
                "has_unseen": False,
                "is_mine": row.author_user_id == user.id,
            },
        )

        seen = row.id in seen_ids

        entry["stories"].append(
            {
                "id": row.id,
                "caption": row.caption,
                "image_url": media_url(row.image_path),
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "seen": seen,
                "is_mine": row.author_user_id == user.id,
                **_moderation_fields(row, user.id),
            }
        )

        if not seen and row.author_user_id != user.id:
            entry["has_unseen"] = True

    # The caller's own stories first, then anyone with something unseen.
    ordered = sorted(
        grouped.values(),
        key=lambda g: (0 if g["is_mine"] else 1, 0 if g["has_unseen"] else 1),
    )

    return {"groups": ordered, "total": len(rows)}


def create_story(
    user: User,
    db: Session,
    *,
    caption: str | None = None,
    image_path: str | None = None,
) -> dict:
    caption = (caption or "").strip()

    if not caption and not image_path:
        raise SocialError("A story needs an image or some text.", "empty")

    if len(caption) > MAX_STORY_CAPTION_CHARS:
        raise SocialError(
            f"A story caption must be {MAX_STORY_CAPTION_CHARS} characters or fewer.",
            "too_long",
        )

    now = datetime.utcnow()

    story = SocialStory(
        author_user_id=user.id,
        caption=caption or None,
        image_path=image_path,
        created_at=now,
        expires_at=now + STORY_LIFETIME,
    )

    db.add(story)
    db.flush()

    # Only the caption is classified. There is no image classifier in V1, so
    # an image-only story publishes - stated here and in the report rather
    # than left to be discovered.
    status, review, _ = moderation.moderate_and_record(
        db,
        content_type="story",
        content_id=story.id,
        author_user_id=user.id,
        text=caption or "",
    )

    story.moderation_status = status
    db.commit()
    db.refresh(story)

    _audit_flagged(db, user, review)

    return story_view(story, user, db)


def story_view(story: SocialStory, viewer: User, db: Session) -> dict:
    seen = (
        db.query(SocialStoryView)
        .filter(SocialStoryView.story_id == story.id)
        .filter(SocialStoryView.viewer_user_id == viewer.id)
        .first()
        is not None
    )

    viewers = (
        db.query(func.count(SocialStoryView.id))
        .filter(SocialStoryView.story_id == story.id)
        .scalar()
        or 0
    )

    return {
        "id": story.id,
        "author": actor(story.author_user_id, db),
        "caption": story.caption,
        "image_url": media_url(story.image_path),
        "created_at": story.created_at,
        "expires_at": story.expires_at,
        "expired": story.expires_at <= datetime.utcnow(),
        "seen": seen,
        "is_mine": story.author_user_id == viewer.id,
        # Only the author is told how many people watched - it is their story.
        "view_count": int(viewers) if story.author_user_id == viewer.id else None,
        **_moderation_fields(story, viewer.id),
    }


def get_story(user: User, story_id: int, db: Session) -> dict:
    story = db.query(SocialStory).filter(SocialStory.id == story_id).first()

    if story is None:
        raise SocialError("That story does not exist.", "not_found")

    if not _can_see(story, user.id):
        raise SocialError("That story does not exist.", "not_found")

    if story.expires_at <= datetime.utcnow() and story.author_user_id != user.id:
        raise SocialError("That story has expired.", "expired")

    return story_view(story, user, db)


def mark_story_seen(user: User, story_id: int, db: Session) -> dict:
    story = db.query(SocialStory).filter(SocialStory.id == story_id).first()

    if story is None:
        raise SocialError("That story does not exist.", "not_found")

    if story.expires_at <= datetime.utcnow():
        raise SocialError("That story has expired.", "expired")

    if story.author_user_id != user.id:
        existing = (
            db.query(SocialStoryView)
            .filter(SocialStoryView.story_id == story_id)
            .filter(SocialStoryView.viewer_user_id == user.id)
            .first()
        )

        if existing is None:
            db.add(SocialStoryView(story_id=story_id, viewer_user_id=user.id))

            try:
                db.commit()
            except IntegrityError:
                # UNIQUE (story_id, viewer_user_id): seeing it twice is one
                # view, so a race here is not a failure.
                db.rollback()

    return story_view(story, user, db)


def delete_story(user: User, story_id: int, db: Session) -> dict:
    story = (
        db.query(SocialStory)
        .filter(SocialStory.id == story_id)
        .filter(SocialStory.author_user_id == user.id)
        .first()
    )

    if story is None:
        raise SocialError("That story does not exist.", "not_found")

    db.delete(story)
    db.commit()

    return {"id": story_id, "deleted": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def conversation_for_member(
    conversation_id: int,
    user: User,
    db: Session,
) -> SocialConversation | None:
    """A conversation the caller is actually in.

    The membership join **is** the authorisation: a thread the caller is not in
    produces no row, so the router answers 404. There is no separate "are you
    allowed" check that could be forgotten, and no way to discover that a
    conversation exists by trying its id.
    """
    return (
        db.query(SocialConversation)
        .join(
            SocialConversationMember,
            SocialConversationMember.conversation_id == SocialConversation.id,
        )
        .filter(SocialConversation.id == conversation_id)
        .filter(SocialConversationMember.user_id == user.id)
        .first()
    )


def _members_of(conversation_ids: list[int], db: Session) -> dict[int, list[int]]:
    if not conversation_ids:
        return {}

    rows = (
        db.query(SocialConversationMember)
        .filter(SocialConversationMember.conversation_id.in_(conversation_ids))
        .all()
    )

    out: dict[int, list[int]] = {}

    for row in rows:
        out.setdefault(row.conversation_id, []).append(row.user_id)

    return out


def list_conversations(user: User, db: Session) -> dict:
    """The caller's threads, newest activity first, with unread counts."""
    memberships = (
        db.query(SocialConversationMember)
        .filter(SocialConversationMember.user_id == user.id)
        .all()
    )

    if not memberships:
        return {"conversations": [], "total": 0, "unread_total": 0}

    by_conversation = {m.conversation_id: m for m in memberships}
    ids = list(by_conversation)

    conversations = (
        db.query(SocialConversation)
        .filter(SocialConversation.id.in_(ids))
        .order_by(
            SocialConversation.last_message_at.desc().nullslast(),
            SocialConversation.id.desc(),
        )
        .all()
    )

    members = _members_of(ids, db)

    other_ids = {
        uid
        for conversation_id in ids
        for uid in members.get(conversation_id, [])
        if uid != user.id
    }

    people = actor_map(other_ids, db)

    # The last message of each thread, one query for all of them.
    last_rows = (
        db.query(SocialMessage)
        .filter(SocialMessage.conversation_id.in_(ids))
        .order_by(SocialMessage.conversation_id, SocialMessage.created_at.desc())
        .all()
    )

    last_by_conversation: dict[int, SocialMessage] = {}

    for row in last_rows:
        last_by_conversation.setdefault(row.conversation_id, row)

    result = []
    unread_total = 0

    for conversation in conversations:
        membership = by_conversation[conversation.id]
        participants = [
            people[uid]
            for uid in members.get(conversation.id, [])
            if uid != user.id and uid in people
        ]

        unread_query = (
            db.query(func.count(SocialMessage.id))
            .filter(SocialMessage.conversation_id == conversation.id)
            .filter(SocialMessage.sender_user_id != user.id)
        )

        if membership.last_read_at is not None:
            unread_query = unread_query.filter(
                SocialMessage.created_at > membership.last_read_at
            )

        unread = int(unread_query.scalar() or 0)
        unread_total += unread

        last = last_by_conversation.get(conversation.id)

        result.append(
            {
                "id": conversation.id,
                # A 1:1 thread has exactly one. The list is what leaves room
                # for group conversations without changing this shape.
                "participants": participants,
                "last_message": (
                    {
                        "body": last.body,
                        "created_at": last.created_at,
                        "from_me": last.sender_user_id == user.id,
                    }
                    if last
                    else None
                ),
                "last_message_at": conversation.last_message_at,
                "unread_count": unread,
            }
        )

    return {
        "conversations": result,
        "total": len(result),
        "unread_total": unread_total,
    }


def start_conversation(user: User, other_user_id: int, db: Session) -> dict:
    """Open (or reopen) a direct thread with one colleague.

    Idempotent: if a 1:1 thread with exactly these two people exists it is
    returned rather than duplicated, so Message from three different screens
    lands in the same conversation.
    """
    if other_user_id == user.id:
        raise SocialError("You cannot start a conversation with yourself.", "self_message")

    other = db.query(User).filter(User.id == other_user_id).first()

    if other is None or other.role_id not in INTERNAL_ROLES or not other.is_active:
        raise SocialError("That person is not in the SmartHR directory.", "not_found")

    mine = {
        m.conversation_id
        for m in db.query(SocialConversationMember)
        .filter(SocialConversationMember.user_id == user.id)
        .all()
    }

    theirs = {
        m.conversation_id
        for m in db.query(SocialConversationMember)
        .filter(SocialConversationMember.user_id == other_user_id)
        .all()
    }

    shared = mine & theirs

    if shared:
        members = _members_of(list(shared), db)

        for conversation_id in sorted(shared):
            # Only a thread that is exactly these two people; a group that
            # happens to contain both is a different conversation.
            if len(members.get(conversation_id, [])) == 2:
                return conversation_detail(user, conversation_id, db)

    conversation = SocialConversation(created_by_user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    db.add(
        SocialConversationMember(
            conversation_id=conversation.id,
            user_id=user.id,
            last_read_at=datetime.utcnow(),
        )
    )
    db.add(
        SocialConversationMember(
            conversation_id=conversation.id,
            user_id=other_user_id,
        )
    )
    db.commit()

    return conversation_detail(user, conversation.id, db)


def conversation_detail(user: User, conversation_id: int, db: Session) -> dict:
    conversation = conversation_for_member(conversation_id, user, db)

    if conversation is None:
        raise SocialError("That conversation does not exist.", "not_found")

    members = _members_of([conversation_id], db).get(conversation_id, [])
    people = actor_map([uid for uid in members if uid != user.id], db)

    return {
        "id": conversation.id,
        "participants": [people[uid] for uid in members if uid in people],
        "created_at": conversation.created_at,
        "last_message_at": conversation.last_message_at,
    }


def list_messages(
    user: User,
    conversation_id: int,
    db: Session,
    *,
    limit: int = 100,
) -> dict:
    """The messages in a thread the caller belongs to, and mark it read.

    Reading the thread is what clears its unread count, which is why this is
    the one GET in the module that writes: it moves the caller's own
    `last_read_at`, and nobody else's.
    """
    conversation = conversation_for_member(conversation_id, user, db)

    if conversation is None:
        raise SocialError("That conversation does not exist.", "not_found")

    rows = (
        db.query(SocialMessage)
        .filter(SocialMessage.conversation_id == conversation_id)
        .order_by(SocialMessage.created_at.desc(), SocialMessage.id.desc())
        .limit(min(limit, 500))
        .all()
    )

    rows.reverse()

    people = actor_map([r.sender_user_id for r in rows], db)

    membership = (
        db.query(SocialConversationMember)
        .filter(SocialConversationMember.conversation_id == conversation_id)
        .filter(SocialConversationMember.user_id == user.id)
        .first()
    )

    if membership is not None:
        membership.last_read_at = datetime.utcnow()
        db.commit()

    return {
        "conversation": conversation_detail(user, conversation_id, db),
        "messages": [
            {
                "id": r.id,
                "sender": people.get(r.sender_user_id),
                "body": r.body,
                "created_at": r.created_at,
                "from_me": r.sender_user_id == user.id,
            }
            for r in rows
        ],
        "total": len(rows),
    }


def send_message(user: User, conversation_id: int, body: str, db: Session) -> dict:
    conversation = conversation_for_member(conversation_id, user, db)

    if conversation is None:
        raise SocialError("That conversation does not exist.", "not_found")

    body = (body or "").strip()

    if not body:
        raise SocialError("A message needs something in it.", "empty")

    if len(body) > MAX_MESSAGE_CHARS:
        raise SocialError(
            f"A message must be {MAX_MESSAGE_CHARS} characters or fewer.",
            "too_long",
        )

    now = datetime.utcnow()

    message = SocialMessage(
        conversation_id=conversation_id,
        sender_user_id=user.id,
        body=body,
        created_at=now,
    )

    db.add(message)

    # Written in the same transaction as the message it describes, so the
    # conversation list can never sort by a timestamp that does not match.
    conversation.last_message_at = now

    db.commit()
    db.refresh(message)

    me = actor(user.id, db) or {}

    for uid in _members_of([conversation_id], db).get(conversation_id, []):
        if uid != user.id:
            notify(
                db,
                uid,
                NOTIFY_MESSAGE,
                "New message",
                f"{me.get('name', 'A colleague')} sent you a message on the Social Hub.",
            )

    return {
        "id": message.id,
        "sender": me,
        "body": message.body,
        "created_at": message.created_at,
        "from_me": True,
    }


# ---------------------------------------------------------------------------
# The hub's own summary
# ---------------------------------------------------------------------------

def hub_status(user: User, db: Session) -> dict:
    """What the Social Hub can tell the caller about itself.

    Reports real counts and is honest about the directory: `directory_size` is
    how many colleagues have an account they could answer from, which on a
    fresh SmartHR is a small number, and the UI says so rather than implying a
    populated network.
    """
    counts = connection_counts(user.id, db)

    directory_query = (
        db.query(func.count(User.id))
        .filter(User.role_id.in_(INTERNAL_ROLES))
        .filter(User.is_active.is_(True))
    )

    # Counted the same way the list is filtered, so the rail's "colleagues"
    # figure is the number of people the People page will actually show.
    if hides_test_accounts():
        directory_query = directory_query.filter(
            func.lower(User.email).notlike(f"%{TEST_ACCOUNT_DOMAIN}")
        )

    directory = directory_query.scalar() or 0

    unread = list_conversations(user, db)["unread_total"]

    unread_notifications = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user.id)
        .filter(Notification.type.in_(SOCIAL_NOTIFICATION_TYPES))
        .filter(Notification.is_read.is_(False))
        .scalar()
        or 0
    )

    return {
        "me": actor(user.id, db),
        "connections": counts["accepted"],
        "pending_requests": counts["pending_incoming"],
        "unread_messages": unread,
        "unread_notifications": int(unread_notifications),
        # Excludes the caller, so it reads as "colleagues", not "accounts".
        "directory_size": max(int(directory) - 1, 0),
        "posts": db.query(func.count(SocialPost.id)).scalar() or 0,
        "active_stories": (
            db.query(func.count(SocialStory.id))
            .filter(SocialStory.expires_at > datetime.utcnow())
            .scalar()
            or 0
        ),
    }
