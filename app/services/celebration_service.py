"""Employee facts for the AI Employee Celebration workflow.

**This module is the only place the celebration feature touches the
database**, and it is the reason no language model ever sees a connection.
The graph in `app/ai/celebration/` receives dictionaries produced here and
nothing else; a model that wants to know when somebody joined reads the
`hire_date` this module copied out of the row, or it does without.

Two functions are the tools the agents are given:

    get_employee(employee_id, db)         who they are
    get_employee_events(employee_id, db)  what actually happened to them

Both **read**, and the graph is handed their output rather than a session, so
"the celebration agents cannot change anybody's record" is a property of the
code rather than a rule the prompts ask a model to respect.

The scheduled half lives here too:

    anniversaries_today(db)   work anniversaries today, straight from hire_date
    celebrations_today(db)    every occasion today, from the employee's dates
    run_daily(db)             detect -> run the graph -> store a draft
    approve_draft(...)        HR posts it, through the ordinary post path
    dismiss_draft(...)        HR decides not to

Those four do write - to `celebration_drafts` and nowhere else. The agents
still cannot: they are called by `run_daily()`, they return dictionaries, and
this module does the storing. **Nothing here posts on its own.** Publishing
happens only inside `approve_draft()`, which a person has to call.

What SmartHR can evidence
-------------------------

Every occasion is detected from a date column on `employees` - never inferred
(`migrations/2026-09-27_employee_celebration_dates.sql` added all but the
first):

    occasion           column            recurs
    work_anniversary   hire_date         yearly, >= 1 completed year (unchanged)
    birthday           birth_date        yearly, on the month/day
    promotion          promotion_date    once, on that date
    graduation         graduation_date   once, on that date
    wedding            wedding_date      once, on that date
    new_baby           new_baby_date     once, on that date

The yearly two use the same month/day rule, including moving a 29 February
date to 1 March in a common year. The one-off four fire on the exact date.
Both kinds use the same windows the anniversary always used: the daily sweep
matches TODAY only, and `get_employee_events()` looks up to
`ANNIVERSARY_WINDOW_DAYS` ahead for a recruiter browsing.

A NULL column is reported per employee in `not_recorded`, **with the reason
why**, in the payload itself. "SmartHR holds no birth date for this person"
and "we looked and today is not their birthday" are different findings, and a
celebration feature that could not tell them apart would eventually invent
one. This is the rule `matching_service` follows with a null score.
"""

import logging
from datetime import date, datetime

from sqlalchemy import extract
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import social_storage
from app.ai.config import setting
from app.models import (
    CelebrationDraft,
    Department,
    Employee,
    Position,
    SocialProfile,
    User,
)

logger = logging.getLogger("smarthr.ai.celebration")

#: The original occasion, still detected exactly as before. Named once so the
#: detection query, the draft row and the uniqueness key cannot drift apart.
OCCASION_ANNIVERSARY = "work_anniversary"
OCCASION_BIRTHDAY = "birthday"

#: occasion -> (employees column, recurs yearly?). The single source of truth
#: for which date means which occasion; detection, the events tool, the
#: status endpoint and the tests all read it.
OCCASION_FIELDS: dict[str, tuple[str, bool]] = {
    "birthday": ("birth_date", True),
    "work_anniversary": ("hire_date", True),
    "promotion": ("promotion_date", False),
    "graduation": ("graduation_date", False),
    "wedding": ("wedding_date", False),
    "new_baby": ("new_baby_date", False),
}

#: Human wording for `not_recorded` - what the missing column is.
_FIELD_WORDS = {
    "birth_date": "birth date",
    "hire_date": "hire date",
    "promotion_date": "promotion date",
    "graduation_date": "graduation date",
    "wedding_date": "wedding date",
    "new_baby_date": "new baby date",
}

#: The stored name of the reusable celebration banner, written by
#: `scripts/seed_celebration_image.py`. Unset - or pointing at a file that is
#: not there - means celebrations carry no image, which is a working state
#: rather than a broken one.
CELEBRATION_IMAGE_VARIABLE = "SMARTHR_CELEBRATION_IMAGE"

#: What a draft can be. `no_occasion` is recorded rather than skipped so the
#: same person's same day is not re-asked of the model on every run.
STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_DISMISSED = "dismissed"
STATUS_NO_OCCASION = "no_occasion"

