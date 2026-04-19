"""Provider registry. Wires 'openai:' and 'anthropic:' prefixes."""
from __future__ import annotations

from .anthropic import AnthropicProvider
from .interface import LLMProvider, UnknownProviderError
from .openai import OpenAIProvider


def parse_model_string(model: str) -> tuple[str, str]:
    if ":" not in model:
        raise UnknownProviderError(
            f"model string must be prefixed (e.g. 'openai:gpt-5.4-mini'), got {model!r}"
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
    if provider == "anthropic":
        return AnthropicProvider(
            model_id=model_id,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    raise UnknownProviderError(
        f"provider {provider!r} not supported. Known: 'openai', 'anthropic'."
    )
