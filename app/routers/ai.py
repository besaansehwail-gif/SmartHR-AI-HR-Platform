"""The SmartHR AI Assistant endpoint.

    POST /ai/chat     ask a question, get an answer grounded in MCP tool output
    GET  /ai/status   what this caller can do, and how the stack is wired

Both require authentication. The caller is taken from the JWT through the
existing `get_current_user`; nothing about identity or role is read from the
request body, so the frontend cannot tell the assistant who it is. That
identity is what the MCP layer binds before any tool runs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.assistant import answer
from app.ai.config import llm_settings
from app.database import SessionLocal
from app.dependencies import require_staff
from app.identity import resolve_employee
from app.mcp import client as mcp
from app.mcp.identity import Principal
from app.mcp.permissions import policy_for
from app.mcp.server import registered_tool_names
from app.models import User
from app.rag.service import knowledge_base_status
from app.routers.auth import get_current_user

logger = logging.getLogger("smarthr.ai")

router = APIRouter(
    prefix="/ai",
    tags=["AI Assistant"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    """Note what is *not* here: no user id, no employee id, no role. The server
    knows all three from the token, and accepting them from the client would be
    the whole vulnerability."""

    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


@router.post("/chat")
def chat(
    payload: ChatRequest,
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ask a question to get an answer.",
        )

    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]

    try:
        return answer(message, history, current_user, db)
    except HTTPException:
        raise
    except Exception:
        # The assistant is an add-on. It fails as a feature, never as a 500
        # that the chat panel cannot render.
        logger.exception("AI turn failed | user_id=%s", current_user.id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The SmartHR assistant could not complete that request. "
                "Your data is unaffected - please try again."
            ),
        )


@router.get("/status")
def ai_status(
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """What this caller can ask, and how the assistant is wired up.

    The tool list comes from the MCP server over `tools/list`, narrowed to the
    role read out of `users` - so it is this caller's real capability set
    rather than a menu the client chose.
    """
    settings = llm_settings()
    employee = resolve_employee(current_user, db)
    principal = Principal(
        user_id=current_user.id, email=current_user.email, role_id=current_user.role_id
    )

    try:
        tools = mcp.list_tools(principal, current_user.role_id)
        mcp_available = True
    except Exception:
        logger.exception("MCP tools/list failed | user_id=%s", current_user.id)
        tools = []
        mcp_available = False

    return {
        "llm_configured": settings.configured,
        "provider": settings.provider,
        "model": settings.model or None,
        "role_id": current_user.role_id,
        "employee_linked": employee is not None,
        "tool_transport": "mcp",
        "mcp": {
            "available": mcp_available,
            "server": mcp.server_info(),
            "registered_tools": registered_tool_names(),
        },
        # What the assistant can read from documents, as opposed to from the
        # database. Shown so "the policy documents are not indexed" is
        # diagnosable without reading logs.
        "knowledge_base": knowledge_base_status(),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "scope": (policy_for(tool.name).scope if policy_for(tool.name) else None),
                "parameters": sorted((tool.input_schema.get("properties") or {}).keys()),
            }
            for tool in tools
        ],
    }
