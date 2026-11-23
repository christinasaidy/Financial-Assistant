"""The Standard mode's model: Claude through Anthropic's Messages API, with the official Python SDK (2026-11-23).

Checked against the official documentation on 2026-11-23 (anthropic 2.12.0, pinned in pyproject.toml):
- models: https://platform.claude.com/docs/en/models/overview and .../models/sonnet-5-5/overview
  (claude-sonnet-5-5 is a pinned snapshot; the id is configuration, STANDARD_ASSISTANT_MODEL);
- tool calls and results: https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
  (one tool_result per tool_use, first in the next user message; is_error for a failed or invalid call) and
  .../tool-use/strict-tool-use (strict: true, so the input follows the schema; the app still checks it);
- thinking: https://platform.claude.com/docs/en/build-with-claude/thinking (on by default on Sonnet 5.5 and cannot
  be turned off; its blocks must be sent back unchanged during tool use, so a reply is sent back exactly as it came;
  max_tokens covers thinking and text together) and .../build-with-claude/effort (low ... max; default high);
- tool_choice "none" works on Sonnet 5.5 (forcing "any"/"tool" is refused), used once the tool limits are reached;
- caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching (prefix order tools, system,
  messages; 512 tokens minimum on Sonnet 5.5; a top-level cache_control caches up to the last block, and one on the
  system block lets every conversation reuse the fixed instructions and tools; hits are read from usage).
temperature/top_p/top_k are refused by this model, so none is sent.

The client is made once and reused (its connections too). Each call is bounded by `timeout` and at most
`max_retries` SDK retries (connection errors, 408, 409, 429, 5xx). Any failure becomes ModelFailed with a short
message: never the key, the request or the provider's raw response.
"""

import anthropic

from app.application.assistant.dtos import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelUsage,
    TextPart,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from app.domain.assistant.errors import ModelFailed

EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AnthropicChatModel:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_output_tokens: int = 2048,
        effort: str = "medium",
        timeout: float = 60.0,
        max_retries: int = 1,
        http_client: anthropic.DefaultHttpxClient | None = None,
    ) -> None:
        if effort not in EFFORTS:
            raise ValueError(f"STANDARD_ASSISTANT_EFFORT must be one of {', '.join(EFFORTS)}")
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._effort = effort
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries,
                                           http_client=http_client)  # fmt: skip

    def respond(self, request: ChatRequest) -> ChatResponse:
        params: dict = {
            "model": self.model,
            "max_tokens": self._max_output_tokens,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "tools": [_tool(spec) for spec in request.tools],
            "messages": [_message(message) for message in request.messages],
            "output_config": {"effort": self._effort},
            "cache_control": {"type": "ephemeral"},  # also cache the conversation so far, for the next tool round
        }
        if not request.allow_tools:
            params["tool_choice"] = {"type": "none"}
        try:
            message = self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise ModelFailed("The Standard model did not answer in time") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelFailed("The Standard model could not be reached") from exc
        except anthropic.APIStatusError as exc:
            raise ModelFailed(f"The Standard model returned an error (HTTP {exc.status_code})") from exc
        except (anthropic.AnthropicError, ValueError, TypeError) as exc:  # e.g. a response that cannot be read
            raise ModelFailed(f"The Standard model's response could not be used ({type(exc).__name__})") from exc
        return _response(message)

    def close(self) -> None:
        self._client.close()


def _tool(spec: ToolSpec) -> dict:
    return {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema, "strict": True}


def _message(message: ChatMessage) -> dict:
    if message.provider_content is not None:  # a reply as the provider sent it, thinking blocks and all
        return {"role": message.role, "content": message.provider_content}
    content: list[dict] = []
    for part in message.parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        elif isinstance(part, ToolCall):
            content.append({"type": "tool_use", "id": part.id, "name": part.name, "input": part.input})
        elif isinstance(part, ToolResult):
            content.append({"type": "tool_result", "tool_use_id": part.call_id, "content": part.content,
                            "is_error": part.is_error})  # fmt: skip
    return {"role": message.role, "content": content}


def _response(message) -> ChatResponse:
    parts: list[TextPart | ToolCall] = []
    for block in message.content or []:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(TextPart(block.text))
        elif kind == "tool_use":  # anything but an object is passed on as is, and refused by the tool's checks
            parts.append(ToolCall(block.id, block.name, block.input if isinstance(block.input, dict) else
                                  {"input": block.input}))  # fmt: skip
        # thinking and redacted_thinking blocks are not shown; they go back in provider_content
    usage = getattr(message, "usage", None)
    return ChatResponse(
        parts=tuple(parts),
        stop_reason=message.stop_reason,
        model=message.model or "",
        usage=None if usage is None else ModelUsage(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None),
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
        ),
        request_id=getattr(message, "_request_id", None),
        provider_content=list(message.content or []),
    )  # fmt: skip
