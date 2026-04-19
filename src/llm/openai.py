"""OpenAI chat completions adapter. Phase 1: gpt-4o only."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx
import tiktoken

from ..models import LLMRequest, LLMResponse
from .interface import ProviderError

log = logging.getLogger(__name__)

# USD per 1M tokens. Phase 1 ships with the single confirmed 4o entry.
# Additional models + providers are phase 2.
OPENAI_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-2024-08-06": {"in": 2.50, "out": 10.00, "ctx": 128_000.0},
}

_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAIProvider:
    def __init__(
        self,
        model_id: str,
        api_key: str,
        *,
        timeout_seconds: int = 60,
        max_retries: int = 5,
    ) -> None:
        if model_id not in OPENAI_PRICING:
            known = ", ".join(sorted(OPENAI_PRICING))
            raise ProviderError(
                f"unknown OpenAI model {model_id!r}. Phase 1 supports: {known}"
            )
        self._model_id = model_id
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        try:
            self._encoder = tiktoken.encoding_for_model(model_id)
        except KeyError:
            self._encoder = tiktoken.get_encoding("o200k_base")

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------
    def model_name(self) -> str:
        return self._model_id

    def context_window(self) -> int:
        return int(OPENAI_PRICING[self._model_id]["ctx"])

    def cost_per_token(self) -> tuple[float, float]:
        p = OPENAI_PRICING[self._model_id]
        return (p["in"] / 1_000_000.0, p["out"] / 1_000_000.0)

    def count_tokens(self, system: str, user: str) -> int:
        # Chat completions overhead: 3 tokens per message + 3 priming (OpenAI cookbook).
        per_message_overhead = 3
        priming = 3
        total = priming
        for content in (system, user):
            total += per_message_overhead
            total += len(self._encoder.encode(content))
        return total

    async def complete(
        self, client: httpx.AsyncClient, request: LLMRequest
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format_json:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self._max_retries + 1):
            try:
                r = await client.post(
                    _CHAT_URL, headers=headers, json=body, timeout=self._timeout
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(f"network error after {attempt} retries: {exc}") from exc
                await self._sleep_backoff(attempt)
                continue

            if r.status_code == 200:
                return self._parse(r)

            if r.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                delay = self._retry_after(r) or self._backoff_delay(attempt)
                log.info(
                    "openai retry %s/%s after %ss (status=%s)",
                    attempt + 1, self._max_retries, round(delay, 1), r.status_code,
                )
                await asyncio.sleep(delay)
                continue

            # Non-retryable or exhausted
            raise ProviderError(self._format_error(r))

        raise ProviderError("retry budget exhausted")  # unreachable

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _parse(self, r: httpx.Response) -> LLMResponse:
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"malformed response: {exc}") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=data.get("model", self._model_id),
            request_id=r.headers.get("x-request-id"),
        )

    def _format_error(self, r: httpx.Response) -> str:
        try:
            err = r.json().get("error") or {}
            msg = err.get("message") or err.get("type") or r.text
        except Exception:
            msg = r.text
        return f"OpenAI {r.status_code}: {msg}"

    @staticmethod
    def _retry_after(r: httpx.Response) -> float | None:
        val = r.headers.get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except ValueError:
            return None

    async def _sleep_backoff(self, attempt: int) -> None:
        await asyncio.sleep(self._backoff_delay(attempt))

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        base = min(2**attempt, 16.0)
        jitter = 1.0 + random.uniform(-0.2, 0.2)
        return base * jitter
