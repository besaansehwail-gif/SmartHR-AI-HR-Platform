from datetime import date, datetime

from sqlalchemy import (
    String,
    Text,
    Date,
    DateTime,
    Time,
    Boolean,
    Float,
    Integer,
    SmallInteger,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# =========================
# Roles
# =========================

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


# =========================
# Users
# =========================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =========================
# Departments
# =========================

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


# =========================
# Positions
# =========================

class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"),
        nullable=False
    )


# =========================
# Employees
# =========================

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        unique=True
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    phone: Mapped[str | None] = mapped_column(String(30))

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id")
    )

    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id")
    )

    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id")
    )

    hire_date: Mapped[date | None] = mapped_column(Date)

    # Celebration dates (migrations/2026-09-27_employee_celebration_dates.sql).
    # All optional: NULL means "not recorded", and the AI Employee Celebration
    # workflow then reports that occasion as not recorded for this person
    # rather than guessing. birth_date recurs yearly (like hire_date); the
    # other four are one-off events celebrated on the date itself.
    birth_date: Mapped[date | None] = mapped_column(Date)
    promotion_date: Mapped[date | None] = mapped_column(Date)
    graduation_date: Mapped[date | None] = mapped_column(Date)
    wedding_date: Mapped[date | None] = mapped_column(Date)
    new_baby_date: Mapped[date | None] = mapped_column(Date)

    employment_status: Mapped[str] = mapped_column(
        String(30),
        default="active"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Jobs
# =========================

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(30),
        default="open"
    )

    # What kind of opportunity this is. One column rather than a second table:
    # an internship is a job row with a different employment_type, and the
    # applicant-facing Opportunities section filters on it.
    employment_type: Mapped[str] = mapped_column(
        String(30),
        default="full_time"
    )

    location: Mapped[str | None] = mapped_column(String(150))

    deadline: Mapped[date | None] = mapped_column(Date)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Candidates
# =========================

class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The account this candidate signs in with, when they are a self-service
    # Applicant. Nullable and unique, exactly like employees.user_id: every
    # candidate HR keyed in by hand has no account and stays valid, and one
    # account is one applicant.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        unique=True
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    phone: Mapped[str | None] = mapped_column(String(30))
    location: Mapped[str | None] = mapped_column(String(150))

    # Comma-separated, typed by the applicant on their own profile. Never
    # written from a model's output without the applicant accepting it first,
    # which is what keeps AI matching free of invented skills.
    skills: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Applications
# =========================

class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"),
        nullable=False
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="applied"
    )

    applied_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# CVs
# =========================

class CV(Base):
    __tablename__ = "cvs"

    id: Mapped[int] = mapped_column(primary_key=True)

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"),
        nullable=False
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Interviews
# =========================

class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False
    )

    interviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    location: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(
        String(30),
        default="scheduled"
    )

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Attendance
# =========================

class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    check_in: Mapped[datetime | None] = mapped_column(Time)
    check_out: Mapped[datetime | None] = mapped_column(Time)

    status: Mapped[str] = mapped_column(
        String(30),
        default="present"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Leave Requests
# =========================

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False
    )

    leave_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    reason: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending"
    )

    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Trainings
# =========================

class Training(Base):
    __tablename__ = "trainings"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(150))
    duration_hours: Mapped[int | None] = mapped_column(Integer)

    # 'training' or 'free_course' - what separates the two applicant-facing
    # learning sections. url is how an external applicant reaches a course:
    # they cannot be enrolled through employee_trainings, which keys on
    # employees.id.
    category: Mapped[str] = mapped_column(
        String(30),
        default="training"
    )

    url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Employee Trainings
# =========================

class EmployeeTraining(Base):
    __tablename__ = "employee_trainings"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False
    )

    training_id: Mapped[int] = mapped_column(
        ForeignKey("trainings.id"),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="assigned"
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


# =========================
# Performance Reviews
# =========================

class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False
    )

    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    feedback: Mapped[str | None] = mapped_column(Text)

    review_date: Mapped[date] = mapped_column(
        Date,
        default=date.today
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Notifications
# =========================

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    type: Mapped[str | None] = mapped_column(String(50))

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Audit Logs
# =========================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    entity_type: Mapped[str | None] = mapped_column(
        String(100)
    )

    entity_id: Mapped[int | None] = mapped_column(Integer)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Social Hub