#: How close to the anniversary still counts as "now". A recruiter opening
#: the Social Hub on Monday should still be offered Saturday's anniversary,
#: and a week is the window `build_attention_items()` already uses for
#: upcoming interviews.
ANNIVERSARY_WINDOW_DAYS = 7

#: Occasions SmartHR has NO column for at all. Empty since every occasion in
#: the vocabulary now has one; kept (and still sent) so the payload shape and
#: the status endpoint do not change. What is missing for ONE person is in
#: `not_recorded_for()`.
NOT_RECORDED: dict[str, str] = {}


def not_recorded_for(employee: Employee) -> dict[str, str]:
    """The occasions this employee has no date for, with the reason.

    Shown to the Occasion Agent, whose prompt says an occasion listed here
    can never be its answer.
    """
    missing = dict(NOT_RECORDED)
    for occasion, (column, _) in OCCASION_FIELDS.items():
        if getattr(employee, column) is None:
            missing[occasion] = (
                f"SmartHR holds no {_FIELD_WORDS[column]} for this employee "
                f"(employees.{column} is empty), so a {occasion.replace('_', ' ')} "
                "cannot be established from any record."
            )
    return missing


class CelebrationError(Exception):
    """A celebration could not be prepared. Carries a machine-readable code."""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


def _full_name(employee: Employee) -> str:
    return f"{employee.first_name} {employee.last_name}".strip()


def get_employee(employee_id: int, db: Session) -> dict:
    """The first tool: who this person is, as SmartHR records them.

    Built field by field rather than by serialising the row, which is the
    rule `opportunity_service.public_job()` and `social_service.actor_map()`
    already follow: a projection that starts from everything and removes the
    private parts leaks whatever is added to the table next. A celebration
    needs a name, a job title and a department - not a phone number, not a
    manager, and not an employment status.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if employee is None:
        raise CelebrationError(
            f"There is no employee {employee_id}.", code="not_found"
        )

    position = (
        db.query(Position).filter(Position.id == employee.position_id).first()
        if employee.position_id
        else None
    )
    department = (
        db.query(Department).filter(Department.id == employee.department_id).first()
        if employee.department_id
        else None
    )
    account = (
        db.query(User).filter(User.id == employee.user_id).first()
        if employee.user_id
        else None
    )

    return {
        "employee_id": employee.id,
        "name": _full_name(employee),
        "first_name": employee.first_name,
        "position_title": position.title if position else None,
        "department_name": department.name if department else None,
        # The Social Hub keys on users.id, so a celebration that is ever
        # posted needs this. None is a legitimate state: most employees rows
        # have no account.
        "user_id": account.id if account else None,
    }


def years_of_service(hire_date: date, today: date) -> int:
    """Whole years between two dates, counted the way a person counts them.

    Not `days // 365`: that drifts a day every leap year and would tell
    somebody they had been here nine years on their tenth anniversary.
    """
    years = today.year - hire_date.year
    if (today.month, today.day) < (hire_date.month, hire_date.day):
        years -= 1
    return max(years, 0)


def _next_anniversary(hire_date: date, today: date) -> date:
    """The next time this date comes round, today included.

    29 February is moved to 1 March in a common year rather than skipped,
    because somebody hired on a leap day still has an anniversary.
    """
    def on(year: int) -> date:
        try:
            return date(year, hire_date.month, hire_date.day)
        except ValueError:
            return date(year, 3, 1)

    this_year = on(today.year)
    return this_year if this_year >= today else on(today.year + 1)


def get_employee_events(employee_id: int, db: Session, *, today: date | None = None) -> dict:
    """The second tool: what SmartHR can actually evidence about this person.

    Returns facts, never a conclusion - deciding which of these is *the*
    occasion is the Occasion Agent's job, and leaving that decision here
    would make the agent decorative. What this does guarantee is that every
    date in the payload was copied out of a row.

    `today` is injectable so a test can stand on somebody's anniversary
    without waiting a year for it. Nothing in production passes it.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if employee is None:
        raise CelebrationError(
            f"There is no employee {employee_id}.", code="not_found"
        )

    today = today or datetime.utcnow().date()
    events: list[dict] = []

    if employee.hire_date:
        upcoming = _next_anniversary(employee.hire_date, today)
        days_away = (upcoming - today).days
        # Years completed *on that anniversary*, which is what a message
        # would say - not years completed today.
        years = years_of_service(employee.hire_date, upcoming)

        if days_away <= ANNIVERSARY_WINDOW_DAYS and years >= 1:
            events.append({
                "type": "work_anniversary",
                "hire_date": employee.hire_date.isoformat(),
                "anniversary_date": upcoming.isoformat(),
                "days_away": days_away,
                "years": years,
            })

    # Birthday: yearly, on the month/day - the anniversary's own date rule.
    # No age is computed or sent: a celebration does not state one.
    if employee.birth_date:
        upcoming = _next_anniversary(employee.birth_date, today)
        days_away = (upcoming - today).days
        if days_away <= ANNIVERSARY_WINDOW_DAYS and upcoming.year > employee.birth_date.year:
            events.append({
                "type": OCCASION_BIRTHDAY,
                "occasion_date": upcoming.isoformat(),
                "days_away": days_away,
            })

    # The one-off occasions: celebrated on the date itself, inside the same
    # window. A date already past is not "upcoming", exactly as a past
    # anniversary is not.
    for occasion, (column, yearly) in OCCASION_FIELDS.items():
        if yearly:
            continue
        on = getattr(employee, column)
        if on is None:
            continue
        days_away = (on - today).days
        if 0 <= days_away <= ANNIVERSARY_WINDOW_DAYS:
            events.append({
                "type": occasion,
                column: on.isoformat(),
                "occasion_date": on.isoformat(),
                "days_away": days_away,
            })

    return {
        "employee_id": employee.id,
        "today": today.isoformat(),
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "events": events,
        # The occasions this person has no date for, with the reason - not
        # "today is an ordinary day". The prompt shows this to the model so
        # it can tell the two apart.
        "not_recorded": not_recorded_for(employee),
    }


