"""What each HR-intelligence role may be given (Phase 12).

Every input is plain structured data (dicts, lists, strings, numbers) built
by the existing services - never a database session, a model row, a request
or a header. `assert_safe_input` is run on it before a role sees it: a key
that names a credential or a piece of contact PII, or a value that looks like
a bearer token / JWT, refuses the whole input rather than passing it on.
"""

import re
from dataclasses import asdict, is_dataclass
from typing import Any

#: Key fragments no role input may contain. Matched case-insensitively
#: against every key at every depth.
FORBIDDEN_KEY_PARTS = (
    "password", "token", "jwt", "authorization", "secret", "api_key", "apikey", "credential",
    "email", "phone", "full_name", "first_name", "last_name", "candidate_name",
)

#: Token-shaped only, so an applicant saying the word "bearer" is not refused.
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


class AgentInputError(Exception):
    """An input that must not reach a role. Carries the role and the key
    PATH (never the value)."""

    def __init__(self, role: str, where: str):
        super().__init__(f"unsafe input for the {role} role at {where}")
        self.role = role
        self.where = where


def _plain(value: Any) -> Any:
    return asdict(value) if is_dataclass(value) and not isinstance(value, type) else value


def unsafe_paths(value: Any, path: str = "$") -> list[str]:
    """Where `value` carries a forbidden key or a token-like string."""
    value = _plain(value)
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in FORBIDDEN_KEY_PARTS):
                found.append(f"{path}.{key}")
            found.extend(unsafe_paths(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple, set)):
        for i, item in enumerate(value):
            found.extend(unsafe_paths(item, f"{path}[{i}]"))
    elif isinstance(value, str):
        if _BEARER.search(value) or _JWT.search(value):
            found.append(path)
    elif value is not None and not isinstance(value, (int, float, bool)):
        # Anything that is not plain data (a Session, a model row, a request).
        found.append(f"{path}<{type(value).__name__}>")
    return found


def assert_safe_input(value: Any, role: str) -> None:
    paths = unsafe_paths(value)
    if paths:
        raise AgentInputError(role, paths[0])
