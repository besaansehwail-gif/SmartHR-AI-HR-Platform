from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import Notification, User
from app.dependencies import require_roles
from app.routers.auth import get_current_user
from app.routers.interviews import describe_user


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str | None = None
    # Defaults to the caller when omitted; notifications.user_id is NOT NULL.
    user_id: int | None = None


class NotificationReadUpdate(BaseModel):
    is_read: bool = True


def notification_to_dict(notification, db):
    user = (
        db.query(User)
        .filter(User.id == notification.user_id)
        .first()
    )

    user_name, user_role = describe_user(user, db)

    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "user_email": user.email if user else None,
        "user_name": user_name,
        "user_role": user_role,
        "title": notification.title,
        "message": notification.message,
        "type": notification.type,
        "is_read": notification.is_read,
        "created_at": notification.created_at,
    }


def get_notification_or_404(notification_id: int, db: Session) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found"
        )

    return notification


def assert_can_touch(notification, current_user: User):
    """A notification belongs to one user. Admin (1) and HR (2) may act on
    any row; everyone else only on their own."""
    if current_user.role_id in (1, 2):
        return

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to modify this notification"
        )


# =========================
# Recipient picker
#
# Declared before /{notification_id} so the literal path wins the match.
# notifications.user_id is a FK to users, and /users/ is Admin-only.
# =========================

@router.get("/recipients")
def get_recipients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )

    result = []

    for user in users:
        name, role = describe_user(user, db)

        result.append({
            "id": user.id,
            "email": user.email,
            "name": name,
            "role": role,
        })

    return result


# =========================
# Mark all of the caller's notifications as read
#
# Also declared before /{notification_id}.
# =========================

@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .filter(Notification.is_read.is_(False))
        .all()
    )

    for notification in notifications:
        notification.is_read = True

    db.commit()

    return {
        "updated": len(notifications),
        "user_id": current_user.id,
    }


# =========================
# Get Notifications
#
# Scoped to the caller by default, which is what the bell and the per-role
# notification pages want. Admin/HR may request the whole table.
# =========================

@router.get("/")
def get_notifications(
    scope: str = Query("mine", pattern="^(mine|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Notification)

    if scope == "all":
        if current_user.role_id not in (1, 2):
            raise HTTPException(
                status_code=403,
                detail="Only Admin and HR may list all notifications"
            )
    else:
        query = query.filter(Notification.user_id == current_user.id)

    notifications = (
        query
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )

    return [
        notification_to_dict(notification, db)
        for notification in notifications
    ]


# =========================
# Get One Notification
# =========================

@router.get("/{notification_id}")
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = get_notification_or_404(notification_id, db)
    assert_can_touch(notification, current_user)

    return notification_to_dict(notification, db)


# =========================
# Create Notification
# =========================

@router.post("/")
def create_notification(
    data: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2))
):
    if not data.title.strip():
        raise HTTPException(
            status_code=400,
            detail="Notification title is required"
        )

    if not data.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Notification message is required"
        )

    user_id = data.user_id or current_user.id

    recipient = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if recipient is None:
        raise HTTPException(
            status_code=400,
            detail=f"Recipient (user) {user_id} does not exist"
        )

    notification = Notification(
        user_id=user_id,
        title=data.title.strip(),
        message=data.message.strip(),
        type=(data.type or None)
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    return notification_to_dict(notification, db)


# =========================
# Mark Read / Unread
# =========================

@router.patch("/{notification_id}/read")
def set_notification_read(
    notification_id: int,
    data: NotificationReadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = get_notification_or_404(notification_id, db)
    assert_can_touch(notification, current_user)

    notification.is_read = data.is_read

    db.commit()
    db.refresh(notification)

    return notification_to_dict(notification, db)
