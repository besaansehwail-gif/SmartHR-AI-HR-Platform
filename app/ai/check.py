"""Check the SmartHR LLM configuration, and prove a key actually works.

    venv\\Scripts\\Activate.ps1
    python -m app.ai.check

It answers the two questions that "No language model is configured" leaves
open: *is a key being seen at all*, and *does the provider accept it*. With a
key present it makes one real, deliberately tiny request to the provider and
reports exactly what came back - so a wrong key, a wrong provider name or a
blocked network are told apart in one command instead of by re-uploading CVs.

Nothing here is part of a request path; it is a diagnostic. It never prints a
key, only whether one was found, how long it is and which variable supplied it.
"""

import sys

from app.ai.config import (
    DEFAULT_MODELS,
    ENV_FILE,
    SUPPORTED_PROVIDERS,
    _env_file_values,
    _setting,
    llm_settings,
)
from app.ai.provider import LlmError, LlmNotConfigured, get_provider

TICK, CROSS, DOT = "[ok]", "[!!]", "[--]"


def _source_of(name: str) -> str:
    """Where a value came from - the environment wins over the file."""
    import os

    if (os.getenv(name) or "").strip():
        return "environment variable"
    if (_env_file_values().get(name) or "").strip():
        return f"{ENV_FILE.name} file"
    return "not set"


def _describe_key(key: str | None) -> str:
    """Enough to identify a key without disclosing it."""
    if not key:
        return "MISSING"

    shape = "unrecognised prefix"
    if key.startswith("sk-ant-"):
        shape = "Anthropic-style (sk-ant-...)"
    elif key.startswith("sk-"):
        shape = "OpenAI-style (sk-...)"

    return f"present, {len(key)} characters, {shape}"


def main() -> int:
    settings = llm_settings()

    print("SmartHR LLM configuration")
    print("=" * 58)
    print(f"  .env file            : {ENV_FILE}")
    print(f"                         {'found' if ENV_FILE.is_file() else 'NOT FOUND'}")
    print(f"  SMARTHR_LLM_PROVIDER : {settings.provider}   (from {_source_of('SMARTHR_LLM_PROVIDER')})")
    print(f"  SMARTHR_LLM_API_KEY  : {_describe_key(settings.api_key)}")

    key_source = _source_of("SMARTHR_LLM_API_KEY")
    if key_source == "not set":
        for alt in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if _setting(alt):
                key_source = f"{alt} ({_source_of(alt)})"
                break
    print(f"                         source: {key_source}")
    print(f"  SMARTHR_LLM_MODEL    : {settings.model}   (from {_source_of('SMARTHR_LLM_MODEL')})")
    print(f"  endpoint             : {settings.base_url}")
    print(f"  max_tokens / timeout : {settings.max_tokens} / {settings.timeout_seconds}s")
    print("=" * 58)

    if settings.provider not in SUPPORTED_PROVIDERS:
        print(f"{CROSS} '{settings.provider}' is not a supported provider.")
        print(f"     Supported values: {', '.join(SUPPORTED_PROVIDERS)}")
        return 2

    if not settings.configured:
        print(f"{CROSS} No API key found, so SmartHR reports "
              '"No language model is configured".')
        print()
        print("     This is why CV analysis returns no parsed fields. It is not a")
        print("     fault in the upload or extraction, which both still work.")
        print()
        print(f"     To fix: open {ENV_FILE}")
        print("     and put a key on the SMARTHR_LLM_API_KEY= line:")
        print()
        print(f"       SMARTHR_LLM_PROVIDER={settings.provider}")
        print("       SMARTHR_LLM_API_KEY=<your key>")
        print(f"       # optional, defaults to {DEFAULT_MODELS.get(settings.provider)}")
        print(f"       # SMARTHR_LLM_MODEL={DEFAULT_MODELS.get(settings.provider)}")
        print()
        print("     anthropic -> https://console.anthropic.com  (key starts sk-ant-)")
        print("     openai    -> https://platform.openai.com    (key starts sk-)")
        print()
        print("     The running server re-reads this file per request, so no")
        print("     restart is needed. Then run this command again.")
        return 1

    print(f"{TICK} A key was found. Making one real request to confirm the "
          "provider accepts it...")
    print()

    provider = get_provider(settings)

    try:
        reply = provider.complete(
            "Reply with the single word: ready.",
            [{"role": "user", "content": "Are you reachable?"}],
            None,
        )
    except LlmNotConfigured as exc:
        print(f"{CROSS} The provider reports it is not configured: {exc}")
        return 1
    except LlmError as exc:
        print(f"{CROSS} The provider rejected the request.")
        print(f"     {exc}")
        print()
        print("     Common causes:")
        print("       401 / invalid x-api-key -> the key is wrong, revoked, or")
        print("           belongs to the other provider (check SMARTHR_LLM_PROVIDER)")
        print("       404 / model not found   -> SMARTHR_LLM_MODEL is not a model")
        print("           this key can reach")
        print("       connection failed       -> network or proxy is blocking the")
        print(f"           endpoint {settings.base_url}")
        return 1
    except Exception as exc:  # pragma: no cover - unexpected shapes
        print(f"{CROSS} Unexpected failure talking to the provider: "
              f"{type(exc).__name__}: {exc}")
        return 1

    answer = (reply.text or "").strip()
    print(f"{TICK} The provider responded. Model replied: {answer[:60]!r}")
    print()
    print(f"     Provider  : {settings.provider}")
    print(f"     Model     : {settings.model}")
    print()
    print("     SmartHR AI is configured. Both features use this same key:")
    print("       * AI Assistant   POST /ai/chat")
    print("       * CV analysis    POST /cvs/upload")
    print()
    print("     Upload a CV from Recruitment -> Candidates -> Resume / CV to see")
    print("     the structured analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
