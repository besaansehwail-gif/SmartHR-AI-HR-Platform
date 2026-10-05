"""The three agents. One function each, and each one does exactly one job.

    occasion_agent(...)  -> OccasionResult    what is being celebrated?
    message_agent(...)   -> MessageResult     what should it say?
    review_agent(...)    -> ReviewResult      may it be published?

Each does the same four things, in the same order, and reading one teaches
the other two:

    1. build the prompt input out of the state - never out of the database;
    2. call `provider.complete()` with its own prompt and its own tool schema;
    3. take the arguments the model handed to that tool;
    4. validate them with Pydantic before anybody downstream sees them.

Step 4 is where a model stops being trusted. `cv_parser.py` and
`candidate_intent.py` already work this way, and the rule they share applies
here too: **lenient about shape, strict about content.**

`AgentUnavailable` is raised when an agent could not be used at all - no
model configured, an unreachable one, a reply that would not validate. It is
never converted into a plausible-looking result. A celebration nobody can
generate must read as a celebration nobody generated.
"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.ai.celebration import prompts
from app.ai.celebration.state import MessageResult, OccasionResult, ReviewResult
from app.ai.config import LlmSettings, llm_settings
from app.ai.cv_parser import CvParseError, _json_from_text
from app.ai.provider import LlmError, LlmNotConfigured, get_provider

logger = logging.getLogger("smarthr.ai.celebration")


class AgentUnavailable(Exception):
    """An agent could not produce a result. Carries a machine-readable code.

    Codes: `llm_not_configured`, `llm_error`, `no_tool_call`,
    `invalid_structure`.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _ask(
    *,
    system: str,
    instruction: str,
    tool: str,
    schema: dict[str, Any],
    description: str,
    settings: LlmSettings | None = None,
) -> dict[str, Any]:
    """One model call, returning the arguments the model passed to `tool`.

    Every agent goes through here, so all three get the same error handling
    and none of them can quietly accept a reply that was not a tool call.
    """
    resolved = settings or llm_settings()
    provider = get_provider(resolved)

    tools = [{"name": tool, "description": description, "parameters": schema}]

    try:
        reply = provider.complete(system, [{"role": "user", "content": instruction}], tools)
    except LlmNotConfigured as exc:
        raise AgentUnavailable(str(exc), code="llm_not_configured") from exc
    except LlmError as exc:
        raise AgentUnavailable(str(exc), code="llm_error") from exc
    except Exception as exc:  # a provider bug must not take the router down
        logger.warning("Celebration agent call failed | tool=%s", tool, exc_info=False)
        raise AgentUnavailable("The language model call failed.", code="llm_error") from exc

    if reply.tool_call is not None and reply.tool_call.name == tool:
        return reply.tool_call.arguments or {}

    # Measured, not guessed: gpt-4o answers this prompt with a fenced JSON
    # block instead of a tool call in roughly one call in ten, and the JSON
    # it sends is the right answer in the right shape. `app/ai/provider.py`
    # has no forced-tool setting for either vendor, so the salvage is the
    # only way to tell "the model refused" from "the model replied in the
    # wrong envelope" - and treating the second as a failure costs a rewrite
    # of a message that was already fine.
    #
    # cv_parser's helper is imported rather than copied: two salvage
    # implementations would eventually disagree about what a fenced block is.
    if reply.text:
        try:
            return _json_from_text(reply.text)
        except CvParseError as exc:
            raise AgentUnavailable(
                f"The model did not call {tool} and its reply was not JSON.",
                code="no_tool_call",
            ) from exc

    raise AgentUnavailable(f"The model did not call {tool}.", code="no_tool_call")


