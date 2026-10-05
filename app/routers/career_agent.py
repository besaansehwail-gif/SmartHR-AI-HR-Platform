"""The Career Agent endpoint.

    POST /applicant/agent/chat    ask the agent something
    GET  /applicant/agent/status  what it can do, and how it is wired

Both are `require_applicant`, so this is role 5 only. The staff assistant at
`/ai/chat` is untouched and remains roles 1-4: two audiences, two endpoints,
one MCP server underneath.

The request body carries a message and history and **nothing else** - no user
id, no candidate id, no role. The agent's principal is built here from the
verified JWT, which is the only reason its tools can be trusted to answer for
the right person.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.career_agent import MAX_STEPS, apply_intent, run_agent
from app.ai.config import llm_settings
from app.dependencies import get_current_candidate, get_db, require_applicant
from app.identity import resolve_candidate
from app.mcp import client as mcp
from app.mcp.identity import Principal
from app.mcp.permissions import policy_for
from app.models import Candidate, User

logger = logging.getLogger("smarthr.ai.career")

router = APIRouter(
    prefix="/applicant/agent",
    tags=["Career Agent"]
)




class AgentTurn(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[AgentTurn] = Field(default_factory=list, max_length=20)


@router.post("/chat")
def agent_chat(
    payload: AgentRequest,
    current_user: User = Depends(require_applicant),
    # Not read by the agent, but it makes the route refuse an applicant account
    # with no candidates row before any tool runs, with a clear 404.
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ask the Career Agent something to get an answer.",
        )

    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]

    try:
        return run_agent(message, history, current_user, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Career agent turn failed | user_id=%s", current_user.id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The Career Agent could not complete that request. Your "
                "profile and applications are unaffected - please try again."
            ),
        )


@router.get("/status")
def agent_status(
    current_user: User = Depends(require_applicant),
    db: Session = Depends(get_db),
):
    """What the agent can do for this applicant.

    The tool list comes from the MCP server over `tools/list`, narrowed to the
    role read out of `users` - this caller's real capability set, not a menu
    the client chose.
    """
    settings = llm_settings()
    principal = Principal(
        user_id=current_user.id, email=current_user.email, role_id=current_user.role_id
    )

    try:
        tools = mcp.list_tools(principal, current_user.role_id)
        mcp_available = True
    except Exception:
        logger.exception("Career agent tools/list failed | user_id=%s", current_user.id)
        tools = []
        mcp_available = False

    return {
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model or None,
        "role_id": current_user.role_id,
        "applicant_linked": resolve_candidate(current_user, db) is not None,
        "tool_transport": "mcp",
        "max_steps": MAX_STEPS,
        "mcp": {"available": mcp_available, "server": mcp.server_info()},
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "scope": (policy_for(tool.name).scope if policy_for(tool.name) else None),
                "parameters": sorted((tool.input_schema.get("properties") or {}).keys()),
                # Surfaced so the UI can explain the gate rather than the
                # applicant wondering why the agent will not apply for them.
                "requires_explicit_request": tool.name == "submit_application",
            }
            for tool in tools
        ],
        "apply_gate": {
            "description": (
                "submit_application is withheld from the model unless your "
                "message asks to apply. Searching or comparing never submits "
                "an application."
            ),
            "example_that_applies": "Apply me to the Data Analyst internship",
            "example_that_does_not": "Find Data Analyst jobs",
        },
    }
