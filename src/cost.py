"""Cost estimation + runtime tracking."""
from __future__ import annotations

from threading import Lock

from .llm.interface import LLMProvider
from .models import CostEstimate, ExperimentConfig, LLMRequest


def _estimate_output_tokens(language: str, response_length: int) -> int:
    """Heuristic; calibrate against real runs and update.

    Base ~90 + 30/sentence; x1.1 for pure German; x2 for bilingual; +60 JSON envelope.
    """
    base = 90 + 30 * response_length
    if language == "deutsch":
        base = int(base * 1.1)
    elif language == "deutsch-english":
        base = int(base * 2)
    return base + 60


def estimate(
    cfg: ExperimentConfig, request: LLMRequest, provider: LLMProvider
) -> CostEstimate:
    in_per_call = provider.count_tokens(request.system, request.user)
    out_per_call = _estimate_output_tokens(cfg.language, cfg.response_length)
    n = cfg.n_responses
    total_in = in_per_call * n
    total_out = out_per_call * n
    in_rate, out_rate = provider.cost_per_token()
    cost = total_in * in_rate + total_out * out_rate
    ctx = provider.context_window()
    fits = (in_per_call + out_per_call) <= ctx
    return CostEstimate(
        input_tokens_per_call=in_per_call,
        output_tokens_per_call=out_per_call,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        n_calls=n,
        cost_usd=cost,
        model=provider.model_name(),
        context_window=ctx,
        fits_context=fits,
    )


class CostTracker:
    def __init__(self, provider: LLMProvider) -> None:
        self._in_rate, self._out_rate = provider.cost_per_token()
        self._lock = Lock()
        self.tokens_in = 0
        self.tokens_out = 0

    def record(self, tokens_in: int, tokens_out: int) -> None:
        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out

    @property
    def cost_usd(self) -> float:
        with self._lock:
            return self.tokens_in * self._in_rate + self.tokens_out * self._out_rate
