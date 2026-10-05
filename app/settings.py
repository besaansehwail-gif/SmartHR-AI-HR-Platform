"""Core configuration: the JWT signing key and the database URL (Phase 10).

Neither is in the source any more. Both are read the way the AI Interview's
LiveKit credentials are - real environment first, then `.env.local`, then
`.env`, an empty value counting as absent (`interview_setting`, the project's
one reader of `.env.local`):

    SMARTHR_SECRET_KEY     signs and verifies every login token (HS256)
    SMARTHR_DATABASE_URL   the SQLAlchemy URL, credentials included
    SMARTHR_ENV            `development` (default) or `production`
    SMARTHR_CORS_ORIGINS   browser origins allowed to call the API (Phase 10)

**Startup refuses rather than guesses.** A missing value is an error in every
environment - there is no fallback key and no fallback database. In
`production` the signing key must also be at least `MIN_SECRET_LENGTH`
characters and must not be the development key that used to be hard-coded
(it is public: it was in the source), and `SMARTHR_ENV` must be spelled
correctly - a typo must not quietly mean "development". Errors name the
variable, never its value.
"""

import hashlib
from urllib.parse import urlsplit

from app.ai.interview.config import interview_setting

ENV_VAR = "SMARTHR_ENV"
SECRET_KEY_VAR = "SMARTHR_SECRET_KEY"
DATABASE_URL_VAR = "SMARTHR_DATABASE_URL"

DEVELOPMENT = "development"
PRODUCTION = "production"
ENVIRONMENTS = (DEVELOPMENT, PRODUCTION)

MIN_SECRET_LENGTH = 32

#: SHA-256 of signing keys that are public and so must never sign a production
#: token - the development key that was hard-coded in app/routers/auth.py.
#: Stored as a digest so the key itself is not repeated in the source.
KNOWN_INSECURE_SECRET_SHA256 = frozenset({
    "7a997c9814ca9373ccfeb043bbad60934b89f2ecf98c926b7fb01a5c00f944ff",
})


class ConfigurationError(RuntimeError):
    """The application cannot start with this configuration. The message names
    the variable and the rule - never the value."""


def environment() -> str:
    value = (interview_setting(ENV_VAR) or DEVELOPMENT).strip().lower()
    if value not in ENVIRONMENTS:
        raise ConfigurationError(f"{ENV_VAR} must be one of {', '.join(ENVIRONMENTS)}.")
    return value


def is_known_insecure(secret: str) -> bool:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest() in KNOWN_INSECURE_SECRET_SHA256


def secret_key() -> str:
    """The JWT signing key - validated, or ConfigurationError."""
    secret = interview_setting(SECRET_KEY_VAR)
    if not secret:
        raise ConfigurationError(
            f"{SECRET_KEY_VAR} is not set. Put a long random value in .env.local "
            f"(or the environment); SmartHR has no default signing key.")
    if environment() == PRODUCTION:
        if is_known_insecure(secret):
            raise ConfigurationError(
                f"{SECRET_KEY_VAR} is the public development key; production refuses to start with it.")
        if len(secret) < MIN_SECRET_LENGTH:
            raise ConfigurationError(
                f"{SECRET_KEY_VAR} must be at least {MIN_SECRET_LENGTH} characters in production.")
    return secret


CORS_ORIGINS_VAR = "SMARTHR_CORS_ORIGINS"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_loopback(host: str | None) -> bool:
    """A host whose traffic never leaves this machine."""
    return (host or "").strip("[]").lower() in LOOPBACK_HOSTS


def _is_origin(value: str) -> bool:
    """scheme://host[:port] and nothing else - what a browser sends as Origin."""
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        return False
    return (parts.scheme in ("http", "https") and bool(parts.hostname)
            and parts.path == "" and not parts.query and not parts.fragment and "@" not in parts.netloc)


def cors_origins() -> list[str]:
    """The browser origins allowed to call the API (Phase 10).

    `SMARTHR_CORS_ORIGINS` is a comma-separated list of origins
    (`https://hr.example.com,https://careers.example.com`).

    * development, unset -> `["*"]`: exactly the behaviour before this setting;
    * production, unset or `*` -> refused: the API must name its frontend(s);
    * production, an `http://` origin that is not this machine -> refused.

    Tokens travel as Bearer headers, never cookies (`allow_credentials` stays
    False), so the list limits which sites' scripts may read responses.
    """
    raw = interview_setting(CORS_ORIGINS_VAR)
    production = environment() == PRODUCTION
    origins = [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]
    if not origins:
        if production:
            raise ConfigurationError(f"{CORS_ORIGINS_VAR} must list the frontend origin(s) in production.")
        return ["*"]
    if "*" in origins:
        if production:
            raise ConfigurationError(f"{CORS_ORIGINS_VAR} may not be '*' in production.")
        return ["*"]
    bad = [o for o in origins if not _is_origin(o)]
    if bad:
        raise ConfigurationError(
            f"{CORS_ORIGINS_VAR}: not an origin (scheme://host[:port]): {', '.join(bad)}")
    if production:
        plain = [o for o in origins if urlsplit(o).scheme != "https" and not is_loopback(urlsplit(o).hostname)]
        if plain:
            raise ConfigurationError(f"{CORS_ORIGINS_VAR}: production origins must be https: {', '.join(plain)}")
    return origins


def database_url() -> str:
    """The SQLAlchemy database URL - or ConfigurationError."""
    url = interview_setting(DATABASE_URL_VAR)
    if not url:
        raise ConfigurationError(
            f"{DATABASE_URL_VAR} is not set. Put the database URL in .env.local "
            f"(or the environment); SmartHR has no default database.")
    return url
