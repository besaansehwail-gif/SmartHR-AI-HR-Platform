"""The LLM provider abstraction.

One small interface - `LlmProvider.complete()` - with an Anthropic and an
OpenAI implementation behind it, plus an `UnconfiguredProvider` for the case
where no key has been supplied yet. Adding a provider means adding a class
here; nothing else in the assistant changes.

HTTP is done with `urllib` from the standard library on purpose: the venv has
no HTTP client installed, and a chat endpoint is not a good reason to add a
dependency for two POST requests.
"""

import http.client
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.config import LlmSettings, llm_settings


class LlmError(RuntimeError):
    """The provider was reachable but the call failed."""


class LlmNotConfigured(LlmError):
    """No provider/key is configured. Not an error the user caused."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    #: The provider's own id for this call. Both APIs require it to be echoed
    #: back on the result, which is what makes a multi-step agent loop possible
    #: (`app/ai/career_agent.py`). Defaulted, so the single-turn assistant that
    #: predates it is unaffected.
    id: str = ""


@dataclass
class LlmReply:
    """Either the model answered, or it asked for a tool. Possibly both."""
    text: str | None = None
    tool_call: ToolCall | None = None


class LlmProvider(Protocol):
    name: str
    model: str
    configured: bool

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmReply:
        ...

    def tool_exchange(
        self,
        reply: LlmReply,
        result_json: str,
    ) -> list[dict[str, Any]]:
        """The messages to append after running a tool the model asked for.

        An agent loop has to show the model what its tool call returned, and
        the two providers spell that differently: Anthropic wants a
        `tool_use` block answered by a `tool_result` block in a user turn,
        OpenAI wants an assistant message carrying `tool_calls` answered by a
        `role: "tool"` message. Both are "the assistant asked, here is the
        answer", so the shape belongs behind this interface rather than in the
        agent, which stays provider-agnostic.
        """
        ...


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise LlmError(f"The language model returned {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"Could not reach the language model: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LlmError("The language model did not respond in time.") from exc
    except json.JSONDecodeError as exc:
        raise LlmError("The language model returned a response that was not JSON.") from exc
    except http.client.HTTPException as exc:
        # A truncated or malformed response - IncompleteRead and friends.
        raise LlmError(f"The language model's response was incomplete: {exc}") from exc
    except OSError as exc:
        # The connection dropping *while the body is being read* raises a bare
        # ConnectionAbortedError/ConnectionResetError from inside the `with`,
        # which none of the clauses above cover. Without this it escapes as an
        # unclassified exception and the caller reports a generic failure
        # instead of "the model could not be reached". Must stay last:
        # HTTPError, URLError and TimeoutError are all OSError subclasses.
        raise LlmError(f"The connection to the language model failed: {exc}") from exc


class UnconfiguredProvider:
    """Stands in when no key is set.

    It does not fabricate an answer - it raises, and the assistant falls back
    to running the tool directly and returning the real result labelled as
    not-LLM-generated.
    """

    name = "unconfigured"
    model = ""
    configured = False

    def complete(self, system, messages, tools=None) -> LlmReply:
        raise LlmNotConfigured(
            "No language model is configured. Set SMARTHR_LLM_PROVIDER and "
            "SMARTHR_LLM_API_KEY to enable generated answers."
        )

    def tool_exchange(self, reply: LlmReply, result_json: str) -> list[dict[str, Any]]:
        return []


class AnthropicProvider:
    """Anthropic Messages API, including its native tool-use block."""

    name = "anthropic"
    configured = True

    def __init__(self, settings: LlmSettings):
        self._settings = settings
        self.model = settings.model

    def complete(self, system, messages, tools=None) -> LlmReply:
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "system": system,
            "messages": messages,
        }

        if tools:
            payload["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["parameters"],
                }
                for tool in tools
            ]

        data = _post_json(
            self._settings.base_url,
            payload,
            {
                "x-api-key": self._settings.api_key or "",
                "anthropic-version": "2023-06-01",
            },
            self._settings.timeout_seconds,
        )

        text_parts: list[str] = []
        tool_call: ToolCall | None = None

        for block in data.get("content", []) or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use" and tool_call is None:
                tool_call = ToolCall(
                    name=block.get("name", ""),
                    arguments=block.get("input") or {},
                    id=block.get("id", ""),
                )

        return LlmReply(text="\n".join(p for p in text_parts if p).strip() or None,
                        tool_call=tool_call)

    def tool_exchange(self, reply: LlmReply, result_json: str) -> list[dict[str, Any]]:
        """Anthropic: a tool_use block, answered by a tool_result block."""
        call = reply.tool_call

        if call is None:
            return []

        assistant_content: list[dict[str, Any]] = []

        if reply.text:
            assistant_content.append({"type": "text", "text": reply.text})

        assistant_content.append({
            "type": "tool_use",
            "id": call.id,
            "name": call.name,
            "input": call.arguments,
        })

        return [
            {"role": "assistant", "content": assistant_content},
            {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result_json,
                }],
            },
        ]


class OpenAIProvider:
    """OpenAI chat completions, using the function-calling tool format."""

    name = "openai"
    configured = True

    def __init__(self, settings: LlmSettings):
        self._settings = settings
        self.model = settings.model

    def complete(self, system, messages, tools=None) -> LlmReply:
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "messages": [{"role": "system", "content": system}] + messages,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                    },
                }
                for tool in tools
            ]

        data = _post_json(
            self._settings.base_url,
            payload,
            {"Authorization": f"Bearer {self._settings.api_key or ''}"},
            self._settings.timeout_seconds,
        )

        choices = data.get("choices") or []

        if not choices:
            raise LlmError("The language model returned no choices.")

        message = choices[0].get("message") or {}
        tool_call = None

        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}

            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}

            tool_call = ToolCall(
                name=function.get("name", ""),
                arguments=arguments,
                id=call.get("id", ""),
            )
            break

        content = message.get("content")

        return LlmReply(
            text=content.strip() if isinstance(content, str) and content.strip() else None,
            tool_call=tool_call,
        )

    def tool_exchange(self, reply: LlmReply, result_json: str) -> list[dict[str, Any]]:
        """OpenAI: an assistant message with tool_calls, then a tool message."""
        call = reply.tool_call

        if call is None:
            return []

        return [
            {
                "role": "assistant",
                "content": reply.text or None,
                "tool_calls": [{
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }],
            },
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": result_json,
            },
        ]


def get_provider(settings: LlmSettings | None = None) -> LlmProvider:
    """The provider named by the environment, or the unconfigured stand-in."""
    settings = settings or llm_settings()

    if not settings.configured:
        return UnconfiguredProvider()

    if settings.provider == "anthropic":
        return AnthropicProvider(settings)

    if settings.provider == "openai":
        return OpenAIProvider(settings)

    return UnconfiguredProvider()
