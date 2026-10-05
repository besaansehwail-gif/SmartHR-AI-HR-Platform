"""LLM configuration, read from the environment.

Nothing here is hardcoded and no key is ever committed: the provider name, the
API key, the model and the endpoint all come from environment variables, which
may also be supplied through a `.env` file at the repository root (see
`.env.example`). `.env` itself is deliberately not part of the project.

If no key is present the assistant still runs - `provider.py` returns an
unconfigured provider, and the chat endpoint reports that plainly instead of
inventing an answer.
"""

import os
from dataclasses import dataclass
from pathlib import Path

#: Repository root: app/ai/config.py -> app/ai -> app -> SmartHR
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

try:  # python-dotenv is already a dependency of the environment.
    from dotenv import dotenv_values
except Exception:  # pragma: no cover - only if the dependency is missing
    dotenv_values = None

#: Cache of the parsed `.env`, keyed by the file's (mtime, size) so an edit is
#: noticed without re-reading the file on every single call.
_env_cache: tuple[tuple[float, int] | None, dict[str, str]] = (None, {})


def _env_file_values() -> dict[str, str]:
    """The current contents of `.env`, re-read whenever the file changes.

    Note what this deliberately does *not* do: it never writes into
    `os.environ`. `load_dotenv` would, and that breaks this feature in a way
    that is genuinely hard to spot - the shipped `.env` contains
    `SMARTHR_LLM_API_KEY=` (empty), so the first load would put an empty
    string into the environment, and because `load_dotenv` does not override
    variables that already exist, filling the key in afterwards would be
    ignored for the life of the process. Keeping the file's values separate
    gives the precedence everyone expects - a real exported variable wins, the
    file is the fallback - and makes an edit take effect on the next request.
    """
    global _env_cache

    if dotenv_values is None:
        return {}

    try:
        if not ENV_FILE.is_file():
            return {}
        stat = ENV_FILE.stat()
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:  # pragma: no cover - an unreadable .env must not 500
        return {}

    cached_stamp, cached_values = _env_cache

    if cached_stamp == stamp:
        return cached_values

    try:
        values = {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None}
    except Exception:  # pragma: no cover
        values = {}

    _env_cache = (stamp, values)
    return values


def _setting(name: str) -> str | None:
    """One configuration value: real environment first, then `.env`.

    An empty value counts as absent, so the commented-out placeholders in
    `.env.example` and a blank `SMARTHR_LLM_API_KEY=` behave as "not set"
    rather than as an empty key that silently fails authentication.
    """
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        raw = _env_file_values().get(name)

    if raw is None:
        return None

    return raw.strip() or None


SUPPORTED_PROVIDERS = ("anthropic", "openai")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
}

DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    api_key: str | None
    model: str
    base_url: str
    max_tokens: int
    timeout_seconds: int

    @property
    def configured(self) -> bool:
        """True only when a supported provider AND a key are both present."""
        return bool(self.api_key) and self.provider in SUPPORTED_PROVIDERS


def _int_setting(name: str, default: int) -> int:
    raw = _setting(name)

    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError:
        return default


def _bool_setting(name: str, default: bool) -> bool:
    """A yes/no setting, read with the same precedence as every other one.

    Anything that is not one of the four affirmative spellings is false. That
    matters for a flag that relaxes a rule: `SMARTHR_AI_INTERVIEW_TEST_MODE=`,
    `=no`, `=maybe` and a typo all leave the rule in force, and only a
    deliberate `true`/`1`/`yes`/`on` lifts it.
    """
    raw = _setting(name)

    if raw is None:
        return default

    return raw.strip().lower() in ("1", "true", "yes", "on")


def llm_settings() -> LlmSettings:
    """Read the current configuration.

    Deliberately read on each call rather than cached at import time, so the
    server picks up a newly added key on the next request instead of needing a
    restart to notice one. That includes a `.env` file created or edited while
    the server is already running - `_env_file_values()` re-reads it whenever
    the file changes.
    """
    provider = (_setting("SMARTHR_LLM_PROVIDER") or "anthropic").lower()

    # Accept the provider's own conventional variable name as well, so a
    # machine that already exports ANTHROPIC_API_KEY needs no extra setup.
    api_key = (
        _setting("SMARTHR_LLM_API_KEY")
        or (_setting("ANTHROPIC_API_KEY") if provider == "anthropic" else None)
        or (_setting("OPENAI_API_KEY") if provider == "openai" else None)
    )

    return LlmSettings(
        provider=provider,
        api_key=api_key,
        model=_setting("SMARTHR_LLM_MODEL") or DEFAULT_MODELS.get(provider, ""),
        base_url=_setting("SMARTHR_LLM_BASE_URL") or DEFAULT_BASE_URLS.get(provider, ""),
        max_tokens=_int_setting("SMARTHR_LLM_MAX_TOKENS", 1024),
        timeout_seconds=_int_setting("SMARTHR_LLM_TIMEOUT", 30),
    )


#: Public aliases, for configuration that is not about the language model.
#:
#: `app/services/email_service.py` needs exactly the precedence this module
#: already implements - a real exported variable first, then `.env`, with an
#: empty value treated as absent, and no `load_dotenv` writing the file into
#: `os.environ`. Re-deriving that elsewhere is how the two would drift, and
#: the `.env`-shadowing bug documented above would come back in the copy.
setting = _setting
int_setting = _int_setting
bool_setting = _bool_setting
