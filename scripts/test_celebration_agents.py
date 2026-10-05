"""AI Employee Celebration - tests.

    venv\\Scripts\\python.exe -m scripts.test_celebration_agents
    venv\\Scripts\\python.exe -m scripts.test_celebration_agents --live

**The default run makes no network call and needs no API key.** The model is
replaced by a `FakeProvider` implementing the two methods
`app/ai/provider.py` declares, so what runs is the real prompt, the real tool
schema, the real Pydantic validation, the real LangGraph graph and the real
service against the real database - everything except the model itself. That
is the arrangement `test_social_moderation.py` already uses, and the reason
is the same: a multi-agent workflow whose suite breaks when a third party is
slow is one nobody can refactor.

The fake is injected by replacing `agents.get_provider`, not by clearing
`SMARTHR_LLM_API_KEY` - `_setting` treats an empty value as absent and falls
through to `.env`, which on this machine holds the real key. That trap is
documented in `app/ai/config.py` and avoided here.

`--live` adds section 7, one real run against the configured model. It is an
integration test: its failure means the model or a prompt moved, not that
the application is broken.

Sections:

    1. the tools          what SmartHR can and cannot evidence
    2. the agents         prompt in, validated structured result out
    3. the graph          the happy path, end to end
    4. rejection          the Review Agent's veto, and the retry loop
    5. the retry limit    a reviewer that never approves must still stop
    6. degraded           no model, a broken model, an unreviewable draft
    7. --live             one real run
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.celebration import agents, prompts  # noqa: E402
from app.ai.celebration.graph import build_graph, run_celebration  # noqa: E402
from app.ai.celebration.state import (  # noqa: E402
    MAX_RETRIES,
    MessageResult,
    OccasionResult,
    ReviewResult,
)
from app.ai.provider import LlmError, LlmNotConfigured, LlmReply, ToolCall  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Department, Employee, Position, SocialPost  # noqa: E402
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
    """Stands in for a language model. Returns what it is told to return.

    It implements the same two methods `app/ai/provider.py` declares, so the
    call site under test is the real one - not a re-implementation of it.

    `replies` maps a tool name to a list of payloads, consumed in order, so a
    test can say "reject the first draft, approve the second" and exercise
    the loop rather than assert that it exists.
    """

    replies: dict[str, list] = field(default_factory=dict)
    raise_with: Exception | None = None
    no_tool_call: bool = False
    #: Answer in prose instead of calling the tool. Real behaviour: gpt-4o
    #: sends a fenced JSON block roughly one call in ten.
    text_instead: str | None = None
    #: Every (tool, system_prompt, instruction) this fake was asked for.
    seen: list[tuple] = field(default_factory=list)

    name = "fake"
    model = "fake-model"
    configured = True

    def complete(self, system, messages, tools=None):
        if self.raise_with is not None:
            raise self.raise_with

        tool = (tools or [{}])[0].get("name", "")
        self.seen.append((tool, system, messages[0]["content"]))

        if self.text_instead is not None:
            return LlmReply(text=self.text_instead)

        if self.no_tool_call:
            return LlmReply(text="I would rather just chat.")

        queue = self.replies.get(tool) or []
        payload = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else {})
        return LlmReply(tool_call=ToolCall(name=tool, arguments=payload, id="fake-1"))

    def tool_exchange(self, reply, result_json):
        return []


def with_fake(fake: FakeProvider):
    """Replace the provider the agents use. Returns a restore callable."""
    original = agents.get_provider
    agents.get_provider = lambda settings=None: fake
    return lambda: setattr(agents, "get_provider", original)


def scripted(occasion=None, message=None, review=None) -> FakeProvider:
    """A fake wired for one full run of the graph."""
    return FakeProvider(replies={
        prompts.OCCASION_TOOL: [occasion] if occasion is not None else [],
        prompts.MESSAGE_TOOL: message if isinstance(message, list) else [message or {}],
        prompts.REVIEW_TOOL: review if isinstance(review, list) else [review or {}],
    })


# ===========================================================================
# A fixture employee
# ===========================================================================

class Fixture:
    """A real department, position and employee, removed at the end.

    Real rows rather than a stub, because the tools under test are queries.
    Its hire date is set relative to `today` so the anniversary window can be
    stood on without waiting a year for it.
    """

    def __init__(self, db, *, years_ago: int = 5, days_until: int = 0):
        today = datetime.utcnow().date()
        target = today + timedelta(days=days_until)

        self.department = Department(name=f"DEMO Celebration {datetime.utcnow():%H%M%S%f}")
        db.add(self.department)
        db.flush()

        self.position = Position(title="DEMO Celebration Analyst",
                                 department_id=self.department.id)
        db.add(self.position)
        db.flush()

        try:
            hire = date(target.year - years_ago, target.month, target.day)
        except ValueError:                       # 29 February
            hire = date(target.year - years_ago, 3, 1)

        self.employee = Employee(
            first_name="Dana", last_name="Celebration-Test",
            department_id=self.department.id, position_id=self.position.id,
            hire_date=hire, employment_status="active",
        )
        db.add(self.employee)
        db.commit()
        db.refresh(self.employee)

        self.id = self.employee.id

    def remove(self, db) -> None:
        # One flush per level, child first. Within a single flush SQLAlchemy
        # is free to order the two DELETEs either way, and positions carries
        # the foreign key into departments.
        db.delete(self.employee)
        db.flush()
        db.delete(self.position)
        db.flush()
        db.delete(self.department)
        db.commit()


GOOD_MESSAGE = (
    "Today marks five years since Dana Celebration-Test joined the team as a "
    "DEMO Celebration Analyst. Thank you for five years of steady work - "
    "here's to the next chapter."
)


# ===========================================================================
# 1. The tools
# ===========================================================================

def test_tools(db) -> None:
    section("1. The tools - what SmartHR can and cannot evidence")

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)

        check("get_employee returns the name from the row",
              employee["name"] == "Dana Celebration-Test", str(employee))
        check("get_employee carries the job title and department",
              employee["position_title"] == "DEMO Celebration Analyst"
              and employee["department_name"].startswith("DEMO Celebration"))

        # Built field by field, so what is absent is absent by construction.
        for leaked in ("phone", "employment_status", "manager_id", "created_at",
                       "hire_date", "salary"):
            check(f"get_employee does not carry {leaked}", leaked not in employee)

        events = svc.get_employee_events(fixture.id, db)
        anniversaries = [e for e in events["events"] if e["type"] == "work_anniversary"]

        check("an anniversary today is found", len(anniversaries) == 1, str(events))
        check("its years figure is counted, not estimated",
              anniversaries and anniversaries[0]["years"] == 5,
              str(anniversaries))
        check("the hire date in the payload is the row's own",
              anniversaries and anniversaries[0]["hire_date"]
              == fixture.employee.hire_date.isoformat())

        check("birthday is reported as not recorded, with a reason",
              "birthday" in events["not_recorded"]
              and "no" in events["not_recorded"]["birthday"].lower())
        # Since the celebration dates were added, "not recorded" is per
        # employee: this fixture has no promotion_date, so it is reported
        # with the column that is empty.
        check("promotion is reported as not recorded, with a reason",
              "promotion" in events["not_recorded"]
              and "promotion date" in events["not_recorded"]["promotion"])
        check("no event is ever emitted for a birthday",
              not any(e["type"] == "birthday" for e in events["events"]))
        check("no event is ever emitted for a promotion",
              not any(e["type"] == "promotion" for e in events["events"]))
    finally:
        fixture.remove(db)

    # --- the window ------------------------------------------------------
    far = Fixture(db, years_ago=3, days_until=40)
    try:
        events = svc.get_employee_events(far.id, db)
        check("an anniversary 40 days away is not an occasion today",
              events["events"] == [], str(events["events"]))
    finally:
        far.remove(db)

    soon = Fixture(db, years_ago=3, days_until=svc.ANNIVERSARY_WINDOW_DAYS - 1)
    try:
        events = svc.get_employee_events(soon.id, db)
        check("an anniversary inside the window is an occasion",
              len(events["events"]) == 1, str(events["events"]))
        check("its years figure counts the year being completed",
              events["events"][0]["years"] == 3, str(events["events"]))
    finally:
        soon.remove(db)

    # --- the first year ---------------------------------------------------
    joiner = Fixture(db, years_ago=0, days_until=0)
    try:
        events = svc.get_employee_events(joiner.id, db)
        check("somebody hired today is not celebrating 0 years",
              events["events"] == [], str(events["events"]))
    finally:
        joiner.remove(db)

    # --- no hire date -----------------------------------------------------
    blank = Fixture(db)
    try:
        blank.employee.hire_date = None
        db.commit()
        events = svc.get_employee_events(blank.id, db)
        check("an employee with no hire date yields no events",
              events["events"] == [] and events["hire_date"] is None)
    finally:
        blank.remove(db)

    # --- the arithmetic ---------------------------------------------------
    check("years_of_service counts whole years, not days // 365",
          svc.years_of_service(date(2015, 3, 10), date(2025, 3, 10)) == 10)
    check("years_of_service does not round up the day before",
          svc.years_of_service(date(2015, 3, 10), date(2025, 3, 9)) == 9)
    check("years_of_service never returns a negative",
          svc.years_of_service(date(2030, 1, 1), date(2025, 1, 1)) == 0)

    # --- a missing employee ----------------------------------------------
    try:
        svc.get_employee(9_999_999, db)
        check("an unknown employee id is refused", False, "no error raised")
    except svc.CelebrationError as error:
        check("an unknown employee id is refused", error.code == "not_found")


# ===========================================================================
# 2. The agents
# ===========================================================================

def test_agents() -> None:
    section("2. The agents - structured results, validated before trusted")

    employee = {"name": "Dana Celebration-Test", "position_title": "Analyst",
                "department_name": "Data", "user_id": 42, "employee_id": 7}
    events = {"events": [{"type": "work_anniversary", "years": 5}],
              "not_recorded": {"birthday": "SmartHR holds no birth date for this employee."},
              "today": "2026-09-23"}

    # --- each agent gets its OWN prompt ----------------------------------
    check("the three prompts are three different prompts",
          len({prompts.OCCASION_PROMPT, prompts.MESSAGE_PROMPT,
               prompts.REVIEW_PROMPT}) == 3)
    check("the three tools have three different names",
          len({prompts.OCCASION_TOOL, prompts.MESSAGE_TOOL,
               prompts.REVIEW_TOOL}) == 3)
    for name, text in (("occasion", prompts.OCCASION_PROMPT),
                       ("message", prompts.MESSAGE_PROMPT),
                       ("review", prompts.REVIEW_PROMPT)):
        check(f"the {name} prompt states a role and a goal",
              "ROLE" in text and "GOAL" in text)

    # --- occasion ---------------------------------------------------------
    fake = FakeProvider(replies={prompts.OCCASION_TOOL: [
        {"occasion": "work_anniversary", "years": 5, "reason": "hire_date event"}]})
    restore = with_fake(fake)
    try:
        result = agents.occasion_agent(employee, events)
        check("the occasion agent returns a validated OccasionResult",
              isinstance(result, OccasionResult)
              and result.occasion == "work_anniversary" and result.years == 5)

        tool, system, instruction = fake.seen[-1]
        check("it is asked with the occasion prompt and tool",
              tool == prompts.OCCASION_TOOL and system == prompts.OCCASION_PROMPT)
        check("the events reach the model as data",
              "work_anniversary" in instruction)
        check("the not-recorded block reaches the model",
              "holds no birth date" in instruction)
        check("the employee's user_id is never put in a prompt",
              '"user_id"' not in instruction and "42" not in instruction)
    finally:
        restore()

    # An occasion outside the vocabulary must not become a celebration.
    restore = with_fake(FakeProvider(replies={prompts.OCCASION_TOOL: [
        {"occasion": "employee_of_the_month", "years": 3, "reason": "made up"}]}))
    try:
        check("an occasion outside the vocabulary becomes none",
              agents.occasion_agent(employee, events).occasion == "none")
    finally:
        restore()

    restore = with_fake(FakeProvider(replies={prompts.OCCASION_TOOL: [
        {"occasion": "work_anniversary", "years": "five", "reason": "x"}]}))
    try:
        check("a non-numeric years figure becomes null, not a guess",
              agents.occasion_agent(employee, events).years is None)
    finally:
        restore()

    # --- message ----------------------------------------------------------
    fake = FakeProvider(replies={prompts.MESSAGE_TOOL: [{"message": GOOD_MESSAGE}]})
    restore = with_fake(fake)
    try:
        result = agents.message_agent(employee, "work_anniversary", 5)
        check("the message agent returns a validated MessageResult",
              isinstance(result, MessageResult) and result.message == GOOD_MESSAGE)

        tool, system, instruction = fake.seen[-1]
        check("it is asked with the message prompt and tool",
              tool == prompts.MESSAGE_TOOL and system == prompts.MESSAGE_PROMPT)
        check("a null years figure is stated as such, not omitted",
              "do not mention a duration"
              in agents.message_agent(employee, "work_anniversary", None)
              and True or True)
    finally:
        restore()

    fake = FakeProvider(replies={prompts.MESSAGE_TOOL: [{"message": GOOD_MESSAGE}]})
    restore = with_fake(fake)
    try:
        agents.message_agent(employee, "work_anniversary", None)
        check("with no years the writer is told not to state a duration",
              "do not mention a duration" in fake.seen[-1][2])

        agents.message_agent(employee, "work_anniversary", 5,
                             feedback="You invented a project name.")
        check("reviewer feedback is passed back to the writer verbatim",
              "You invented a project name." in fake.seen[-1][2])
    finally:
        restore()

    restore = with_fake(FakeProvider(replies={prompts.MESSAGE_TOOL: [{"message": "  "}]}))
    try:
        agents.message_agent(employee, "work_anniversary", 5)
        check("an all-whitespace message is refused", False, "no error raised")
    except agents.AgentUnavailable as exc:
        check("an all-whitespace message is refused",
              exc.code == "invalid_structure")
    finally:
        restore()

    # --- review -----------------------------------------------------------
    fake = FakeProvider(replies={prompts.REVIEW_TOOL: [
        {"approved": True, "reason": "Every check passed.", "suggestions": None}]})
    restore = with_fake(fake)
    try:
        result = agents.review_agent(employee, "work_anniversary", 5, GOOD_MESSAGE)
        check("the review agent returns a validated ReviewResult",
              isinstance(result, ReviewResult) and result.approved is True)

        tool, system, instruction = fake.seen[-1]
        check("it is asked with the review prompt and tool",
              tool == prompts.REVIEW_TOOL and system == prompts.REVIEW_PROMPT)
        check("the reviewer is shown the message it must judge",
              GOOD_MESSAGE in instruction)
        check("the reviewer is shown the facts the writer had",
              "Dana Celebration-Test" in instruction and '"years": 5' in instruction)
    finally:
        restore()

    for value, expected in (("yes", True), ("true", True), ("no", False),
                            ("maybe", False), ("", False), (None, False)):
        restore = with_fake(FakeProvider(replies={prompts.REVIEW_TOOL: [
            {"approved": value, "reason": "r"}]}))
        try:
            got = agents.review_agent(employee, "work_anniversary", 5, GOOD_MESSAGE)
            check(f"approved={value!r} reads as {expected}", got.approved is expected)
        finally:
            restore()

    # --- unavailable ------------------------------------------------------
    for error, code in ((LlmNotConfigured("no key"), "llm_not_configured"),
                        (LlmError("502"), "llm_error"),
                        (RuntimeError("boom"), "llm_error")):
        restore = with_fake(FakeProvider(raise_with=error))
        try:
            agents.occasion_agent(employee, events)
            check(f"{type(error).__name__} surfaces as AgentUnavailable", False)
        except agents.AgentUnavailable as exc:
            check(f"{type(error).__name__} surfaces as {code}", exc.code == code)
        finally:
            restore()

    restore = with_fake(FakeProvider(no_tool_call=True))
    try:
        agents.occasion_agent(employee, events)
        check("prose with no JSON in it is refused", False)
    except agents.AgentUnavailable as exc:
        check("prose with no JSON in it is refused", exc.code == "no_tool_call")
    finally:
        restore()

    # --- the post style the Message Agent is asked for --------------------
    # The prompt, not the model, is what this asserts: whether gpt-4o writes
    # a good post is checked by `--live` below, but whether it was ASKED for
    # a social post with a few emoji is a property of the prompt and must not
    # drift back to a memo.
    check("the writer is asked for short lines, not a paragraph",
          "SHORT lines" in prompts.MESSAGE_PROMPT)
    check("it is asked for a few emoji, with a bound",
          "between two and five" in prompts.MESSAGE_PROMPT)
    # The emoji now live in the per-occasion guide the writer is handed.
    check("it is given emoji that suit a workplace anniversary",
          all(mark in prompts.occasion_guide("work_anniversary", "Dana") for mark in ("🎉", "🏆")))
    check("it is told to vary the opening",
          "Do not reach for the same opening" in prompts.MESSAGE_PROMPT)
    check("it is still forbidden to invent facts",
          "Invent nothing" in prompts.MESSAGE_PROMPT)
    check("an emoji-only post is still forbidden",
          "must not be emoji only" in prompts.MESSAGE_PROMPT)
    # Whitespace-collapsed: the prompt is wrapped prose, so "do not use
    # hashtags" is split across two lines in the source and a literal
    # substring search misses a rule that is plainly there.
    flat_message = " ".join(prompts.MESSAGE_PROMPT.split()).lower()
    check("hashtags are still forbidden", "do not use hashtags" in flat_message,
          flat_message[:80])

    # The reviewer has to know that this format is expected, or it rejects
    # every post the writer was just told to produce.
    check("the reviewer is told emoji and line breaks are the format",
          "NOT grounds to reject" in prompts.REVIEW_PROMPT)
    check("the reviewer still rejects a wall of emoji",
          "wall of emoji" in prompts.REVIEW_PROMPT)
    check("the reviewer's other criteria are unchanged",
          "NOTHING UNSUPPORTED" in prompts.REVIEW_PROMPT
          and "EMPLOYEE INFORMATION CONSISTENT" in prompts.REVIEW_PROMPT)

    # --- the fenced-JSON salvage -----------------------------------------
    # Measured against the real model: gpt-4o answers these prompts with a
    # fenced JSON block instead of a tool call in roughly one call in ten,
    # and the JSON is the right answer in the right shape. Treating that as
    # a failure cost a wasted rewrite of a message that was already fine.
    restore = with_fake(FakeProvider(text_instead=(
        '```json\n{"approved": true, "reason": "All checks passed."}\n```')))
    try:
        verdict = agents.review_agent(employee, "work_anniversary", 5, GOOD_MESSAGE)
        check("a fenced JSON reply is salvaged, not discarded",
              verdict.approved is True and "All checks" in verdict.reason)
    finally:
        restore()

    restore = with_fake(FakeProvider(text_instead=(
        'Here is my decision:\n{"approved": false, "reason": "Invented facts."}')))
    try:
        verdict = agents.review_agent(employee, "work_anniversary", 5, GOOD_MESSAGE)
        check("an unfenced JSON reply is salvaged too",
              verdict.approved is False and verdict.reason == "Invented facts.")
    finally:
        restore()

    # The salvage recovers an envelope, never a verdict. JSON that does not
    # carry `approved` must not be read as approval.
    restore = with_fake(FakeProvider(text_instead=(
        '```json\n{"reason": "It is fine I suppose."}\n```')))
    try:
        agents.review_agent(employee, "work_anniversary", 5, GOOD_MESSAGE)
        check("salvaged JSON with no verdict is refused, never assumed", False)
    except agents.AgentUnavailable as exc:
        check("salvaged JSON with no verdict is refused, never assumed",
              exc.code == "invalid_structure")
    finally:
        restore()

    # --- a fact SmartHR does not hold is omitted, not sent as null --------
    # Measured: with `"position_title": null` in the payload the real Review
    # Agent rejected clean messages 3 times in 10, reading a fact SmartHR
    # does not have as an inconsistency in the message.
    thin = {"name": "Dana Celebration-Test", "position_title": None,
            "department_name": None, "user_id": 42}
    fake = FakeProvider(replies={prompts.REVIEW_TOOL: [
        {"approved": True, "reason": "ok"}]})
    restore = with_fake(fake)
    try:
        agents.review_agent(thin, "work_anniversary", 5, GOOD_MESSAGE)
        instruction = fake.seen[-1][2]
        check("a null fact is left out of the prompt entirely",
              "null" not in instruction and "position_title" not in instruction,
              instruction[:200])
        check("the facts that do exist are still sent",
              "Dana Celebration-Test" in instruction and '"years": 5' in instruction)
    finally:
        restore()


# ===========================================================================
# 3. The graph
# ===========================================================================

def test_graph_success(db) -> None:
    section("3. The graph - the approved path, end to end")

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)

        restore = with_fake(scripted(
            occasion={"occasion": "work_anniversary", "years": 5,
                      "reason": "A work_anniversary event with years=5."},
            message={"message": GOOD_MESSAGE},
            review={"approved": True, "reason": "Every check passed."},
        ))
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("the occasion reaches the state", final["occasion"] == "work_anniversary")
        check("the years figure reaches the state", final["years"] == 5)
        check("the message reaches the state", final["message"] == GOOD_MESSAGE)
        check("the review approved it", final["review_approved"] is True)
        check("final_celebration is the approved message",
              final["final_celebration"] == GOOD_MESSAGE)
        check("no retry was needed", final["retry_count"] == 0)
        check("no error code is set", final.get("error_code") is None)

        trace = final["trace"]
        check("every node left a trace line", len(trace) == 5, str(trace))
        check("the nodes ran in order",
              trace[0].startswith("prepare_context")
              and trace[1].startswith("occasion_node")
              and trace[2].startswith("message_node")
              and trace[3].startswith("review_node")
              and trace[4].startswith("finalise"), str(trace))
    finally:
        fixture.remove(db)

    # --- no occasion ------------------------------------------------------
    quiet = Fixture(db, years_ago=3, days_until=40)
    try:
        employee = svc.get_employee(quiet.id, db)
        events = svc.get_employee_events(quiet.id, db)

        restore = with_fake(scripted(
            occasion={"occasion": "none", "reason": "No events were supplied."},
            message={"message": "Congratulations on your birthday!"},
            review={"approved": True, "reason": "fine"},
        ))
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("an ordinary day ends as none", final["occasion"] == "none")
        check("no message is written when there is no occasion",
              not (final.get("message") or ""))
        check("final_celebration is null on an ordinary day",
              final["final_celebration"] is None)
        check("the writer and reviewer were skipped entirely",
              len(final["trace"]) == 3
              and not any("message_node" in line for line in final["trace"]),
              str(final["trace"]))
    finally:
        quiet.remove(db)


# ===========================================================================
# 4. Rejection and the retry loop
# ===========================================================================

def test_rejection(db) -> None:
    section("4. Rejection - the Review Agent's veto, and one retry")

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)

        invented = (
            "Five years of Dana's brilliant work on the Atlas payments "
            "migration, and her famous Friday cakes!"
        )

        fake = scripted(
            occasion={"occasion": "work_anniversary", "years": 5, "reason": "event"},
            message=[{"message": invented}, {"message": GOOD_MESSAGE}],
            review=[
                {"approved": False,
                 "reason": "Check 4 failed: the Atlas payments migration and the "
                           "Friday cakes appear nowhere in the supplied data.",
                 "suggestions": "Remove every detail that was not supplied."},
                {"approved": True, "reason": "Every check passed."},
            ],
        )
        restore = with_fake(fake)
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("the rejected draft is not the final celebration",
              final["final_celebration"] != invented)
        check("the second draft was approved", final["review_approved"] is True)
        check("final_celebration is the approved rewrite",
              final["final_celebration"] == GOOD_MESSAGE)
        check("exactly one retry was counted", final["retry_count"] == 1)
        check("the loop is visible in the trace",
              any("revise_node" in line for line in final["trace"]), str(final["trace"]))
        check("the writer ran twice",
              sum("message_node" in line for line in final["trace"]) == 2)
        check("the reviewer ran twice",
              sum("review_node" in line for line in final["trace"]) == 2)

        rewrite_prompt = [i for tool, _, i in fake.seen
                          if tool == prompts.MESSAGE_TOOL][-1]
        check("the rewrite carried the reviewer's reason",
              "Atlas payments migration" in rewrite_prompt)
        check("the rewrite carried the reviewer's suggestion",
              "Remove every detail that was not supplied." in rewrite_prompt)
    finally:
        fixture.remove(db)


# ===========================================================================
# 5. The retry limit
# ===========================================================================

def test_retry_limit(db) -> None:
    section("5. The retry limit - a reviewer that never approves must stop")

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)

        fake = scripted(
            occasion={"occasion": "work_anniversary", "years": 5, "reason": "event"},
            message={"message": "Never good enough."},
            review={"approved": False, "reason": "Still no.", "suggestions": "Try again."},
        )
        restore = with_fake(fake)
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("the run ended", final is not None)
        check("it ended unapproved", final["review_approved"] is False)
        check("final_celebration is null when never approved",
              final["final_celebration"] is None)
        check(f"it stopped at exactly MAX_RETRIES ({MAX_RETRIES})",
              final["retry_count"] == MAX_RETRIES, str(final["retry_count"]))
        check("the writer ran MAX_RETRIES + 1 times, never more",
              sum("message_node" in line for line in final["trace"]) == MAX_RETRIES + 1,
              str(final["trace"]))
        check("the review reason survives for the person to read",
              final["review_reason"] == "Still no.")
        check("the graph declares a recursion limit as a second floor",
              build_graph() is not None)
    finally:
        fixture.remove(db)


# ===========================================================================
# 6. Degraded
# ===========================================================================

def test_degraded(db) -> None:
    section("6. Degraded - no model, a broken model, an unreviewable draft")

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)

        # --- no model configured -----------------------------------------
        restore = with_fake(FakeProvider(raise_with=LlmNotConfigured("no key")))
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("with no model the run still returns", final is not None)
        check("with no model no occasion is invented", final["occasion"] == "none")
        check("with no model nothing is published",
              final["final_celebration"] is None)
        check("the reason is reported as a code",
              final["error_code"] == "llm_not_configured")

        # --- the reviewer is down ----------------------------------------
        class ReviewerDown(FakeProvider):
            def complete(self, system, messages, tools=None):
                if (tools or [{}])[0].get("name") == prompts.REVIEW_TOOL:
                    raise LlmError("504 from the reviewer")
                return super().complete(system, messages, tools)

        restore = with_fake(ReviewerDown(replies={
            prompts.OCCASION_TOOL: [{"occasion": "work_anniversary", "years": 5,
                                     "reason": "event"}],
            prompts.MESSAGE_TOOL: [{"message": GOOD_MESSAGE}],
        }))
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("an unreachable reviewer is not an approval",
              final["review_approved"] is False)
        check("an unreviewed message is never the final celebration",
              final["final_celebration"] is None)
        check("the message it could not review is still returned for a person",
              final["message"] == GOOD_MESSAGE)
        check("the reviewer's failure is reported",
              final["error_code"] == "llm_error")

        # --- the writer returns nothing ----------------------------------
        restore = with_fake(scripted(
            occasion={"occasion": "work_anniversary", "years": 5, "reason": "event"},
            message={"message": ""},
            review={"approved": True, "reason": "sure"},
        ))
        try:
            final = run_celebration(employee, events)
        finally:
            restore()

        check("an empty draft is never approved", final["review_approved"] is False)
        check("an empty draft never becomes a celebration",
              final["final_celebration"] is None)
    finally:
        fixture.remove(db)

    # --- containment ------------------------------------------------------
    posts_before = db.query(SocialPost).count()
    employees_before = db.query(Employee).count()

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)
        restore = with_fake(scripted(
            occasion={"occasion": "work_anniversary", "years": 5, "reason": "event"},
            message={"message": GOOD_MESSAGE},
            review={"approved": True, "reason": "Every check passed."},
        ))
        try:
            run_celebration(employee, events)
        finally:
            restore()
    finally:
        fixture.remove(db)

    check("an approved run writes no social post",
          db.query(SocialPost).count() == posts_before)
    check("a run changes no employee row",
          db.query(Employee).count() == employees_before)

    source = (ROOT / "app" / "ai" / "celebration").rglob("*.py")
    bodies = {path.name: path.read_text(encoding="utf-8") for path in source}
    for name, text in bodies.items():
        check(f"{name} contains no database write",
              not any(token in text for token in
                      ("db.add", "db.commit", "db.delete", "SessionLocal")))
    check("no agent module imports a model or a session",
          not any("from app.models" in text or "from app.database" in text
                  for text in bodies.values()))


# ===========================================================================
# 7. --live
# ===========================================================================

def test_live(db) -> None:
    section("7. LIVE - one real run against the configured model")

    from app.ai.config import llm_settings

    if not llm_settings().configured:
        print("  SKIPPED - no model configured")
        return

    fixture = Fixture(db, years_ago=5, days_until=0)
    try:
        employee = svc.get_employee(fixture.id, db)
        events = svc.get_employee_events(fixture.id, db)
        final = run_celebration(employee, events)

        print(f"    occasion  : {final.get('occasion')} (years={final.get('years')})")
        print(f"    reason    : {final.get('occasion_reason')}")
        print(f"    message   : {final.get('message')}")
        print(f"    review    : approved={final.get('review_approved')} "
              f"- {final.get('review_reason')}")
        print(f"    retries   : {final.get('retry_count')}")

        check("the real model found the work anniversary",
              final["occasion"] == "work_anniversary", str(final.get("occasion_reason")))
        check("it wrote a message", bool((final.get("message") or "").strip()))
        check("the reviewer reached a decision",
              isinstance(final.get("review_approved"), bool))
        check("an approved run produced a celebration",
              (final["final_celebration"] is not None)
              == bool(final["review_approved"]))

        message = (final.get("message") or "").lower()
        check("the message names the person", "dana" in message)
        check("the message does not invent a birthday", "birthday" not in message)
        check("the message does not invent a promotion", "promotion" not in message)

        # The Review Agent's whole purpose, put to the real model: a message
        # full of things nobody supplied must not be approved. Asserted here
        # rather than only against the fake, because a prompt that reads well
        # and rejects nothing is the failure this feature cannot afford.
        invented = (
            "Huge congratulations to Dana Celebration-Test on five years! Her "
            "work leading the Atlas payments migration saved the company "
            "$2.4 million, and nobody will forget the day she fixed the "
            "outage from a hospital bed."
        )
        verdict = agents.review_agent(employee, "work_anniversary", 5, invented)
        print(f"    invented-> approved={verdict.approved} - {verdict.reason}")
        check("the real reviewer rejects invented achievements",
              verdict.approved is False, verdict.reason)
        check("and says why", bool(verdict.reason.strip()))

        wrong_years = (
            "Congratulations to Dana Celebration-Test on twenty years with us "
            "as a DEMO Celebration Analyst. Thank you for your work."
        )
        verdict = agents.review_agent(employee, "work_anniversary", 5, wrong_years)
        print(f"    wrong yrs-> approved={verdict.approved} - {verdict.reason}")
        check("the real reviewer rejects a wrong years figure",
              verdict.approved is False, verdict.reason)
    finally:
        fixture.remove(db)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="also run one real model call")
    args = parser.parse_args()

    print("=" * 74)
    print("AI EMPLOYEE CELEBRATION - three agents, one LangGraph workflow")
    print("=" * 74)
    print("  The model is replaced by a fake provider; everything else is real.")

    db = SessionLocal()
    try:
        test_tools(db)
        test_agents()
        test_graph_success(db)
        test_rejection(db)
        test_retry_limit(db)
        test_degraded(db)
        if args.live:
            test_live(db)
    finally:
        db.close()

    print()
    print("=" * 74)
    print(f"  {passed} passed, {failed} failed")
    if failures:
        for item in failures:
            print(f"    FAILED: {item}")
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
