"""SmartHR business logic, independent of how it is called.

A service here knows about SmartHR's data and rules and nothing about
transport: it does not know whether it was reached from a REST endpoint, from
an MCP tool, or from a script. That is what lets the MCP layer expose real
SmartHR behaviour instead of re-implementing it against the same tables.

    app/routers/*   REST  ─┐
                           ├─> app/services/*  ─> app/models.py ─> PostgreSQL
    app/mcp/tools/* MCP   ─┘
"""
