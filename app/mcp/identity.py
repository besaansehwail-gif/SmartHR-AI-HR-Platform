"""Who the current MCP call is being made for.

The identity of the caller is the one thing that must never be an argument to
an MCP tool. If `get_my_leave(employee_id=...)` existed, then the model - or
anything that could influence the model - could ask for a different employee,
and the only thing standing between a curious prompt and someone else's HR
record would be the model's good behaviour.

So identity travels **out of band**, in a `contextvars.ContextVar` that the
FastAPI layer binds from the verified JWT before the MCP session is opened.
Tools read it; nobody can send it. A context variable is the right mechanism
because it is per-task rather than global: two concurrent requests each see
their own principal, and a task that was never bound sees nothing at all.
"""

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, as established by FastAPI from the JWT."""

    user_id: int
    email: str
    #: Recorded for logging only. Authorisation always re-reads the role from
    #: the database rather than trusting this copy.
    role_id: int | None = None


_CURRENT: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "smarthr_mcp_principal", default=None
)


class NoPrincipalBound(RuntimeError):
    """A tool that needs an identity ran without one.

    This is a programming error, not a user error: it means a tool was invoked
    outside `bind_principal()`. Failing loudly is deliberate - the alternative
    would be a tool quietly running with no idea whose data it is returning.
    """


@contextmanager
def bind_principal(principal: Principal):
    """Bind the caller for the duration of an MCP session."""
    token = _CURRENT.set(principal)
    try:
        yield principal
    finally:
        _CURRENT.reset(token)


def current_principal() -> Principal:
    """The bound caller, or raise. Tools use this instead of an argument."""
    principal = _CURRENT.get()

    if principal is None:
        raise NoPrincipalBound(
            "No authenticated principal is bound to this MCP call. SmartHR "
            "tools must be invoked inside bind_principal()."
        )

    return principal


def current_principal_or_none() -> Principal | None:
    """For logging and diagnostics, where absence is not an error."""
    return _CURRENT.get()
