"""The AI Interview worker's production profile (Phase 10).

    venv\\Scripts\\python.exe -m app.ai.interview.production     # production
    venv\\Scripts\\python.exe -m app.ai.interview.worker dev     # development (unchanged)

The launcher validates the configuration and then runs the worker exactly as
`worker start --log-level info` - LiveKit's normal mode: no file watching or
reloading (that is `dev`), no console (that is `console`), INFO logging. The
transcript PII filter (`logging_policy`) is applied by the worker module
itself, whichever way it is started.

It refuses to start unless:

* `SMARTHR_ENV=production` - the profile and the environment must agree;
* `SMARTHR_INTERVIEW_BACKEND_URL` is set explicitly (no silent
  http://127.0.0.1:8000 default), is a plain http(s) base URL, and is
  `https://` - except for a loopback host (localhost / 127.0.0.1 / ::1),
  where the traffic never leaves the machine;
* the three LiveKit variables are present (names are reported, never values).

`worker.py` also calls `guard_cli()` when run directly: with
`SMARTHR_ENV=production` it refuses `dev`, `console` and the other
development commands, a DEBUG/TRACE log level (flag or `LIVEKIT_LOG_LEVEL`),
and credentials on the command line (`--api-key` / `--api-secret` would be
visible in the process list). In development nothing changes.

This module reads configuration only - never the database.
"""

import os
import sys
from urllib.parse import urlsplit

from app import settings
from app.ai.interview.config import interview_setting, voice_settings

BACKEND_URL_VAR = "SMARTHR_INTERVIEW_BACKEND_URL"

#: What the production launcher runs. Asserted by the tests.
PRODUCTION_ARGS = ("start", "--log-level", "info")

#: LiveKit CLI commands for development only (`dev` watches files and reloads).
DEVELOPMENT_COMMANDS = frozenset({"dev", "console", "connect", "download-files"})
UNSAFE_LOG_LEVELS = frozenset({"debug", "trace"})
SECRET_FLAGS = ("--api-key", "--api-secret")


class WorkerConfigurationError(RuntimeError):
    """The worker must not start with this configuration. Names, never values."""


def backend_url_problem(url: str | None, production: bool) -> str | None:
    """Why this worker -> backend URL is unacceptable, or None."""
    if not url:
        return f"{BACKEND_URL_VAR} must be set explicitly in production." if production else None
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        return f"{BACKEND_URL_VAR} is not a valid URL."
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment \
            or "@" in parts.netloc:
        return f"{BACKEND_URL_VAR} must be an http(s) base URL, e.g. https://api.example.com."
    if production and parts.scheme != "https" and not settings.is_loopback(parts.hostname):
        return f"{BACKEND_URL_VAR} must use https in production (http is allowed only for localhost)."
    return None


def cli_problem(args: list[str], production: bool, env_log_level: str | None = None) -> str | None:
    """Why these worker command-line arguments are unacceptable, or None."""
    if not production:
        return None
    command = next((a for a in args if not a.startswith("-")), None)
    if command in DEVELOPMENT_COMMANDS:
        return f"'{command}' is a development command; production runs 'start' (python -m app.ai.interview.production)."
    level = (env_log_level or "").strip().lower()
    for i, arg in enumerate(args):
        if arg == "--log-level" and i + 1 < len(args):
            level = args[i + 1].strip().lower()
        elif arg.startswith("--log-level="):
            level = arg.split("=", 1)[1].strip().lower()
    if level in UNSAFE_LOG_LEVELS:
        return f"log level '{level}' is not allowed in production (INFO or above)."
    if any(a == flag or a.startswith(flag + "=") for a in args for flag in SECRET_FLAGS):
        return "LiveKit credentials must come from the environment / .env.local, not the command line."
    return None


def validate_production() -> str:
    """Check the whole production configuration; returns the backend URL."""
    if settings.environment() != settings.PRODUCTION:
        raise WorkerConfigurationError(
            f"the production worker profile needs {settings.ENV_VAR}=production.")
    url = interview_setting(BACKEND_URL_VAR)
    problem = backend_url_problem(url, production=True)
    if problem:
        raise WorkerConfigurationError(problem)
    missing = voice_settings().missing
    if missing:
        raise WorkerConfigurationError("LiveKit is not configured. Missing: " + ", ".join(missing) + ".")
    from app.ai.interview.debug_capture import CAPTURE_VAR, capture_requested
    if capture_requested():
        # Debug capture writes applicant audio and transcripts to disk.
        raise WorkerConfigurationError(f"{CAPTURE_VAR} must not be enabled in production.")
    return url.rstrip("/")


def guard_cli(args: list[str]) -> None:
    """Called by `worker.py` before LiveKit's CLI parses `args`."""
    if settings.environment() != settings.PRODUCTION:
        return
    problem = cli_problem(args, production=True, env_log_level=os.environ.get("LIVEKIT_LOG_LEVEL"))
    if problem:
        raise WorkerConfigurationError(problem)
    validate_production()


def main() -> None:
    validate_production()
    from livekit import agents

    from app.ai.interview.worker import server

    sys.argv = [sys.argv[0], *PRODUCTION_ARGS]
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
