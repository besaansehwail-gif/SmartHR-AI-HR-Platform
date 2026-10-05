"""The Internal HR Agent.

SmartHR's third AI surface, and the third audience for one MCP server:

    /ai/chat             the staff assistant   roles 1-4   one tool, one turn
    /applicant/agent/*   the Career Agent      role 5      multi-step, applicant
    /hr/agent/*          this                  roles 1-2   multi-step, recruiter

It shares the provider abstraction (`app/ai/provider.py`), the MCP client
(`app/mcp/client.py`) and the scoring arithmetic (`matching_service`) with
both of the others. What it does not share is a single tool: `tools_for_role`
gives a recruiter the ten recruitment tools and gives an applicant the eight
self-service ones, and the two sets do not intersect. Keeping the agents
separate is therefore not a convention anybody has to remember - the tool
lists are disjoint by policy, so neither agent can reach the other's data even
if its prompt were replaced wholesale.

The loop
--------

    "Find the best candidates for the Data Analyst position."
      -> get_job / search_jobs         which requisition is this?
      -> get_job_requirements          what does it actually ask for?
      -> rank_candidates_for_job       score the real applicants
      -> get_candidate_cv              read the evidence for the top few
      -> final answer, written from those results

The sequence is the model's to choose; nothing here scripts it. `MAX_STEPS`
bounds it so a confused model costs a bounded amount rather than looping.

Why this agent cannot hire anybody
----------------------------------

Not because the prompt says so - though it does - but because **every HR Agent
tool reads**. There is no tool to change an application's stage, create an
interview, write a note or send anything to a candidate. Advancing or
rejecting someone remains `PATCH /applications/{id}/status` in the Recruitment
UI, a recruiter's deliberate act. The Career Agent needed a two-gate
arrangement around `submit_application` because it has one write; this agent
needs none because it has none, which is the stronger arrangement of the two.

What it must never do is invent
-------------------------------

A screening answer is read as being about real people, so a fabricated skill
is worse here than a fabricated job title is on the applicant side. Three
things defend against it: the tools return provenance with every skill
(`skills_sources`), an unevidenced candidate is scored `null` rather than `0`,
and the prompt tells the model in as many words that a null is missing
evidence and not a low score. The tool trace is shown in the UI under every
answer for the same reason.
"""

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.ai.config import llm_settings
from app.ai.provider import LlmError, LlmNotConfigured, get_provider
from app.mcp import client as mcp
from app.mcp.identity import Principal
from app.models import User

logger = logging.getLogger("smarthr.ai.hr")

#: Requisition -> requirements -> rank -> read two CVs -> answer is five, so
#: eight leaves room for a recruiter's follow-up within one turn without
#: letting a stuck model run away.
MAX_STEPS = 8

#: Tools whose result carries per-candidate screening rows. Used only to lift
#: those rows into the response so the UI can render cards from real data
#: rather than parsing them back out of the model's prose.
RESULT_TOOLS = ("rank_candidates_for_job", "match_candidate_to_job")


SYSTEM_PROMPT = """You are the SmartHR Internal AI Agent. You work for the \
recruiting team of this organisation, and you are talking to a signed-in HR \
user or administrator.

Your goal: help this recruiter understand their own recruitment data - which \
requisitions are open, who has applied, what evidence SmartHR holds about \
each candidate, and how that evidence lines up with what a job asks for.

How you work:
1. You have tools that read the live SmartHR PostgreSQL database. Use them. \
You know nothing about this organisation's jobs, candidates or applications \
except what a tool returns in this conversation.
2. Call as many tools as the question needs, one at a time. A typical \
screening request means: find the requisition, read its requirements, rank \
the candidates who applied, then read the CVs of the strongest few before you \
describe them.
3. If the recruiter names a position in words, resolve it with get_job or \
search_jobs first. If a title is ambiguous the tool will tell you so and list \
the matches - ask which one is meant. Never pick one yourself and never screen \
against a requisition you have not confirmed.

Never invent anything about a person:
4. Every skill, job title, employer, qualification, certification and date you \
mention must have come back from a tool in this conversation. If you did not \
read it, you do not know it.
5. A match score of null is NOT a low score and NOT zero. It means SmartHR \
holds no CV and no profile skills for that candidate, so there is nothing to \
compare. Say exactly that - "SmartHR holds no CV or skills for this candidate" \
- and suggest asking them for a CV. Never describe such a person as a weak or \
poor match, and never place them in a ranking as though they had scored low.
6. An empty list from a CV means the document did not state it. It does not \
mean the candidate lacks it. Say "their CV does not mention X", never "they do \
not have X".
7. SmartHR stores CV files, not CV text, so searching candidates does not \
search inside CVs. If a recruiter asks who has a particular skill, say which \
people you found and that others may have it in a CV you have not read.

Match scores:
8. A score is skill overlap: how many of the requirements the job lists are \
evidenced by what SmartHR holds about that candidate. Always give the score, \
the matching skills, the skill gaps and where the evidence came from. Label it \
"AI Match / Recommendation".
9. It is a suggested reading order for a recruiter. It is not a shortlist, not \
a ranking of people, and not a measure of anyone's worth.

The decision is not yours:
10. You cannot hire, reject, shortlist, advance, withdraw or schedule \
anything. You have no tool for any of it, because those decisions belong to \
HR and are made in the Recruitment screens. Never say a candidate should be \
rejected or hired. You may say who is worth reading first and why.
11. Never comment on or infer anything about a candidate's age, gender, \
nationality, ethnicity, religion, health or family circumstances, even if a CV \
mentions it. Screen on skills and experience only.

Style: brief and concrete, written for a busy recruiter. Name real people, \
real requisitions and real figures. Lead with the ranking, then the evidence. \
Answer in the language the recruiter used."""


