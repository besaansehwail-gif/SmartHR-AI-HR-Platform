"""The MCP client side, as used by the AI endpoint.

`POST /ai/chat` is a synchronous FastAPI route and the MCP SDK is async, so
this module owns the bridge: the two public helpers are synchronous, and each
opens a real MCP client session against `smarthr_mcp` over the SDK's in-memory
transport, performs one operation, and closes it.

A session per operation is the honest trade here. It is a handful of in-memory
JSON-RPC messages with no process, socket or network involved, and it means a
request can never observe another request's session or principal. The principal
is bound before the session opens and reset after it closes.

Both helpers return plain data. Nothing above this module imports the MCP SDK,
so swapping the transport - to a stdio subprocess, or to a remote SmartHR MCP
server over streamable HTTP - is a change confined to this file.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from mcp import Client

from app.mcp.identity import Principal, bind_principal
from app.mcp.permissions import tools_for_role
from app.mcp.server import smarthr_mcp

logger = logging.getLogger("smarthr.mcp.client")


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class McpToolResult:
    tool: str
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None

    @property
    def payload(self) -> dict[str, Any]:
        return self.data or {}


def _run(coro):
    """Run an async MCP operation from a synchronous request handler.

    FastAPI executes `def` endpoints in a worker thread, which has no running
    event loop, so a private loop here is correct and cheap. If this is ever
    called from an async context, that is a bug worth failing on rather than
    deadlocking quietly.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    raise RuntimeError(
        "SmartHR MCP helpers are synchronous and must not be called from an "
        "async context; await the MCP client directly instead."
    )


def _text_of(result: Any) -> str:
    """Concatenate the text blocks of a tools/call result."""
    parts: list[str] = []

    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)

    return "\n".join(parts).strip()


async def _strip_undeclared(
    client: Any, name: str, arguments: dict[str, Any], principal: Principal
) -> dict[str, Any]:
    """Keep only arguments the tool's own schema declares."""
    listing = await client.list_tools()
    schema: dict[str, Any] = {}

    for tool in listing.tools:
        if tool.name == name:
            schema = dict(tool.input_schema or {})
            break

    declared = set((schema.get("properties") or {}).keys())

    if not declared:
        return arguments

    kept = {key: value for key, value in arguments.items() if key in declared}
    dropped = sorted(set(arguments) - declared)

    if dropped:
        logger.warning(
            "MCP tools/call dropped undeclared arguments | tool=%s user_id=%s dropped=%s",
            name,
            principal.user_id,
            dropped,
        )

    return kept


async def _list_tools_async(principal: Principal) -> list[McpTool]:
    with bind_principal(principal):
        async with Client(smarthr_mcp) as client:
            listing = await client.list_tools()

    return [
        McpTool(
            name=tool.name,
            description=tool.description or "",
            input_schema=dict(tool.input_schema or {"type": "object", "properties": {}}),
        )
        for tool in listing.tools
    ]


async def _call_tool_async(
    principal: Principal, name: str, arguments: dict[str, Any] | None
) -> McpToolResult:
    with bind_principal(principal):
        async with Client(smarthr_mcp) as client:
            # Drop anything the tool did not declare. The SDK would ignore an
            # extra argument anyway, but an unrequested `employee_id` is worth
            # discarding deliberately and logging: it is exactly the shape an
            # attempt to widen scope would take.
            safe_arguments = await _strip_undeclared(client, name, arguments or {}, principal)
            result = await client.call_tool(name, safe_arguments)

    if getattr(result, "is_error", False):
        message = _text_of(result) or f"The tool '{name}' failed."
        return McpToolResult(tool=name, ok=False, error=message, error_code="tool_error")

    payload: Any = getattr(result, "structured_content", None)

    if payload is None:
        text = _text_of(result)
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"result": text}

    # The SDK wraps a non-object return value as {"result": ...}.
    if isinstance(payload, dict) and set(payload.keys()) == {"result"} and isinstance(
        payload["result"], dict
    ):
        payload = payload["result"]

    if not isinstance(payload, dict):
        payload = {"result": payload}

    # SmartHR tools report their own refusals in the body rather than as a
    # protocol error, so that the model can explain them.
    if payload.get("ok") is False:
        return McpToolResult(
            tool=name,
            ok=False,
            error=payload.get("error") or "The tool refused the request.",
            error_code=payload.get("error_code"),
        )

    payload.pop("ok", None)
    return McpToolResult(tool=name, ok=True, data=payload)


def list_tools(principal: Principal, role_id: int | None) -> list[McpTool]:
    """The MCP tools this caller may run.

    The server is asked over the protocol for everything it offers, then the
    list is narrowed to the caller's role so a model is never shown a
    capability its caller could not use. Narrowing here is convenience;
    `authorise()` inside the tool is the boundary.
    """
    allowed = set(tools_for_role(role_id))
    discovered = _run(_list_tools_async(principal))
    tools = [tool for tool in discovered if tool.name in allowed]

    logger.info(
        "MCP tools/list | user_id=%s discovered=%s offered=%s",
        principal.user_id,
        [t.name for t in discovered],
        [t.name for t in tools],
    )

    return tools


def call_tool(
    principal: Principal, name: str, arguments: dict[str, Any] | None = None
) -> McpToolResult:
    """Invoke one MCP tool for this caller."""
    logger.info(
        "MCP tools/call -> %s | user_id=%s args=%s",
        name,
        principal.user_id,
        sorted((arguments or {}).keys()),  # keys only; values may be personal
    )

    try:
        result = _run(_call_tool_async(principal, name, arguments))
    except Exception:
        logger.exception("MCP tools/call failed | tool=%s user_id=%s", name, principal.user_id)
        return McpToolResult(
            tool=name,
            ok=False,
            error="The SmartHR tool layer could not be reached.",
            error_code="mcp_unavailable",
        )

    logger.info(
        "MCP tools/call <- %s | user_id=%s ok=%s code=%s",
        name,
        principal.user_id,
        result.ok,
        result.error_code,
    )

    return result


def server_info() -> dict[str, Any]:
    """Static description of the MCP server, for /ai/status and diagnostics."""
    return {
        "name": getattr(smarthr_mcp, "name", "smarthr"),
        "transport": "in-process (stdio available via `python -m app.mcp`)",
    }
