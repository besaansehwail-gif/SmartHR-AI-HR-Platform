"""AI Employee Celebration - the six occasions (birthday, work anniversary,
promotion, graduation, wedding, new baby).

    venv\\Scripts\\python.exe -m scripts.test_celebration_occasions

**Offline** for the workflow: the three agents are replaced by a fake provider
(`app/ai/provider.py`'s two methods) that ECHOES the occasion it was shown, so
what runs is the real detection SQL, the real `get_employee_events`, the real
graph, the real `run_daily`, and the real `celebration_drafts` table with its
UNIQUE constraint - everything except the model. The same arrangement as
`test_celebration_scheduler.py`, which still covers the anniversary sweep,
HR's approve/dismiss and no-auto-publish, and is unchanged.

The employee API part launches its own server on port 8048 (the model is not
used there; `SMARTHR_LLM_PROVIDER=none`).

Every employee this suite creates is named `CelebOcc-Test ...`, and every row
it writes - employees and their drafts - is removed at the end.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.celebration import agents, prompts  # noqa: E402
from app.ai.celebration.state import OCCASIONS  # noqa: E402
from app.ai.provider import LlmReply, ToolCall  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import CelebrationDraft, Employee, SocialPost  # noqa: E402
from app.services import celebration_service as svc  # noqa: E402
from scripts import test_helpers as e2e  # noqa: E402

passed = 0
failed: list[str] = []

TODAY = date(2026, 6, 15)       # fixed, so the suite is not seasonal
MARKER = "CelebOcc-Test"
PORT = 8048


def check(label: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed.append(label)
        print(f"  FAIL  {label}" + (f"   -> {detail}" if detail else ""))
    return bool(ok)


def section(title: str) -> None:
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74)


# ===========================================================================
# A fake model that echoes the detected occasion
# ===========================================================================

@dataclass
class EchoProvider:
    """Answers the Occasion Agent with the `type` of the (single) event it was
    shown - or `answer`, to simulate a model that names something else."""

    answer: str | None = None
    calls: int = 0
    seen: list[tuple[str, str]] = field(default_factory=list)

    name = "fake"
    model = "fake-model"
    configured = True

    def complete(self, system, messages, tools=None):
        tool = (tools or [{}])[0].get("name", "")
        text = messages[0]["content"]
        self.calls += 1
        self.seen.append((tool, text))
        if tool == prompts.OCCASION_TOOL:
            block = text.split("EVENTS FOUND IN SMARTHR'S RECORDS:\n", 1)[1].split("\n\nOCCASIONS", 1)[0]
            events = json.loads(block)
            occasion = self.answer or (events[0]["type"] if events else "none")
            years = events[0].get("years") if events else None
            payload = {"occasion": occasion, "years": years, "reason": "echoed the event"}
        elif tool == prompts.MESSAGE_TOOL:
            occasion = text.split("VERIFIED OCCASION: ", 1)[1].split("\n", 1)[0]
            payload = {"message": f"Celebrating a {occasion.replace('_', ' ')} today. Congratulations!"}
        else:
            payload = {"approved": True, "reason": "Every check passed.", "suggestions": None}
        return LlmReply(tool_call=ToolCall(name=tool, arguments=payload, id="fake"))

    def tool_exchange(self, reply, result_json):
        return []


def with_fake(fake):
    original = agents.get_provider
    agents.get_provider = lambda settings=None: fake
    return lambda: setattr(agents, "get_provider", original)


# ===========================================================================
# Fixtures
# ===========================================================================

CREATED: list[int] = []


def make(db, last: str, **dates) -> Employee:
    e = Employee(first_name=MARKER, last_name=last, employment_status="active", **dates)
    db.add(e)
    db.commit()
    db.refresh(e)
    CREATED.append(e.id)
    return e


def cleanup() -> None:
    db = SessionLocal()
    try:
        ids = [e.id for e in db.query(Employee).filter(Employee.first_name == MARKER).all()]
        if ids:
            db.query(CelebrationDraft).filter(CelebrationDraft.employee_id.in_(ids)).delete(
                synchronize_session=False)
            db.query(Employee).filter(Employee.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
        print(f"\n  cleanup: removed {len(ids)} test employee(s) and their drafts")
    finally:
        db.close()


def mine(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["employee_id"] in CREATED]


# ===========================================================================
# 1-2. Detection
# ===========================================================================

def test_detection(db) -> dict:
    section("1. Detection - one rule per date column, the anniversary unchanged")
    t = TODAY
    people = {
        "birthday": make(db, "Birthday", birth_date=date(1990, t.month, t.day)),
        "anniversary": make(db, "Anniversary", hire_date=date(2021, t.month, t.day)),
        "promotion": make(db, "Promotion", promotion_date=t),
        "graduation": make(db, "Graduation", graduation_date=t),
        "wedding": make(db, "Wedding", wedding_date=t),
        "new_baby": make(db, "NewBaby", new_baby_date=t),
        "two": make(db, "TwoOccasions", hire_date=date(2019, t.month, t.day),
                    birth_date=date(1985, t.month, t.day)),
        # none of these should be found today
        "nulls": make(db, "AllNull"),
        "tomorrow": make(db, "Tomorrow", birth_date=date(1990, 6, 16), promotion_date=t + timedelta(days=1)),
        "yesterday": make(db, "Yesterday", graduation_date=t - timedelta(days=1)),
        "past_year": make(db, "PastWedding", wedding_date=date(2019, t.month, t.day)),
        "born_today": make(db, "BornToday", birth_date=t),
        "hired_today": make(db, "HiredToday", hire_date=t),
        "far": make(db, "FarAway", new_baby_date=t + timedelta(days=30)),
    }
    found = mine(svc.celebrations_today(db, today=t))
    got = {(r["employee_id"], r["occasion"]) for r in found}

    for label, key, occasion in (
        ("birthday", "birthday", "birthday"),
        ("work anniversary", "anniversary", "work_anniversary"),
        ("promotion", "promotion", "promotion"),
        ("graduation", "graduation", "graduation"),
        ("wedding", "wedding", "wedding"),
        ("new baby", "new_baby", "new_baby"),
    ):
        check(f"{label}: detected on its date", (people[key].id, occasion) in got, str(got))

    check("one employee with a birthday AND an anniversary today -> two entries",
          {(people["two"].id, "birthday"), (people["two"].id, "work_anniversary")} <= got)
    check("multiple employees celebrating today are all found (8 entries in total)",
          len(found) == 8, str(sorted(got)))
    ignored = ("nulls", "tomorrow", "yesterday", "past_year", "born_today", "hired_today", "far")
    check("an employee with every optional date NULL has no occasion",
          not any(e == people["nulls"].id for e, _ in got))
    check("a birthday / promotion tomorrow is not today's", not any(e == people["tomorrow"].id for e, _ in got))
    check("a graduation yesterday is not today's", not any(e == people["yesterday"].id for e, _ in got))
    check("a wedding on this month/day in a PAST year is not a new wedding (one-off)",
          not any(e == people["past_year"].id for e, _ in got))
    check("a birth date of today is not a birthday", not any(e == people["born_today"].id for e, _ in got))
    check("hired today is still not a 0-year anniversary (unchanged rule)",
          not any(e == people["hired_today"].id for e, _ in got))
    check("a new baby 30 days away is not today's", not any(e == people["far"].id for e, _ in got))
    check("nothing that should be ignored was found", not any(
        e == people[k].id for k in ignored for e, _ in got))

    ann = [r for r in found if r["occasion"] == "work_anniversary" and r["employee_id"] == people["anniversary"].id]
    check("the anniversary entry keeps its years figure from hire_date", ann and ann[0]["years"] == 5, str(ann))
    check("non-anniversary entries carry no years (no age is ever computed)",
          all(r["years"] is None for r in found if r["occasion"] != "work_anniversary"))

    legacy = {r["employee_id"] for r in svc.anniversaries_today(db, today=t)} & set(CREATED)
    check("anniversaries_today() is unchanged: exactly the two hire-date matches",
          legacy == {people["anniversary"].id, people["two"].id}, str(legacy))

    # Leap day: a 29 February birthday is celebrated on 1 March in a common year.
    leap = make(db, "LeapDay", birth_date=date(2000, 2, 29))
    on_mar1 = mine(svc.celebrations_today(db, today=date(2027, 3, 1)))
    check("29 Feb birthday -> 1 March in a common year (the anniversary's rule)",
          (leap.id, "birthday") in {(r["employee_id"], r["occasion"]) for r in on_mar1})

    section("2. get_employee_events - the window, and not_recorded per person")
    ev = svc.get_employee_events(people["tomorrow"].id, db, today=t)
    types = {e["type"]: e for e in ev["events"]}
    check("a birthday tomorrow is in the 7-day window, 1 day away",
          types.get("birthday", {}).get("days_away") == 1, str(ev["events"]))
    check("a promotion tomorrow is in the window, with its date",
          types.get("promotion", {}).get("promotion_date") == (t + timedelta(days=1)).isoformat())
    far = svc.get_employee_events(people["far"].id, db, today=t)
    check("a date 30 days away is outside the window", far["events"] == [], str(far["events"]))
    past = svc.get_employee_events(people["yesterday"].id, db, today=t)
    check("a one-off date already past is not upcoming", past["events"] == [])
    nulls = svc.get_employee_events(people["nulls"].id, db, today=t)
    check("all-NULL employee: no events", nulls["events"] == [])
    check("...and all six occasions reported as not recorded, each naming its column",
          set(nulls["not_recorded"]) == set(svc.OCCASION_FIELDS)
          and "employees.birth_date" in nulls["not_recorded"]["birthday"])
    wed = svc.get_employee_events(people["wedding"].id, db, today=t)
    check("an employee with a wedding date: wedding is NOT in not_recorded",
          "wedding" not in wed["not_recorded"] and "birthday" in wed["not_recorded"])
    ann_ev = svc.get_employee_events(people["anniversary"].id, db, today=t)["events"]
    check("the work-anniversary event shape is unchanged",
          ann_ev == [{"type": "work_anniversary", "hire_date": "2021-06-15",
                      "anniversary_date": "2026-06-15", "days_away": 0, "years": 5}], str(ann_ev))
    return people


# ===========================================================================
# 3-5. The workflow
# ===========================================================================

def test_sweep(db, people) -> None:
    section("3. run_daily - each occasion through the existing workflow")
    fake = EchoProvider()
    restore = with_fake(fake)
    try:
        posts_before = db.query(SocialPost).count()
        summary = svc.run_daily(db, today=TODAY)
    finally:
        restore()

    drafts = db.query(CelebrationDraft).filter(CelebrationDraft.employee_id.in_(CREATED)).all()
    by_key = {(d.employee_id, d.occasion): d for d in drafts}
    check("a draft for each of the 8 detected (employee, occasion) pairs",
          len(drafts) == 8, str(sorted(by_key)))
    for occasion in svc.OCCASION_FIELDS:
        rows = [d for d in drafts if d.occasion == occasion]
        check(f"{occasion}: draft stored, pending, approved, keyed on its occasion",
              rows and all(d.status == "pending" and d.review_approved and d.occasion_date == TODAY
                           for d in rows), str([(d.occasion, d.status) for d in rows]))
    check("the employee with two occasions got two separate drafts",
          (people["two"].id, "birthday") in by_key and (people["two"].id, "work_anniversary") in by_key)
    check("years are stored only for the work anniversary",
          all((d.years is not None) == (d.occasion == "work_anniversary") for d in drafts),
          str([(d.occasion, d.years) for d in drafts]))
    check("the sweep published nothing", db.query(SocialPost).count() == posts_before)

    section("4. The agents receive the correct celebration type")
    occasion_calls = [text for tool, text in fake.seen if tool == prompts.OCCASION_TOOL]
    message_calls = [text for tool, text in fake.seen if tool == prompts.MESSAGE_TOOL]
    check("one Occasion Agent call per draft", len(occasion_calls) == 8, str(len(occasion_calls)))
    shown = []
    for text in occasion_calls:
        block = text.split("EVENTS FOUND IN SMARTHR'S RECORDS:\n", 1)[1].split("\n\nOCCASIONS", 1)[0]
        shown.append([e["type"] for e in json.loads(block)])
    check("each Occasion Agent call is shown exactly ONE event - the detected one",
          all(len(s) == 1 for s in shown), str(shown))
    check("...covering all six types",
          {s[0] for s in shown} == set(svc.OCCASION_FIELDS), str(shown))
    two = sorted(s[0] for s, text in zip(shown, occasion_calls) if "TwoOccasions" in text)
    check("the two-occasion employee had two runs, each shown only its own event",
          two == ["birthday", "work_anniversary"], str(two))
    for occasion in svc.OCCASION_FIELDS:
        text = next((t for t in message_calls if f"VERIFIED OCCASION: {occasion}\n" in t), "")
        check(f"Message Agent got '{occasion}' with its occasion guide",
              f"OCCASION GUIDE ({occasion})" in text)
    check("no Message Agent call mentions an age or a birth year",
          not any("1990" in t or "1985" in t for t in message_calls))

    section("5. No duplicates - the existing de-duplication rules")
    fake2 = EchoProvider()
    restore = with_fake(fake2)
    try:
        again = svc.run_daily(db, today=TODAY)
    finally:
        restore()
    check("a second run the same day prepares nothing", again["prepared"] == 0, str(again))
    check("...reports all 8 as already prepared", again["skipped_existing"] >= 8, str(again))
    check("...and spends no model call", fake2.calls == 0, str(fake2.calls))
    from sqlalchemy.exc import IntegrityError
    dup = CelebrationDraft(employee_id=people["wedding"].id, occasion="wedding", occasion_date=TODAY,
                           review_approved=False, retry_count=0, status="pending")
    db.add(dup)
    try:
        db.commit()
        check("the UNIQUE constraint refuses a duplicate wedding draft", False)
    except IntegrityError:
        db.rollback()
        check("the UNIQUE constraint refuses a duplicate wedding draft", True)


def test_mismatch(db) -> None:
    section("6. An agent that names a different occasion prepares nothing")
    person = make(db, "Mismatch", graduation_date=TODAY + timedelta(days=2))
    day = TODAY + timedelta(days=2)
    fake = EchoProvider(answer="wedding")
    restore = with_fake(fake)
    try:
        svc.run_daily(db, today=day)
    finally:
        restore()
    d = db.query(CelebrationDraft).filter(CelebrationDraft.employee_id == person.id).one_or_none()
    check("the draft is keyed on the DETECTED occasion (graduation)", d is not None and d.occasion == "graduation")
    check("...marked no_occasion with error_code occasion_mismatch, not pending",
          d is not None and d.status == "no_occasion" and d.error_code == "occasion_mismatch",
          str(d and (d.status, d.error_code)))

    section("7. Vocabulary kept in step")
    check("the agents' OCCASIONS = the six detected occasions + none",
          set(OCCASIONS) == set(svc.OCCASION_FIELDS) | {"none"})
    enum = set(prompts.OCCASION_SCHEMA["properties"]["occasion"]["enum"])
    check("the Occasion Agent's tool enum matches", enum == set(OCCASIONS))
    check("every occasion has a message guide", set(prompts.OCCASION_GUIDE) == set(svc.OCCASION_FIELDS))
    from app.ai.celebration.state import OccasionResult
    check("an unknown occasion from a model still becomes 'none'",
          OccasionResult.model_validate({"occasion": "retirement", "reason": "x"}).occasion == "none")


# ===========================================================================
# 8. The employee API (own server)
# ===========================================================================

class Server:
    def __enter__(self):
        self._p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "SMARTHR_LLM_PROVIDER": "none"})
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)
        raise SystemExit("test server did not start")

    def __exit__(self, *_):
        self._p.terminate()
        try:
            self._p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._p.kill()


def test_api() -> None:
    section("8. Employee API - the dates are managed through the existing CRUD")
    e2e.BASE = f"http://127.0.0.1:{PORT}"
    R = e2e.request
    e2e.ensure_staff_account("celebocc.hr@smarthr.test", 2)
    e2e.ensure_staff_account("celebocc.manager@smarthr.test", 3)
    hr, manager = e2e.login("celebocc.hr@smarthr.test"), e2e.login("celebocc.manager@smarthr.test")

    body = {"first_name": MARKER, "last_name": "Api", "hire_date": "2020-01-10",
            "birth_date": "1992-04-03", "wedding_date": "2026-10-01"}
    r = R("POST", "/employees/", token=hr, json_body=body)
    check("HR creates an employee with celebration dates", r.ok, repr(r))
    emp = r.body if r.ok else {}
    eid = emp.get("id")
    if eid:
        CREATED.append(eid)
    check("the response carries all five date fields",
          all(k in emp for k in ("birth_date", "promotion_date", "graduation_date",
                                 "wedding_date", "new_baby_date")))
    check("...with the values sent", emp.get("birth_date") == "1992-04-03" and emp.get("wedding_date") == "2026-10-01")

    old_client = {"first_name": MARKER, "last_name": "Api", "hire_date": "2020-01-10"}
    r = R("PUT", f"/employees/{eid}", token=hr, json_body=old_client)
    check("a PUT that omits the dates (an older client) does NOT erase them",
          r.ok and r.body.get("birth_date") == "1992-04-03" and r.body.get("wedding_date") == "2026-10-01",
          repr(r))
    r = R("PUT", f"/employees/{eid}", token=hr, json_body={**old_client, "wedding_date": None,
                                                          "promotion_date": "2026-06-01"})
    check("a PUT that sends null clears one; a value sets one",
          r.ok and r.body.get("wedding_date") is None and r.body.get("promotion_date") == "2026-06-01", repr(r))
    r = R("PUT", f"/employees/{eid}", token=hr, json_body={**old_client, "birth_date": "2999-01-01"})
    check("a birth date in the future is refused (422)", r.status == 422, repr(r))
    r = R("PUT", f"/employees/{eid}", token=hr, json_body={**old_client, "graduation_date": "not-a-date"})
    check("a malformed date is refused (422)", r.status == 422, repr(r))

    r = R("GET", "/employees/", token=hr)
    row = next((x for x in (r.body or []) if x.get("id") == eid), {})
    check("HR's list includes the dates", row.get("birth_date") == "1992-04-03")
    r = R("GET", f"/employees/{eid}", token=manager)
    check("a Manager reading another employee's record does NOT see personal dates",
          r.ok and "birth_date" not in r.body and "wedding_date" not in r.body, repr(r)[:200])
    r = R("PUT", f"/employees/{eid}", token=manager, json_body=old_client)
    check("a Manager cannot edit them (403, existing RBAC)", r.status == 403, repr(r))

    r = R("GET", "/social/celebration/status", token=hr)
    st = r.body if r.ok else {}
    check("status reports all six occasions available",
          set(st.get("occasions_available", [])) == set(svc.OCCASION_FIELDS) | {"none"}, str(st)[:200])
    check("status names the column each occasion is detected from",
          st.get("occasion_fields", {}).get("new_baby") == {"column": "new_baby_date", "yearly": False})


def main() -> int:
    print("SmartHR - AI Employee Celebration: six occasions")
    db = SessionLocal()
    try:
        people = test_detection(db)
        test_sweep(db, people)
        test_mismatch(db)
        with Server():
            test_api()
    finally:
        db.close()
        cleanup()
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