#
# Ten additive tables. Nothing above this line was changed: `employees` did
# not gain a bio, an avatar or a skills column, and `notifications` is reused
# as it is - a Social Hub notification is an ordinary notifications row whose
# `type` starts with `social_`, so it appears in the existing bell without the
# bell being taught about this feature.
#
# **Every table keys on `users.id`, not `employees.id`.** `employees.user_id`
# is nullable, so keying on employees would lock out accounts without a linked
# employee row before a handler ran. The participant in a social network is
# the signed-in account; the person's name,
# department and position are still read from the linked employees row on
# every response, falling back to the email exactly as `describe_user()`
# already does. Applicants are excluded by `require_staff` on the router, not
# by the choice of key.
#
# See migrations/2026-09-16_social_hub.sql for the constraints - several rules
# the API would otherwise have to remember are enforced there instead.
# =========================

class SocialProfile(Base):
    """What a person chooses to say about themselves, 1:1 with a users row.

    Separate from `employees` because these are self-authored, presentational
    fields on a social surface, not HR master data - and because `employees`
    is read by nine other features that have nothing to do with this one.
    """

    __tablename__ = "social_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        unique=True
    )

    headline: Mapped[str | None] = mapped_column(String(150))
    bio: Mapped[str | None] = mapped_column(Text)

    #: Free text typed by the employee, the same shape as `candidates.skills`
    #: on the applicant side - so a later People Search reads one column that
    #: contains only words a human wrote.
    skills: Mapped[str | None] = mapped_column(Text)

    interests: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(150))

    #: Relative paths under uploads/social/, served only through
    #: GET /social/media/{name}, which is itself behind require_staff.
    avatar_path: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class SocialPost(Base):
    """One post on the feed."""

    __tablename__ = "social_posts"

    id: Mapped[int] = mapped_column(primary_key=True)

    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text)

    #: 'company' or 'department'. Neither is a permission - it is which feed
    #: filter the post answers to.
    audience: Mapped[str] = mapped_column(String(20), default="company")

    #: The author's department *as it was when they posted*, resolved once
    #: rather than joined on every read. NULL when the account has no
    #: employees row, which is legitimate.
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    #: Set only when the author actually edits, so "edited" is never implied
    #: by a timestamp that merely moved.
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)

    #: 'published' | 'pending_review' | 'removed'. The visibility flag the feed
    #: filters on; the moderation *record* lives in
    #: `social_moderation_reviews`. Defaults to published, so a row written by
    #: any path that does not know about moderation is visible exactly as
    #: before.
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="published",
    )


class SocialComment(Base):
    __tablename__ = "social_comments"

    id: Mapped[int] = mapped_column(primary_key=True)

    post_id: Mapped[int] = mapped_column(
        ForeignKey("social_posts.id"),
        nullable=False
    )

    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    #: See SocialPost.moderation_status.
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="published",
    )


class SocialReaction(Base):
    """One person's reaction to one post.

    UNIQUE (post_id, user_id) in the database, so liking twice cannot create a
    second row and a like count is a COUNT that cannot be inflated.
    """

    __tablename__ = "social_reactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    post_id: Mapped[int] = mapped_column(
        ForeignKey("social_posts.id"),
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    #: 'like' is the only value V1 writes. The column exists so a richer set
    #: later is a new value rather than a new table.
    kind: Mapped[str] = mapped_column(String(20), default="like")

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class SocialStory(Base):
    """A story, which stops being visible 24 hours after it is posted.

    `expires_at` is stored rather than derived: it makes the active-story query
    one indexed comparison, and means changing the window later cannot
    retroactively resurrect stories published under the old one.
    """

    __tablename__ = "social_stories"

    id: Mapped[int] = mapped_column(primary_key=True)

    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    caption: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    #: See SocialPost.moderation_status. Only the caption is moderated - there
    #: is no image classifier in V1, and an image-only story is published.
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="published",
    )


