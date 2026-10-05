"""The Social Hub - SmartHR's internal employee network.

    GET    /social/status                      my hub summary
    GET    /social/feed                        paginated feed
    POST   /social/posts                       create a post (multipart)
    GET    /social/posts/{id}                  one post
    PUT    /social/posts/{id}                  edit my own post
    DELETE /social/posts/{id}                  delete my own post
    GET    /social/posts/{id}/comments         comments on a post
    POST   /social/posts/{id}/comments         add a comment
    DELETE /social/comments/{id}               delete my own comment
    POST   /social/posts/{id}/like             like (idempotent)
    DELETE /social/posts/{id}/like             unlike
    GET    /social/stories                     active stories, grouped
    POST   /social/stories                     post a story (multipart)
    GET    /social/stories/{id}                one story
    POST   /social/stories/{id}/view           mark it seen
    DELETE /social/stories/{id}                delete my own story
    GET    /social/people                      directory search
    GET    /social/people/{user_id}            one person's profile
    GET    /social/connections                 mine, incoming, outgoing
    POST   /social/connections/{user_id}       request a connection
    POST   /social/connections/{id}/accept     accept one addressed to me
    POST   /social/connections/{id}/reject     reject one addressed to me
    DELETE /social/connections/{id}            disconnect / withdraw
    GET    /social/conversations               my threads
    POST   /social/conversations               open a thread with a colleague
    GET    /social/conversations/{id}/messages read a thread I am in
    POST   /social/conversations/{id}/messages send into it
    GET    /social/profile/me                  my own profile
    PUT    /social/profile/me                  edit my own profile
    POST   /social/profile/me/avatar           replace my avatar (multipart)
    GET    /social/profile/{user_id}           somebody else's profile
    GET    /social/notifications               my social notifications
    POST   /social/notifications/{id}/read     mark one read
    GET    /social/media/{name}                an uploaded image

**RBAC is the router's own dependency, not a convention.** Every route below
carries `require_staff` (roles 1-4), declared once on the `APIRouter` so a
route added later cannot be left unguarded by forgetting it. An Applicant
(role 5) receives 403 from every one of them, including the media route -
hiding the nav entry in the frontend is not what keeps them out.

**Ownership is enforced in `social_service`, inside the query.** This file does
not re-check it; it maps the service's error codes onto status codes. A row
belonging to somebody else comes back as `not_found` and is answered 404 rather
than 403, following `application_for_candidate()` and
`interview_for_candidate()`, so ids cannot be probed.

There is no AI here. No endpoint calls a model, and nothing in this module
imports `app/ai/` or `app/mcp/`.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import (
    ACTION_APPROVE,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_REJECT,
    ACTION_UPDATE,
    ENTITY_SOCIAL_MODERATION,
    ENTITY_SOCIAL_POST,
    record_audit,
)
from app.dependencies import get_db, require_roles, require_staff
from app.models import User
from app.services import social_moderation_service, social_service
from app.social_storage import ImageError, resolve_media, store_image

router = APIRouter(
    prefix="/social",
    tags=["Social Hub"],
    # Roles 1-4. One declaration, so every route in this file inherits it and
    # a new route cannot be added unguarded.
    dependencies=[Depends(require_staff)],
)


#: service error code -> HTTP status. Anything unlisted is a 422, which is the
#: right default for "SmartHR will not do that with this input".
_STATUS = {
    "not_found": 404,
    "already_connected": 409,
    "already_pending": 409,
    "already_answered": 409,
    "conflict": 409,
    "expired": 410,
    "file_too_large": 413,
}


def _fail(error: social_service.SocialError):
    raise HTTPException(
        status_code=_STATUS.get(error.code, 422),
        detail=str(error),
    )


async def _read_image(image: UploadFile | None) -> str | None:
    """Store an uploaded image, or return None when none was sent.

    The type is detected from the file's signature inside `social_storage`, so
    a renamed executable is refused here rather than written to disk.
    """
    if image is None or not image.filename:
        return None

    data = await image.read()

    try:
        return store_image(data)
    except ImageError as error:
        raise HTTPException(
            status_code=_STATUS.get(error.code, 422),
            detail=str(error),
        )


# =========================
# Status
# =========================

@router.get("/status")
def hub_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.hub_status(current_user, db)


# =========================
# Media
#
# Declared before the parameterised routes below that could otherwise shadow
# it, and guarded like everything else: an uploaded photograph is only
# reachable by an internal user, never by an Applicant and never anonymously.
# The name is validated against a pattern before it becomes a path, so a
# traversal attempt is a 404 rather than a file read.
# =========================

@router.get("/media/{name}")
def get_media(name: str):
    found = resolve_media(name)

    if found is None:
        raise HTTPException(status_code=404, detail="That image does not exist")

    path, media_type = found

    return FileResponse(path, media_type=media_type)


# =========================
# Feed
# =========================

@router.get("/feed")
def get_feed(
    scope: str = Query("all", pattern="^(all|department|following|company)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(social_service.DEFAULT_PAGE_SIZE, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.feed(
        current_user,
        db,
        scope=scope,
        page=page,
        page_size=page_size,
    )


# =========================
# Posts
#
# Multipart rather than JSON because a post may carry an image, and a browser
# cannot send a file in a JSON body. `content` arrives as a form field.
# =========================

@router.post("/posts")
async def create_post(
    content: str = Form(...),
    audience: str = Form("company"),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    image_path = await _read_image(image)

    try:
        post = social_service.create_post(
            current_user,
            db,
            content=content,
            image_path=image_path,
            audience=audience,
        )
    except social_service.SocialError as error:
        _fail(error)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_SOCIAL_POST, post["id"])

    return post


@router.get("/posts/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.get_post(current_user, post_id, db)
    except social_service.SocialError as error:
        _fail(error)


class PostUpdate(BaseModel):
    content: str


@router.put("/posts/{post_id}")
def update_post(
    post_id: int,
    data: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        post = social_service.update_post(current_user, post_id, data.content, db)
    except social_service.SocialError as error:
        _fail(error)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_SOCIAL_POST, post_id)

    return post


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        result = social_service.delete_post(current_user, post_id, db)
    except social_service.SocialError as error:
        _fail(error)

    record_audit(db, current_user, ACTION_DELETE, ENTITY_SOCIAL_POST, post_id)

    return result


# =========================
# Comments
# =========================

@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.list_comments(current_user, post_id, db)
    except social_service.SocialError as error:
        _fail(error)


class CommentCreate(BaseModel):
    content: str


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.add_comment(current_user, post_id, data.content, db)
    except social_service.SocialError as error:
        _fail(error)


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.delete_comment(current_user, comment_id, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Reactions
# =========================

@router.post("/posts/{post_id}/like")
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.like_post(current_user, post_id, db)
    except social_service.SocialError as error:
        _fail(error)


@router.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.unlike_post(current_user, post_id, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Stories
# =========================

@router.get("/stories")
def get_stories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.active_stories(current_user, db)


@router.post("/stories")
async def create_story(
    caption: str = Form(""),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    image_path = await _read_image(image)

    try:
        return social_service.create_story(
            current_user,
            db,
            caption=caption,
            image_path=image_path,
        )
    except social_service.SocialError as error:
        _fail(error)


@router.get("/stories/{story_id}")
def get_story(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.get_story(current_user, story_id, db)
    except social_service.SocialError as error:
        _fail(error)


@router.post("/stories/{story_id}/view")
def view_story(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.mark_story_seen(current_user, story_id, db)
    except social_service.SocialError as error:
        _fail(error)


@router.delete("/stories/{story_id}")
def delete_story(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.delete_story(current_user, story_id, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# People
#
# `/people/suggested` is declared before `/people/{user_id}` so the literal
# path wins the match - the same ordering rule `/interviews/interviewers` and
# `/notifications/recipients` follow.
# =========================

@router.get("/people/suggested")
def get_suggestions(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return {"people": social_service.suggestions(current_user, db, limit)}


@router.get("/people")
def search_people(
    q: str = Query("", max_length=200),
    department_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.search_people(
        current_user,
        db,
        query=q,
        department_id=department_id,
        limit=limit,
    )


@router.get("/people/{user_id}")
def get_person(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.profile_view(user_id, current_user, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Connections
# =========================

@router.get("/connections")
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.list_connections(current_user, db)


@router.post("/connections/{user_id}")
def request_connection(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.request_connection(current_user, user_id, db)
    except social_service.SocialError as error:
        _fail(error)


@router.post("/connections/{connection_id}/accept")
def accept_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.respond_to_connection(
            current_user, connection_id, "accepted", db
        )
    except social_service.SocialError as error:
        _fail(error)


@router.post("/connections/{connection_id}/reject")
def reject_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.respond_to_connection(
            current_user, connection_id, "rejected", db
        )
    except social_service.SocialError as error:
        _fail(error)


@router.delete("/connections/{connection_id}")
def remove_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.remove_connection(current_user, connection_id, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Messages
# =========================

@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.list_conversations(current_user, db)


class ConversationCreate(BaseModel):
    user_id: int


@router.post("/conversations")
def start_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.start_conversation(current_user, data.user_id, db)
    except social_service.SocialError as error:
        _fail(error)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.list_messages(
            current_user, conversation_id, db, limit=limit
        )
    except social_service.SocialError as error:
        _fail(error)


class MessageCreate(BaseModel):
    body: str


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.send_message(
            current_user, conversation_id, data.body, db
        )
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Profile
#
# `/profile/me` is declared before `/profile/{user_id}` so the literal path
# wins the route match.
# =========================

@router.get("/profile/me")
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return social_service.profile_view(current_user.id, current_user, db)


class ProfileUpdate(BaseModel):
    headline: str | None = None
    bio: str | None = None
    skills: str | None = None
    interests: str | None = None
    location: str | None = None


@router.put("/profile/me")
def update_my_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        # `exclude_unset` so an omitted field is left alone rather than
        # cleared - a partial edit must not wipe what it did not mention.
        return social_service.update_my_profile(
            current_user, data.model_dump(exclude_unset=True), db
        )
    except social_service.SocialError as error:
        _fail(error)


@router.post("/profile/me/avatar")
async def set_my_avatar(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    stored = await _read_image(image)

    if stored is None:
        raise HTTPException(status_code=422, detail="No image was uploaded")

    return social_service.set_avatar(current_user, stored, db)


@router.get("/profile/{user_id}")
def get_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.profile_view(user_id, current_user, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# Notifications
#
# The existing `notifications` table, narrowed to the `social_*` types. Marking
# one read is the same row the bell marks read, so the two cannot disagree.
# =========================

@router.get("/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return {
        "notifications": social_service.list_notifications(current_user, db, limit),
    }


@router.post("/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    try:
        return social_service.mark_notification_read(current_user, notification_id, db)
    except social_service.SocialError as error:
        _fail(error)


# =========================
# AI Moderation - HR / Admin only
#
# The router-level `require_staff` admits roles 1-4. These five routes narrow
# that to roles 1-2 with their own dependency, so Manager and Employee get 403
# on the moderation surface while keeping the Social Hub itself. That is the
# same tier `/candidates/`, `/applications/` and `/cvs/` sit in: reviewing a
# colleague's flagged content is an HR act, not a management one.
#
# `require_roles` re-reads `role_id` from `users`, so a forged claim does not
# widen access here any more than it does anywhere else.
#
# Declaration order matters: the literal `/moderation/summary` is declared
# before `/moderation/{review_id}`, or "summary" would be matched as a review
# id and rejected as a bad integer - the rule `/interviews/interviewers` and
# `/hr/interviews/status` already follow.
# =========================

def _fail_moderation(error: social_moderation_service.ModerationError):
    raise HTTPException(
        status_code=_STATUS.get(error.code, 422),
        detail=str(error),
    )


class ModerationDecision(BaseModel):
    #: The reviewer's own words about why. Optional, stored, HR-only.
    note: str | None = None


@router.get("/moderation", dependencies=[Depends(require_roles(1, 2))])
def list_moderation(
    status: str = Query("pending"),
    content_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        return social_moderation_service.list_reviews(
            db,
            status=status,
            content_type=content_type,
            page=page,
            page_size=page_size,
        )
    except social_moderation_service.ModerationError as error:
        _fail_moderation(error)


@router.get("/moderation/summary", dependencies=[Depends(require_roles(1, 2))])
def moderation_summary(db: Session = Depends(get_db)):
    return social_moderation_service.summary(db)


@router.get("/moderation/{review_id}", dependencies=[Depends(require_roles(1, 2))])
def get_moderation(review_id: int, db: Session = Depends(get_db)):
    try:
        return social_moderation_service.get_review(db, review_id)
    except social_moderation_service.ModerationError as error:
        _fail_moderation(error)


@router.post("/moderation/{review_id}/approve")
def approve_moderation(
    review_id: int,
    payload: ModerationDecision | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2)),
):
    """Publish content the model held. The human decides; the model advised."""
    try:
        review = social_moderation_service.decide(
            db,
            review_id=review_id,
            reviewer=current_user,
            decision=social_moderation_service.REVIEW_APPROVED,
            note=(payload.note if payload else None),
        )
    except social_moderation_service.ModerationError as error:
        _fail_moderation(error)

    record_audit(
        db, current_user, ACTION_APPROVE, ENTITY_SOCIAL_MODERATION, review_id
    )

    return review


@router.post("/moderation/{review_id}/remove")
def remove_moderation(
    review_id: int,
    payload: ModerationDecision | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2)),
):
    """Hide content from the Social Hub.

    A status change, never a DELETE: the post, the model's classification and
    the reviewer's decision all stay readable afterwards, which is the whole
    point of holding a moderation history.
    """
    try:
        review = social_moderation_service.decide(
            db,
            review_id=review_id,
            reviewer=current_user,
            decision=social_moderation_service.REVIEW_REMOVED,
            note=(payload.note if payload else None),
        )
    except social_moderation_service.ModerationError as error:
        _fail_moderation(error)

    record_audit(
        db, current_user, ACTION_REJECT, ENTITY_SOCIAL_MODERATION, review_id
    )

    return review
