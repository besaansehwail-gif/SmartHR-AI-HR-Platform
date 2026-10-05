"""HR document tools - the retrieval half of RAG.

`search_hr_policies` is how the assistant reads company documents. It is an
MCP tool like any other, which is the point: the model already knows how to
choose between tools, so asking "what is the remote work policy?" versus "how
many leave requests do I have?" is a tool choice it makes, not a keyword rule
somebody wrote.

    search_hr_policies  ->  app/rag/service.search_policies()  ->  vector store

**RAG does not replace MCP here; it sits behind it.** `get_my_leave` reads rows
from PostgreSQL, `search_hr_policies` reads passages from indexed documents,
and both are reached the same way. There is one retrieval implementation -
this tool calls the same `search_policies()` that anything else would.

**The tool returns passages, not answers.** It never summarises or concludes;
it hands back the retrieved text with its citation and lets the model write the
answer from it. That is what makes the answer checkable: every sentence should
be traceable to a passage the tool returned.
"""

import logging
from typing import Annotated, Any

from pydantic import Field

from app.mcp.identity import NoPrincipalBound, current_principal
from app.mcp.permissions import ToolNotPermitted, authorise
from app.mcp.server import smarthr_mcp
from app.rag.service import DEFAULT_TOP_K, search_policies

logger = logging.getLogger("smarthr.mcp.tools")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message}


@smarthr_mcp.tool(
    name="search_hr_policies",
    title="Search HR policy documents",
    description=(
        "Search the organisation's written HR policy documents and return the "
        "passages most relevant to a question, each with its source. Use this "
        "for questions about rules, entitlements, procedures and what the "
        "policy says - annual leave allowance, sick leave, working hours, "
        "lateness, remote and hybrid working, onboarding, probation. This "
        "returns document passages, not live records: for what a specific "
        "person has actually done or requested, use the tools that read "
        "SmartHR's database instead. If the documents do not cover the "
        "question this returns nothing, which means the policy is silent on "
        "it - do not answer from general knowledge in that case."
    ),
)
def search_hr_policies(
    query: Annotated[
        str,
        Field(description=(
            "What to look for, in the user's own words. Natural language "
            "works better than keywords."
        )),
    ],
    top_k: Annotated[
        int | None,
        Field(default=None, ge=1, le=10,
              description="How many passages to return. Defaults to 4."),
    ] = None,
) -> dict[str, Any]:
    """Retrieve the passages most relevant to a question."""
    try:
        principal = current_principal()
    except NoPrincipalBound as exc:
        logger.warning("search_hr_policies called with no principal bound")
        return _error("no_principal", str(exc))

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # Authorisation from the database, like every other tool. These are
        # published internal documents, so every signed-in role may read them -
        # but "every role" is still a decision recorded in permissions.py, and
        # an inactive or deleted account is still refused here.
        try:
            authorise("search_hr_policies", principal.user_id, db)
        except ToolNotPermitted as exc:
            logger.info(
                "search_hr_policies refused | user_id=%s code=%s",
                principal.user_id, exc.code,
            )
            return _error(exc.code, str(exc))
    finally:
        db.close()

    result = search_policies(query, top_k=top_k or DEFAULT_TOP_K)

    if result.error_code:
        return _error(result.error_code, result.error or "The document search failed.")

    payload = result.to_dict()

    if not result.found:
        # An explicit, actionable "nothing found" rather than an empty list the
        # model might paper over with something plausible.
        return {
            "ok": True,
            **payload,
            "guidance": (
                "No passage in the HR documents matches this question. Tell the "
                "user the documents do not cover it. Do not answer from general "
                "knowledge and do not guess what the policy might say."
            ),
        }

    logger.info(
        "search_hr_policies ok | user_id=%s passages=%s demo=%s",
        principal.user_id, len(result.chunks), payload["contains_demo_content"],
    )

    return {
        "ok": True,
        **payload,
        "guidance": (
            "Answer using only the passages above. Quote figures exactly as "
            "written. Name the source document in the answer. If the passages "
            "do not contain the answer, say so rather than filling the gap."
            + (
                " These passages come from DEMO documents written for testing, "
                "not real company policy - say so in the answer."
                if payload["contains_demo_content"] else ""
            )
        ),
    }