def _validate(model, payload: dict[str, Any], what: str):
    """Pydantic validation with an error that names fields, never values.

    The values here are a real person's details, so a validation message is
    somewhere a name could leak into a log. `cv_parser.validate_parsed_cv`
    makes the same choice for the same reason.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        fields = ", ".join(
            ".".join(str(part) for part in error["loc"]) for error in exc.errors()[:5]
        )
        raise AgentUnavailable(
            f"The {what} agent's reply did not match its schema ({fields}).",
            code="invalid_structure",
        ) from exc


def _facts(employee: dict, years: int | None = None) -> str:
    """The employee facts, as JSON, exactly as they came from SmartHR.

    Handed over as data rather than prose so there is no sentence for a model
    to read a detail into. Only the four fields a celebration may mention are
    included - `get_employee()` returns a `user_id` too, and an internal
    identifier has no business in a prompt.
    """
    candidates = {
        "name": employee.get("name"),
        "position_title": employee.get("position_title"),
        "department_name": employee.get("department_name"),
        "years": years,
    }

    # A null is left out entirely rather than sent as `null`. Measured: with
    # `"position_title": null` in the payload the Review Agent rejected clean
    # messages 3 times in 10, reading a fact SmartHR does not hold as an
    # inconsistency in the message - and `employees.position_id` and
    # `department_id` are both nullable, so that is an ordinary employee, not
    # an edge case. What is absent here is simply not a fact the message may
    # state, which is what both prompts now say.
    return json.dumps(
        {key: value for key, value in candidates.items() if value is not None},
        ensure_ascii=False,
        indent=2,
    )


# ===========================================================================
# 1. Occasion
# ===========================================================================

def occasion_agent(
    employee: dict, events: dict, *, settings: LlmSettings | None = None
) -> OccasionResult:
    """Decide what, if anything, is being celebrated.

    Both arguments came out of `celebration_service`, which read them from
    PostgreSQL. This agent has no database access and no tool with which to
    get any, so an occasion it reports is either in `events` or invented -
    and the prompt, the schema's enum and the validator all push an invention
    towards `none`.
    """
    instruction = (
        "EMPLOYEE (from SmartHR):\n"
        f"{_facts(employee)}\n\n"
        "EVENTS FOUND IN SMARTHR'S RECORDS:\n"
        f"{json.dumps(events.get('events') or [], ensure_ascii=False, indent=2)}\n\n"
        "OCCASIONS SMARTHR KEEPS NO DATA FOR - these can never be your answer:\n"
        f"{json.dumps(events.get('not_recorded') or {}, ensure_ascii=False, indent=2)}\n\n"
        f"TODAY'S DATE: {events.get('today')}\n\n"
        "Call report_occasion with your decision."
    )

    payload = _ask(
        system=prompts.OCCASION_PROMPT,
        instruction=instruction,
        tool=prompts.OCCASION_TOOL,
        schema=prompts.OCCASION_SCHEMA,
        description="Report which occasion the supplied HR records establish.",
        settings=settings,
    )
    return _validate(OccasionResult, payload, "occasion")


# ===========================================================================
# 2. Message
# ===========================================================================

def message_agent(
    employee: dict,
    occasion: str,
    years: int | None,
    *,
    feedback: str | None = None,
    settings: LlmSettings | None = None,
) -> MessageResult:
    """Write the celebration for an occasion that has already been verified.

    `feedback` is the Review Agent's reason and suggestions on a retry. It is
    passed as instructions to act on, which is why the prompt tells the agent
    to fix what it names and change nothing else - a rewrite that also
    rewrites the parts nobody objected to is how a second rejection happens.
    """
    instruction = (
        "EMPLOYEE (from SmartHR - these are the only facts you may use):\n"
        f"{_facts(employee, years)}\n\n"
        f"VERIFIED OCCASION: {occasion}\n"
        f"YEARS: {years if years is not None else 'not applicable - do not mention a duration'}\n\n"
        f"{prompts.occasion_guide(occasion, employee.get('first_name'))}"
    )

    if feedback:
        instruction += (
            "\nYOUR PREVIOUS DRAFT WAS REJECTED BY THE REVIEWER:\n"
            f"{feedback}\n"
            "Fix exactly what the reviewer named. Change nothing else.\n"
        )

    instruction += "\nCall write_celebration with the message."

    payload = _ask(
        system=prompts.MESSAGE_PROMPT,
        instruction=instruction,
        tool=prompts.MESSAGE_TOOL,
        schema=prompts.MESSAGE_SCHEMA,
        description="Write the celebration message for this occasion.",
        settings=settings,
    )
    return _validate(MessageResult, payload, "message")


# ===========================================================================
# 3. Review
# ===========================================================================

def review_agent(
    employee: dict,
    occasion: str,
    years: int | None,
    message: str,
    *,
    settings: LlmSettings | None = None,
) -> ReviewResult:
    """Decide whether the drafted message may be published.

    It is shown the same facts the writer was shown, so "is there anything in
    this message that was not in the data" is a question it can actually
    answer. It is a separate call with a separate prompt rather than a second
    question to the writer, because a writer asked to check its own work
    checks it against what it meant.
    """
    instruction = (
        "EMPLOYEE FACTS SMARTHR SUPPLIED:\n"
        f"{_facts(employee, years)}\n\n"
        f"VERIFIED OCCASION: {occasion}\n"
        f"YEARS: {years if years is not None else 'null - the message must not state a duration'}\n\n"
        "THE DRAFTED MESSAGE:\n"
        f"---\n{message}\n---\n\n"
        "Call report_review with your decision."
    )

    payload = _ask(
        system=prompts.REVIEW_PROMPT,
        instruction=instruction,
        tool=prompts.REVIEW_TOOL,
        schema=prompts.REVIEW_SCHEMA,
        description="Review the drafted celebration and approve or reject it.",
        settings=settings,
    )
    return _validate(ReviewResult, payload, "review")