# ===========================================================================
# The scheduled half: detect, run, store
# ===========================================================================

def anniversaries_today(db: Session, *, today: date | None = None) -> list[dict]:
    """Everybody whose hire date falls on today's month and day.

    Arithmetic and SQL, no model: the scheduler must not spend a model call to
    discover that nobody is celebrating, and "is today their anniversary" is a
    question the database can answer exactly.

    The rules, each one from the brief:

      * `hire_date IS NULL` is skipped - there is nothing to compare, and a
        person with no hire date on record is not a person whose anniversary
        we may guess at;
      * the month and the day must both equal today's, so this is the *day*
        itself rather than the seven-day window `get_employee_events()` uses
        for a recruiter browsing;
      * a completed year is required, so somebody hired this morning is not
        told they have been here zero years.

    29 February: in a common year a leap-day hire has no 29th to match, so
    they are picked up on 1 March - the same day `_next_anniversary()` moves
    them to, so the two halves of this feature agree about when it is.
    """
    today = today or datetime.utcnow().date()

    rows = (
        db.query(Employee)
        .filter(Employee.hire_date.isnot(None))
        .filter(extract("month", Employee.hire_date) == today.month)
        .filter(extract("day", Employee.hire_date) == today.day)
        .order_by(Employee.id)
        .all()
    )

    if today.month == 3 and today.day == 1 and not _is_leap(today.year):
        rows += (
            db.query(Employee)
            .filter(Employee.hire_date.isnot(None))
            .filter(extract("month", Employee.hire_date) == 2)
            .filter(extract("day", Employee.hire_date) == 29)
            .order_by(Employee.id)
            .all()
        )

    found: list[dict] = []
    for employee in rows:
        years = years_of_service(employee.hire_date, today)
        if years < 1:
            continue
        found.append({
            "employee_id": employee.id,
            "name": _full_name(employee),
            "hire_date": employee.hire_date.isoformat(),
            "years": years,
        })

    return found


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _on_month_day(db: Session, column, today: date) -> list[Employee]:
    """Employees whose `column` falls on today's month/day (29 Feb -> 1 Mar
    in a common year) - the anniversary's rule, for any yearly date."""
    rows = (
        db.query(Employee)
        .filter(column.isnot(None))
        .filter(extract("month", column) == today.month)
        .filter(extract("day", column) == today.day)
        .order_by(Employee.id)
        .all()
    )
    if today.month == 3 and today.day == 1 and not _is_leap(today.year):
        rows += (
            db.query(Employee)
            .filter(column.isnot(None))
            .filter(extract("month", column) == 2)
            .filter(extract("day", column) == 29)
            .order_by(Employee.id)
            .all()
        )
    return rows


