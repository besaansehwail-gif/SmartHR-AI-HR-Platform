"""Social Hub: API, RBAC and ownership tests.

    venv\\Scripts\\python.exe -m scripts.test_social_hub

It **launches its own uvicorn** on port 8041 and shuts it down afterwards, so
it needs no server running and cannot collide with the one on 8000. The HTTP
helpers, the multipart builder and the account fixtures are imported from
`scripts.test_helpers` rather than copied - there is one definition of
"sign in as a staff account" in this project and this file uses it.

What it proves, in four groups:

* **Features** - post, feed, paginate, like (twice), comment, edit, delete;
  stories including expiry; people search; connections including the duplicate
  and self cases; conversations and messages.
* **RBAC** - an Applicant is refused every route, anonymous is refused every
  route, and all four internal roles are allowed.
* **Ownership** - B cannot edit or delete A's post, cannot delete A's comment,
  cannot delete A's story, cannot read a conversation they are not in, cannot
  answer somebody else's connection request, and cannot mark another person's
  notification read. Each of those is checked to be **404, not 403**, because
  a 403 would confirm the row exists.
* **Containment** - the profile projection carries no salary, no attendance,
  no leave and no performance data, and the Social Hub writes to no HR table.

Every row it creates is deleted at the end unless `--keep` is passed.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402

PORT = 8041
BASE = f"http://127.0.0.1:{PORT}"

PASSWORD = e2e.PASSWORD

#: Four internal accounts, one per role, plus an applicant to be refused with.
#: `.test` addresses so they can never be confused with a real SmartHR account.
ALICE = "social.alice@smarthr.test"      # role 4, Employee
BOB = "social.bob@smarthr.test"          # role 4, Employee
CAROL_HR = "social.hr@smarthr.test"      # role 2, HR
DAVE_MGR = "social.manager@smarthr.test"  # role 3, Manager
EVE_ADMIN = "social.admin@smarthr.test"  # role 1, Admin
APPLICANT = "social.applicant@smarthr.test"  # role 5 - must be refused

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  FAIL  {name}{f' - {detail}' if detail else ''}")
    return bool(ok)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# A 1x1 PNG, written byte by byte rather than read from the repo: the point is
# to exercise signature detection, and an image that lives in the test is one
# nobody can delete out from under it.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


class Server:
    """A uvicorn for this test alone."""

    def __init__(self, port: int):
        self.port = port
        self._process: subprocess.Popen | None = None

    def __enter__(self) -> "Server":
        self._process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT),
            # The directory hides `@smarthr.test` fixtures in a normal
            # deployment - they are not colleagues. This test's own accounts
            # live under that domain and it asserts they are listed, so its
            # server is told to show them.
            #
            # AI moderation is switched off for the same kind of reason: this
            # suite tests the Social Hub, and with moderation on, every post
            # it creates would make a real API call - so a slow or unreachable
            # model would fail 154 checks that have nothing to do with it.
            # Moderation has its own suite, `test_social_moderation.py`, whose
            # default run is deterministic and makes no network call either.
            env={
                **os.environ,
                "SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS": "true",
                "SMARTHR_SOCIAL_MODERATION": "false",
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(80):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/", timeout=2
                ):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)

        raise SystemExit(f"The test server on port {self.port} did not start.")

    def __exit__(self, *_exc) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._process.kill()


def req(method, path, **kwargs):
    return e2e.request(method, path, **kwargs)


def user_id_of(email: str) -> int:
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


def cleanup() -> None:
    """Remove everything this test created, in FK order."""
    from app.database import SessionLocal
    from app.models import (
        Notification,
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
        User,
    )
    from sqlalchemy import or_

    db = SessionLocal()
    try:
        emails = [ALICE, BOB, CAROL_HR, DAVE_MGR, EVE_ADMIN, APPLICANT]
        ids = [
            u.id for u in db.query(User).filter(User.email.in_(emails)).all()
        ]

        if not ids:
            return

        conversation_ids = [
            m.conversation_id
            for m in db.query(SocialConversationMember)
            .filter(SocialConversationMember.user_id.in_(ids))
            .all()
        ]

        story_ids = [
            s.id
            for s in db.query(SocialStory)
            .filter(SocialStory.author_user_id.in_(ids))
            .all()
        ]

        post_ids = [
            p.id
            for p in db.query(SocialPost)
            .filter(SocialPost.author_user_id.in_(ids))
            .all()
        ]

        if story_ids:
            db.query(SocialStoryView).filter(
                SocialStoryView.story_id.in_(story_ids)
            ).delete(synchronize_session=False)
        db.query(SocialStoryView).filter(
            SocialStoryView.viewer_user_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(SocialStory).filter(
            SocialStory.author_user_id.in_(ids)
        ).delete(synchronize_session=False)

        if post_ids:
            db.query(SocialReaction).filter(
                SocialReaction.post_id.in_(post_ids)
            ).delete(synchronize_session=False)
            db.query(SocialComment).filter(
                SocialComment.post_id.in_(post_ids)
            ).delete(synchronize_session=False)
        db.query(SocialReaction).filter(
            SocialReaction.user_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(SocialComment).filter(
            SocialComment.author_user_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(SocialPost).filter(
            SocialPost.author_user_id.in_(ids)
        ).delete(synchronize_session=False)

        if conversation_ids:
            db.query(SocialMessage).filter(
                SocialMessage.conversation_id.in_(conversation_ids)
            ).delete(synchronize_session=False)
            db.query(SocialConversationMember).filter(
                SocialConversationMember.conversation_id.in_(conversation_ids)
            ).delete(synchronize_session=False)
            db.query(SocialConversation).filter(
                SocialConversation.id.in_(conversation_ids)
            ).delete(synchronize_session=False)

        db.query(SocialConnection).filter(
            or_(
                SocialConnection.requester_user_id.in_(ids),
                SocialConnection.receiver_user_id.in_(ids),
            )
        ).delete(synchronize_session=False)

        db.query(SocialProfile).filter(
            SocialProfile.user_id.in_(ids)
        ).delete(synchronize_session=False)

        db.query(Notification).filter(
            Notification.user_id.in_(ids)
        ).delete(synchronize_session=False)

        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the rows this test created in the database",
    )
    args = parser.parse_args()

    e2e.BASE = BASE

    print("SmartHR - Social Hub tests")
    print(f"Server: {BASE}\n")

    # ------------------------------------------------------------------
    section("0. Accounts")
    # ------------------------------------------------------------------
    alice_id = e2e.ensure_staff_account(ALICE, 4)
    bob_id = e2e.ensure_staff_account(BOB, 4)
    hr_id = e2e.ensure_staff_account(CAROL_HR, 2)
    mgr_id = e2e.ensure_staff_account(DAVE_MGR, 3)
    admin_id = e2e.ensure_staff_account(EVE_ADMIN, 1)

    with Server(PORT):
        applicant_token = e2e.register_applicant(APPLICANT, "Social Applicant")

        alice = e2e.login(ALICE)
        bob = e2e.login(BOB)
        hr = e2e.login(CAROL_HR)
        mgr = e2e.login(DAVE_MGR)
        admin = e2e.login(EVE_ADMIN)

        check("five internal accounts sign in",
              all([alice, bob, hr, mgr, admin]))
        check("the applicant account signs in", bool(applicant_token))

        # The baseline for section 10 is taken **here**, after the fixtures
        # exist, not at import time: registering the test applicant legitimately
        # creates a users and a candidates row, and that is the test's own
        # setup rather than something the Social Hub did.
        global EXPECTED
        EXPECTED = baseline()

        # --------------------------------------------------------------
        section("1. RBAC - who may reach the Social Hub")
        # --------------------------------------------------------------
        for label, token in (
            ("Employee", alice),
            ("HR", hr),
            ("Manager", mgr),
            ("Admin", admin),
        ):
            response = req("GET", "/social/status", token=token)
            check(f"{label} may open the Social Hub", response.ok,
                  f"{response.status}")

        # Every shape of route, not just one: a guard that is declared on the
        # router should hold for reads, writes and media alike.
        applicant_routes = [
            ("GET", "/social/status"),
            ("GET", "/social/feed"),
            ("GET", "/social/people"),
            ("GET", "/social/connections"),
            ("GET", "/social/conversations"),
            ("GET", "/social/stories"),
            ("GET", "/social/profile/me"),
            ("GET", "/social/notifications"),
            ("GET", "/social/media/x.png"),
        ]

        for method, path in applicant_routes:
            response = req(method, path, token=applicant_token)
            check(f"Applicant is refused {method} {path}", response.status == 403,
                  f"got {response.status}")

        response = req("POST", "/social/posts", token=applicant_token,
                       files={}, form={"content": "hello"})
        check("Applicant is refused POST /social/posts",
              response.status == 403, f"got {response.status}")

        for method, path in applicant_routes:
            response = req(method, path)
            check(f"anonymous is refused {method} {path}", response.status == 401,
                  f"got {response.status}")

        # --------------------------------------------------------------
        section("2. Profile")
        # --------------------------------------------------------------
        response = req("GET", "/social/profile/me", token=alice)
        check("my profile is created on first read", response.ok, f"{response.status}")
        check("my profile knows it is mine", bool(response.body.get("is_me")))
        check("an empty profile has no invented bio",
              response.body.get("bio") is None)

        response = req("PUT", "/social/profile/me", token=alice,
                       json_body={"headline": "Backend developer",
                                  "bio": "I like databases.",
                                  "skills": "Python, SQL, FastAPI"})
        check("profile update is saved", response.ok, f"{response.status}")
        check("skills are split, never interpreted",
              response.body.get("skills") == ["Python", "SQL", "FastAPI"],
              str(response.body.get("skills")))

        response = req("PUT", "/social/profile/me", token=alice,
                       json_body={"bio": "Updated bio."})
        check("a partial edit leaves the headline alone",
              response.body.get("headline") == "Backend developer",
              str(response.body.get("headline")))

        response = req("PUT", "/social/profile/me", token=alice,
                       json_body={"headline": "x" * 200})
        check("an over-long headline is refused, not truncated",
              response.status == 422, f"got {response.status}")

        # The projection must not carry HR data. Checked by field name across
        # the whole serialised payload, so a field added later that happens to
        # be called `salary` or `leave_balance` fails this test.
        response = req("GET", "/social/profile/me", token=alice)
        forbidden = ("salary", "compensation", "attendance", "leave",
                     "performance", "rating", "review", "password", "hash",
                     "employment_status", "manager_id")
        leaked = [word for word in forbidden if word in response.raw.lower()]
        check("the profile projection exposes no HR record", not leaked,
              f"found {leaked}")

        response = req("GET", f"/social/profile/{bob_id}", token=alice)
        check("I can read a colleague's profile", response.ok, f"{response.status}")
        check("their profile is not marked as mine",
              response.body.get("is_me") is False)

        applicant_user_id = user_id_of(APPLICANT)
        response = req("GET", f"/social/profile/{applicant_user_id}", token=alice)
        check("an Applicant is not in the directory", response.status == 404,
              f"got {response.status}")

        response = req("POST", "/social/profile/me/avatar", token=alice,
                       files={"image": ("me.png", PNG_1PX)})
        check("an avatar uploads", response.ok, f"{response.status}")
        avatar_url = response.body.get("avatar_url") or ""
        check("the avatar is served from /social/media/",
              avatar_url.startswith("/social/media/"), avatar_url)

        if avatar_url:
            response = req("GET", avatar_url, token=bob)
            check("a colleague can load the avatar", response.ok,
                  f"{response.status}")
            response = req("GET", avatar_url, token=applicant_token)
            check("an Applicant cannot load the avatar",
                  response.status == 403, f"got {response.status}")

        response = req("POST", "/social/profile/me/avatar", token=alice,
                       files={"image": ("evil.png", b"#!/bin/sh\necho hi\n")})
        check("a non-image with an image name is refused",
              response.status == 422, f"got {response.status}")

        for name in ("../../app/main.py", "..%2f..%2fapp%2fmain.py", "main.py"):
            response = req("GET", f"/social/media/{name}", token=alice)
            check(f"traversal {name!r} is refused",
                  response.status in (404, 400), f"got {response.status}")

        # --------------------------------------------------------------
        section("3. Feed - posts, likes, comments")
        # --------------------------------------------------------------
        response = req("POST", "/social/posts", token=alice,
                       form={"content": "First post from the test suite."},
                       files={})
        check("a post is created", response.ok, f"{response.status}")
        post_id = (response.body or {}).get("id")
        check("a new post starts with no likes",
              (response.body or {}).get("like_count") == 0)
        check("the author is resolved",
              bool((response.body or {}).get("author", {}).get("name")))

        response = req("POST", "/social/posts", token=alice,
                       form={"content": "   "}, files={})
        check("an empty post is refused", response.status == 422,
              f"got {response.status}")

        response = req("POST", "/social/posts", token=alice,
                       form={"content": "With a picture."},
                       files={"image": ("shot.png", PNG_1PX)})
        check("a post with an image is created", response.ok, f"{response.status}")
        image_post_id = (response.body or {}).get("id")
        check("the image is served from /social/media/",
              str((response.body or {}).get("image_url", "")).startswith(
                  "/social/media/"))

        response = req("GET", "/social/feed", token=bob)
        check("the feed loads for another colleague", response.ok,
              f"{response.status}")
        check("the feed is paginated",
              all(k in (response.body or {}) for k in
                  ("page", "page_size", "total", "pages")))
        check("the feed does not return everything at once",
              len((response.body or {}).get("posts", [])) <=
              (response.body or {}).get("page_size", 0))

        response = req("GET", "/social/feed?page=1&page_size=1", token=bob)
        check("page_size is honoured",
              len((response.body or {}).get("posts", [])) == 1,
              str(len((response.body or {}).get("posts", []))))

        for scope in ("all", "department", "following", "company"):
            response = req("GET", f"/social/feed?scope={scope}", token=alice)
            check(f"feed scope {scope!r} answers", response.ok,
                  f"{response.status}")

        response = req("GET", "/social/feed?scope=nonsense", token=alice)
        check("an unknown scope is refused by the route",
              response.status == 422, f"got {response.status}")

        response = req("POST", f"/social/posts/{post_id}/like", token=bob)
        check("a post can be liked", response.ok, f"{response.status}")
        check("the like counts once",
              (response.body or {}).get("like_count") == 1,
              str((response.body or {}).get("like_count")))

        response = req("POST", f"/social/posts/{post_id}/like", token=bob)
        check("liking twice is still one like",
              (response.body or {}).get("like_count") == 1,
              str((response.body or {}).get("like_count")))
        check("the post knows I liked it",
              (response.body or {}).get("liked_by_me") is True)

        response = req("DELETE", f"/social/posts/{post_id}/like", token=bob)
        check("unliking removes it",
              (response.body or {}).get("like_count") == 0,
              str((response.body or {}).get("like_count")))

        response = req("POST", f"/social/posts/{post_id}/comments", token=bob,
                       json_body={"content": "Good post."})
        check("a comment is added", response.ok, f"{response.status}")
        comment_id = (response.body or {}).get("id")

        response = req("POST", f"/social/posts/{post_id}/comments", token=bob,
                       json_body={"content": ""})
        check("an empty comment is refused", response.status == 422,
              f"got {response.status}")

        response = req("GET", f"/social/posts/{post_id}/comments", token=alice)
        check("comments are listed", response.ok, f"{response.status}")
        check("the comment count is real",
              (response.body or {}).get("total") == 1,
              str((response.body or {}).get("total")))

        response = req("POST", "/social/posts/999999/comments", token=bob,
                       json_body={"content": "x"})
        check("commenting on a missing post is 404",
              response.status == 404, f"got {response.status}")

        response = req("PUT", f"/social/posts/{post_id}", token=alice,
                       json_body={"content": "Edited by its author."})
        check("an author may edit their own post", response.ok,
              f"{response.status}")
        check("an edit is marked as edited",
              (response.body or {}).get("edited_at") is not None)

        # --------------------------------------------------------------
        section("4. Ownership - and 404 rather than 403")
        # --------------------------------------------------------------
        response = req("PUT", f"/social/posts/{post_id}", token=bob,
                       json_body={"content": "Hijacked."})
        check("another user cannot edit my post", response.status == 404,
              f"got {response.status}")

        response = req("DELETE", f"/social/posts/{post_id}", token=bob)
        check("another user cannot delete my post", response.status == 404,
              f"got {response.status}")

        # Admin is checked explicitly: being an Admin is not a moderation
        # surface, and V1 deliberately has none.
        response = req("DELETE", f"/social/posts/{post_id}", token=admin)
        check("not even an Admin deletes somebody else's post",
              response.status == 404, f"got {response.status}")

        response = req("DELETE", f"/social/comments/{comment_id}", token=alice)
        check("a post author cannot delete somebody else's comment",
              response.status == 404, f"got {response.status}")

        response = req("DELETE", f"/social/comments/{comment_id}", token=bob)
        check("a commenter deletes their own comment", response.ok,
              f"{response.status}")

        response = req("GET", f"/social/posts/{post_id}", token=bob)
        check("the post survived the failed deletes", response.ok,
              f"{response.status}")

        response = req("DELETE", f"/social/posts/{image_post_id}", token=alice)
        check("an author deletes their own post", response.ok,
              f"{response.status}")

        response = req("GET", f"/social/posts/{image_post_id}", token=alice)
        check("a deleted post is gone", response.status == 404,
              f"got {response.status}")

        # --------------------------------------------------------------
        section("5. Stories")
        # --------------------------------------------------------------
        response = req("POST", "/social/stories", token=alice,
                       form={"caption": "At the office today."},
                       files={"image": ("story.png", PNG_1PX)})
        check("a story is created", response.ok, f"{response.status}")
        story_id = (response.body or {}).get("id")
        check("a story carries an expiry",
              (response.body or {}).get("expires_at") is not None)
        check("a new story is not expired",
              (response.body or {}).get("expired") is False)

        response = req("POST", "/social/stories", token=alice,
                       form={"caption": ""}, files={})
        check("a story with neither text nor image is refused",
              response.status == 422, f"got {response.status}")

        response = req("GET", "/social/stories", token=bob)
        check("active stories are listed", response.ok, f"{response.status}")
        groups = (response.body or {}).get("groups", [])
        mine = [g for g in groups if g.get("author", {}).get("user_id") == alice_id]
        check("the story is grouped under its author", bool(mine))
        check("it starts unseen for a colleague",
              bool(mine and mine[0].get("has_unseen")), str(mine[:1]))

        response = req("POST", f"/social/stories/{story_id}/view", token=bob)
        check("viewing marks it seen", (response.body or {}).get("seen") is True)

        response = req("GET", "/social/stories", token=bob)
        groups = (response.body or {}).get("groups", [])
        mine = [g for g in groups if g.get("author", {}).get("user_id") == alice_id]
        check("it stays seen on the next load",
              bool(mine) and not mine[0].get("has_unseen"))

        response = req("GET", f"/social/stories/{story_id}", token=alice)
        check("the author sees their own view count",
              (response.body or {}).get("view_count") == 1,
              str((response.body or {}).get("view_count")))

        response = req("GET", f"/social/stories/{story_id}", token=bob)
        check("a viewer is not told the view count",
              (response.body or {}).get("view_count") is None)

        response = req("DELETE", f"/social/stories/{story_id}", token=bob)
        check("another user cannot delete my story", response.status == 404,
              f"got {response.status}")

        # Expiry is proven against the database rather than by waiting 24
        # hours: the row is aged, and the API must then stop returning it.
        from app.database import SessionLocal
        from app.models import SocialStory
        from datetime import datetime, timedelta

        db = SessionLocal()
        try:
            row = db.query(SocialStory).filter(SocialStory.id == story_id).first()
            row.created_at = datetime.utcnow() - timedelta(hours=30)
            row.expires_at = datetime.utcnow() - timedelta(hours=6)
            db.commit()
        finally:
            db.close()

        response = req("GET", "/social/stories", token=bob)
        groups = (response.body or {}).get("groups", [])
        still_there = any(
            s.get("id") == story_id
            for g in groups
            for s in g.get("stories", [])
        )
        check("an expired story leaves the active list", not still_there)

        response = req("GET", f"/social/stories/{story_id}", token=bob)
        check("an expired story cannot be opened by a colleague",
              response.status == 410, f"got {response.status}")

        response = req("POST", f"/social/stories/{story_id}/view", token=bob)
        check("an expired story cannot be marked seen",
              response.status == 410, f"got {response.status}")

        # --------------------------------------------------------------
        section("6. People")
        # --------------------------------------------------------------
        response = req("GET", "/social/people", token=alice)
        check("the directory loads", response.ok, f"{response.status}")
        listed = {p["user_id"] for p in (response.body or {}).get("people", [])}
        check("it includes colleagues", bob_id in listed)
        check("it excludes me", alice_id not in listed)
        check("it excludes Applicants", applicant_user_id not in listed)

        response = req("GET", f"/social/people?q={BOB.split('@')[0]}", token=alice)
        found = (response.body or {}).get("people", [])
        check("search by name or address finds a person",
              any(p["user_id"] == bob_id for p in found), str(len(found)))

        response = req("GET", "/social/people?q=zzzznobodyhere", token=alice)
        check("a search that matches nobody returns nothing, not everybody",
              (response.body or {}).get("total") == 0,
              str((response.body or {}).get("total")))

        response = req("GET", "/social/people/suggested", token=alice)
        check("suggestions load", response.ok, f"{response.status}")

        # --------------------------------------------------------------
        section("7. Connections")
        # --------------------------------------------------------------
        response = req("POST", f"/social/connections/{alice_id}", token=alice)
        check("I cannot connect with myself", response.status == 422,
              f"got {response.status}")

        response = req("POST", f"/social/connections/{applicant_user_id}",
                       token=alice)
        check("I cannot connect with an Applicant", response.status == 404,
              f"got {response.status}")

        response = req("POST", f"/social/connections/{bob_id}", token=alice)
        check("a connection request is sent", response.ok, f"{response.status}")
        connection_id = (response.body or {}).get("id")
        check("it starts pending",
              (response.body or {}).get("status") == "pending")
        check("it is outgoing from my side",
              (response.body or {}).get("direction") == "outgoing")

        response = req("POST", f"/social/connections/{bob_id}", token=alice)
        check("a duplicate request is refused", response.status == 409,
              f"got {response.status}")

        response = req("GET", "/social/connections", token=bob)
        incoming = (response.body or {}).get("incoming_requests", [])
        check("the request shows as incoming for the receiver",
              any(c["id"] == connection_id for c in incoming))

        response = req("POST", f"/social/connections/{connection_id}/accept",
                       token=mgr)
        check("a third party cannot accept somebody else's request",
              response.status == 404, f"got {response.status}")

        response = req("POST", f"/social/connections/{connection_id}/accept",
                       token=alice)
        check("the requester cannot accept their own request",
              response.status == 404, f"got {response.status}")

        response = req("POST", f"/social/connections/{connection_id}/accept",
                       token=bob)
        check("the receiver accepts", response.ok, f"{response.status}")
        check("the connection is accepted",
              (response.body or {}).get("status") == "accepted")

        response = req("POST", f"/social/connections/{connection_id}/accept",
                       token=bob)
        check("accepting twice is refused", response.status == 409,
              f"got {response.status}")

        response = req("GET", f"/social/profile/{bob_id}", token=alice)
        check("the profile shows us as connected",
              (response.body or {}).get("connection", {}).get("state")
              == "connected",
              str((response.body or {}).get("connection")))

        response = req("POST", f"/social/connections/{connection_id}/reject",
                       token=mgr)
        check("a third party cannot reject either", response.status == 404,
              f"got {response.status}")

        # Reject path, on a fresh pair.
        response = req("POST", f"/social/connections/{mgr_id}", token=alice)
        reject_id = (response.body or {}).get("id")
        response = req("POST", f"/social/connections/{reject_id}/reject",
                       token=mgr)
        check("a request can be rejected",
              (response.body or {}).get("status") == "rejected",
              f"{response.status}")

        response = req("POST", f"/social/connections/{mgr_id}", token=alice)
        check("a rejection does not block the pair forever", response.ok,
              f"{response.status}")

        response = req("DELETE", f"/social/connections/{connection_id}",
                       token=admin)
        check("a third party cannot remove a connection",
              response.status == 404, f"got {response.status}")

        response = req("DELETE", f"/social/connections/{connection_id}",
                       token=alice)
        check("either party may disconnect", response.ok, f"{response.status}")

        # --------------------------------------------------------------
        section("8. Messages")
        # --------------------------------------------------------------
        response = req("POST", "/social/conversations", token=alice,
                       json_body={"user_id": alice_id})
        check("I cannot message myself", response.status == 422,
              f"got {response.status}")

        response = req("POST", "/social/conversations", token=alice,
                       json_body={"user_id": applicant_user_id})
        check("I cannot message an Applicant", response.status == 404,
              f"got {response.status}")

        response = req("POST", "/social/conversations", token=alice,
                       json_body={"user_id": bob_id})
        check("a conversation opens", response.ok, f"{response.status}")
        conversation_id = (response.body or {}).get("id")

        response = req("POST", "/social/conversations", token=alice,
                       json_body={"user_id": bob_id})
        check("opening it again returns the same thread",
              (response.body or {}).get("id") == conversation_id,
              str((response.body or {}).get("id")))

        response = req("POST", f"/social/conversations/{conversation_id}/messages",
                       token=alice, json_body={"body": "Hello Bob."})
        check("a message sends", response.ok, f"{response.status}")

        response = req("POST", f"/social/conversations/{conversation_id}/messages",
                       token=alice, json_body={"body": "   "})
        check("an empty message is refused", response.status == 422,
              f"got {response.status}")

        response = req("GET", "/social/conversations", token=bob)
        threads = (response.body or {}).get("conversations", [])
        thread = next((t for t in threads if t["id"] == conversation_id), None)
        check("the thread appears for the recipient", thread is not None)
        check("it carries an unread count",
              bool(thread) and thread.get("unread_count") == 1,
              str(thread.get("unread_count") if thread else None))
        check("it carries the last message",
              bool(thread) and thread.get("last_message", {}).get("body")
              == "Hello Bob.")

        response = req("GET", f"/social/conversations/{conversation_id}/messages",
                       token=bob)
        check("the recipient reads the thread", response.ok, f"{response.status}")
        check("the messages are there",
              len((response.body or {}).get("messages", [])) == 1,
              str(len((response.body or {}).get("messages", []))))

        response = req("GET", "/social/conversations", token=bob)
        threads = (response.body or {}).get("conversations", [])
        thread = next((t for t in threads if t["id"] == conversation_id), None)
        check("reading clears the unread count",
              bool(thread) and thread.get("unread_count") == 0,
              str(thread.get("unread_count") if thread else None))

        for label, token in (("Manager", mgr), ("HR", hr), ("Admin", admin)):
            response = req(
                "GET", f"/social/conversations/{conversation_id}/messages",
                token=token
            )
            check(f"{label} cannot read a conversation they are not in",
                  response.status == 404, f"got {response.status}")

            response = req(
                "POST", f"/social/conversations/{conversation_id}/messages",
                token=token, json_body={"body": "intruding"}
            )
            check(f"{label} cannot post into it either",
                  response.status == 404, f"got {response.status}")

        response = req("GET", "/social/conversations", token=mgr)
        ids = {t["id"] for t in (response.body or {}).get("conversations", [])}
        check("it does not appear in a non-member's list",
              conversation_id not in ids)

        # --------------------------------------------------------------
        section("9. Notifications - the existing table, not a second one")
        # --------------------------------------------------------------
        response = req("GET", "/social/notifications", token=bob)
        check("social notifications load", response.ok, f"{response.status}")
        kinds = {n["type"] for n in (response.body or {}).get("notifications", [])}
        check("a connection request notified the receiver",
              "social_connection_request" in kinds, str(kinds))
        check("every notification listed here is a social one",
              all(k.startswith("social_") for k in kinds), str(kinds))

        response = req("GET", "/social/notifications", token=alice)
        alice_kinds = {
            n["type"] for n in (response.body or {}).get("notifications", [])
        }
        check("the acceptance notified the requester",
              "social_connection_accepted" in alice_kinds, str(alice_kinds))
        check("a message notified its recipient",
              "social_message" in kinds, str(kinds))

        notifications = req("GET", "/social/notifications", token=bob).body
        first = (notifications or {}).get("notifications", [{}])[0]

        if first.get("id"):
            response = req(
                "POST", f"/social/notifications/{first['id']}/read", token=alice
            )
            check("another user cannot mark my notification read",
                  response.status == 404, f"got {response.status}")

            response = req(
                "POST", f"/social/notifications/{first['id']}/read", token=bob
            )
            check("I mark my own notification read",
                  (response.body or {}).get("is_read") is True,
                  f"{response.status}")

        # The same rows the existing bell reads - not a parallel inbox.
        response = req("GET", "/notifications/", token=bob)
        bell = {n["id"] for n in (response.body or [])}
        check("social notifications appear in the existing bell",
              bool(first.get("id")) and first["id"] in bell)

        # --------------------------------------------------------------
        section("10. Containment - no HR table was written")
        # --------------------------------------------------------------
        from sqlalchemy import text as sql_text

        db = SessionLocal()
        try:
            counts = db.execute(sql_text("""
                SELECT
                  (SELECT count(*) FROM employees),
                  (SELECT count(*) FROM departments),
                  (SELECT count(*) FROM positions),
                  (SELECT count(*) FROM attendance),
                  (SELECT count(*) FROM leave_requests),
                  (SELECT count(*) FROM performance_reviews),
                  (SELECT count(*) FROM candidates),
                  (SELECT count(*) FROM interviews)
            """)).fetchone()
        finally:
            db.close()

        check("the Social Hub created no employee", counts[0] == EXPECTED[0],
              f"{counts[0]} vs {EXPECTED[0]}")
        check("it created no department", counts[1] == EXPECTED[1],
              f"{counts[1]} vs {EXPECTED[1]}")
        check("it created no position", counts[2] == EXPECTED[2],
              f"{counts[2]} vs {EXPECTED[2]}")
        check("it wrote no attendance", counts[3] == EXPECTED[3],
              f"{counts[3]} vs {EXPECTED[3]}")
        check("it wrote no leave request", counts[4] == EXPECTED[4],
              f"{counts[4]} vs {EXPECTED[4]}")
        check("it wrote no performance review", counts[5] == EXPECTED[5],
              f"{counts[5]} vs {EXPECTED[5]}")
        check("it created no candidate", counts[6] == EXPECTED[6],
              f"{counts[6]} vs {EXPECTED[6]}")
        check("it created no interview", counts[7] == EXPECTED[7],
              f"{counts[7]} vs {EXPECTED[7]}")

    if not args.keep:
        cleanup()
        print("\nTest rows removed.")
    else:
        print("\n--keep: test rows left in the database.")

    print(f"\n{'=' * 60}")
    print(f"Passed: {passed}   Failed: {len(failed)}")

    if failed:
        print("\nFailures:")
        for item in failed:
            print(f"  - {item}")

    return 1 if failed else 0


def baseline() -> tuple:
    """HR table counts before anything runs, so section 10 compares against
    reality rather than against numbers hard-coded when this was written."""
    from app.database import SessionLocal
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        return tuple(db.execute(sql_text("""
            SELECT
              (SELECT count(*) FROM employees),
              (SELECT count(*) FROM departments),
              (SELECT count(*) FROM positions),
              (SELECT count(*) FROM attendance),
              (SELECT count(*) FROM leave_requests),
              (SELECT count(*) FROM performance_reviews),
              (SELECT count(*) FROM candidates),
              (SELECT count(*) FROM interviews)
        """)).fetchone())
    finally:
        db.close()


EXPECTED: tuple = ()

if __name__ == "__main__":
    raise SystemExit(main())