# ---------------------------------------------------------------------------
# The loop
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
                "This tool refused or failed. Tell the recruiter what "
                "happened. Do not work around it and do not answer from "
                "memory or assumption."
            ),
        }

    # Screening payloads are large - a ranking with eight parsed CVs carries a
    # lot of detail. Truncating mid-JSON would hand the model malformed input,
    # so oversized results are trimmed structurally instead: the candidate
    # rows are kept, their bulkiest sub-objects dropped, and the model is told.
    encoded = json.dumps(payload, ensure_ascii=False, default=str)

    if len(encoded) <= 24000:
        return encoded

    trimmed = _trim_results(payload)
    encoded = json.dumps(trimmed, ensure_ascii=False, default=str)

    return encoded[:24000]


def _trim_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Shrink a ranking payload by dropping detail, never by cutting the JSON."""
    rows = payload.get("results")

    if not isinstance(rows, list):
        return payload

    slim = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        evidence = row.get("evidence") or {}
        slim.append({
            "candidate": {
                key: (row.get("candidate") or {}).get(key)
                for key in ("candidate_id", "full_name", "email", "has_cv")
            },
            "match": row.get("match"),
            "evidence": {
                key: evidence.get(key)
                for key in (
                    "evidence_available", "skills", "skills_sources",
                    "cv_read", "evidence_note",
                )
            },
            "relevant_experience": row.get("relevant_experience"),
        })

    return {
        **{k: v for k, v in payload.items() if k != "results"},
        "results": slim,
        "truncation_note": (
            "Full education, certification and experience detail was omitted "
            "from this result because it was large. Call get_candidate_cv for "
            "a specific candidate to see it."
        ),
    }


def _screening_rows(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The per-candidate screening rows this turn produced, newest tool first.

    Lifted out of the tool results so the UI can render candidate cards from
    the *same* data the model was given, rather than re-parsing its prose.
    Whatever the model writes, these rows are what the tools actually
    returned.
    """
    for step in reversed(steps):
        if not step.get("ok") or step.get("tool") not in RESULT_TOOLS:
            continue

        data = step.get("data") or {}

        if step["tool"] == "rank_candidates_for_job":
            rows = data.get("results")
            if isinstance(rows, list) and rows:
                return rows

        if step["tool"] == "match_candidate_to_job" and data.get("candidate"):
            return [{
                "candidate": data.get("candidate"),
                "job": data.get("job"),
                "match": data.get("match"),
                "evidence": data.get("evidence"),
                "relevant_experience": data.get("relevant_experience"),
                "education": data.get("education"),
                "certifications": data.get("certifications"),
            }]

    return []


