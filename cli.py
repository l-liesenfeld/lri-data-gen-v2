"""synth-data CLI entry point.

Two usage paths:

    # Interactive wizard (asks a handful of questions, writes a YAML, runs it)
    python cli.py

    # Config file (edit a YAML, run it)
    python cli.py generate config/example.yaml

Run `python cli.py <command> --help` for per-command help.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

from src import pipeline, report
from src.cost import estimate
from src.llm.interface import UnknownProviderError
from src.llm.registry import build_provider
from src.models import (
    ConfigError,
    CostEstimate,
    ExperimentConfig,
    MotiveMatrix,
    RunSummary,
    load_config,
)
from src.prompt_builder import build_prompt

ROOT = Path(__file__).resolve().parent
DEFAULT_MATRIX = ROOT / "data" / "motive_matrix.json"
VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Shared helpers
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


def _require_api_key(provider: str) -> str:
    env_var = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
    if env_var is None:
        raise click.ClickException(f"unknown provider prefix: {provider!r}")
    key = os.environ.get(env_var)
    if not key:
        raise click.ClickException(
            f"{env_var} not set. Add it to .env or export it:\n"
            f'  echo "{env_var}=..." >> .env'
        )
    return key


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def print_estimate(est: CostEstimate) -> None:
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


def _confirm_cost(est: CostEstimate, auto_yes: bool) -> None:
    if not est.fits_context:
        raise click.ClickException("aborting: context window exceeded")
    if est.cost_usd > 20 or est.n_calls > 500:
        click.secho(
            f"  Heads up: large run (${est.cost_usd:.2f}, {est.n_calls} calls)", fg="yellow"
        )
    if auto_yes:
        return
    if not click.confirm("Proceed?", default=False):
        raise click.ClickException("aborted by user")


def _write_run_meta(
    path: Path,
    cfg: ExperimentConfig,
    summary: RunSummary,
    est: CostEstimate,
    started_at: str,
    finished_at: str,
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
# Core workflow (shared by `generate` subcommand and wizard)
# ---------------------------------------------------------------------------

def run_generate(
    config_path: Path,
    matrix_path: Path,
    *,
    out_dir: Path | None = None,
    concurrency: int | None = None,
    auto_yes: bool = False,
    no_csv: bool = False,
    resume_path: Path | None = None,
    show_progress: bool = True,
) -> RunSummary:
    """Load config, estimate, confirm, run pipeline, export CSV. Returns the summary."""
    matrix = _load_matrix(matrix_path)
    cfg = _load_cfg(config_path, matrix)
    if concurrency is not None:
        cfg.concurrency = concurrency
    if out_dir is not None:
        cfg.output_dir = out_dir

    api_key = _require_api_key(cfg.provider_prefix)
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
    if cfg.requests_per_minute or cfg.tokens_per_minute:
        rpm = f"{cfg.requests_per_minute} RPM" if cfg.requests_per_minute else "—"
        tpm = f"{cfg.tokens_per_minute:,} TPM" if cfg.tokens_per_minute else "—"
        click.echo(f"Rate limit: {rpm}   {tpm}")
    click.echo("")
    print_estimate(est)
    click.echo("")
    _confirm_cost(est, auto_yes)

    run_dir = _make_output_dir(cfg)
    shutil.copyfile(config_path, run_dir / "config_snapshot.yaml")
    started_at = _utc_iso()

    summary = asyncio.run(
        pipeline.run(
            cfg, matrix, provider, request,
            output_dir=run_dir,
            resume_path=resume_path,
            show_progress=show_progress,
        )
    )
    finished_at = _utc_iso()

    _write_run_meta(run_dir / "run_meta.json", cfg, summary, est, started_at, finished_at)

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

    click.echo("")
    click.secho(f"Done in {summary.elapsed_seconds:.1f}s", bold=True)
    fail_suffix = ""
    if summary.failure_breakdown:
        fail_suffix = "  (" + ", ".join(
            f"{n} {cls}" for cls, n in sorted(summary.failure_breakdown.items(), key=lambda kv: -kv[1])
        ) + ")"
    click.echo(f"  Completed: {summary.n_completed}    Failed: {summary.n_failed}{fail_suffix}")
    click.echo(f"  Tokens in: {summary.tokens_in_total:,}  out: {summary.tokens_out_total:,}")
    click.echo(f"  Actual cost: ${summary.cost_usd_total:.2f}  (est ${est.cost_usd:.2f})")
    click.echo(f"  Output:    {run_dir}/")
    if summary.failure_breakdown.get("rate_limited") and not (
        cfg.requests_per_minute or cfg.tokens_per_minute
    ):
        click.secho(
            "\nTip: configure `runtime.requests_per_minute` / `runtime.tokens_per_minute` "
            "in your YAML to pace below your OpenAI tier's limits proactively.",
            fg="yellow",
        )
    return summary


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

GROUP_HELP = f"""\
synth-data v{VERSION} — synthetic psychological training data generator.

