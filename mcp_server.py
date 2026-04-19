"""synth-data MCP server.

Local stdio MCP server that exposes the synth-data generation pipeline to
Claude Desktop (or any MCP client). Register in Claude Desktop's config at
`~/Library/Application Support/Claude/claude_desktop_config.json`:

    {
      "mcpServers": {
        "synth-data": {
          "command": "/abs/path/to/synth-data/.venv/bin/python",
          "args": ["/abs/path/to/synth-data/mcp_server.py"]
        }
      }
    }

API keys come from the project's `.env` (loaded at startup).

NEVER write to stdout — MCP uses stdout for JSON-RPC frames. All diagnostic
output must go to stderr via the standard `logging` module.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))  # allow `from src import ...` when Claude spawns us

load_dotenv(ROOT / ".env")

from src import report, runner  # noqa: E402
from src.llm.interface import ProviderError  # noqa: E402
from src.models import (  # noqa: E402
    ExperimentConfig,
    MotiveMatrix,
    MotiveWeight,
)
from src.runner import ContextWindowExceeded, CostCapExceeded  # noqa: E402

logging.basicConfig(
    level=os.environ.get("SYNTH_MCP_LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("synth-data.mcp")

DEFAULT_MATRIX = ROOT / "data" / "motive_matrix.json"
DEFAULT_OUTPUT = ROOT / "data" / "output"
VERSION = "0.1.0"

# Load the motive matrix once at server startup — it's read-only, tiny, and
# used by every tool call.
MATRIX: MotiveMatrix = MotiveMatrix.load(DEFAULT_MATRIX)

# Hard caps that override caller input. Claude Desktop has a tool-call timeout;
# anything larger belongs in the CLI.
MAX_N_RESPONSES = 100
DEFAULT_MAX_COST_USD = 1.0

mcp = FastMCP(
    name="synth-data",
    instructions=(
        "Generate synthetic psychological journal entries with configurable "
        "subconscious motives at configurable strengths. Use `list_motives` "
        "first to see the catalog, `estimate_cost` for a dry-run budget check, "
        "and `generate` to produce entries. Results are returned in-chat for "
        "small runs; for larger runs the tool returns a preview plus file paths."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_api_key(provider_prefix: str) -> str:
    env_var = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider_prefix)
    if env_var is None:
        raise ValueError(f"unknown provider prefix: {provider_prefix!r}")
    key = os.environ.get(env_var)
    if not key:
        raise ValueError(
            f"{env_var} not set. Put it in the project's .env or pass it as "
            "an `env:` entry in the Claude Desktop MCP config."
        )
    return key


def _build_config(
    *,
    motives: dict[str, float],
    n_responses: int,
    model: str,
    language: str,
    response_length: int,
    context_hint: str,
    experiment_name: str | None,
    temperature: float,
    output_dir: str | None,
) -> ExperimentConfig:
    if n_responses < 1 or n_responses > MAX_N_RESPONSES:
        raise ValueError(
            f"n_responses must be 1..{MAX_N_RESPONSES}. For larger runs, use the CLI."
        )
    if response_length < 1 or response_length > 5:
        raise ValueError("response_length must be 1..5")
    if language not in ("english", "deutsch", "deutsch-english"):
        raise ValueError(
            "language must be one of: 'english', 'deutsch', 'deutsch-english'"
        )
    if ":" not in model:
        raise ValueError(
            "model must be provider-prefixed, e.g. 'openai:gpt-5.4-mini' "
            "or 'anthropic:claude-sonnet-4-6'"
        )
    if not motives:
        raise ValueError("at least one motive must be provided")

    weights: list[MotiveWeight] = []
    for mid, strength in motives.items():
        if mid not in MATRIX.cells:
            valid = ", ".join(sorted(MATRIX.cells))
            raise ValueError(f"unknown motive id {mid!r}. Valid: {valid}")
        s = float(strength)
        if not (0.1 <= s <= 1.0):
            raise ValueError(
                f"motive {mid!r} strength must be in [0.1, 1.0], got {s}"
            )
        weights.append(MotiveWeight(id=mid, strength=s))

    # Stable order A1..A5, L1..L5, M1..M5, F1..F5
    weights.sort(key=lambda w: (("A", "L", "M", "F").index(w.id[0]), int(w.id[1:])))

    name = experiment_name or "mcp_run"
    out = Path(output_dir) if output_dir else DEFAULT_OUTPUT

    return ExperimentConfig(
        experiment_name=name,
        output_dir=out,
        notes="generated via MCP",
        model=model,
        n_responses=n_responses,
        response_length=response_length,
        language=language,
        context_hint=context_hint,
        temperature=temperature,
        max_tokens=512,
        concurrency=3,
        max_retries=8,
        timeout_seconds=60,
        motives=weights,
    )


def _estimate_dict(est: Any) -> dict:
    return {
        "model": est.model,
        "n_calls": est.n_calls,
        "input_tokens_per_call": est.input_tokens_per_call,
        "output_tokens_per_call_estimated": est.output_tokens_per_call,
        "total_input_tokens": est.total_input_tokens,
        "total_output_tokens_estimated": est.total_output_tokens,
        "total_cost_usd_estimated": round(est.cost_usd, 6),
        "context_window": est.context_window,
        "fits_context": est.fits_context,
    }


def _result_to_dict(r) -> dict:
    return {
        "response_id": r.response_id,
        "status": r.status,
        "text": r.text,
        "text_deutsch": r.text_deutsch,
        "motives_present": [
            {"id": m.id, "name": m.name, "strength": m.strength}
            for m in r.motives_present
        ],
        "error": r.error,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_motives() -> list[dict]:
    """List the 20 motives available for generation, grouped by category.

    Returns one dict per motive: {id, category, category_name, name, description}.
    IDs like "A1".."A5" (Affiliation), "L1".."L5" (Leistung/Achievement),
    "M1".."M5" (Macht/Power), "F1".."F5" (Freiheit/Freedom).
    Use these IDs in the `motives` arg of `estimate_cost` and `generate`.
    """
    out: list[dict] = []
    for cat_key in ("A", "L", "M", "F"):
        cat_name = MATRIX.categories.get(cat_key, cat_key)
        for mid in MATRIX.category_ids(cat_key):
            cell = MATRIX.get(mid)
            out.append({
                "id": cell.id,
                "category": cat_key,
                "category_name": cat_name,
                "name": cell.name,
                "description": cell.description,
            })
    return out


@mcp.tool()
def estimate_cost(
    motives: dict[str, float],
    n_responses: int,
    model: str = "openai:gpt-5.4-mini",
    language: str = "english",
    response_length: int = 3,
    context_hint: str = "",
) -> dict:
    """Dry-run cost + token estimate. No API calls made.

    motives: mapping of motive id -> strength in [0.1, 1.0], e.g. {"A1": 0.7, "L3": 0.4}.
    n_responses: number of journal entries to generate, 1..100.
    model: provider-prefixed (openai:... or anthropic:...).
    language: 'english' | 'deutsch' | 'deutsch-english'.
    response_length: sentences per entry, 1..5.
    context_hint: optional scene/situation nudge for the prompt.

    Returns a dict with estimated token counts and total USD cost. Input tokens
    are exact for OpenAI (tiktoken); an approximation for Anthropic. Output
    tokens are heuristic in both cases — the actual run will record exact numbers.
    """
    cfg = _build_config(
        motives=motives,
        n_responses=n_responses,
        model=model,
        language=language,
        response_length=response_length,
        context_hint=context_hint,
        experiment_name=None,
        temperature=0.9,
        output_dir=None,
    )
    api_key = _resolve_api_key(cfg.provider_prefix)
    try:
        prepared = runner.prepare(cfg, MATRIX, api_key)
    except ContextWindowExceeded as exc:
        return {"error": str(exc), "estimate": _estimate_dict(exc.estimate)}
    return _estimate_dict(prepared.estimate)


@mcp.tool()
async def generate(
    motives: dict[str, float],
    n_responses: int,
    model: str = "openai:gpt-5.4-mini",
    language: str = "english",
    response_length: int = 3,
    context_hint: str = "",
    experiment_name: str | None = None,
    temperature: float = 0.9,
    max_cost_usd: float = DEFAULT_MAX_COST_USD,
    output_dir: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Generate synthetic journal entries for the given motive profile.

    motives: mapping of motive id -> strength in [0.1, 1.0].
    n_responses: number of entries to generate, 1..100.
    model: provider-prefixed (openai:... or anthropic:...). Default is
      openai:gpt-5.4-mini; openai:gpt-4.1-mini is cheaper; anthropic:claude-sonnet-4-6
      is a good alternative provider.
    language: 'english' | 'deutsch' | 'deutsch-english'. Bilingual adds a German translation.
    response_length: sentences per entry, 1..5.
    context_hint: optional scene/situation nudge (e.g. "workplace situation").
    experiment_name: used in the output directory name. Defaults to "mcp_run".
    temperature: 0.0..2.0; lower = more deterministic.
    max_cost_usd: pre-flight budget cap. If the estimate exceeds this, the tool
      refuses and returns the estimate instead — re-call with a higher cap to
      proceed. Default $1.00.
    output_dir: where to write results.jsonl / results.csv / run_meta.json.
      Defaults to the project's `data/output/` directory.

    Returns a dict:
      - status: "ok" | "refused" | "partial"
      - summary: {n_completed, n_failed, cost_usd_actual, elapsed_seconds, output_dir}
      - estimate: pre-flight estimate
      - results: inline for n<=20, else a 5-entry preview with a note pointing at output_dir
      - failure_breakdown: {rate_limited, network, parse_error, auth, ...} counts

    Files (JSONL + CSV + run_meta) are always written to output_dir regardless
    of n_responses — Claude Desktop's filesystem MCP can pick them up from there.
    """
    cfg = _build_config(
        motives=motives,
        n_responses=n_responses,
        model=model,
        language=language,
        response_length=response_length,
        context_hint=context_hint,
        experiment_name=experiment_name,
        temperature=temperature,
        output_dir=output_dir,
    )
    api_key = _resolve_api_key(cfg.provider_prefix)

    try:
        prepared = runner.prepare(cfg, MATRIX, api_key)
    except ContextWindowExceeded as exc:
        return {
            "status": "refused",
            "reason": "context_window_exceeded",
            "detail": str(exc),
            "estimate": _estimate_dict(exc.estimate),
        }

    if ctx is not None:
        await ctx.info(
            f"preflight ok: {cfg.n_responses} × {cfg.model}  "
            f"~${prepared.estimate.cost_usd:.4f} estimated"
        )

    try:
        summary, run_dir, _started, _finished = runner.execute(
            prepared, MATRIX,
            max_cost_usd=max_cost_usd,
            show_progress=False,
            version=VERSION,
        )
    except CostCapExceeded as exc:
        return {
            "status": "refused",
            "reason": "cost_cap_exceeded",
            "detail": str(exc),
            "estimate": _estimate_dict(exc.estimate),
            "max_cost_usd": exc.cap,
        }
    except ProviderError as exc:
        return {
            "status": "refused",
            "reason": "provider_error",
            "detail": str(exc),
        }

    results = report.load_jsonl(summary.results_jsonl)

    if len(results) <= 20:
        results_payload = [_result_to_dict(r) for r in results]
        truncated = False
    else:
        results_payload = [_result_to_dict(r) for r in results[:5]]
        truncated = True

    status = "ok" if summary.n_failed == 0 else "partial"

    payload: dict = {
        "status": status,
        "summary": {
            "n_requested": summary.n_requested,
            "n_completed": summary.n_completed,
            "n_failed": summary.n_failed,
            "cost_usd_actual": round(summary.cost_usd_total, 6),
            "elapsed_seconds": round(summary.elapsed_seconds, 2),
            "output_dir": str(run_dir),
            "results_jsonl": str(summary.results_jsonl),
            "results_csv": str(summary.results_csv) if summary.results_csv else None,
        },
        "estimate": _estimate_dict(prepared.estimate),
        "results": results_payload,
        "results_truncated": truncated,
        "failure_breakdown": summary.failure_breakdown,
    }
    if truncated:
        payload["note"] = (
            f"only the first 5 of {len(results)} results returned inline; "
            f"full set on disk at {run_dir}/results.jsonl"
        )
    return payload


if __name__ == "__main__":
    log.info("synth-data MCP server starting (stdio)")
    mcp.run()
