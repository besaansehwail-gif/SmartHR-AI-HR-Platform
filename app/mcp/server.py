"""The SmartHR MCP server.

One `MCPServer` instance, `smarthr_mcp`, with SmartHR's capabilities
registered on it as MCP tools. It is a real MCP server: clients `initialize`,
`tools/list` and `tools/call` against it over the protocol.

It can be reached two ways, and both talk MCP:

* **In process** - `app/mcp/client.py` opens a client session against this
  object over the SDK's in-memory transport. This is what `POST /ai/chat`
  uses, and it is why a chat turn costs no subprocess.

* **Over stdio** - ``python -m app.mcp`` serves the same tools to any
  external MCP client (Claude Desktop, the MCP Inspector, another agent).

Note for stdio mode: SmartHR tools need an authenticated principal, which an
external client cannot supply through the protocol. Set `SMARTHR_MCP_USER_ID`
when running standalone and the server binds that account for the session.
That is a development and inspection affordance - the application path binds
the principal from a verified JWT per request instead.

The SDK here is **mcp 2.x**, where v1's `FastMCP` is called `MCPServer`.
"""

import logging
import os
import sys

from mcp.server.mcpserver import MCPServer

logger = logging.getLogger("smarthr.mcp")

smarthr_mcp = MCPServer(
    name="smarthr",
    title="SmartHR",
    version="1.0.0",
    instructions=(
        "SmartHR exposes an organisation's own HR records. Every tool answers "
        "for the authenticated user and returns rows from the SmartHR "
        "PostgreSQL database. Tools take no user, employee or role argument: "
        "the caller's identity is established by SmartHR itself. If a figure "
        "is not in a tool result, SmartHR does not store it - say so rather "
        "than estimating."
    ),
)


def register_tools() -> None:
    """Import the tool modules so their decorators run.

    Registration is a side effect of import, so this has to happen before any
    client lists tools. It is idempotent: importing twice does not re-register.
    """
    from app.mcp.tools import (  # noqa: F401  (imported for their decorators)
        career, cv, leave, policies, screening,
    )


register_tools()


def registered_tool_names() -> list[str]:
    """The tools currently registered, for diagnostics and tests."""
    manager = getattr(smarthr_mcp, "_tool_manager", None)

    if manager is not None and hasattr(manager, "list_tools"):
        return sorted(tool.name for tool in manager.list_tools())

    return sorted(TOOL_NAMES_FALLBACK)


#: Kept in step with the registrations below; used only if the SDK's internal
#: tool manager is not reachable under this name in a future version.
TOOL_NAMES_FALLBACK = [
    "get_my_leave", "parse_cv", "search_hr_policies",
    # Career Agent (Applicant, role 5)
    "get_my_profile", "get_my_cv", "search_opportunities", "get_opportunity",
    "match_my_profile_to_opportunity", "get_my_applications",
    "get_my_application_status", "submit_application",
    # Internal HR Agent (Admin and HR, roles 1-2)
    "search_jobs", "get_job", "get_job_requirements", "search_candidates",
    "get_candidate", "get_candidate_cv", "search_applications",
    "get_application", "match_candidate_to_job", "rank_candidates_for_job",
]


def _bind_principal_from_environment():
    """Standalone mode only: bind the account named by the environment."""
    from app.database import SessionLocal
    from app.mcp.identity import Principal
    from app.models import User

    raw = os.getenv("SMARTHR_MCP_USER_ID")

    if not raw:
        return None

    try:
        user_id = int(raw)
    except ValueError:
        print(
            f"SMARTHR_MCP_USER_ID={raw!r} is not a user id.",
            file=sys.stderr,
        )
        return None

    db = SessionLocal()
    try:
        account = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    if account is None:
        print(f"No user with id {user_id}.", file=sys.stderr)
        return None

    return Principal(user_id=account.id, email=account.email, role_id=account.role_id)


def main() -> None:
    """stdio entry point: ``python -m app.mcp.server``."""
    logging.basicConfig(
        level=os.getenv("SMARTHR_LOG_LEVEL", "INFO"),
        # stdout is the protocol channel in stdio mode; logs must go to stderr.
        stream=sys.stderr,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )

    from app.mcp.identity import bind_principal

    principal = _bind_principal_from_environment()

    print(
        f"SmartHR MCP server (stdio) - tools: {', '.join(registered_tool_names())}",
        file=sys.stderr,
    )

    if principal is None:
        print(
            "No SMARTHR_MCP_USER_ID set: tools needing an identity will refuse. "
            "Set it to a users.id to inspect this server interactively.",
            file=sys.stderr,
        )
        smarthr_mcp.run(transport="stdio")
        return

    print(f"Bound principal: user_id={principal.user_id}", file=sys.stderr)

    with bind_principal(principal):
        smarthr_mcp.run(transport="stdio")


if __name__ == "__main__":
    # Delegate to the canonical module rather than running this one.
    # `python -m app.mcp.server` executes this file as `__main__`, so the tool
    # modules that import `app.mcp.server` would otherwise build a *second*
    # MCPServer and register their tools on that instead of this one.
    # `python -m app.mcp` is the preferred form; both work.
    from app.mcp.server import main as _canonical_main

    _canonical_main()
