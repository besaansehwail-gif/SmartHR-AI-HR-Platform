"""SmartHR AI Assistant.

The assistant is a thin layer on top of the application that already exists.
It owns no data and talks to no database of its own: every answer it gives is
produced by running one of the tools in `tools.py`, and those tools go through
the same models, the same identity resolution and the same role rules as the
REST endpoints.

    chat message
      -> app/routers/ai.py          authenticate, identify the caller
      -> app/ai/assistant.py        orchestrate
      -> app/ai/provider.py         ask the LLM which tool answers this
      -> app/ai/tools.py            check the role, run the tool
      -> app/models.py              SQLAlchemy -> PostgreSQL
      -> app/ai/provider.py         ask the LLM to phrase the result

The split matters for one reason: **the LLM chooses, it never authorises.**
`run_tool()` re-checks the caller's role against the tool's allowed roles from
the database before the handler runs, so a model that asks for a tool the
caller may not use gets a refusal rather than data.
"""
