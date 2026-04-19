"""LLM provider protocol."""
from __future__ import annotations

from typing import Protocol

import httpx

from ..models import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    async def complete(self, client: httpx.AsyncClient, request: LLMRequest) -> LLMResponse: ...

    def count_tokens(self, system: str, user: str) -> int: ...

    def cost_per_token(self) -> tuple[float, float]:
        """Returns (input_usd_per_token, output_usd_per_token)."""
        ...

    def model_name(self) -> str: ...

    def context_window(self) -> int: ...


class ProviderError(Exception):
    """Raised by providers for non-retryable failures."""


class UnknownProviderError(Exception):
    """Raised when the model string's provider prefix isn't registered."""
