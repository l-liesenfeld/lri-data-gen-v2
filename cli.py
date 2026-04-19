"""synth-data CLI entry point."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv

from src import pipeline, report
from src.cost import estimate
from src.llm.interface import UnknownProviderError
from src.llm.registry import build_provider
from src.models import ConfigError, ExperimentConfig, MotiveMatrix, load_config
from src.prompt_builder import build_prompt

ROOT = Path(__file__).resolve().parent
DEFAULT_MATRIX = ROOT / "data" / "motive_matrix.json"
VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_matrix(path: Path) -> MotiveMatrix:
    if not path.exists():
        raise click.ClickException(f"motive matrix not found: {path}")
    return MotiveMatrix.load(path)


def _load_cfg(config_path: Path, matrix: MotiveMatrix) -> ExperimentConfig:
    if not config_path.exists():
        raise click.ClickException(f"config not found: {config_path}")
    try:
        return load_config(config_path, matrix)
    except ConfigError as exc:
        raise click.ClickException(f"config error: {exc}") from exc


def _require_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise click.ClickException(
            "OPENAI_API_KEY not set. Add it to .env or export it:\n"
            '  echo "OPENAI_API_KEY=sk-..." >> .env'
        )
    return key


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


def _print_estimate(est) -> None:
    click.echo("Cost estimate")
    click.echo(f"  Model:             {est.model}")
    click.echo(f"  Calls:             {est.n_calls}")
    click.echo(f"  Input / call:      {est.input_tokens_per_call:,} tokens")
    click.echo(f"  Output / call:     ~{est.output_tokens_per_call:,} tokens (estimated)")
    click.echo(f"  Total input:       ~{est.total_input_tokens:,}")
    click.echo(f"  Total output:      ~{est.total_output_tokens:,}")
    click.echo(f"  Estimated cost:    ${est.cost_usd:.2f}")
    if not est.fits_context:
        click.secho(
            f"  WARNING: per-call tokens exceed context window ({est.context_window:,})",
            fg="red",
        )


def _confirm_cost(est, auto_yes: bool) -> None:
    if not est.fits_context:
        raise click.ClickException("aborting: context window exceeded")
    warn_big = est.cost_usd > 20 or est.n_calls > 500
    if warn_big:
        click.secho(
            f"  Heads up: large run (${est.cost_usd:.2f}, {est.n_calls} calls)", fg="yellow"
        )
    if auto_yes:
        return
    if not click.confirm("Proceed?", default=False):
        raise click.ClickException("aborted by user")


def _write_run_meta(
    path: Path, cfg: ExperimentConfig, summary, est, started_at: str, finished_at: str
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
                "synth_version": VERSION,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group(help=f"synth-data v{VERSION} — synthetic psychological training data generator")
@click.option("--matrix", type=click.Path(path_type=Path), default=DEFAULT_MATRIX, show_default=True)
@click.option("-v", "--verbose", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, matrix: Path, verbose: bool, quiet: bool) -> None:
    load_dotenv()  # .env -> os.environ
    ctx.ensure_object(dict)
    ctx.obj["matrix_path"] = matrix
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


@cli.command("validate")
@click.argument("config_path", type=click.Path(path_type=Path))
@click.pass_context
def cmd_validate(ctx: click.Context, config_path: Path) -> None:
    """Check a config file without making any network calls."""
    matrix = _load_matrix(ctx.obj["matrix_path"])
    cfg = _load_cfg(config_path, matrix)
    click.echo(f"OK  {config_path}")
    click.echo(f"    model={cfg.model}  n={cfg.n_responses}  lang={cfg.language}")
    click.echo(f"    motives: {', '.join(f'{m.id}@{m.strength}' for m in cfg.motives)}")


@cli.command("list-motives")
@click.pass_context
def cmd_list_motives(ctx: click.Context) -> None:
    """Print the motive matrix."""
    matrix = _load_matrix(ctx.obj["matrix_path"])
    for cat_key, cat_name in matrix.categories.items():
        click.secho(f"\n{cat_key}  {cat_name}", bold=True)
        for mid in matrix.category_ids(cat_key):
            cell = matrix.get(mid)
            click.echo(f"  {cell.id}  {cell.name}")


@cli.command("estimate")
@click.argument("config_path", type=click.Path(path_type=Path))
@click.pass_context
def cmd_estimate(ctx: click.Context, config_path: Path) -> None:
    """Print a token/cost estimate and exit."""
    matrix = _load_matrix(ctx.obj["matrix_path"])
    cfg = _load_cfg(config_path, matrix)
    api_key = _require_openai_key()
    try:
        provider = build_provider(
            cfg.model, api_key,
            timeout_seconds=cfg.timeout_seconds,
            max_retries=cfg.max_retries,
        )
    except UnknownProviderError as exc:
        raise click.ClickException(str(exc)) from exc
    request = build_prompt(cfg, matrix)
    est = estimate(cfg, request, provider)
    _print_estimate(est)


@cli.command("generate")
@click.argument("config_path", type=click.Path(path_type=Path))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None,
              help="Override output directory")
@click.option("--concurrency", type=int, default=None, help="Override concurrency")
@click.option("-y", "--yes", "auto_yes", is_flag=True, help="Skip cost confirmation")
@click.option("--no-csv", is_flag=True, help="Stop after JSONL, skip CSV export")
@click.option("--resume", "resume_path", type=click.Path(path_type=Path), default=None,
              help="Resume from an existing results.jsonl")
@click.pass_context
def cmd_generate(
    ctx: click.Context,
    config_path: Path,
    out_dir: Path | None,
    concurrency: int | None,
    auto_yes: bool,
    no_csv: bool,
    resume_path: Path | None,
) -> None:
    """Primary workflow: estimate -> confirm -> run -> export."""
    matrix = _load_matrix(ctx.obj["matrix_path"])
    cfg = _load_cfg(config_path, matrix)
    if concurrency is not None:
        cfg.concurrency = concurrency
    if out_dir is not None:
        cfg.output_dir = out_dir

    api_key = _require_openai_key()
    try:
        provider = build_provider(
            cfg.model, api_key,
            timeout_seconds=cfg.timeout_seconds,
            max_retries=cfg.max_retries,
        )
    except UnknownProviderError as exc:
        raise click.ClickException(str(exc)) from exc

    request = build_prompt(cfg, matrix)
    est = estimate(cfg, request, provider)

    click.echo(f"synth-data v{VERSION}")
    click.echo(f"Config:  {config_path}")
    click.echo(f"Model:   {cfg.model}   Calls: {cfg.n_responses}   Concurrency: {cfg.concurrency}")
    click.echo("")
    _print_estimate(est)
    click.echo("")
    _confirm_cost(est, auto_yes)

    run_dir = _make_output_dir(cfg)
    shutil.copyfile(config_path, run_dir / "config_snapshot.yaml")
    started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    summary = asyncio.run(
        pipeline.run(
            cfg, matrix, provider, request,
            output_dir=run_dir,
            resume_path=resume_path,
            show_progress=not ctx.obj["quiet"],
        )
    )
    finished_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # run_meta.json
    _write_run_meta(run_dir / "run_meta.json", cfg, summary, est, started_at, finished_at)

    # CSV export
    if not no_csv:
        results = report.load_jsonl(summary.results_jsonl)
        token_total = summary.tokens_in_total + summary.tokens_out_total
        csv_path = run_dir / "results.csv"
        report.write_csv(
            results,
            csv_path,
            model=cfg.model,
            timestamp=started_at,
            token_usage=token_total,
            request_id=run_dir.name,
        )
        summary.results_csv = csv_path

    # Final summary
    click.echo("")
    click.secho(f"Done in {summary.elapsed_seconds:.1f}s", bold=True)
    click.echo(f"  Completed: {summary.n_completed}    Failed: {summary.n_failed}")
    click.echo(f"  Tokens in: {summary.tokens_in_total:,}  out: {summary.tokens_out_total:,}")
    click.echo(f"  Actual cost: ${summary.cost_usd_total:.2f}  (est ${est.cost_usd:.2f})")
    click.echo(f"  Output:    {run_dir}/")
    if summary.n_failed:
        sys.exit(2)


@cli.command("report")
@click.argument("jsonl_path", type=click.Path(path_type=Path))
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="CSV output path (default: sibling results.csv)")
def cmd_report(jsonl_path: Path, out_path: Path | None) -> None:
    """Convert an existing results.jsonl to CSV."""
    if not jsonl_path.exists():
        raise click.ClickException(f"not found: {jsonl_path}")
    results = report.load_jsonl(jsonl_path)
    if not results:
        raise click.ClickException("no results in jsonl")
    out = out_path or jsonl_path.with_suffix(".csv")

    # Derive meta from results (no run_meta.json required).
    model = results[0].model
    timestamp = results[0].created_at
    token_usage = sum(r.tokens_in + r.tokens_out for r in results)
    request_id = jsonl_path.parent.name

    report.write_csv(
        results, out,
        model=model, timestamp=timestamp,
        token_usage=token_usage, request_id=request_id,
    )
    click.echo(f"wrote {out}  ({len(results)} rows)")


if __name__ == "__main__":
    cli()
