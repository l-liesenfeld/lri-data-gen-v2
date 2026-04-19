"""Provider registry. Phase 1: openai: only."""
from __future__ import annotations

from .interface import LLMProvider, UnknownProviderError
from .openai import OpenAIProvider


def parse_model_string(model: str) -> tuple[str, str]:
    if ":" not in model:
        raise UnknownProviderError(
            f"model string must be prefixed (e.g. 'openai:gpt-4o-...'), got {model!r}"
        )
    provider, model_id = model.split(":", 1)
    return provider, model_id


def build_provider(
    model: str,
    api_key: str,
    *,
    timeout_seconds: int = 60,
    max_retries: int = 5,
) -> LLMProvider:
    provider, model_id = parse_model_string(model)
    if provider == "openai":
        return OpenAIProvider(
            model_id=model_id,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    raise UnknownProviderError(
        f"provider {provider!r} not supported in phase 1 (only 'openai' is wired)"
    )
