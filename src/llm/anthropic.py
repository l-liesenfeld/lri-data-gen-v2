"""Anthropic Messages API adapter.

Uses /v1/messages with x-api-key auth. Structured output via output_config.format
with type: json_schema (GA as of early 2026 — no beta header needed).

Token counting for cost estimation uses a char/4 heuristic. Anthropic's official
count-tokens endpoint requires a live API call, which isn't worth it for
pre-flight estimates. Actual usage is taken from response.usage, so the
post-run cost is exact.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from ..models import LLMRequest, LLMResponse
from .interface import ProviderError

log = logging.getLogger(__name__)

# Pricing in USD per 1M tokens. "ctx" is the context window.
# Keep in sync with anthropic.com/pricing.
ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":   {"in": 5.00, "out": 25.00, "ctx": 1_000_000.0},
    "claude-opus-4-6":   {"in": 5.00, "out": 25.00, "ctx": 1_000_000.0},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "ctx": 1_000_000.0},
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00,  "ctx": 200_000.0},
}

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
# Retryable: rate limit, overloaded (529), and standard server errors.
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class AnthropicProvider:
    def __init__(
        self,
        model_id: str,
        api_key: str,
        *,
        timeout_seconds: int = 60,
        max_retries: int = 8,
    ) -> None:
        if model_id not in ANTHROPIC_PRICING:
            known = ", ".join(sorted(ANTHROPIC_PRICING))
            raise ProviderError(
                f"unknown Anthropic model {model_id!r}. Known models: {known}"
            )
        self._model_id = model_id
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------
    def model_name(self) -> str:
        return self._model_id

    def context_window(self) -> int:
        return int(ANTHROPIC_PRICING[self._model_id]["ctx"])

    def cost_per_token(self) -> tuple[float, float]:
        p = ANTHROPIC_PRICING[self._model_id]
        return (p["in"] / 1_000_000.0, p["out"] / 1_000_000.0)

    def count_tokens(self, system: str, user: str) -> int:
        # Heuristic: ~4 chars/token. Anthropic's count-tokens endpoint requires
        # a network call; not worth it for pre-flight estimates. Post-run cost
        # uses exact usage from response.usage.
        return max(1, (len(system) + len(user)) // 4)

    async def complete(
        self, client: httpx.AsyncClient, request: LLMRequest
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.json_schema is not None:
            body["output_config"] = {
                "format": {"type": "json_schema", "schema": request.json_schema}
            }

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "Content-Type": "application/json",
        }

        for attempt in range(self._max_retries + 1):
            try:
                r = await client.post(
                    _MESSAGES_URL, headers=headers, json=body, timeout=self._timeout
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(
                        f"network error after {attempt} retries: {exc}"
                    ) from exc
                await asyncio.sleep(self._backoff_delay(attempt))
                continue

            if r.status_code == 200:
                return self._parse(r)

            if r.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                delay = self._retry_after(r) or self._backoff_delay(attempt)
                log.info(
                    "anthropic retry %s/%s after %ss (status=%s)",
                    attempt + 1, self._max_retries, round(delay, 1), r.status_code,
                )
                await asyncio.sleep(delay)
                continue

            raise ProviderError(self._format_error(r))

        raise ProviderError("retry budget exhausted")  # unreachable

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _parse(self, r: httpx.Response) -> LLMResponse:
        data = r.json()
        try:
            # content is a list of blocks; concatenate text blocks.
            blocks = data.get("content") or []
            text = "".join(
                b.get("text", "") for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderError(f"malformed response: {exc}") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            tokens_in=int(usage.get("input_tokens", 0)),
            tokens_out=int(usage.get("output_tokens", 0)),
            model=data.get("model", self._model_id),
            request_id=r.headers.get("request-id") or data.get("id"),
        )

    def _format_error(self, r: httpx.Response) -> str:
        try:
            err = r.json().get("error") or {}
            msg = err.get("message") or err.get("type") or r.text
        except Exception:
            msg = r.text
        return f"Anthropic {r.status_code}: {msg}"

    @staticmethod
    def _retry_after(r: httpx.Response) -> float | None:
        val = r.headers.get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        base = min(2**attempt, 60.0)
        jitter = 1.0 + random.uniform(-0.2, 0.2)
        return base * jitter
