"""The dataset's question writers: the free stand-in, and Qwen through an OpenAI-compatible API (vLLM).

The app's model client always uses temperature 0; the generator needs about 0.8 for varied phrasings, so it has
its own small client here (decided with the user on 2026-11-07) rather than a research-only option in the app.
"""

import json
import time
from typing import Protocol

import httpx

from research.dataset.generator_prompt import LANGUAGES
from research.dataset.templates import Spec

TEMPERATURE = 0.8
TIMEOUT = 180.0  # seconds; six versions with replies can take a while on a busy server
RETRYABLE = frozenset({429, 500, 502, 503, 504})


class QuestionWriter(Protocol):
    name: str

    def write(self, spec: Spec, prompt: str, seed: int) -> str:
        """The writer's reply to the generator prompt: JSON with six versions."""


class StandInWriter:
    """Writes plain questions from the spec itself, using the first spellings of the words each question must
    contain, so the whole pipeline can run without calling a model. Its questions are not training material."""

    name = "stand-in"

    def write(self, spec: Spec, prompt: str, seed: int) -> str:
        versions = []
        for number, language in enumerate(LANGUAGES):
            version = {"language": language, "question": self._question(spec.mentions, language, number)}
            if spec.base is not None:
                version["first"] = self._question(spec.base.mentions, language, number)
            if spec.kind == "clarify":
                version["reply"] = "CLARIFY: " + (spec.reply_hint or "What do you mean?")
            elif spec.kind == "reply":
                version["reply"] = "REPLY: " + (spec.reply_hint or "Hello!").replace(" Never state amounts.", "")
            versions.append(version)
        return json.dumps({"versions": versions})

    @staticmethod
    def _question(mentions: tuple[tuple[str, ...], ...], language: str, number: int) -> str:
        words = [group[min(number % 3 + (language != "english"), len(group) - 1)] for group in mentions]
        start = {"arabizi": "adde sarafet", "mixed": "how much sarafet", "english": "How much did I spend on"}[language]
        return f"{start} {' '.join(words)} ({number})?".replace("  ", " ")


class QwenWriter:
    """Qwen (or any model) through the OpenAI-compatible chat API, as vLLM serves it: thinking off, temperature
    0.8, JSON output, and a seed per call so a run can be repeated. A temporary failure is tried once more."""

    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None,
                 wait: float = 5.0) -> None:  # fmt: skip
        self.name = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._wait = wait

    def write(self, spec: Spec, prompt: str, seed: int) -> str:
        body = {
            "model": self.name, "messages": [{"role": "user", "content": prompt}], "temperature": TEMPERATURE,
            "seed": seed, "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }  # fmt: skip
        for attempt in (1, 2):
            try:
                response = self._client.post(self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"})
            except httpx.TimeoutException:
                if attempt == 2:
                    raise
            else:
                if response.status_code not in RETRYABLE or attempt == 2:
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"] or ""
            time.sleep(self._wait)
        raise RuntimeError("unreachable")
