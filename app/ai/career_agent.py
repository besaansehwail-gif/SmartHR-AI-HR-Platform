"""The AI Career Agent.

The difference between this and `app/ai/assistant.py` is the loop. The
assistant makes one tool call and phrases the result; the agent keeps going
until it has what it needs:

    applicant's question
      -> LLM: which tool first?                     step 1
      -> MCP tools/call -> SmartHR service -> PostgreSQL
      -> LLM: here is the result. What now?         step 2
      -> MCP tools/call ...                         step 3
      -> LLM: final answer, written from the results

"What opportunities are suitable for me?" is a question no single tool
answers. The agent typically reads the profile, reads the CV status, searches
what is open, matches the two, and only then writes a reply - and each of
those is a real MCP call against real rows.

**The agent decides; it never authorises.** `mcp.list_tools()` returns what
role 5 may run and nothing else, `authorise()` re-reads the role from `users`
before any handler executes, and no tool takes an identity argument. Those
three facts are what make an agent loop safe to run against HR data: the worst
a confused or manipulated model can do is call an allowed tool with the wrong
arguments about its own caller.

**Two gates stand in front of the one tool that writes.**

1. `submit_application` is removed from the tool list entirely unless the
   applicant's message expresses intent to apply. The model cannot choose a
   tool it was never shown, so "find me data analyst jobs" cannot end in an
   application no matter what the model decides.
2. The tool itself requires `confirmed_by_applicant` and refuses without it.

Gate 1 is code and holds regardless of the model; gate 2 is the model's own
assertion. Both have to pass.

**With no language model configured the agent still answers**, from real tool
output, resolved by keyword and flagged as such - the same degradation the
assistant uses. It will not submit an application on that path: applying is a
consequential write and a keyword match is not a decision.
"""

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.ai.config import llm_settings
from app.ai.provider import LlmError, LlmNotConfigured, get_provider
from app.mcp import client as mcp
from app.mcp.identity import Principal
from app.models import User

logger = logging.getLogger("smarthr.ai.career")

#: How many tool calls one turn may make before the agent must answer. Six is
#: enough for profile -> CV -> search -> match -> answer with room to spare,
#: and low enough that a model stuck in a loop costs a bounded amount.
MAX_STEPS = 6

#: The one tool that writes. Named here because the gate below is about it
#: specifically, not about write tools in general.
WRITE_TOOL = "submit_application"


SYSTEM_PROMPT = """You are the SmartHR Career Agent. You help one signed-in \
job seeker find suitable opportunities and manage their own recruitment tasks.

Your goal: help this applicant discover opportunities that genuinely suit \
them, understand what each one requires, and - only when they ask - apply.

How you work:
1. You have tools that read the live SmartHR database. Use them. You know \
nothing about this applicant or about what is on offer except what a tool \
returns in this conversation.
2. Call as many tools as the question needs, one at a time. To recommend \
opportunities you will usually need the applicant's profile, then the open \
opportunities, then a match.
3. Every fact in your answer must come from a tool result. Never invent an \
opportunity, a job title, a requirement, a deadline, a skill, a match score \
or an application. If the tools return nothing, say plainly that SmartHR has \
nothing matching - that is a correct and useful answer.
4. If a tool reports that information is unavailable, relay that instead of \
filling the gap. SmartHR does not store parsed CV text, so you do not know \
what the CV says; the skills you may reason about are the ones on the \
applicant's profile.

Applying:
5. Submitting an application writes to the database and is seen by recruiters. \
Do it only when the applicant has asked in words to apply to a specific \
opportunity. Searching, comparing, explaining or expressing interest is not \
asking to apply.
6. If they ask to apply but you are not certain which opportunity they mean, \
ask them - do not guess.
7. You cannot change an application's status, withdraw an application, or \
affect a hiring decision. You have no tool for any of those, because those \
decisions belong to the recruiter.

Match scores:
8. A match score is a skill-overlap suggestion labelled "AI Match / \
Recommendation". It is not a hiring decision and not a judgement of the \
person. Present it as a suggestion, always explain which skills matched and \
which are missing, and never tell an applicant they are or are not qualified.

Style: warm, brief and concrete. Name real opportunities and real figures. \
Answer in the language the applicant used - if they wrote in Arabic, reply in \
Arabic."""


