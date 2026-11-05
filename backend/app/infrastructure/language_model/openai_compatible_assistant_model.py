import logging
import time
from collections.abc import Callable

import httpx

from app.domain.assistant.errors import ModelFailed

logger = logging.getLogger(__name__)

# Temporary failures worth one more try after a short wait: rate limits and "overloaded" answers.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_WAIT = 2.0  # seconds before the one retry
DEFAULT_TIMEOUT = 60.0  # seconds per call, like the receipt reader (Gemini often takes 15-20 s)


class OpenAiCompatibleAssistantModel:
    """The assistant's language model through the OpenAI-compatible chat API, which both Gemini (during
    development) and vLLM (serving the fine-tuned model on RunPod) offer. Switching between them is a settings change:
    the base URL, the key and the two model names (for vLLM, the SQL model is the LoRA adapter and the answer model is
    the same base model without it).

    Every call uses temperature 0 and sends the prompt as one user message, exactly as `build_prompt` made it.
    `thinking` turns the model's thinking on or off (vLLM's chat_template_kwargs); None sends nothing. A
    temporary failure (429, 5xx, a timeout) is tried once more after a short wait; anything else, or a second
    failure, raises ModelFailed."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        sql_model: str,
        answer_model: str,
        timeout: float = DEFAULT_TIMEOUT,
        thinking: bool | None = None,
        client: httpx.Client | None = None,
        wait: float = DEFAULT_WAIT,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self.sql_model = sql_model
        self.answer_model = answer_model
        self._thinking = thinking
        self._client = client or httpx.Client(timeout=timeout)
        self._wait = wait
        self._sleep = sleep

    def write_sql(self, prompt: str) -> str:
        return self._complete(self.sql_model, prompt)

    def write_answer(self, prompt: str) -> str:
        return self._complete(self.answer_model, prompt)

    def _complete(self, model: str, prompt: str) -> str:
        body: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        if self._thinking is not None:  # vLLM passes this to the model's chat template (Qwen3: enable_thinking)
            body["chat_template_kwargs"] = {"enable_thinking": self._thinking}
        try:
            return self._ask(body)
        except _Retryable as first:
            logger.warning("The language model %s failed, trying once more: %s", model, first)
            self._sleep(self._wait)
            try:
                return self._ask(body)
            except _Retryable as second:
                raise ModelFailed(f"The language model did not answer: {second}") from second

    def _ask(self, body: dict) -> str:
        try:
            response = self._client.post(self._url, headers={"Authorization": f"Bearer {self._api_key}"}, json=body)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise _Retryable(type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise ModelFailed(f"The language model could not be reached ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            # The body says why (overloaded, quota, unknown model). It never contains the API key.
            message = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code in RETRYABLE_STATUS:
                raise _Retryable(message)
            raise ModelFailed(f"The language model returned {message}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelFailed(f"The language model did not return a usable response ({type(exc).__name__})") from exc
        if not isinstance(content, str):
            raise ModelFailed("The language model did not return any text")
        return content


class _Retryable(Exception):
    """A temporary failure: worth waiting and trying once more."""
