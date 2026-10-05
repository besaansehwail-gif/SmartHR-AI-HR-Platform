"""The Internal HR Agent endpoint.

    POST /hr/agent/chat    ask the agent something
    GET  /hr/agent/status  what it can do, and how it is wired

Both are `require_roles(1, 2)` - Admin and HR, the same pair that already
guards `/candidates/`, `/applications/`, `/cvs/` and `/dashboard/hr`. The
agent reads recruitment data, so it is guarded exactly as recruitment data is
guarded, and adding an AI surface did not widen who may see it.

**Manager (role 3) is refused deliberately.** A Manager reaches their own
team's attendance, leave and performance in SmartHR, and no existing rule
gives them the candidate pipeline; letting their agent read it would have been
a privilege the REST API does not grant. Employee and Applicant are refused
for the same reason, more obviously. If a future business rule brings Managers
into recruitment, the change is one tuple here and one in
`app/mcp/permissions.py` - not a rewrite.

The request body carries a message and history and **nothing else** - no user
id, no role, no candidate id. The agent's principal is built here from the
verified JWT, and `authorise()` re-reads the role from `users` before any tool
body runs, so neither the browser nor the model can widen what this turn may
read.

The staff assistant at `/ai/chat` and the Career Agent at `/applicant/agent/*`
are untouched: three audiences, three endpoints, one MCP server underneath.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.config import llm_settings
from app.ai.hr_agent import MAX_STEPS, run_agent
from app.dependencies import get_db, require_roles
from app.mcp import client as mcp
from app.mcp.identity import Principal
from app.mcp.permissions import policy_for
from app.models import User

logger = logging.getLogger("smarthr.ai.hr")

router = APIRouter(
    prefix="/hr/agent",
    tags=["Internal HR Agent"]
)

#: Admin and HR. Named once so the guard and the documentation cannot drift.
HR_AGENT_ROLES = (1, 2)


class AgentTurn(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[AgentTurn] = Field(default_factory=list, max_length=20)


@router.post("/chat")
def agent_chat(
    payload: AgentRequest,
    current_user: User = Depends(require_roles(*HR_AGENT_ROLES)),
    db: Session = Depends(get_db),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ask the Internal HR Agent something to get an answer.",
        )

    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]

    try:
        return run_agent(message, history, current_user, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("HR agent turn failed | user_id=%s", current_user.id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The Internal HR Agent could not complete that request. No "
                "candidate, application or requisition has been changed - the "
                "agent only reads. Please try again."
            ),
        )


@router.get("/status")
def agent_status(
    current_user: User = Depends(require_roles(*HR_AGENT_ROLES)),
    db: Session = Depends(get_db),
):
    """What the agent can do for this recruiter.

    The tool list comes from the MCP server over `tools/list`, narrowed to the
    role read out of `users` - this caller's real capability set, not a menu
    the client chose. `writes` is reported per tool and is False for every one
    of them, which is the property the UI states rather than asserts.
    """
    settings = llm_settings()
    principal = Principal(
        user_id=current_user.id, email=current_user.email, role_id=current_user.role_id
    )

    try:
        tools = mcp.list_tools(principal, current_user.role_id)
        mcp_available = True
    except Exception:
        logger.exception("HR agent tools/list failed | user_id=%s", current_user.id)
        tools = []
        mcp_available = False

    return {
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model or None,
        "role_id": current_user.role_id,
        "tool_transport": "mcp",
        "max_steps": MAX_STEPS,
        "read_only": True,
        "mcp": {"available": mcp_available, "server": mcp.server_info()},
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "scope": (policy_for(tool.name).scope if policy_for(tool.name) else None),
                "parameters": sorted((tool.input_schema.get("properties") or {}).keys()),
                # No HR Agent tool writes. Surfaced per tool rather than as one
                # claim so the UI shows the evidence, not the assertion.
                "writes": False,
            }
            for tool in tools
        ],
        "guarantees": {
            "read_only": (
                "Every tool this agent has reads. There is no tool to change "
                "an application's stage, hire, reject, shortlist or schedule "
                "an interview, so no answer it gives has changed anything."
            ),
            "decision_owner": (
                "A match score is a suggested reading order for a recruiter. "
                "The hiring decision is always HR's, made in the Recruitment "
                "screens."
            ),
            "no_invention": (
                "Skills come from a candidate's profile and from reading their "
                "CV, and every one is reported with its source. A candidate "
                "SmartHR holds no evidence for scores null, never zero."
            ),
        },
        "examples": [
            "Find the best candidates for the Data Analyst position",
            "Rank the candidates for the QA Engineer job",
            "Show me candidates with Python and SQL skills",
            "Why is candidate 5 a strong match for the Data Analyst role?",
            "What skills is Samer Ali missing for the Data Analyst job?",
            "Which candidates are at the interview stage?",
        ],
    }