\b
Typical use (interactive):
  python cli.py

\b
Typical use (config file):
  python cli.py generate config/example.yaml

\b
Other commands:
  estimate      dry-run token + cost estimate
  validate      schema-check a YAML without touching the network
  list-motives  print the motive matrix
  report        convert a results.jsonl to CSV
  wizard        explicit alias for the interactive flow
"""


@click.group(
    help=GROUP_HELP,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--matrix",
    type=click.Path(path_type=Path),
    default=DEFAULT_MATRIX,
    show_default=True,
    help="Motive matrix JSON file.",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress progress bar (errors still print).")
@click.version_option(VERSION, "-V", "--version", message="synth-data %(version)s")
@click.pass_context
def cli(ctx: click.Context, matrix: Path, verbose: bool, quiet: bool) -> None:
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["matrix_path"] = matrix
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    if ctx.invoked_subcommand is None:
        # No subcommand — launch the wizard if we have a TTY, else show help.
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            click.echo(ctx.get_help())
            ctx.exit(0)
        from src.wizard import run_wizard
        run_wizard(ctx)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@cli.command("wizard")
@click.option(
    "--save-to",
    "save_to",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to save the generated YAML. Default: config/<experiment_name>.yaml",
)
@click.pass_context
def cmd_wizard(ctx: click.Context, save_to: Path | None) -> None:
    """Interactive wizard: ask a handful of questions, save a YAML, optionally run it.

    Non-technical users: this is the intended path. Run with no flags and follow
    the prompts. The wizard writes a config file you can re-use or edit.
    """
    from src.wizard import run_wizard
    run_wizard(ctx, save_to=save_to)


@cli.command("validate")
@click.argument("config_path", type=click.Path(path_type=Path))
@click.pass_context
def cmd_validate(ctx: click.Context, config_path: Path) -> None:
    """Schema-check a YAML config without making any network calls.

    Exits 0 on success, non-zero with a readable error on failure.
    """
    matrix = _load_matrix(ctx.obj["matrix_path"])
    cfg = _load_cfg(config_path, matrix)
    click.echo(f"OK  {config_path}")
    click.echo(f"    model={cfg.model}  n={cfg.n_responses}  lang={cfg.language}")
    click.echo(f"    motives: {', '.join(f'{m.id}@{m.strength}' for m in cfg.motives)}")


@cli.command("list-motives")
@click.pass_context
def cmd_list_motives(ctx: click.Context) -> None:
    """Print the motive matrix: 4 categories, 5 motives each."""
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
    """Print a token and cost estimate for a config. No network calls for generation,
    but does load tiktoken encodings. Use before `generate` to budget a run."""
    matrix = _load_matrix(ctx.obj["matrix_path"])
    cfg = _load_cfg(config_path, matrix)
    api_key = _require_api_key(cfg.provider_prefix)
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
    print_estimate(est)


@cli.command("generate")
@click.argument("config_path", type=click.Path(path_type=Path))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None,
              help="Override the output directory from the config.")
@click.option("--concurrency", type=int, default=None,
              help="Override parallel in-flight call limit.")
@click.option("-y", "--yes", "auto_yes", is_flag=True,
              help="Skip the cost-confirmation prompt.")
@click.option("--no-csv", is_flag=True,
              help="Stop after writing JSONL; skip CSV export.")
@click.option("--resume", "resume_path", type=click.Path(path_type=Path), default=None,
              help="Resume from an existing results.jsonl (skip completed response_ids).")
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
    """Run an experiment: estimate -> confirm -> execute -> export CSV.

    Writes a timestamped directory under data/output/ containing results.jsonl,
    results.csv, run_meta.json, and a config_snapshot.yaml.
    """
    summary = run_generate(
        config_path=config_path,
        matrix_path=ctx.obj["matrix_path"],
        out_dir=out_dir,
        concurrency=concurrency,
        auto_yes=auto_yes,
        no_csv=no_csv,
        resume_path=resume_path,
        show_progress=not ctx.obj["quiet"],
    )
    if summary.n_failed:
        sys.exit(2)


@cli.command("report")
@click.argument("jsonl_path", type=click.Path(path_type=Path))
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="Destination CSV path (default: sibling results.csv).")
def cmd_report(jsonl_path: Path, out_path: Path | None) -> None:
    """Convert an existing results.jsonl into CSV (e.g. after a Ctrl+C)."""
    if not jsonl_path.exists():
        raise click.ClickException(f"not found: {jsonl_path}")
    results = report.load_jsonl(jsonl_path)
    if not results:
        raise click.ClickException("no results in jsonl")
    out = out_path or jsonl_path.with_suffix(".csv")

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