def celebrations_today(db: Session, *, today: date | None = None) -> list[dict]:
    """Every occasion falling TODAY, one entry per (employee, occasion).

    The sweep's detection, extended from `anniversaries_today()` - which is
    still what finds work anniversaries, unchanged. SQL and arithmetic only;
    no model is spent on an ordinary day. Someone with two occasions today
    (a birthday and an anniversary) gets two entries, and later two drafts,
    because they are two celebrations.
    """
    today = today or datetime.utcnow().date()
    found: list[dict] = []

    for row in anniversaries_today(db, today=today):
        found.append({**row, "occasion": OCCASION_ANNIVERSARY,
                      "occasion_date": today.isoformat()})

    for employee in _on_month_day(db, Employee.birth_date, today):
        if employee.birth_date.year >= today.year:
            continue  # not a birthday yet: a date this year or in the future
        found.append({
            "employee_id": employee.id,
            "name": _full_name(employee),
            "occasion": OCCASION_BIRTHDAY,
            "occasion_date": today.isoformat(),
            "years": None,
        })

    for occasion, (column, yearly) in OCCASION_FIELDS.items():
        if yearly:
            continue
        attribute = getattr(Employee, column)
        for employee in db.query(Employee).filter(attribute == today).order_by(Employee.id).all():
            found.append({
                "employee_id": employee.id,
                "name": _full_name(employee),
                "occasion": occasion,
                "occasion_date": today.isoformat(),
                "years": None,
            })

    order = list(OCCASION_FIELDS)
    found.sort(key=lambda r: (r["employee_id"], order.index(r["occasion"])))
    return found


def draft_for(
    employee_id: int, occasion: str, occasion_date: date, db: Session
) -> CelebrationDraft | None:
    """The existing draft for this person, this occasion, this date - if any.

    Checked before the graph runs so a second run of the day costs no model
    calls. It is **not** the duplicate protection - that is the UNIQUE
    constraint, which holds even when two runs race past this check.
    """
    return (
        db.query(CelebrationDraft)
        .filter(CelebrationDraft.employee_id == employee_id)
        .filter(CelebrationDraft.occasion == occasion)
        .filter(CelebrationDraft.occasion_date == occasion_date)
        .first()
    )


