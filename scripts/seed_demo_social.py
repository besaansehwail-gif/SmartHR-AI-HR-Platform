"""A handful of clearly-labelled DEMO Social Hub records, so the UI has
something in it.

    venv\\Scripts\\python.exe -m scripts.seed_demo_social            # report
    venv\\Scripts\\python.exe -m scripts.seed_demo_social --apply    # write
    venv\\Scripts\\python.exe -m scripts.seed_demo_social --remove   # undo

Reports by default and writes only with `--apply`, following
`scripts/link_applicant_profiles.py`; `--remove` takes it all out again,
following `scripts/seed_demo_opportunities.py`.

**Why this exists.** A freshly migrated Social Hub may have too little
development content to exercise the feed, stories strip and comment thread.
This script provides clearly labelled demo content for those UI states.

**What it will not do**, and these are the rules that make it safe to run
against this database:

* **It creates no users and no employees.** It posts as accounts that already
  exist, and if fewer than two internal accounts exist it stops and says so.
* **Every post, comment and story begins with `DEMO - `,** so what it wrote is
  identifiable by reading it, not by consulting this file - the same convention
  `seed_demo_opportunities.py` uses for job titles.
* **It touches no HR table.** Nothing outside `social_*` is read for writing or
  written at all.
* **It is idempotent.** Re-running it adds nothing, because it looks for its
  own `DEMO - ` rows first.
* **`--remove` deletes only rows whose text carries the marker**, plus the
  reactions, comments and views hanging off those rows. A real post somebody
  wrote is never in scope.

Note that it deliberately does **not** seed connections or conversations.
A connection is a statement that two colleagues agreed to something and a
message is private correspondence; inventing either would put words between two
real accounts. Posts, comments and stories are visibly labelled content, which
is a different thing.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Employee,
    SocialComment,
    SocialPost,
    SocialReaction,
    SocialStory,
    SocialStoryView,
    User,
)
from app.services.social_service import STORY_LIFETIME  # noqa: E402

MARKER = "DEMO - "

#: Written to read as ordinary workplace posts, so the layout is exercised at
#: realistic lengths - but every one of them says DEMO first.
POSTS = [
    MARKER + "Welcome to the SmartHR Social Hub. This is where we share what "
    "we are working on, ask each other questions and mark the things worth "
    "marking. Say hello when you get a moment.",
    MARKER + "Finished migrating the reporting queries this week. Roughly "
    "half the dashboard load time is gone. Happy to walk anyone through what "
    "changed.",
    MARKER + "Reminder that the quarterly training catalogue has been "
    "refreshed. If there is a course you want on it, tell us rather than "
    "assuming somebody already has.",
    MARKER + "Short one: thanks to everyone who helped cover last week. It "
    "was noticed.",
]

COMMENTS = [
    MARKER + "Good to see this up and running.",
    MARKER + "Interested in the detail on this - will follow up.",
]

STORY = MARKER + "Testing the stories strip. This one expires on its own."


def internal_accounts(db) -> list[User]:
    return (
        db.query(User)
        .filter(User.role_id.in_((1, 2, 3, 4)))
        .filter(User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )


def existing(db) -> dict:
    return {
        "posts": db.query(SocialPost)
        .filter(SocialPost.content.like(f"{MARKER}%"))
        .all(),
        "comments": db.query(SocialComment)
        .filter(SocialComment.content.like(f"{MARKER}%"))
        .all(),
        "stories": db.query(SocialStory)
        .filter(SocialStory.caption.like(f"{MARKER}%"))
        .all(),
    }


def report(db) -> None:
    accounts = internal_accounts(db)
    found = existing(db)

    print(f"Internal accounts available to post as: {len(accounts)}")
    for account in accounts:
        employee = db.query(Employee).filter(Employee.user_id == account.id).first()
        name = (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else account.email
        )
        print(f"  #{account.id}  role {account.role_id}  {name}")

    print()
    print(f"DEMO posts already present:    {len(found['posts'])}")
    print(f"DEMO comments already present: {len(found['comments'])}")
    print(f"DEMO stories already present:  {len(found['stories'])}")


def apply(db) -> int:
    accounts = internal_accounts(db)

    if len(accounts) < 2:
        print(
            "Fewer than two internal accounts exist, so there is nobody to "
            "post as and nobody to comment back.\n"
            "This script will not create accounts. Add them through Admin > "
            "Users first."
        )
        return 2

    found = existing(db)

    if found["posts"] or found["stories"]:
        print("DEMO social records are already present - nothing to do.")
        report(db)
        return 0

    written = 0
    now = datetime.utcnow()

    posts = []

    for index, content in enumerate(POSTS):
        author = accounts[index % len(accounts)]
        employee = db.query(Employee).filter(Employee.user_id == author.id).first()

        post = SocialPost(
            author_user_id=author.id,
            content=content,
            audience="company",
            # The author's real department, or NULL when their account has no
            # employees row. Never invented.
            department_id=employee.department_id if employee else None,
            # Spread over the last few hours so the feed is not one timestamp.
            created_at=now - timedelta(hours=index * 5 + 1),
            updated_at=now - timedelta(hours=index * 5 + 1),
        )
        db.add(post)
        posts.append(post)
        written += 1

    db.commit()

    for post in posts:
        db.refresh(post)

    # One comment thread and a couple of likes, so those surfaces are not empty
    # either. Both are from a different account than the author.
    first, second = accounts[0], accounts[1]

    for index, content in enumerate(COMMENTS):
        db.add(
            SocialComment(
                post_id=posts[0].id,
                author_user_id=(second if index == 0 else first).id,
                content=content,
                created_at=now - timedelta(minutes=30 - index * 10),
            )
        )
        written += 1

    for post in posts[:2]:
        liker = second if post.author_user_id == first.id else first
        db.add(SocialReaction(post_id=post.id, user_id=liker.id, kind="like"))
        written += 1

    db.add(
        SocialStory(
            author_user_id=first.id,
            caption=STORY,
            created_at=now,
            # The same 24-hour window the API uses, imported rather than
            # re-typed, so this cannot drift from the real rule.
            expires_at=now + STORY_LIFETIME,
        )
    )
    written += 1

    db.commit()

    print(f"Wrote {written} DEMO social records.")
    print("Remove them again with:  --remove")
    return 0


def remove(db) -> int:
    found = existing(db)

    post_ids = [p.id for p in found["posts"]]
    story_ids = [s.id for s in found["stories"]]

    removed = 0

    if story_ids:
        removed += (
            db.query(SocialStoryView)
            .filter(SocialStoryView.story_id.in_(story_ids))
            .delete(synchronize_session=False)
        )
        removed += (
            db.query(SocialStory)
            .filter(SocialStory.id.in_(story_ids))
            .delete(synchronize_session=False)
        )

    if post_ids:
        # Reactions and comments on a DEMO post go with it - including a real
        # like somebody left on it, which has nothing to belong to afterwards.
        removed += (
            db.query(SocialReaction)
            .filter(SocialReaction.post_id.in_(post_ids))
            .delete(synchronize_session=False)
        )
        removed += (
            db.query(SocialComment)
            .filter(SocialComment.post_id.in_(post_ids))
            .delete(synchronize_session=False)
        )
        removed += (
            db.query(SocialPost)
            .filter(SocialPost.id.in_(post_ids))
            .delete(synchronize_session=False)
        )

    # A DEMO comment left on a real post is removed by its own marker.
    removed += (
        db.query(SocialComment)
        .filter(SocialComment.content.like(f"{MARKER}%"))
        .delete(synchronize_session=False)
    )

    db.commit()

    print(f"Removed {removed} DEMO social rows.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="write the records")
    group.add_argument("--remove", action="store_true", help="delete them again")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.remove:
            return remove(db)
        if args.apply:
            return apply(db)

        print("Reporting only. Pass --apply to write, --remove to undo.\n")
        report(db)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
