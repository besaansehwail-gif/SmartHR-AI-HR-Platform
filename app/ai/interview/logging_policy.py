"""What the AI Interview worker may log (Phase 10).

LiveKit's own library logs what the applicant SAID: at DEBUG,
`livekit.agents` writes every final and preflight transcript as a
`lk.pii.user_transcript` field ("received user transcript"). SmartHR's code
never logs speech, but a worker started with `--log-level debug` would.

Two layers, applied when the worker module is imported - before LiveKit's
CLI configures logging, and again in each job process, which re-imports
this module and inherits the parent's logger levels:

* `livekit.agents` is set to INFO. LiveKit's CLI only sets that logger's
  level when it is still unset (NOTSET), so `--log-level debug` no longer
  lowers it, while the rest of the worker still logs at the requested level;
* `DropPii` on that logger drops ANY record carrying a `lk.pii.*` field, at
  any level - so even a later `setLevel(DEBUG)` cannot bring transcripts back.
"""

import logging

LIVEKIT_LOGGER = "livekit.agents"
LIVEKIT_LEVEL = logging.INFO
PII_PREFIX = "lk.pii."


class DropPii(logging.Filter):
    """Refuse a log record that carries LiveKit's personal-data fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(key.startswith(PII_PREFIX) for key in vars(record))


def configure_worker_logging() -> None:
    """Idempotent: safe to call in every process that imports the worker."""
    logger = logging.getLogger(LIVEKIT_LOGGER)
    logger.setLevel(LIVEKIT_LEVEL)
    if not any(isinstance(f, DropPii) for f in logger.filters):
        logger.addFilter(DropPii())