class SocialStoryView(Base):
    """Seen / unseen. UNIQUE (story_id, viewer_user_id)."""

    __tablename__ = "social_story_views"

    id: Mapped[int] = mapped_column(primary_key=True)

    story_id: Mapped[int] = mapped_column(
        ForeignKey("social_stories.id"),
        nullable=False
    )

    viewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    viewed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class SocialConnection(Base):
    """A connection between two accounts, in either direction.

    The database holds **one row per pair**, forever: a unique index on
    (LEAST, GREATEST) of the two ids. So a duplicate request is refused by
    Postgres rather than by a check a handler could lose a race on, and a
    CHECK constraint makes a self-connection unstorable.

    status: pending | accepted | rejected. Disconnecting deletes the row, so a
    rejection does not block the pair forever - re-requesting revives the same
    row, swapping requester and receiver when it is the other person asking.
    """

    __tablename__ = "social_connections"

    id: Mapped[int] = mapped_column(primary_key=True)

    requester_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    receiver_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class SocialConversation(Base):
    """A message thread.

    `last_message_at` is denormalised here so the conversation list sorts
    without a correlated subquery per row; it is written in the same
    transaction as the message it describes.
    """

    __tablename__ = "social_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)


class SocialConversationMember(Base):
    """Who is in a conversation - and therefore who may read it.

    Membership is the authorisation: every message query joins through this
    table filtered on the caller, so reading somebody else's thread is a
    missing row rather than a permission check that could be forgotten.

    `last_read_at` is the per-participant read marker an unread count needs,
    and is the reason messaging is three tables rather than one
    (from, to, body) table with nowhere to put it.
    """

    __tablename__ = "social_conversation_members"

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("social_conversations.id"),
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    last_read_at: Mapped[datetime | None] = mapped_column(DateTime)


class SocialMessage(Base):
    __tablename__ = "social_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("social_conversations.id"),
        nullable=False
    )

    sender_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# Social Hub - AI Moderation
# =========================

class SocialModerationReview(Base):
    """One moderation record for one piece of Social Hub content.

    The model's decision and the human's decision live on the same row,
    because "what the AI said" and "what HR then did about it" are one event
    in the life of one post - and keeping them together is what makes the
    queue answerable without a join.

    UNIQUE (content_type, content_id) in the database, so one post can never
    acquire two queue entries. That is a constraint rather than a check in the
    service for the same reason `social_reactions` has one: a repeated request
    is refused by Postgres instead of by a guard that could lose a race.

    Nothing here stores the content itself. The words stay in
    `social_posts` / `social_comments` / `social_stories`, so editing a post
    cannot leave a stale copy sitting in the moderation queue.
    """

    __tablename__ = "social_moderation_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: 'post' | 'comment' | 'story'
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_id: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Denormalised from the content row: it cannot change for a given piece
    #: of content, and carrying it means listing the queue does not join three
    #: different content tables to find out who wrote each item.
    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    #: 'allow' | 'flag' | 'unavailable'. `unavailable` is a real outcome, not
    #: a swallowed error: moderation was required and could not run, which is
    #: why the content is in the queue rather than on the feed.
    ai_decision: Mapped[str] = mapped_column(String(20), nullable=False)

    #: Comma-separated tokens from the fixed taxonomy; empty unless flagged.
    categories: Mapped[str | None] = mapped_column(Text)

    #: 'low' | 'medium' | 'high'. NULL when the model did not run.
    severity: Mapped[str | None] = mapped_column(String(10))

    #: 0.0 - 1.0. NULL when the model did not run.
    confidence: Mapped[float | None] = mapped_column(Float)

    #: Internal. Never sent to the content's author.
    reason: Mapped[str | None] = mapped_column(Text)

    #: Why the model could not be used: 'llm_not_configured' | 'llm_error' |
    #: 'invalid_output' | 'disabled'.
    error_code: Mapped[str | None] = mapped_column(String(40))

    #: 'pending' | 'approved' | 'removed'
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending"
    )

    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )

    #: 'approved' | 'removed' - what the human chose, kept beside `status` so
    #: the record says a person decided rather than the queue having moved on
    #: its own.
    reviewer_decision: Mapped[str | None] = mapped_column(String(20))

    reviewer_note: Mapped[str | None] = mapped_column(Text)

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================
# AI Employee Celebration
# =========================

