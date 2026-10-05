"""The scheduled AI Employee Celebration sweep - tests.

    venv\\Scripts\\python.exe -m scripts.test_celebration_scheduler

**Offline.** The three agents are replaced by a fake provider implementing
`app/ai/provider.py`'s two methods, so what runs is the real detection query,
the real graph, the real service, the real `celebration_drafts` table and the
real posting path - everything except the model. That is the arrangement
`test_celebration_agents.py` already uses.

`scripts/test_celebration_agents.py` covers the agents and the graph and is
unchanged. This file covers only what the scheduler added:

    1. detection       who is celebrating, and who is correctly ignored
    2. the sweep       one workflow per employee, drafts stored
    3. idempotence     a second run creates nothing, spends no model call
    4. no publishing   the sweep cannot post; only a person can
    5. HR's decisions  approve posts through the ordinary path; dismiss does not

Every row it writes is removed at the end.
"""

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.celebration import agents, prompts  # noqa: E402
from app.ai.provider import LlmReply, ToolCall  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    CelebrationDraft,
    Employee,
    SocialModerationReview,
    SocialPost,
    User,
)
from app.services import celebration_service as svc  # noqa: E402

passed = 0
failed = 0
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        failures.append(label)
        print(f"  FAIL  {label}" + (f"   -> {detail}" if detail else ""))
    return bool(ok)


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


# ===========================================================================
# A fake provider
# ===========================================================================

@dataclass
class FakeProvider:
    """Stands in for the language model. Counts how often it was asked.

    The count is the evidence for "a second run spends no model calls" - a
    claim about cost that only a counter can make.
    """

    approve: bool = True
    calls: int = 0
    seen: list[str] = field(default_factory=list)

    name = "fake"
    model = "fake-model"
    configured = True

    def complete(self, system, messages, tools=None):
        tool = (tools or [{}])[0].get("name", "")
        self.calls += 1
        self.seen.append(tool)

        if tool == prompts.OCCASION_TOOL:
            payload = {"occasion": "work_anniversary", "years": None,
                       "reason": "A work_anniversary event was supplied."}
            for line in messages[0]["content"].splitlines():
                if '"years"' in line:
                    digits = "".join(c for c in line if c.isdigit())
                    if digits:
                        payload["years"] = int(digits)
                    break
        elif tool == prompts.MESSAGE_TOOL:
            payload = {"message": "Congratulations on the milestone. Thank you "
                                  "for your work here."}
        else:
            payload = {"approved": self.approve,
                       "reason": "Every check passed." if self.approve
                                 else "Check 4 failed: unsupported detail.",
                       "suggestions": None if self.approve else "Remove it."}

        return LlmReply(tool_call=ToolCall(name=tool, arguments=payload, id="fake"))

    def tool_exchange(self, reply, result_json):
        return []


def with_fake(fake: FakeProvider):
    original = agents.get_provider
    agents.get_provider = lambda settings=None: fake
    return lambda: setattr(agents, "get_provider", original)


# ===========================================================================
# Fixtures
# ===========================================================================

TODAY = date(2026, 6, 15)          # a fixed date, so the suite is not seasonal
MARKER = "Scheduler-Test"