def run_daily(
    db: Session, *, today: date | None = None, dry_run: bool = False
) -> dict:
    """The scheduled job: find today's celebrations and prepare one each.

    Each (employee, occasion) gets **its own run of the graph** and its own
    draft row - three people celebrating today are three separate
    celebrations, never one post that lists them. The graph is shown only the
    ONE event that was detected, so the Occasion Agent confirms that event
    rather than choosing among several; if it answers anything else, nothing
    is prepared (`occasion_mismatch`).

    Nothing is published. The most this does is write a `pending` draft for a
    person to look at, which is the whole design: the AI detects, writes and
    reviews; HR decides.
    """
    from app.ai.celebration.graph import run_celebration

    today = today or datetime.utcnow().date()
    candidates = celebrations_today(db, today=today)

    summary = {
        "date": today.isoformat(),
        "found": len(candidates),
        "prepared": 0,
        "skipped_existing": 0,
        "no_occasion": 0,
        "failed": 0,
        "dry_run": dry_run,
        "drafts": [],
    }

    logger.info(
        "Celebration sweep starting | date=%s | candidates=%s | dry_run=%s",
        today.isoformat(), len(candidates), dry_run,
    )

    for candidate in candidates:
        employee_id = candidate["employee_id"]
        detected = candidate["occasion"]

        existing = draft_for(employee_id, detected, today, db)
        if existing is not None:
            summary["skipped_existing"] += 1
            logger.info(
                "Celebration already prepared | employee_id=%s occasion=%s date=%s status=%s",
                employee_id, detected, today.isoformat(), existing.status,
            )
            continue

        if dry_run:
            summary["drafts"].append({
                "employee_id": employee_id,
                "employee_name": candidate["name"],
                "occasion": detected,
                "years": candidate["years"],
                "would_run": True,
            })
            continue

        try:
            employee = get_employee(employee_id, db)
            events = get_employee_events(employee_id, db, today=today)
            # Only the event this draft is for, and only today's instance of it.
            events = {**events, "events": [
                e for e in events["events"]
                if e["type"] == detected and e.get("days_away") == 0
            ]}
            final = run_celebration(employee, events)
        except Exception:
            # One employee's failure must not stop the sweep: the next person
            # having an anniversary today is not implicated in it.
            summary["failed"] += 1
            logger.exception(
                "Celebration workflow failed | employee_id=%s", employee_id
            )
            continue

        occasion = final.get("occasion") or "none"
        found_one = occasion == detected
        error_code = final.get("error_code")
        if occasion not in ("none", detected):
            # The agent named an occasion that was not the one detected. That
            # is not a celebration SmartHR can evidence, so none is prepared.
            error_code = "occasion_mismatch"

        draft = CelebrationDraft(
            employee_id=employee_id,
            # The row is keyed on the occasion we detected, even when the
            # agent declined it - otherwise "the agent said none" would not be
            # remembered and the model would be asked again on every run.
            occasion=detected,
            occasion_date=today,
            years=final.get("years") if detected == OCCASION_ANNIVERSARY else None,
            message=final.get("message") or None,
            review_approved=bool(final.get("review_approved")),
            review_reason=final.get("review_reason") or None,
            review_suggestions=final.get("review_suggestions") or None,
            retry_count=int(final.get("retry_count") or 0),
            error_code=error_code,
            status=STATUS_PENDING if found_one else STATUS_NO_OCCASION,
        )

        db.add(draft)
        try:
            db.commit()
        except IntegrityError:
            # The UNIQUE constraint refused it, which means another run got
            # there first. That is the protection working, not an error.
            db.rollback()
            summary["skipped_existing"] += 1
            logger.info(
                "Celebration draft already existed | employee_id=%s date=%s",
                employee_id, today.isoformat(),
            )
            continue

        db.refresh(draft)

        if found_one:
            summary["prepared"] += 1
        else:
            summary["no_occasion"] += 1

        summary["drafts"].append(draft_view(draft, db))

        logger.info(
            "Celebration prepared | draft_id=%s employee_id=%s occasion=%s years=%s "
            "approved=%s retries=%s status=%s",
            draft.id, employee_id, detected, draft.years, draft.review_approved,
            draft.retry_count, draft.status,
        )

    logger.info(
        "Celebration sweep finished | prepared=%s skipped=%s none=%s failed=%s",
        summary["prepared"], summary["skipped_existing"],
        summary["no_occasion"], summary["failed"],
    )
    return summary


# ===========================================================================
# HR's queue
# ===========================================================================

def celebration_image(employee_id: int, db: Session) -> tuple[str | None, str]:
    """The image a celebration should carry, and where it came from.

    Returns `(stored_path, source)` where source is one of:

        "avatar"       the employee's own profile picture - real data
        "graphic"      the reusable celebration banner
        "none"         there is nothing to attach, and the post is text

    **It is never a photograph of a person SmartHR does not have.** There is
    no image column on `employees`; the only picture in the system is the
    avatar on `social_profiles`, which is keyed on a *user account*, and most
    employee rows have none. A stock face beside a real colleague's name
    would be a fabricated identity, which is the thing this whole feature is
    built not to do - so the fallback is decoration, plainly abstract.

    **Resolved when it is needed, not stored on the draft.** The draft row
    carries no image column, which keeps a schema change out of this and has
    a second benefit: an employee who uploads an avatar between the sweep and
    HR pressing Post gets their own picture on it.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if employee is not None and employee.user_id:
        profile = (
            db.query(SocialProfile)
            .filter(SocialProfile.user_id == employee.user_id)
            .first()
        )
        if profile is not None and (profile.avatar_path or "").strip():
            return profile.avatar_path, "avatar"

    name = (setting(CELEBRATION_IMAGE_VARIABLE) or "").strip()
    if name and social_storage.resolve_media(name) is not None:
        # Validated through the Social Hub's own resolver, so a name that is
        # not a stored image - or is an attempt at a path - never becomes one.
        return f"uploads/social/{name}", "graphic"

    return None, "none"


def draft_view(draft: CelebrationDraft, db: Session) -> dict:
    """One draft, built field by field for HR's panel.

    Built rather than serialised, the rule `public_job()` and
    `interview_room_view()` already follow: a projection that starts from the
    row and removes what it should not carry leaks the next column somebody
    adds.
    """
    employee = db.query(Employee).filter(Employee.id == draft.employee_id).first()
    image_path, image_source = celebration_image(draft.employee_id, db)

    return {
        "id": draft.id,
        "employee_id": draft.employee_id,
        "employee_name": _full_name(employee) if employee else None,
        # The image the post would carry, so HR sees it before deciding -
        # a URL the browser can fetch, never the path on disk.
        "image_url": social_storage.media_url(image_path),
        "image_source": image_source,
        "occasion": draft.occasion,
        "occasion_date": draft.occasion_date.isoformat(),
        "years": draft.years,
        "message": draft.message,
        "review": {
            "approved": bool(draft.review_approved),
            "reason": draft.review_reason or "",
            "suggestions": draft.review_suggestions,
        },
        "retry_count": draft.retry_count,
        "error_code": draft.error_code,
        "status": draft.status,
        "post_id": draft.post_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "decided_at": draft.decided_at.isoformat() if draft.decided_at else None,
        # Only a draft the Review Agent approved may be posted. The UI reads
        # this rather than re-deriving the rule and drifting from it.
        "postable": (
            draft.status == STATUS_PENDING
            and bool(draft.review_approved)
            and bool((draft.message or "").strip())
        ),
    }


def list_drafts(
    db: Session, *, status: str | None = STATUS_PENDING, limit: int = 50
) -> list[dict]:
    """HR's queue. `status=None` returns every draft, newest first."""
    query = db.query(CelebrationDraft)

    if status:
        query = query.filter(CelebrationDraft.status == status)

    rows = (
        query.order_by(
            CelebrationDraft.created_at.desc(), CelebrationDraft.id.desc()
        )
        .limit(max(1, min(int(limit or 50), 200)))
        .all()
    )
    return [draft_view(row, db) for row in rows]