def _screened_job(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The requisition this turn ended up screening against, if any."""
    for step in reversed(steps):
        if not step.get("ok"):
            continue

        data = step.get("data") or {}
        job = data.get("job")

        if isinstance(job, dict) and job.get("job_id"):
            return job

    return None


def _envelope(
    *,
    reply: str,
    steps: list[dict[str, Any]],
    settings,
    generated_by: str,
    notice: str | None,
) -> dict[str, Any]:
    """One response shape, used by every exit from this module."""
    return {
        "reply": reply,
        "steps": steps,
        "tools_used": [s["tool"] for s in steps],
        "tool_used": steps[-1]["tool"] if steps else None,
        "data": steps[-1]["data"] if steps else None,
        # Real screening rows from the tools, for the candidate cards.
        "candidates": _screening_rows(steps),
        "job": _screened_job(steps),
        "generated_by": generated_by,
        "tool_transport": "mcp",
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model,
        # Stated on every response because it is the point: this agent has no
        # tool that writes, so no answer it gives has changed anything.
        "is_hiring_decision": False,
        "read_only": True,
        "notice": notice,
    }


def run_agent(
    message: str,
    history: list[dict[str, str]],
    user: User,
    db: Session,
) -> dict[str, Any]:
    """One Internal HR Agent turn.

    `db` is the request's session and is used for nothing but consistency with
    the router's signature: every read goes through MCP, which opens its own
    session per tool. The agent holds no database handle, so it cannot read
    around its own tools.
    """
    started = time.perf_counter()
    settings = llm_settings()
    principal = Principal(user_id=user.id, email=user.email, role_id=user.role_id)

    logger.info(
        "HR agent turn start | user_id=%s role_id=%s llm=%s provider=%s",
        user.id, user.role_id, settings.configured, settings.provider,
    )

    try:
        offered = mcp.list_tools(principal, user.role_id)
    except Exception:
        logger.exception("HR agent: MCP tools/list failed | user_id=%s", user.id)
        offered = []

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
    offered_names = {tool.name for tool in offered}

    try:
        for step in range(1, MAX_STEPS + 1):
            reply = provider.complete(SYSTEM_PROMPT, messages, tools=specs)

            if reply.tool_call is None:
                logger.info(
                    "HR agent done | user_id=%s steps=%s elapsed_ms=%s",
                    user.id, len(steps), round((time.perf_counter() - started) * 1000),
                )

                return _envelope(
                    reply=reply.text or _no_text_fallback(steps),
                    steps=steps,
                    settings=settings,
                    generated_by="llm",
                    notice=None,
                )

            call = reply.tool_call

            # A model asking for a tool it was not offered - which for this
            # agent means a tool its caller's role may not run, or one that
            # does not exist. Refused in the transcript rather than dropped
            # silently, so the trace shows the attempt.
            if call.name not in offered_names:
                logger.warning(
                    "HR agent requested an unoffered tool | user_id=%s tool=%s",
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
                        f"'{call.name}' is not a tool you have. SmartHR's HR "
                        f"Agent can only read recruitment data - it cannot "
                        f"change an application, hire, reject or schedule "
                        f"anything."
                    ),
                })))
                continue

            result = mcp.call_tool(principal, call.name, call.arguments)

            steps.append({
                "step": step,
                "tool": call.name,
                # Keys only - an argument value could be personal.
                "arguments": sorted(call.arguments.keys()),
                "ok": result.ok,
                "error_code": result.error_code,
                "data": result.payload if result.ok else None,
            })

            messages.extend(provider.tool_exchange(reply, _result_json(result)))

        logger.warning(
            "HR agent hit the step limit | user_id=%s steps=%s", user.id, len(steps)
        )

        return _envelope(
            reply=_no_text_fallback(steps),
            steps=steps,
            settings=settings,
            generated_by="tool",
            notice=(
                "The agent reached its step limit. This summary comes straight "
                "from the SmartHR data it gathered."
            ),
        )

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
        logger.warning("HR agent LLM error | user_id=%s error=%s", user.id, exc)

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
# Real tool output, resolved by keyword and rendered. Every figure came out of
# PostgreSQL. This path is deliberately kept: an HR user whose model is down
# should still be able to see who applied to a requisition.
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Order matters - the first tool whose keywords appear wins, so the
    # screening verbs are checked before the plain lookups.
    "rank_candidates_for_job": (
        "best candidate", "rank", "top candidate", "strongest", "shortlist",
        "suitable candidate", "match candidates", "who should", "screen",
        "أفضل مرشح", "ترتيب", "ترشيح",
    ),
    "search_candidates": (
        "candidate", "applicant", "who applied", "people with", "skills",
        "مرشح", "متقدم", "مهارات",
    ),
    "search_applications": (
        "application", "pipeline", "stage", "applied to", "طلبات", "مرحلة",
    ),
    "search_jobs": (
        "job", "position", "role", "requisition", "vacancy", "opening",
        "requirement", "وظيف", "شاغر", "متطلبات",
    ),
}


def _keyword_tool(message: str, offered: set[str]) -> str | None:
    text = (message or "").lower()

    for tool, keywords in INTENT_KEYWORDS.items():
        if tool not in offered:
            continue

        if any(keyword in text for keyword in keywords):
            return tool

    return "search_jobs" if "search_jobs" in offered else None


def _fallback_arguments(tool: str, message: str) -> dict[str, Any]:
    """Arguments for the one call the no-model path makes.

    The recruiter's own words are passed as the search so an absent topic
    returns nothing rather than the whole table - the same reasoning as the
    Career Agent's fallback. `rank_candidates_for_job` needs a requisition it
    cannot resolve without a model, so it is given the message as a title and
    will refuse cleanly if that names nothing.
    """
    if tool in ("search_jobs", "search_candidates"):
        return {"search": message, "limit": 10}

    if tool == "rank_candidates_for_job":
        return {"job_title": message, "limit": 10}

    return {"limit": 10}


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
    names = {tool.name for tool in offered}
    tool = _keyword_tool(message, names)

    if tool is None:
        return _envelope(
            reply=(
                "I could not reach the SmartHR tools just now, so I have "
                "nothing to tell you rather than something I made up. Please "
                "try again in a moment."
            ),
            steps=steps,
            settings=settings,
            generated_by="none",
            notice=notice,
        )

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
        "HR agent answered without a model | user_id=%s tool=%s ok=%s elapsed_ms=%s",
        principal.user_id, tool, result.ok,
        round((time.perf_counter() - started) * 1000),
    )

    if not result.ok:
        reply = (
            f"I could not read that from SmartHR: {result.error} "
            f"Nothing here is guessed - if I cannot read it, I will not "
            f"invent it."
        )
    else:
        reply = _render(tool, result.payload)

    return _envelope(
        reply=reply,
        steps=steps,
        settings=settings,
        generated_by="tool",
        notice=notice,
    )


# ---------------------------------------------------------------------------
# Rendering real tool output, with no model
# ---------------------------------------------------------------------------

def _candidate_line(index: int, row: dict[str, Any]) -> str:
    candidate = row.get("candidate") or {}
    match = row.get("match") or {}
    name = candidate.get("full_name") or f"Candidate {candidate.get('candidate_id')}"

    if match.get("score") is None:
        return (
            f"{index}. {name} — not scored\n"
            f"    {match.get('score_basis') or 'SmartHR holds no evidence for this candidate.'}"
        )

    line = f"{index}. {name} — {match['score']}% (AI Match / Recommendation)"

    if match.get("matching_skills"):
        line += f"\n    Matching skills: {', '.join(match['matching_skills'])}"

    if match.get("skill_gaps"):
        line += f"\n    Skill gaps: {', '.join(match['skill_gaps'])}"

    experience = row.get("relevant_experience") or {}
    if experience.get("basis"):
        line += f"\n    Experience: {experience['basis']}"

    evidence = row.get("evidence") or {}
    if evidence.get("skills_sources"):
        line += f"\n    Evidence from: {' and '.join(evidence['skills_sources'])}"

    return line


def _render(tool: str, payload: dict[str, Any]) -> str:
    """Turn one tool result into readable text. Every value comes from payload."""
    if tool == "rank_candidates_for_job":
        job = payload.get("job") or {}
        rows = payload.get("results") or []

        if not rows:
            return (
                f"{payload.get('note') or 'No candidate matched.'} Nothing has "
                f"been invented to fill the gap."
            )

        listed = "\n".join(
            _candidate_line(i, row) for i, row in enumerate(rows, start=1)
        )

        text = (
            f"Candidates for {job.get('title')} "
            f"(requirements: {', '.join(job.get('requirements') or []) or 'none listed'}):\n\n"
            f"{listed}\n\n"
            f"This is a suggested reading order, not a shortlist and not a "
            f"hiring decision. Nothing has been changed."
        )

        if payload.get("unevidenced_note"):
            text += f"\n\n{payload['unevidenced_note']}"

        return text

    if tool == "match_candidate_to_job":
        return _candidate_line(1, payload)

    if tool == "search_candidates":
        rows = payload.get("candidates") or []

        if not rows:
            return "No candidate in SmartHR matches those filters."

        listed = "\n".join(
            f"• {row.get('full_name')} — {row.get('email')}"
            + (f"\n    Profile skills: {', '.join(row['profile_skills'])}"
               if row.get("profile_skills") else "")
            + (f"\n    CV on file: {row.get('cv_file_name')}"
               if row.get("has_cv") else "\n    No CV on file")
            for row in rows
        )

        return (
            f"{len(rows)} candidate(s):\n\n{listed}\n\n"
            f"This searched candidate records, not CV text - SmartHR stores CV "
            f"files, not their contents."
        )

    if tool == "search_jobs":
        rows = payload.get("jobs") or []

        if not rows:
            return "No requisition in SmartHR matches those words."

        listed = "\n".join(
            f"• {row.get('title')} ({row.get('status')}) — "
            f"{row.get('department_name') or 'no department'}, "
            f"{row.get('applications_count', 0)} applicant(s)"
            + (f"\n    Requires: {', '.join(row['requirements'])}"
               if row.get("requirements") else "\n    No requirements listed")
            for row in rows
        )

        return f"{len(rows)} requisition(s):\n\n{listed}"

    if tool == "search_applications":
        rows = payload.get("applications") or []

        if not rows:
            return "No application matches those filters."

        listed = "\n".join(
            f"• {row.get('candidate_name')} — {row.get('job_title')} "
            f"({row.get('status')})"
            for row in rows
        )

        return f"{len(rows)} application(s):\n\n{listed}"

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
    return _render(last["tool"], last["data"])