def make_employee(db, *, first: str, years_ago: int | None, offset_days: int = 0):
    """An employee whose anniversary is `offset_days` from TODAY."""
    hire = None
    if years_ago is not None:
        target = TODAY + timedelta(days=offset_days)
        try:
            hire = date(target.year - years_ago, target.month, target.day)
        except ValueError:
            hire = date(target.year - years_ago, 3, 1)

    row = Employee(first_name=first, last_name=MARKER, hire_date=hire,
                   employment_status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def cleanup(db, employees: list[Employee]) -> None:
    ids = [e.id for e in employees]
    if not ids:
        return

    drafts = (db.query(CelebrationDraft)
              .filter(CelebrationDraft.employee_id.in_(ids)).all())
    post_ids = [d.post_id for d in drafts if d.post_id]

    for draft in drafts:
        db.delete(draft)
    db.commit()

    for post_id in post_ids:
        (db.query(SocialModerationReview)
         .filter(SocialModerationReview.content_type == "post")
         .filter(SocialModerationReview.content_id == post_id)
         .delete(synchronize_session=False))
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        if post:
            db.delete(post)
    db.commit()

    for employee in employees:
        row = db.query(Employee).filter(Employee.id == employee.id).first()
        if row:
            db.delete(row)
    db.commit()


def hr_user(db) -> User:
    """Any real Admin/HR account - the poster has to be somebody."""
    return (db.query(User).filter(User.role_id.in_((1, 2)))
            .filter(User.is_active.is_(True)).order_by(User.id).first())


# ===========================================================================
# 1. Detection
# ===========================================================================

def test_detection(db) -> None:
    section("1. Detection - from hire_date, by SQL, with no model")

    people = [
        make_employee(db, first="Today", years_ago=3),               # celebrating
        make_employee(db, first="Alsotoday", years_ago=10),          # celebrating
        make_employee(db, first="Tomorrow", years_ago=4, offset_days=1),
        make_employee(db, first="Lastweek", years_ago=6, offset_days=-7),
        make_employee(db, first="Nodate", years_ago=None),           # no hire_date
        make_employee(db, first="Hiredtoday", years_ago=0),          # 0 years
    ]

    try:
        found = svc.anniversaries_today(db, today=TODAY)
        names = {f["name"].split()[0] for f in found}

        check("an employee whose anniversary is today is found",
              "Today" in names, str(names))
        check("a second employee celebrating the same day is also found",
              "Alsotoday" in names, str(names))
        check("an anniversary tomorrow is ignored", "Tomorrow" not in names)
        check("an anniversary last week is ignored", "Lastweek" not in names)
        check("an employee with no hire_date is ignored", "Nodate" not in names)
        check("somebody hired today is not celebrating 0 years",
              "Hiredtoday" not in names)

        today_row = next(f for f in found if f["name"].startswith("Today"))
        check("the years figure is counted from the row",
              today_row["years"] == 3, str(today_row))

        # Multiple people, each their own entry - never merged.
        celebrating = [f for f in found if f["name"].endswith(MARKER)]
        check("two people celebrating today are two separate entries",
              len(celebrating) == 2, str(len(celebrating)))
    finally:
        cleanup(db, people)


# ===========================================================================
# 2. The sweep
# ===========================================================================

def test_sweep(db) -> None:
    section("2. The sweep - one workflow per employee, a draft each")

    people = [
        make_employee(db, first="Amal", years_ago=3),
        make_employee(db, first="Basim", years_ago=5),
        make_employee(db, first="Carmen", years_ago=10),
        make_employee(db, first="Absent", years_ago=2, offset_days=30),
    ]
    fake = FakeProvider()
    restore = with_fake(fake)

    try:
        summary = svc.run_daily(db, today=TODAY)

        check("the sweep found the three people celebrating",
              summary["found"] == 3, str(summary["found"]))
        check("it prepared a celebration for each", summary["prepared"] == 3,
              str(summary))
        check("nothing failed", summary["failed"] == 0, str(summary))

        drafts = (db.query(CelebrationDraft)
                  .filter(CelebrationDraft.employee_id.in_([p.id for p in people]))
                  .all())
        check("one draft row per celebrating employee", len(drafts) == 3,
              str(len(drafts)))
        check("the employee with no anniversary today got no draft",
              not any(d.employee_id == people[3].id for d in drafts))

        by_employee = {d.employee_id: d for d in drafts}
        check("each draft is for its own employee, never merged",
              len(by_employee) == 3)
        check("the years differ per person, as the rows do",
              sorted(d.years for d in drafts) == [3, 5, 10],
              str(sorted(d.years for d in drafts if d.years)))
        check("every draft is pending, awaiting a person",
              all(d.status == svc.STATUS_PENDING for d in drafts))
        check("every draft carries the review verdict",
              all(d.review_approved for d in drafts))
        check("every draft has the message the agent wrote",
              all((d.message or "").strip() for d in drafts))
        check("the occasion_date is the day it was detected for",
              all(d.occasion_date == TODAY for d in drafts))

        # Three employees x three agents = nine calls, and not one more.
        check("the graph ran once per employee, not once for all of them",
              fake.calls == 9, f"{fake.calls} model calls")
    finally:
        restore()
        cleanup(db, people)


# ===========================================================================
# 3. Idempotence
# ===========================================================================

def test_idempotence(db) -> None:
    section("3. Idempotence - running twice creates nothing the second time")

    people = [make_employee(db, first="Dalia", years_ago=7)]
    fake = FakeProvider()
    restore = with_fake(fake)

    try:
        first = svc.run_daily(db, today=TODAY)
        calls_after_first = fake.calls

        second = svc.run_daily(db, today=TODAY)

        check("the first run prepared one celebration", first["prepared"] == 1)
        check("the second run prepared none", second["prepared"] == 0, str(second))
        check("the second run reported it as already prepared",
              second["skipped_existing"] == 1, str(second))
        check("the second run spent no model calls at all",
              fake.calls == calls_after_first,
              f"{fake.calls - calls_after_first} extra calls")

        rows = (db.query(CelebrationDraft)
                .filter(CelebrationDraft.employee_id == people[0].id).all())
        check("there is still exactly one draft row", len(rows) == 1,
              str(len(rows)))

        # And the guarantee underneath: the database itself refuses a second
        # row, so two runs racing past the check cannot both insert.
        duplicate = CelebrationDraft(
            employee_id=people[0].id, occasion=svc.OCCASION_ANNIVERSARY,
            occasion_date=TODAY, years=7, message="A second one.",
            review_approved=True, status=svc.STATUS_PENDING,
        )
        db.add(duplicate)
        try:
            db.commit()
            check("the UNIQUE constraint refuses a duplicate row", False,
                  "the insert succeeded")
            db.delete(duplicate)
            db.commit()
        except Exception:
            db.rollback()
            check("the UNIQUE constraint refuses a duplicate row", True)

        # A different date for the same person is a different anniversary.
        next_year = CelebrationDraft(
            employee_id=people[0].id, occasion=svc.OCCASION_ANNIVERSARY,
            occasion_date=date(TODAY.year + 1, TODAY.month, TODAY.day),
            years=8, message="Next year.", review_approved=True,
            status=svc.STATUS_PENDING,
        )
        db.add(next_year)
        try:
            db.commit()
            check("next year's anniversary is allowed as its own draft", True)
        except Exception:
            db.rollback()
            check("next year's anniversary is allowed as its own draft", False)
    finally:
        restore()
        cleanup(db, people)


# ===========================================================================
# 4. The sweep cannot publish
# ===========================================================================

def test_no_auto_publish(db) -> None:
    section("4. The AI does not publish - only a person can")

    posts_before = db.query(SocialPost).count()
    people = [make_employee(db, first="Elias", years_ago=4)]
    fake = FakeProvider()
    restore = with_fake(fake)

    try:
        svc.run_daily(db, today=TODAY)

        check("a full sweep wrote no social post",
              db.query(SocialPost).count() == posts_before,
              str(db.query(SocialPost).count() - posts_before))

        draft = (db.query(CelebrationDraft)
                 .filter(CelebrationDraft.employee_id == people[0].id).first())
        check("the draft is pending, not posted",
              draft.status == svc.STATUS_PENDING, draft.status)
        check("no post is linked to it", draft.post_id is None)
        check("nobody is recorded as having decided", draft.decided_by is None)

        # Structural: the sweep has no user to post as.
        #
        # Parsed rather than grepped, because the docstrings in this module
        # name `create_post` when explaining that only one function calls it -
        # a text search counts the explanation as a second call site.
        import ast

        source = (ROOT / "app" / "services" / "celebration_service.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)

        callers: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "create_post"):
                    callers.append(node.name)

        check("run_daily contains no call to create_post",
              "run_daily" not in callers, str(callers))
        check("exactly one function publishes, and it is approve_draft",
              callers == ["approve_draft"], str(callers))
    finally:
        restore()
        cleanup(db, people)


# ===========================================================================
# 5. HR's decisions
# ===========================================================================

def test_hr_decisions(db) -> None:
    section("5. HR approves or dismisses - the human step")

    user = hr_user(db)
    if user is None:
        check("an Admin/HR account exists to post as", False, "none found")
        return

    people = [
        make_employee(db, first="Farid", years_ago=6),
        make_employee(db, first="Ghada", years_ago=9),
    ]
    fake = FakeProvider()
    restore = with_fake(fake)

    try:
        svc.run_daily(db, today=TODAY)
        posts_before = db.query(SocialPost).count()
        audits_before = db.query(AuditLog).count()

        drafts = svc.list_drafts(db)
        mine = [d for d in drafts if d["employee_id"] in [p.id for p in people]]
        check("both drafts are in HR's queue", len(mine) == 2, str(len(mine)))
        check("the queue says they are postable",
              all(d["postable"] for d in mine), str(mine[:1]))
        check("the queue names the employee",
              all(MARKER in (d["employee_name"] or "") for d in mine))

        # --- approve ------------------------------------------------------
        first_id = mine[0]["id"]
        result = svc.approve_draft(first_id, user, db)

        check("approving created exactly one post",
              db.query(SocialPost).count() == posts_before + 1)
        check("the draft is now posted",
              result["draft"]["status"] == svc.STATUS_POSTED)
        check("the draft records which post it became",
              result["draft"]["post_id"] == result["post"]["id"])
        check("the post carries the celebration's words",
              result["post"]["content"] == mine[0]["message"])
        check("the recruiter is recorded as the decider",
              db.query(CelebrationDraft).filter(
                  CelebrationDraft.id == first_id).first().decided_by == user.id)

        post_row = (db.query(SocialPost)
                    .filter(SocialPost.id == result["post"]["id"]).first())
        check("the post is authored by the recruiter, not by an agent",
              post_row.author_user_id == user.id)
        check("it went through the ordinary moderation path",
              post_row.moderation_status in ("published", "pending_review"),
              post_row.moderation_status)
        # A strict count, not `>=`. The first version of this check used
        # `>=`, which passes whatever happens, and it did pass while the
        # celebration post was in fact reaching the feed unaudited - the
        # audit row for a post is written by the router, not by
        # `create_post()`. The service call under test here does not write
        # one; `test_celebration_api.py` covers the router that does.
        check("the service layer alone writes no audit row",
              db.query(AuditLog).count() == audits_before,
              str(db.query(AuditLog).count() - audits_before))

        # --- the image travelled with it ------------------------------
        # The draft row has no image column: the image is resolved when it is
        # needed, so the draft carries it through the projection and the post
        # gets it at the moment a person approves - never before.
        image_path, image_source = svc.celebration_image(people[0].id, db)
        posted_row = (db.query(SocialPost)
                      .filter(SocialPost.id == result["post"]["id"]).first())

        if image_source == "none":
            check("with no image configured the post carries none",
                  posted_row.image_path is None)
        else:
            check("the approved post carries the image",
                  posted_row.image_path == image_path,
                  f"{posted_row.image_path} != {image_path}")
            check("the image came from a real source, never a fabricated one",
                  image_source in ("avatar", "graphic"), image_source)
            check("the draft projection showed HR the same image first",
                  mine[0]["image_url"] is not None
                  and mine[0]["image_url"].endswith(image_path.rsplit("/", 1)[-1]),
                  str(mine[0]["image_url"]))
            check("the image file really exists on disk",
                  (ROOT / image_path).exists(), image_path)

        check("approving the same draft twice is refused",
              _refused(lambda: svc.approve_draft(first_id, user, db),
                       "already_decided"))

        # --- dismiss ------------------------------------------------------
        second_id = mine[1]["id"]
        dismissed = svc.dismiss_draft(second_id, user, db)

        check("dismissing marks it dismissed",
              dismissed["status"] == svc.STATUS_DISMISSED)
        check("dismissing wrote no post",
              db.query(SocialPost).count() == posts_before + 1)
        check("a dismissed draft cannot then be posted",
              _refused(lambda: svc.approve_draft(second_id, user, db),
                       "already_decided"))

        check("the queue is empty once both are decided",
              not [d for d in svc.list_drafts(db)
                   if d["employee_id"] in [p.id for p in people]])
    finally:
        restore()
        cleanup(db, people)

    # --- a rejected draft has no route to the feed -----------------------
    people = [make_employee(db, first="Hisham", years_ago=5)]
    fake = FakeProvider(approve=False)
    restore = with_fake(fake)

    try:
        svc.run_daily(db, today=TODAY)
        draft = (db.query(CelebrationDraft)
                 .filter(CelebrationDraft.employee_id == people[0].id).first())

        check("a rejected draft is still stored for HR to see",
              draft is not None and draft.status == svc.STATUS_PENDING)
        check("it records that the reviewer refused it",
              draft.review_approved is False)
        check("it used the retry loop first",
              draft.retry_count == 2, str(draft.retry_count))
        check("the queue marks it not postable",
              not svc.draft_view(draft, db)["postable"])

        posts_before = db.query(SocialPost).count()
        check("posting a draft the reviewer rejected is refused",
              _refused(lambda: svc.approve_draft(draft.id, user, db),
                       "not_approved"))
        check("and no post was written",
              db.query(SocialPost).count() == posts_before)
    finally:
        restore()
        cleanup(db, people)


def _refused(call, expected_code: str) -> bool:
    try:
        call()
        return False
    except svc.CelebrationError as error:
        return error.code == expected_code


def main() -> int:
    print("=" * 74)
    print("AI EMPLOYEE CELEBRATION - the scheduled sweep")
    print("=" * 74)
    print("  The model is replaced by a fake provider; everything else is real.")
    print(f"  Running as if today were {TODAY.isoformat()}.")

    db = SessionLocal()
    try:
        test_detection(db)
        test_sweep(db)
        test_idempotence(db)
        test_no_auto_publish(db)
        test_hr_decisions(db)
    finally:
        db.close()

    print()
    print("=" * 74)
    print(f"  {passed} passed, {failed} failed")
    for item in failures:
        print(f"    FAILED: {item}")
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