# ---------------------------------------------------------------------------
# Gate 1: does this message actually ask to apply?
#
# Keyword gates are usually a smell - this one is not routing, it is scope
# reduction. A message that does not ask to apply cannot reach the write tool
# regardless of what the model concludes, which is exactly the property the
# brief asks for: "Find Data Analyst jobs" must not submit an application.
#
# It errs towards refusing. A question ("what can I apply to?") is a question,
# not an instruction, so the tool stays hidden and the model has to answer with
# the read tools - the worst case is the applicant being told to ask again more
# directly, which is a good failure.
# ---------------------------------------------------------------------------

_APPLY_VERB = re.compile(
    r"\bapply\b|\bapplying\b|\bsubmit\s+(?:my|an|the)\s+application\b"
    r"|\bsend\s+(?:my|an|the)\s+application\b"
    r"|قدم|قدّم|تقديم|سجلني|رشحني",
    re.IGNORECASE,
)

_QUESTION_OPENER = re.compile(
    r"^\s*(what|which|how|where|when|why|who|can|could|should|shall|do|does|"
    r"did|is|are|am|was|will|would|any|show|find|search|list|tell|explain|"
    r"compare|recommend|suggest)\b",
    re.IGNORECASE,
)


def apply_intent(message: str) -> bool:
    """True when the applicant is instructing, not enquiring."""
    text = (message or "").strip()

    if not _APPLY_VERB.search(text):
        return False

    # "What jobs can I apply to?" asks about applying; it does not ask to apply.
    return not _QUESTION_OPENER.match(text)


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def _tool_specs(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def _result_json(result: mcp.McpToolResult) -> str:
    """The tool result as the model sees it."""
    if result.ok:
        payload: dict[str, Any] = dict(result.payload)
    else:
        payload = {
            "error": result.error,
            "error_code": result.error_code,
            "instruction": (
                "This tool refused. Explain the reason to the applicant. Do not "
                "retry with a different identity and do not work around it."
            ),
        }

    return json.dumps(payload, ensure_ascii=False, default=str)[:20000]


def run_agent(
    message: str,
    history: list[dict[str, str]],
    user: User,
    db: Session,
) -> dict[str, Any]:
    """One Career Agent turn.

    `db` is the request's session; it is used for nothing but consistency with
    the router's signature - every read the agent makes goes through MCP, which
    opens its own session per tool. That is deliberate: the agent has no
    database handle of its own, so it cannot read around its tools.
    """
    started = time.perf_counter()
    settings = llm_settings()
    principal = Principal(user_id=user.id, email=user.email, role_id=user.role_id)

    logger.info(
        "Career agent turn start | user_id=%s llm=%s provider=%s",
        user.id, settings.configured, settings.provider,
    )

    try:
        available = mcp.list_tools(principal, user.role_id)
    except Exception:
        logger.exception("Career agent: MCP tools/list failed | user_id=%s", user.id)
        available = []

    wants_to_apply = apply_intent(message)

    # Gate 1. The model is never shown the write tool unless the applicant
    # asked to apply, so it cannot pick it.
    offered = [
        tool for tool in available
        if tool.name != WRITE_TOOL or wants_to_apply
    ]

    logger.info(
        "Career agent tools | user_id=%s available=%s offered=%s apply_intent=%s",
        user.id, len(available), len(offered), wants_to_apply,
    )

    steps: list[dict[str, Any]] = []

    if not settings.configured:
        return _without_model(
            message, principal, offered, steps, settings,
            notice=(
                "No language model is configured, so this answer was assembled "
                "directly from SmartHR data rather than written by a model."
            ),
            started=started,
        )

    provider = get_provider(settings)
    messages: list[dict[str, Any]] = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in history
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]
    messages.append({"role": "user", "content": message})

    specs = _tool_specs(offered)

    try:
        for step in range(1, MAX_STEPS + 1):
            reply = provider.complete(SYSTEM_PROMPT, messages, tools=specs)

            if reply.tool_call is None:
                logger.info(
                    "Career agent done | user_id=%s steps=%s elapsed_ms=%s",
                    user.id, len(steps), round((time.perf_counter() - started) * 1000),
                )

                return {
                    "reply": reply.text or _no_text_fallback(steps),
                    "steps": steps,
                    "tools_used": [s["tool"] for s in steps],
                    "tool_used": steps[-1]["tool"] if steps else None,
                    "data": steps[-1]["data"] if steps else None,
                    "generated_by": "llm",
                    "tool_transport": "mcp",
                    "llm_configured": True,
                    "provider": settings.provider,
                    "model": settings.model,
                    "apply_intent_detected": wants_to_apply,
                    "notice": None,
                }

            call = reply.tool_call

            # A model asking for a tool it was not offered. This is what an
            # attempt to reach the write tool without apply intent looks like,
            # so it is refused in the transcript rather than silently dropped -
            # the model is told, and the turn continues.
            if call.name not in {tool.name for tool in offered}:
                logger.warning(
                    "Career agent requested an unoffered tool | user_id=%s tool=%s",
                    user.id, call.name,
                )
                steps.append({
                    "step": step,
                    "tool": call.name,
                    "arguments": sorted(call.arguments.keys()),
                    "ok": False,
                    "error_code": "tool_not_available",
                    "data": None,
                })
                messages.extend(provider.tool_exchange(reply, json.dumps({
                    "error_code": "tool_not_available",
                    "error": (
                        f"'{call.name}' is not available in this conversation. "
                        f"If the applicant wants to apply, ask them to say so "
                        f"explicitly."
                    ),
                })))
                continue

            result = mcp.call_tool(principal, call.name, call.arguments)

            steps.append({
                "step": step,
                "tool": call.name,
                # Keys only - a value could be personal.
                "arguments": sorted(call.arguments.keys()),
                "ok": result.ok,
                "error_code": result.error_code,
                "data": result.payload if result.ok else None,
            })

            messages.extend(provider.tool_exchange(reply, _result_json(result)))

        # Out of steps. Answer from what was actually gathered rather than
        # looping forever or returning nothing.
        logger.warning(
            "Career agent hit the step limit | user_id=%s steps=%s", user.id, len(steps)
        )

        return {
            "reply": _no_text_fallback(steps),
            "steps": steps,
            "tools_used": [s["tool"] for s in steps],
            "tool_used": steps[-1]["tool"] if steps else None,
            "data": steps[-1]["data"] if steps else None,
            "generated_by": "tool",
            "tool_transport": "mcp",
            "llm_configured": True,
            "provider": settings.provider,
            "model": settings.model,
            "apply_intent_detected": wants_to_apply,
            "notice": (
                "The agent reached its step limit. This summary comes straight "
                "from the SmartHR data it gathered."
            ),
        }

    except LlmNotConfigured:
        return _without_model(
            message, principal, offered, steps, settings,
            notice=(
                "No language model is configured, so this answer was assembled "
                "directly from SmartHR data."
            ),
            started=started,
        )
    except LlmError as exc:
        # The model is unreachable or refused. Degrade to real data rather than
        # to an apology - the applicant's question is usually still answerable.
        logger.warning("Career agent LLM error | user_id=%s error=%s", user.id, exc)

        return _without_model(
            message, principal, offered, steps, settings,
            notice=(
                "The language model could not be reached, so this answer was "
                "assembled directly from SmartHR data."
            ),
            started=started,
        )


