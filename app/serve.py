"""The backend's production run profile (Phase 10).

    venv\\Scripts\\python.exe -m app.serve                 # production
    uvicorn app.main:app --reload                          # development (unchanged)

Runs uvicorn with `reload=False` - always; there is no flag to turn it on -
at INFO, on `SMARTHR_BACKEND_HOST` (default 127.0.0.1) and
`SMARTHR_BACKEND_PORT` (default 8000). The default host is loopback on
purpose: TLS is expected to end at a reverse proxy in front of it, which is
also what makes an `https://` SMARTHR_INTERVIEW_BACKEND_URL possible for the
worker.

Before binding it requires `SMARTHR_ENV=production` and validates everything
the application would otherwise refuse at import - signing key, database URL,
CORS allow-list - so a bad configuration fails here, with the variable named
(never its value).
"""

from app import settings
from app.ai.interview.config import interview_setting

HOST_VAR = "SMARTHR_BACKEND_HOST"
PORT_VAR = "SMARTHR_BACKEND_PORT"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def uvicorn_options() -> dict:
    """The uvicorn.run() arguments of the production profile."""
    raw_port = interview_setting(PORT_VAR)
    try:
        port = int(raw_port) if raw_port else DEFAULT_PORT
    except ValueError:
        raise settings.ConfigurationError(f"{PORT_VAR} must be a port number.") from None
    if not 1 <= port <= 65535:
        raise settings.ConfigurationError(f"{PORT_VAR} must be between 1 and 65535.")
    return {
        "app": "app.main:app",
        "host": interview_setting(HOST_VAR) or DEFAULT_HOST,
        "port": port,
        "reload": False,
        "log_level": "info",
    }


def validate_production() -> dict:
    if settings.environment() != settings.PRODUCTION:
        raise settings.ConfigurationError(
            f"the production backend profile needs {settings.ENV_VAR}=production.")
    settings.secret_key()
    settings.database_url()
    settings.cors_origins()
    return uvicorn_options()


def main() -> None:
    options = validate_production()
    import uvicorn

    uvicorn.run(**options)


if __name__ == "__main__":
    main()
