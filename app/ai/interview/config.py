"""AI Interview configuration: LiveKit credentials and the voice models.

**Where the values come from, in order** - the first non-empty one wins:

1. a real exported environment variable;
2. `.env.local` at the repository root;
3. `.env` at the repository root (through `app.ai.config.setting`).

`.env.local` is where `lk app env -w` writes a LiveKit Cloud project's
credentials, which is why this feature reads it. The rest of SmartHR does not,
and that is deliberate: `app/ai/config.py` is shared by the assistant, both
agents, moderation and the Celebration workflow, and teaching it a second file
would change which LLM key all of them use. This module adds the extra layer
for the AI Interview alone.

Like `app/ai/config.py`, nothing is written into `os.environ` here and an
empty value counts as absent - so a blank `LIVEKIT_API_SECRET=` behaves as
"not configured" rather than as an empty secret that fails at connect time.
The one exception is `export_livekit_environment()`, which the worker process
calls because LiveKit Inference reads its credentials from `os.environ`.

Nothing in this module ever returns or logs a secret: `public_status()` says
which variables are *present*, never what they contain.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.ai.config import setting

try:  # python-dotenv is already a dependency of the environment.
    from dotenv import dotenv_values
except Exception:  # pragma: no cover - only if the dependency is missing
    dotenv_values = None

#: Repository root: app/ai/interview/config.py -> interview -> ai -> app -> SmartHR
LOCAL_ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"

#: The three values LiveKit needs. Named once, so the status report, the
#: worker's environment export and the tests cannot disagree about them.
LIVEKIT_VARIABLES = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")

#: The worker registers under this name and the token dispatches to it. With
#: an explicit name, LiveKit sends the agent only to rooms whose token asks for
#: it - never automatically to every room in the project.
AGENT_NAME = "smarthr-interviewer"

#: The interviewer's language model. Fixed rather than configurable: the
#: trainer specified GPT-4o, and a setting would let it be replaced silently.
#: It is reached through LiveKit Inference, so no OpenAI key is involved.
LLM_MODEL = "openai/gpt-4o"

#: Speech-to-text and text-to-speech, also through LiveKit Inference. These
#: only convert audio; they may be changed with the variables below without
#: touching the interviewer's model.
DEFAULT_STT_MODEL = "deepgram/nova-3"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
DEFAULT_LANGUAGE = "en"

#: How long a minted room token can be used to join. Short, because it is a
#: bearer credential for one room: 10 minutes covers a slow page load and a
#: microphone permission prompt, and a leaked token is useless soon after.
DEFAULT_TOKEN_TTL_MINUTES = 10

_local_cache: tuple[tuple[float, int] | None, dict[str, str]] = (None, {})


def _local_env_values(path: Path = LOCAL_ENV_FILE) -> dict[str, str]:
    """The current contents of `.env.local`, re-read whenever the file changes."""
    global _local_cache

    if dotenv_values is None:
        return {}

    try:
        if not path.is_file():
            return {}
        stat = path.stat()
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:  # pragma: no cover - an unreadable file must not 500
        return {}

    cached_stamp, cached_values = _local_cache

    if path == LOCAL_ENV_FILE and cached_stamp == stamp:
        return cached_values

    try:
        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
    except Exception:  # pragma: no cover
        values = {}

    if path == LOCAL_ENV_FILE:
        _local_cache = (stamp, values)

    return values


def interview_setting(name: str, local_file: Path | None = LOCAL_ENV_FILE) -> str | None:
    """One value: real environment, then `.env.local`, then `.env`.

    `local_file=None` skips the `.env.local` layer, which is how the tests
    prove the precedence without depending on what this machine's file holds.
    """
    raw = os.getenv(name)

    if raw is not None and raw.strip():
        return raw.strip()

    if local_file is not None:
        local = (_local_env_values(local_file).get(name) or "").strip()
        if local:
            return local

    # `setting` repeats the environment check and then reads `.env`, with the
    # same empty-is-absent rule - reused rather than re-derived.
    return setting(name)


@dataclass(frozen=True)
class VoiceSettings:
    livekit_url: str | None
    api_key: str | None
    api_secret: str | None
    stt_model: str
    tts_model: str
    llm_model: str
    language: str
    token_ttl_minutes: int
    agent_name: str = AGENT_NAME

    @property
    def missing(self) -> list[str]:
        """Names of the LiveKit variables that are absent. Names only."""
        values = {
            "LIVEKIT_URL": self.livekit_url,
            "LIVEKIT_API_KEY": self.api_key,
            "LIVEKIT_API_SECRET": self.api_secret,
        }
        return [name for name in LIVEKIT_VARIABLES if not values[name]]

    @property
    def configured(self) -> bool:
        return not self.missing

    def public_status(self) -> dict:
        """What the UI and `/ai-interview/status` may see. No secret, ever.

        The URL is reported only as present/absent too: it names the LiveKit
        Cloud project, and the browser receives it only inside a session it is
        entitled to join.
        """
        return {
            "configured": self.configured,
            "missing": self.missing,
            "agent_name": self.agent_name,
            "models": {
                "stt": self.stt_model,
                "llm": self.llm_model,
                "tts": self.tts_model,
            },
            "language": self.language,
            "transport": "livekit",
            "inference": "livekit-inference",
            "camera": False,
        }


def _int(name: str, default: int, local_file: Path | None) -> int:
    raw = interview_setting(name, local_file)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        return default
    return value if value > 0 else default


#: The STT language: an ISO code ("en", "ar", "en-US") or "multi" (the
#: provider detects the language per utterance). Anything else is ignored in
#: favour of DEFAULT_LANGUAGE rather than sent to the provider. Note that the
#: default is English: Arabic speech transcribed as "en" comes back as
#: Latin-letter nonsense, so an Arabic-speaking deployment must set this.
_LANGUAGE = re.compile(r"(multi|[a-z]{2,3}(-[A-Za-z0-9]{2,8})?)")


def stt_language(raw: str | None) -> str:
    value = (raw or "").strip()
    return value if _LANGUAGE.fullmatch(value) else DEFAULT_LANGUAGE


def camera_vision_enabled(local_file: Path | None = LOCAL_ENV_FILE) -> bool:
    """Opt in to forwarding one camera frame to GPT-4o; disabled by default."""
    value = interview_setting("SMARTHR_INTERVIEW_CAMERA_VISION", local_file)
    return value is not None and value.casefold() in {"1", "true", "yes", "on"}


def voice_settings(local_file: Path | None = LOCAL_ENV_FILE) -> VoiceSettings:
    """Read the current configuration.

    Read per call, like `llm_settings()`, so credentials added to `.env.local`
    while the backend is running take effect on the next request.
    """
    return VoiceSettings(
        livekit_url=interview_setting("LIVEKIT_URL", local_file),
        api_key=interview_setting("LIVEKIT_API_KEY", local_file),
        api_secret=interview_setting("LIVEKIT_API_SECRET", local_file),
        stt_model=interview_setting("SMARTHR_INTERVIEW_STT_MODEL", local_file) or DEFAULT_STT_MODEL,
        tts_model=interview_setting("SMARTHR_INTERVIEW_TTS_MODEL", local_file) or DEFAULT_TTS_MODEL,
        llm_model=LLM_MODEL,
        language=stt_language(interview_setting("SMARTHR_INTERVIEW_LANGUAGE", local_file)),
        token_ttl_minutes=_int("SMARTHR_INTERVIEW_TOKEN_TTL_MINUTES", DEFAULT_TOKEN_TTL_MINUTES, local_file),
    )


def export_livekit_environment(settings: VoiceSettings | None = None) -> list[str]:
    """Put the three LiveKit values into `os.environ` for the worker process.

    LiveKit's own code - the worker's connection and LiveKit Inference - reads
    `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` from the process
    environment. Only those three are exported, and a variable that is already
    set is left alone. Returns the names exported, never the values.
    """
    settings = settings or voice_settings()
    values = {
        "LIVEKIT_URL": settings.livekit_url,
        "LIVEKIT_API_KEY": settings.api_key,
        "LIVEKIT_API_SECRET": settings.api_secret,
    }
    exported = []

    for name, value in values.items():
        if value and not (os.environ.get(name) or "").strip():
            os.environ[name] = value
            exported.append(name)

    return exported


#: Where the worker reaches the SmartHR backend for the interview plan. The
#: worker never opens the database; it asks the backend, like any client.
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


def backend_url() -> str:
    return (interview_setting("SMARTHR_INTERVIEW_BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")


#: Phase 9: when an AI Interview may start, relative to `interviews.scheduled_at`
#: (a local wall-clock time, as HR entered it). Minutes; 0 is allowed.
DEFAULT_EARLY_MINUTES = 15
DEFAULT_LATE_MINUTES = 30


@dataclass(frozen=True)
class InterviewWindow:
    early_minutes: int
    late_minutes: int


def _minutes(name: str, default: int, local_file: Path | None) -> int:
    raw = interview_setting(name, local_file)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        return default
    return value if value >= 0 else default


def interview_window(local_file: Path | None = LOCAL_ENV_FILE) -> InterviewWindow:
    """The start window around an interview's scheduled time. Read per call,
    like `voice_settings()`: `SMARTHR_INTERVIEW_EARLY_MINUTES` (default 15)
    before it, until `SMARTHR_INTERVIEW_LATE_MINUTES` (default 30) after it."""
    return InterviewWindow(
        early_minutes=_minutes("SMARTHR_INTERVIEW_EARLY_MINUTES", DEFAULT_EARLY_MINUTES, local_file),
        late_minutes=_minutes("SMARTHR_INTERVIEW_LATE_MINUTES", DEFAULT_LATE_MINUTES, local_file),
    )


def window_exempt_ids(local_file: Path | None = LOCAL_ENV_FILE) -> frozenset[int]:
    """DEVELOPMENT ONLY: interview ids that may start at any time (permanent
    test interviews), from `SMARTHR_INTERVIEW_WINDOW_EXEMPT_IDS` (comma-separated).
    Only the start window is skipped - status, HR approval, the active-session
    and attempt limits still apply. Always empty in production."""
    from app.settings import PRODUCTION, environment

    if environment() == PRODUCTION:
        return frozenset()
    raw = interview_setting("SMARTHR_INTERVIEW_WINDOW_EXEMPT_IDS", local_file) or ""
    return frozenset(int(part) for part in (p.strip() for p in raw.split(",")) if part.isdigit())
