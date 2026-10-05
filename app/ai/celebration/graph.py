"""The LangGraph workflow: five nodes, one conditional edge, one retry loop.

                          START
                            |
                    prepare_context          employee facts, from SmartHR
                            |
                     occasion_node           WHICH occasion?
                            |
                     (occasion == none?) ----------------.
                            |                            |
                      message_node          WHAT should it say?
                            |                            |
                      review_node           MAY it be published?
                            |                            |
                 .----------+----------.                 |
        approved |          | rejected  | retries spent  |
                 v          v           v                v
            finalise    message_node   finalise      finalise
                 |                                       |
                 '-------------------> END <-------------'

Why a graph rather than three calls in a row
--------------------------------------------

Only one edge here is conditional, and it is the whole feature: what the
Review Agent decides determines whether the next node is the writer again or
the end. Written as straight-line code that is a `while` loop with a counter
in it; written as a graph the routing is one function that returns a node
name, and the retry bound is visible rather than buried in a loop condition.

**The loop is bounded in code, not by asking a model nicely.** `_after_review`
compares `retry_count` against `MAX_RETRIES` before it may return
`"message"`, so an agent that rejects everything ends the run unapproved
after a fixed number of attempts. LangGraph's own `recursion_limit` is set as
well, as a second floor under the first.

**Nothing in this file touches the database.** The facts arrive in the state,
put there by `prepare_context` from `celebration_service`, and the result
goes back to the router as a dictionary. No node writes anything anywhere.
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.ai.celebration.agents import (
    AgentUnavailable,
    message_agent,
    occasion_agent,
    review_agent,
)
from app.ai.celebration.state import MAX_RETRIES, CelebrationState
from app.ai.config import LlmSettings

logger = logging.getLogger("smarthr.ai.celebration")

#: LangGraph stops a run that takes more steps than this. The real bound is
#: `MAX_RETRIES` in `_after_review`; this is the floor under it, so a routing
#: bug becomes a stopped run rather than a spinning one.
RECURSION_LIMIT = 25


def _note(state: CelebrationState, line: str) -> list[str]:
    """Append to the trace without mutating the state LangGraph handed us."""
    return list(state.get("trace") or []) + [line]


# ===========================================================================
# Nodes
# ===========================================================================

def prepare_context(state: CelebrationState) -> dict:
    """Start the run from facts that are already in the state.

    The router put them there, having read them through
    `celebration_service`. This node deliberately does not fetch anything
    itself: a graph that can reach the database is a graph whose nodes can
    each reach the database, and then "the agents only read what SmartHR
    handed them" stops being checkable in one place.
    """
    employee = state.get("employee_data") or {}
    events = (state.get("events") or {}).get("events") or []

    return {
        "employee_name": employee.get("name") or "",
        "retry_count": 0,
        "final_celebration": None,
        "error_code": None,
        "trace": _note(state, f"prepare_context: {len(events)} event(s) from SmartHR"),
    }


def occasion_node(state: CelebrationState) -> dict:
    """Agent 1: decide what is being celebrated."""
    settings: LlmSettings | None = state.get("_settings")  # type: ignore[assignment]

    try:
        result = occasion_agent(
            state.get("employee_data") or {},
            state.get("events") or {},
            settings=settings,
        )
    except AgentUnavailable as exc:
        # No occasion is invented to keep the run going. An unavailable agent
        # ends the workflow with a reason a person can act on.
        return {
            "occasion": "none",
            "years": None,
            "occasion_reason": str(exc),
            "error_code": exc.code,
            "trace": _note(state, f"occasion_node: unavailable ({exc.code})"),
        }

    return {
        "occasion": result.occasion,
        "years": result.years,
        "occasion_reason": result.reason,
        "trace": _note(
            state, f"occasion_node: {result.occasion} (years={result.years})"
        ),
    }


def message_node(state: CelebrationState) -> dict:
    """Agent 2: write the celebration, or rewrite a rejected one."""
    settings: LlmSettings | None = state.get("_settings")  # type: ignore[assignment]

    feedback = None
    if state.get("retry_count"):
        # Only what the reviewer actually said. Nothing is added here, so a
        # rewrite cannot be steered by this module's own opinion of the draft.
        parts = [state.get("review_reason") or "", state.get("review_suggestions") or ""]
        feedback = "\n".join(part for part in parts if part).strip() or None

    try:
        result = message_agent(
            state.get("employee_data") or {},
            state.get("occasion") or "none",
            state.get("years"),
            feedback=feedback,
            settings=settings,
        )
    except AgentUnavailable as exc:
        return {
            "message": "",
            "error_code": exc.code,
            "trace": _note(state, f"message_node: unavailable ({exc.code})"),
        }

    attempt = int(state.get("retry_count") or 0) + 1
    return {
        "message": result.message,
        "trace": _note(state, f"message_node: draft {attempt} written"),
    }


def review_node(state: CelebrationState) -> dict:
    """Agent 3: approve or reject the draft."""
    settings: LlmSettings | None = state.get("_settings")  # type: ignore[assignment]

    if not (state.get("message") or "").strip():
        # There is nothing to review. Approving an empty draft would put an
        # empty post in front of a person.
        return {
            "review_approved": False,
            "review_reason": "There is no message to review.",
            "review_suggestions": None,
            "trace": _note(state, "review_node: nothing to review"),
        }

    try:
        result = review_agent(
            state.get("employee_data") or {},
            state.get("occasion") or "none",
            state.get("years"),
            state.get("message") or "",
            settings=settings,
        )
    except AgentUnavailable as exc:
        # An unavailable reviewer is not an approval. Publishing an unreviewed
        # message because the reviewer was down is the one outcome this agent
        # exists to prevent.
        return {
            "review_approved": False,
            "review_reason": f"The message could not be reviewed: {exc}",
            "review_suggestions": None,
            "error_code": exc.code,
            "trace": _note(state, f"review_node: unavailable ({exc.code})"),
        }

    return {
        "review_approved": result.approved,
        "review_reason": result.reason,
        "review_suggestions": result.suggestions,
        "trace": _note(
            state,
            f"review_node: {'approved' if result.approved else 'rejected'}"
            f" - {result.reason[:80]}",
        ),
    }


def revise_node(state: CelebrationState) -> dict:
    """Count one rejection, then hand back to the writer.

    A node of its own rather than a counter incremented inside
    `message_node`, so the number of rewrites is changed in exactly one place
    and the graph shows where the loop turns.
    """
    count = int(state.get("retry_count") or 0) + 1
    return {
        "retry_count": count,
        "trace": _note(state, f"revise_node: retry {count} of {MAX_RETRIES}"),
    }


def finalise(state: CelebrationState) -> dict:
    """The Final Celebration - reached by every path, approving or not.

    `final_celebration` is set **only** when the Review Agent approved. On
    every other path it stays None, which is what makes "nothing unreviewed
    reaches the Social Hub" a property of the state rather than a claim about
    the prompts.
    """
    approved = bool(state.get("review_approved"))
    occasion = state.get("occasion") or "none"

    if approved and occasion != "none" and (state.get("message") or "").strip():
        return {
            "final_celebration": state["message"],
            "trace": _note(state, "finalise: celebration ready"),
        }

    return {
        "final_celebration": None,
        "trace": _note(state, f"finalise: nothing to publish (occasion={occasion})"),
    }


# ===========================================================================
# Edges
# ===========================================================================

def _after_occasion(state: CelebrationState) -> str:
    """No occasion means no message. Most days, for most people, this is it."""
    return "finalise" if (state.get("occasion") or "none") == "none" else "message"


def _after_review(state: CelebrationState) -> str:
    """The conditional edge the whole graph is built around.

    Three outcomes, and the retry bound is enforced here in Python rather
    than by trusting an agent to stop asking:

        approved                    -> finalise
        rejected, retries left      -> revise (and back to the writer)
        rejected, retries exhausted -> finalise, unapproved
    """
    if state.get("review_approved"):
        return "finalise"
    if int(state.get("retry_count") or 0) >= MAX_RETRIES:
        logger.info("Celebration rejected %s times; stopping.", MAX_RETRIES)
        return "finalise"
    return "revise"


# ===========================================================================
# The graph
# ===========================================================================

def build_graph():
    """Compile the workflow. Cheap enough to call per request, but cached."""
    graph = StateGraph(CelebrationState)

    graph.add_node("prepare_context", prepare_context)
    graph.add_node("occasion", occasion_node)
    graph.add_node("message", message_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("finalise", finalise)

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "occasion")

    graph.add_conditional_edges(
        "occasion", _after_occasion, {"message": "message", "finalise": "finalise"}
    )
    graph.add_edge("message", "review")
    graph.add_conditional_edges(
        "review", _after_review, {"revise": "revise", "finalise": "finalise"}
    )
    graph.add_edge("revise", "message")  # the loop, bounded by _after_review
    graph.add_edge("finalise", END)

    return graph.compile()


_COMPILED = None


def get_graph():
    """The compiled graph, built once per process.

    It holds no per-run state - everything a run needs travels in the state
    dictionary - so one compiled graph is safe to share between requests.
    """
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED


def run_celebration(
    employee: dict, events: dict, *, settings: LlmSettings | None = None
) -> dict:
    """Run the workflow once and return the finished state.

    `employee` and `events` come from `celebration_service`; this function
    does not read them itself, which is what keeps every database access in
    the service layer.
    """
    initial: dict = {
        "employee_id": employee.get("employee_id"),
        "employee_data": employee,
        "events": events,
        "trace": [],
    }

    # Carried in the state so a test can run the whole graph against a fake
    # provider without touching the environment - the rule the interview
    # suites follow, where the model is switched off by replacing settings
    # rather than by clearing variables that fall through to `.env`.
    if settings is not None:
        initial["_settings"] = settings

    return get_graph().invoke(initial, {"recursion_limit": RECURSION_LIMIT})
