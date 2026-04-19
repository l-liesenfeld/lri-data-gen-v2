"""Headless run orchestration shared by the CLI and the MCP server.

`prepare()` does the pure-data pre-flight (build provider, build prompt, estimate cost).
`execute()` runs the async pipeline and writes all artifacts.

Callers (CLI, MCP) handle their own pre-run confirmation and post-run reporting.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline, report
from .cost import estimate as _estimate
from .llm.interface import LLMProvider, UnknownProviderError
from .llm.registry import build_provider
from .models import (
    CostEstimate,
    ExperimentConfig,
    LLMRequest,
    MotiveMatrix,
    RunSummary,
)
from .prompt_builder import build_prompt


@dataclass
class PreparedRun:
    cfg: ExperimentConfig
    provider: LLMProvider
    request: LLMRequest
    estimate: CostEstimate


class CostCapExceeded(Exception):
    """Raised when a pre-flight estimate exceeds a caller-supplied budget cap."""

    def __init__(self, est: CostEstimate, cap: float) -> None:
        self.estimate = est
        self.cap = cap
        super().__init__(
            f"estimated cost ${est.cost_usd:.4f} exceeds cap ${cap:.2f}"
        )


class ContextWindowExceeded(Exception):
    def __init__(self, est: CostEstimate) -> None:
        self.estimate = est
        super().__init__(
            f"per-call tokens ({est.input_tokens_per_call + est.output_tokens_per_call}) "
            f"exceed context window ({est.context_window})"
        )


def prepare(cfg: ExperimentConfig, matrix: MotiveMatrix, api_key: str) -> PreparedRun:
    """Build provider, render prompt, compute estimate. No network writes."""
    try:
        provider = build_provider(
            cfg.model, api_key,
            timeout_seconds=cfg.timeout_seconds,
            max_retries=cfg.max_retries,
        )
    except UnknownProviderError as exc:
        raise ValueError(str(exc)) from exc
    request = build_prompt(cfg, matrix)
    est = _estimate(cfg, request, provider)
    if not est.fits_context:
        raise ContextWindowExceeded(est)
    return PreparedRun(cfg=cfg, provider=provider, request=request, estimate=est)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)


def _make_output_dir(cfg: ExperimentConfig) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = cfg.output_dir / f"{_slug(cfg.experiment_name)}_{ts}"
    candidate = base
    n = 2
    while candidate.exists():
        candidate = Path(f"{base}-{n}")
        n += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _write_run_meta(
    path: Path,
    cfg: ExperimentConfig,
    summary: RunSummary,
    est: CostEstimate,
    started_at: str,
    finished_at: str,
    version: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "experiment_name": cfg.experiment_name,
                "notes": cfg.notes,
                "started_at": started_at,
                "finished_at": finished_at,
                "model": cfg.model,
                "language": cfg.language,
                "n_responses_requested": summary.n_requested,
                "n_completed": summary.n_completed,
                "n_failed": summary.n_failed,
                "tokens_in_total": summary.tokens_in_total,
                "tokens_out_total": summary.tokens_out_total,
                "cost_usd_total": round(summary.cost_usd_total, 6),
                "cost_estimate_usd": round(est.cost_usd, 6),
                "elapsed_seconds": round(summary.elapsed_seconds, 2),
                "concurrency": cfg.concurrency,
                "synth_version": version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


async def execute_async(
    prepared: PreparedRun,
    matrix: MotiveMatrix,
    *,
    max_cost_usd: float | None = None,
    resume_path: Path | None = None,
    show_progress: bool = False,
    config_snapshot_path: Path | None = None,
    write_csv: bool = True,
    version: str = "0.1.0",
) -> tuple[RunSummary, Path, str, str]:
    """Async pipeline runner. Callers already inside an event loop (e.g. MCP
    tools) should await this directly; sync callers (CLI) should use `execute()`.

    Writes results.jsonl (always), results.csv (unless write_csv=False), run_meta.json,
    and optionally config_snapshot.yaml into a fresh timestamped output directory.
    """
    if max_cost_usd is not None and prepared.estimate.cost_usd > max_cost_usd:
        raise CostCapExceeded(prepared.estimate, max_cost_usd)

    run_dir = _make_output_dir(prepared.cfg)
    if config_snapshot_path is not None and config_snapshot_path.exists():
        shutil.copyfile(config_snapshot_path, run_dir / "config_snapshot.yaml")

    started_at = _utc_iso()
    summary = await pipeline.run(
        prepared.cfg,
        matrix,
        prepared.provider,
        prepared.request,
        output_dir=run_dir,
        resume_path=resume_path,
        show_progress=show_progress,
    )
    finished_at = _utc_iso()

    _write_run_meta(
        run_dir / "run_meta.json",
        prepared.cfg, summary, prepared.estimate,
        started_at, finished_at, version,
    )

    if write_csv:
        results = report.load_jsonl(summary.results_jsonl)
        token_total = summary.tokens_in_total + summary.tokens_out_total
        csv_path = run_dir / "results.csv"
        report.write_csv(
            results, csv_path,
            model=prepared.cfg.model,
            timestamp=started_at,
            token_usage=token_total,
            request_id=run_dir.name,
        )
        summary.results_csv = csv_path

    return summary, run_dir, started_at, finished_at


def execute(
    prepared: PreparedRun,
    matrix: MotiveMatrix,
    **kwargs,
) -> tuple[RunSummary, Path, str, str]:
    """Sync wrapper around `execute_async`. Only safe to call when NOT already
    inside a running event loop."""
    return asyncio.run(execute_async(prepared, matrix, **kwargs))
