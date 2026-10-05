"""Audit trail helper.

The audit_logs table is deliberately narrow - it holds exactly
(id, user_id, action, entity_type, entity_id, timestamp) and nothing else.
There is no details/ip_address/status/metadata column, so everything a page
shows beyond those six values has to be derived on read, never stored.

This module lives outside app/routers/ on purpose: almost every router calls
record_audit(), and app/routers/audit_logs.py in turn imports describe_user()
from app/routers/interviews.py. Keeping the writer here is what stops that
from becoming an import cycle.
"""

from app.models import AuditLog


# =========================
# Action vocabulary
#
# action is varchar(100). These are the only tokens SmartHR writes, so the
# frontend can map each one onto the AuditActionType badge it already has.
# =========================

ACTION_CREATE = "CREATE"
ACTION_UPDATE = "UPDATE"
ACTION_DELETE = "DELETE"
ACTION_APPROVE = "APPROVE"
ACTION_REJECT = "REJECT"
ACTION_STATUS_CHANGE = "STATUS_CHANGE"
ACTION_ASSIGN = "ASSIGN"
ACTION_ACTIVATE = "ACTIVATE"
ACTION_DEACTIVATE = "DEACTIVATE"
ACTION_LOGIN = "LOGIN"
ACTION_LOGIN_FAILED = "LOGIN_FAILED"
ACTION_EXPORT = "EXPORT"


# =========================
# Entity vocabulary
#
# entity_type is varchar(100) and free text. These labels match the table the
# row lives in, so entity_id can always be resolved back to a real record.
# =========================

ENTITY_EMPLOYEE = "Employee"
ENTITY_JOB = "Job"
ENTITY_CANDIDATE = "Candidate"
ENTITY_CV = "CV"
ENTITY_APPLICATION = "Application"
ENTITY_INTERVIEW = "Interview"
ENTITY_ATTENDANCE = "Attendance"
ENTITY_LEAVE_REQUEST = "LeaveRequest"
ENTITY_TRAINING = "Training"
ENTITY_EMPLOYEE_TRAINING = "EmployeeTraining"
ENTITY_PERFORMANCE_REVIEW = "PerformanceReview"
ENTITY_USER = "User"
ENTITY_DEPARTMENT = "Department"
ENTITY_POSITION = "Position"
ENTITY_AUDIT_LOG = "AuditLog"
ENTITY_SESSION = "Session"
# The Social Hub. Only posts are audited: a post is content an organisation may
# later need to account for, and creating, editing and deleting one is a
# deliberate act. Likes, comments, stories, connections and messages are not -
# an audit row per like would bury the trail in noise, and a private message
# between two colleagues is not an administrative event.
ENTITY_SOCIAL_POST = "SocialPost"

# AI moderation. Three events are auditable, and they are exactly the three a
# company may later have to account for: content was held for review, and a
# named person then approved or removed it. The model's own classification is
# not a separate event - it is why the STATUS_CHANGE row exists, and the
# detail lives on `social_moderation_reviews`, which is where a reviewer would
# look anyway.
#
# `audit_logs` has six columns and no `details`, so the row says *that* a
# moderation decision happened and points at the review id. That is the same
# discipline every other entity here follows.
ENTITY_SOCIAL_MODERATION = "SocialModeration"

# The AI Interview Question Bank. Creating, editing, activating and
# deactivating a question are audited: the bank decides what applicants are
# asked, so who changed it and when is exactly what an organisation may need
# to account for.
ENTITY_INTERVIEW_QUESTION = "InterviewQuestion"

# An AI Interview session whose agent actually STARTED (Phase 10). Exactly one
# STATUS_CHANGE row per session, written with no user in the same transaction
# that moves the interview to in_progress - never through `record_audit`,
# because this row is also the record the attempt limit counts
# (`interview_progress_service.started_attempts`) and must not be lost.
ENTITY_AI_INTERVIEW_SESSION = "AiInterviewSession"


def record_audit(
    db,
    user,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    """Write one audit row for a system action.

    Call this *after* the business write has been committed. The audit trail
    is secondary to the operation it describes, so a failure here is swallowed
    rather than allowed to surface as a 500 on a write that already succeeded.

    user is the authenticated User resolved from the JWT, or None for actions
    with no caller (audit_logs.user_id is nullable for exactly that reason).
    """
    try:
        db.add(
            AuditLog(
                user_id=getattr(user, "id", None),
                action=action[:100],
                entity_type=entity_type[:100] if entity_type else None,
                entity_id=entity_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
