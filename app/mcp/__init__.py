"""SmartHR's Model Context Protocol layer.

MCP is the **protocol** by which SmartHR offers its capabilities to a language
model. It is not the model, not the API and not the database - it sits between
the model and SmartHR's own services:

    React assistant
      -> POST /ai/chat                (FastAPI, authenticates the caller)
      -> app/ai/assistant.py          (orchestrates the turn)
      -> app/mcp/client.py            MCP client  ──┐ real JSON-RPC session
      -> app/mcp/server.py            MCP server  ──┘ (tools/list, tools/call)
      -> app/mcp/tools/*.py           @mcp.tool() registrations
      -> app/services/*.py            SmartHR business logic
      -> app/models.py                SQLAlchemy -> PostgreSQL

Modules:

    identity.py     who the current call is for, carried out of band
    permissions.py  which roles may run which tool
    server.py       the MCPServer instance and its stdio entry point
    client.py       the in-process client the AI endpoint uses
    tools/          one module per capability area

**The security property that matters.** The MCP tools take no user id,
employee id or role as an argument. Identity travels in a `contextvars`
binding that the FastAPI layer sets from the verified JWT before the session
opens, so it is not part of the tool schema the model sees and there is no
field for a model - or a crafted frontend request - to put somebody else's id
in. `permissions.py` then re-reads the role from `users` before any tool body
runs, exactly as `require_roles` does for the REST API.
"""