# ---------------------------------------------------------------------------
# Without a model
#
# Real tool output, resolved by keyword and rendered. Everything shown came out
# of PostgreSQL; nothing here fabricates a figure. `submit_application` is
# absent by construction: a keyword is not consent to write.
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Order matters - the first tool whose keywords appear wins.
    "get_my_applications": (
        "my application", "applications", "applied", "status of my",
        "track", "progress", "طلباتي", "تقديماتي", "حالة طلب",
    ),
    "match_my_profile_to_opportunity": (
        "suitable", "suit me", "match", "recommend", "best for me", "fit",
        "right for me", "مناسب", "يناسبني", "توصية", "ترشيح",
    ),
    "search_opportunities": (
        "opportunit", "job", "internship", "vacancy", "vacancies", "course",
        "training", "hiring", "opening", "position", "role",
        "وظيف", "فرص", "تدريب", "دورة", "شاغر",
    ),
    "get_my_cv": ("cv", "resume", "سيرة", "السيرة الذاتية"),
    "get_my_profile": ("profile", "my skills", "about me", "ملفي", "مهاراتي"),
}


def _keyword_tool(message: str, offered: set[str]) -> str | None:
    text = (message or "").lower()

    for tool, keywords in INTENT_KEYWORDS.items():
        if tool not in offered:
            continue

        if any(keyword in text for keyword in keywords):
            return tool

    return "search_opportunities" if "search_opportunities" in offered else None