class CelebrationDraft(Base):
    """One celebration the scheduled workflow prepared, awaiting HR.

    The workflow used to hand its result straight back in the HTTP response HR
    had asked for. A scheduled job has nobody to answer, so what it produces
    has to be stored - and this is the only thing the celebration feature
    writes anywhere.

    **A draft is not a post.** It has no author, it is not in `social_posts`,
    and nothing renders it in the feed. It becomes a post only when HR presses
    Post, which calls `social_service.create_post()` - the ordinary path, with
    its moderation call and its audit row - and `post_id` is then the evidence
    of what reached the feed.

    `UNIQUE (employee_id, occasion, occasion_date)` is the duplicate
    protection: a daily job that runs twice cannot produce two drafts for the
    same person's same anniversary, and Postgres enforces that rather than a
    handler remembering to.
    """

    __tablename__ = "celebration_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    #: What the Occasion Agent decided, and the date it decided it for.
    occasion: Mapped[str] = mapped_column(String(30), nullable=False)
    occasion_date: Mapped[date] = mapped_column(Date, nullable=False)
    years: Mapped[int | None] = mapped_column(Integer)

    #: Kept even when the Review Agent rejected it - "the AI tried and could
    #: not produce something publishable" is a different finding from "nothing
    #: happened", and HR should be able to tell them apart.
    message: Mapped[str | None] = mapped_column(Text)
    review_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text)
    review_suggestions: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))

    #: pending | posted | dismissed | no_occasion
    status: Mapped[str] = mapped_column(String(20), default="pending")

    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_posts.id", ondelete="SET NULL")
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class InterviewQuestion(Base):
    """The AI Interview Question Bank (migrations/2026-09-26_ai_interview_question_bank.sql).

    The controlled source of the interview's MAIN questions: the interview
    controller asks these, in `position` order, and GPT-4o never invents one.
    A `follow_up` row belongs to one `main` row through `parent_question_id`
    (a CHECK constraint enforces the pairing); follow-ups are stored now and
    used in a later phase. There is no delete - a question is deactivated.
    """

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_text_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: general | behavioral | technical | situational | role_specific
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    #: easy | medium | hard
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    #: main | follow_up
    question_type: Mapped[str] = mapped_column(String(20), nullable=False, default="main")
    #: What a good answer shows. For HR and later analysis - never spoken.
    evaluation_focus: Mapped[str | None] = mapped_column(Text)
    parent_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_questions.id")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiInterviewSession(Base):
    """AI Interview (Phase 4): the interview one LiveKit voice room belongs to.

    Written by `POST /ai-interview/session` after ownership is checked, read by
    `POST /ai-interview/agent/plan` to resolve room -> interview -> application
    -> job for the agent worker. A binding, not a record of the conversation:
    nothing said in the room is stored here.
    """

    __tablename__ = "ai_interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    #: The agent must ask for its context before this. Equal to the
    #: applicant's LiveKit join window, so a stale room resolves to nothing.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)


class AiInterviewAnswer(Base):
    """AI Interview (Phase 7): one ACCEPTED applicant answer, as it was said.

    Written only by `POST /ai-interview/agent/answers` (the agent worker, via
    its room-bound agent token), after the backend has resolved room ->
    session -> interview and matched the question against the Question Bank
    plan. Never updated: a retried request for the same (session, sequence)
    finds this row instead of writing another. `question_text` is the bank's
    text at the time of the interview, copied from the bank row - not from the
    worker. See migrations/2026-09-27_ai_interview_answers.sql.
    """

    __tablename__ = "ai_interview_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("interview_questions.id"), nullable=False)
    #: 1-based, as the applicant heard it ("Question N of M").
    question_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_text: Mapped[str] = mapped_column(String(500), nullable=False)
    #: 1-based order of the answer within its session.
    sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    answer_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The accepted STT transcript, exactly as the worker accepted it.
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: UTC, when the worker accepted the turn.
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    #: UTC, when the backend stored it.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AiInterviewAnswerAnalysis(Base):
    """AI Interview (Phase 7): GPT-4o's structured reading of one answer.

    Derived and replaceable (it can be re-run); the answer itself is not.
    `analysis` holds the validated schema of `app/ai/interview_analysis.py`,
    which has no field for a score, a match or a hiring decision.
    """

    __tablename__ = "ai_interview_answer_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("ai_interview_answers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # completed | failed
    #: none_as_null: a failed analysis stores SQL NULL, not JSON null (the
    #: payload CHECK constraint tells the two apart).
    analysis: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    analysed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
