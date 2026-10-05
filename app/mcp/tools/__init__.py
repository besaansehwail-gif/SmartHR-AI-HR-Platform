"""SmartHR MCP tools, one module per capability area.

A tool module registers its tools on `smarthr_mcp` with `@smarthr_mcp.tool()`
and keeps no business logic of its own: it resolves the caller, checks the
policy, calls a service in `app/services/`, and returns the result.

    @smarthr_mcp.tool()      protocol surface + schema the model sees
      -> authorise()         role re-read from users
      -> resolve_employee()  identity from the bound principal
      -> app/services/*      the actual SmartHR behaviour
      -> PostgreSQL

To add one: write the service function first, then a module here, then a
`ToolPolicy` in `app/mcp/permissions.py`, then import it from
`register_tools()` in `app/mcp/server.py`.
"""
