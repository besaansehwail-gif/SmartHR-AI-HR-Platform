"""Entry point for ``python -m app.mcp``.

Running a module that defines shared state with ``python -m`` imports it twice:
once as ``__main__`` and again under its real name when another module imports
it. That produced two `MCPServer` instances - the tools registered on one, and
the stdio loop served the other, which advertised no tools at all.

Keeping the entry point in its own module fixes that at the root: the server
object is only ever created by ``app.mcp.server``, imported here as an ordinary
module.
"""

from app.mcp.server import main

if __name__ == "__main__":
    main()