def _fallback_arguments(tool: str, message: str) -> dict[str, Any]:
    if tool == "search_opportunities":
        # The applicant's own words are passed through as the search. Without
        # this the fallback would answer "find me quantum cryptography jobs"
        # with the entire catalogue, and a reader would reasonably conclude
        # those roles existed. `_search_terms` drops the filler; what is left
        # must all appear, so an absent topic correctly returns nothing.
        return {"search": message, "limit": 10}

    return {}


def _without_model(
    message: str,
    principal: Principal,
    offered: list[Any],
    steps: list[dict[str, Any]],
    settings,
    *,
    notice: str,
    started: float,
) -> dict[str, Any]:
    """Answer from one real tool call, with no model involved."""
    # Never the write tool on this path, whatever the message said.
    names = {tool.name for tool in offered if tool.name != WRITE_TOOL}
    tool = _keyword_tool(message, names)

    if tool is None:
        return {
            "reply": (
                "I could not reach the SmartHR tools just now, so I have "
                "nothing to tell you rather than something I made up. Please "
                "try again in a moment."
            ),
            "steps": steps,
            "tools_used": [],
            "tool_used": None,
            "data": None,
            "generated_by": "none",
            "tool_transport": "mcp",
            "llm_configured": settings.configured,
            "provider": settings.provider,
            "model": settings.model,
            "apply_intent_detected": False,
            "notice": notice,
        }

    arguments = _fallback_arguments(tool, message)
    result = mcp.call_tool(principal, tool, arguments)

    steps.append({
        "step": len(steps) + 1,
        "tool": tool,
        "arguments": sorted(arguments.keys()),
        "ok": result.ok,
        "error_code": result.error_code,
        "data": result.payload if result.ok else None,
    })

    logger.info(
        "Career agent answered without a model | user_id=%s tool=%s ok=%s elapsed_ms=%s",
        principal.user_id, tool, result.ok,
        round((time.perf_counter() - started) * 1000),
    )

    if not result.ok:
        reply = (
            f"I could not read that from SmartHR: {result.error} "
            f"Nothing here is guessed - if I cannot read it, I will not invent it."
        )
    else:
        reply = _render(tool, result.payload, apply_offered=False)

    return {
        "reply": reply,
        "steps": steps,
        "tools_used": [tool],
        "tool_used": tool,
        "data": result.payload if result.ok else None,
        "generated_by": "tool",
        "tool_transport": "mcp",
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model,
        "apply_intent_detected": False,
        "notice": notice,
    }