def approve_draft(draft_id: int, user: User, db: Session) -> dict:
    """HR posts a prepared celebration. **The only way one reaches the feed.**

    It goes through `social_service.create_post()` - the same function the
    composer calls - so the post is moderated and audited exactly as anything
    a colleague types. There is no second publishing path, and the scheduler
    cannot reach this one: it takes a `User`, and only a signed-in recruiter
    has one.
    """
    from app.services import social_service

    draft = (
        db.query(CelebrationDraft).filter(CelebrationDraft.id == draft_id).first()
    )

    if draft is None:
        raise CelebrationError(f"There is no draft {draft_id}.", code="not_found")

    if draft.status != STATUS_PENDING:
        raise CelebrationError(
            f"That celebration is already {draft.status}.", code="already_decided"
        )

    if not draft.review_approved or not (draft.message or "").strip():
        # The Review Agent's veto is real on this side too: a rejected draft
        # has no route to the feed, which is what keeps the reviewer from
        # being a label in the UI.
        raise CelebrationError(
            "That celebration was not approved by the review agent, so it "
            "cannot be posted.",
            code="not_approved",
        )

    # The image is attached HERE, at the moment a person approves - never by
    # the sweep. Until this line runs there is no post and no picture
    # anywhere near the feed.
    image_path, image_source = celebration_image(draft.employee_id, db)

    post = social_service.create_post(
        user, db, content=draft.message, image_path=image_path,
        audience="company",
    )

    draft.status = STATUS_POSTED
    draft.post_id = post["id"]
    draft.decided_by = user.id
    draft.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)

    logger.info(
        "Celebration posted by a person | draft_id=%s post_id=%s user_id=%s "
        "image=%s",
        draft.id, post["id"], user.id, image_source,
    )

    return {"draft": draft_view(draft, db), "post": post}


def dismiss_draft(draft_id: int, user: User, db: Session) -> dict:
    """HR decides not to post it. The row stays, so the decision is legible."""
    draft = (
        db.query(CelebrationDraft).filter(CelebrationDraft.id == draft_id).first()
    )

    if draft is None:
        raise CelebrationError(f"There is no draft {draft_id}.", code="not_found")

    if draft.status != STATUS_PENDING:
        raise CelebrationError(
            f"That celebration is already {draft.status}.", code="already_decided"
        )

    draft.status = STATUS_DISMISSED
    draft.decided_by = user.id
    draft.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)

    logger.info("Celebration dismissed | draft_id=%s user_id=%s", draft.id, user.id)
    return draft_view(draft, db)