def _opportunity_line(item: dict[str, Any]) -> str:
    bits = [f"• {item.get('title')}"]

    label = item.get("opportunity_type_label")
    if label:
        bits.append(f"({label})")

    where = item.get("location") or item.get("department_name")
    if where:
        bits.append(f"— {where}")

    line = " ".join(bits)

    skills = item.get("skills") or []
    if skills:
        line += f"\n    Requires: {', '.join(skills)}"

    deadline = item.get("deadline")
    if deadline:
        line += f"\n    Closes: {deadline}"

    match = item.get("match")
    if match and match.get("score") is not None:
        line += f"\n    AI Match / Recommendation: {match['score']}%"

        if match.get("matching_skills"):
            line += f" — you have {', '.join(match['matching_skills'])}"

        if match.get("skill_gaps"):
            line += f"; not evidenced: {', '.join(match['skill_gaps'])}"

    return line


def _render(tool: str, payload: dict[str, Any], *, apply_offered: bool) -> str:
    """Turn one tool result into readable text. Every value comes from payload."""
    if tool == "search_opportunities":
        items = payload.get("opportunities") or []

        if not items:
            return (
                "SmartHR has no open opportunity matching that right now. "
                "I have not made one up."
            )

        lines = "\n".join(_opportunity_line(item) for item in items)
        return f"SmartHR currently has {len(items)} matching opportunities:\n\n{lines}"

    if tool == "match_my_profile_to_opportunity":
        if not payload.get("skills_available"):
            return (
                "Your profile does not list any skills yet, so I cannot match "
                "you to anything — and I will not guess what you can do. Add "
                "your skills on My Profile and ask me again."
            )

        matches = payload.get("matches") or []

        if not matches:
            return "There are no open opportunities to match against right now."

        lines = "\n".join(_opportunity_line(item) for item in matches)
        return (
            "Based on the skills on your profile, these fit best. This is an "
            "AI Match / Recommendation — a skill-overlap suggestion, not a "
            f"hiring decision:\n\n{lines}"
        )

    if tool == "get_my_applications":
        summary = payload.get("summary") or {}
        applications = payload.get("applications") or []

        if not applications:
            return "You have not applied to anything yet."

        lines = "\n".join(
            f"• {a.get('job_title')} — {a.get('status_label')}"
            + (f" (applied {a['applied_at'][:10]})" if a.get("applied_at") else "")
            for a in applications
        )

        return (
            f"You have {summary.get('total', len(applications))} application(s), "
            f"{summary.get('active', 0)} still in progress:\n\n{lines}"
        )

    if tool == "get_my_profile":
        skills = payload.get("skills") or []
        completeness = payload.get("completeness") or {}

        return (
            f"You are registered as {payload.get('full_name')} "
            f"({payload.get('email')}).\n"
            f"Skills on your profile: "
            f"{', '.join(skills) if skills else 'none listed yet'}.\n"
            f"CV on file: {'yes' if payload.get('has_cv') else 'no'}.\n"
            f"Profile completeness: {completeness.get('percent', 0)}%."
        )

    if tool == "get_my_cv":
        if not payload.get("has_cv"):
            return (
                "You have no CV on file yet. Upload one from the My CV page — "
                "you will need it before you can apply."
            )

        current = payload.get("current_cv") or {}
        return (
            f"Your CV on file is {current.get('file_name')}, uploaded "
            f"{(current.get('uploaded_at') or '')[:10]}. SmartHR stores the "
            f"file itself, not its text, so the skills I match on are the ones "
            f"on your profile."
        )

    return json.dumps(payload, ensure_ascii=False, default=str)[:1500]


def _no_text_fallback(steps: list[dict[str, Any]]) -> str:
    """The model asked for tools and then produced no prose."""
    successful = [s for s in steps if s["ok"] and s["data"]]

    if not successful:
        return (
            "I could not gather anything from SmartHR for that. Rather than "
            "guess, I would rather tell you I do not know."
        )

    last = successful[-1]
    return _render(last["tool"], last["data"], apply_offered=False)
