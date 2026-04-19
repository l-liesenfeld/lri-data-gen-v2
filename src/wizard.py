"""Interactive configuration wizard.

Asks a handful of questions, writes a YAML to config/, then optionally hands off
to the existing `generate` workflow. There is no parallel in-memory pipeline —
the wizard is purely a YAML builder + launcher.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import click

from .models import MotiveMatrix

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = ROOT / "config"
DEFAULT_MATRIX = ROOT / "data" / "motive_matrix.json"

# Phase 1 model list. Add entries here as providers come online.
MODEL_CHOICES: list[tuple[str, str]] = [
    ("openai:gpt-4o-2024-08-06", "OpenAI GPT-4o"),
]

LANGUAGE_CHOICES: list[tuple[str, str]] = [
    ("english", "English"),
    ("deutsch", "Deutsch"),
    ("deutsch-english", "English + Deutsch (bilingual)"),
]


# ---------------------------------------------------------------------------
# Prompting helpers
# ---------------------------------------------------------------------------

def _banner(text: str) -> None:
    click.secho(f"\n{text}", bold=True)
    click.secho("-" * len(text), dim=True)


def _menu(label: str, choices: list[tuple[str, str]], default_index: int = 0) -> str:
    """Numeric menu. Returns the selected value (choice[0])."""
    click.echo(label)
    for i, (_, display) in enumerate(choices, 1):
        click.echo(f"  [{i}] {display}")
    while True:
        raw = click.prompt("Choice", default=str(default_index + 1), show_default=True)
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1][0]
        except ValueError:
            pass
        click.secho(f"  enter a number 1..{len(choices)}", fg="red")


def _prompt_int(label: str, default: int, minimum: int, maximum: int | None = None) -> int:
    while True:
        raw = click.prompt(label, default=str(default), show_default=True)
        try:
            v = int(raw)
        except ValueError:
            click.secho("  not a number", fg="red")
            continue
        if v < minimum:
            click.secho(f"  must be >= {minimum}", fg="red")
            continue
        if maximum is not None and v > maximum:
            click.secho(f"  must be <= {maximum}", fg="red")
            continue
        return v


def _prompt_float_strength(label: str, default: float = 0.7) -> float:
    while True:
        raw = click.prompt(label, default=f"{default}", show_default=True)
        try:
            v = float(raw)
        except ValueError:
            click.secho("  not a number", fg="red")
            continue
        if not (0.1 <= v <= 1.0):
            click.secho("  strength must be between 0.1 and 1.0", fg="red")
            continue
        return v


def _parse_index_list(raw: str, n: int) -> list[int]:
    """Parse '1,3,5' or 'all' into a sorted list of 1..n indices."""
    raw = raw.strip().lower()
    if raw in ("", "none", "skip"):
        return []
    if raw == "all":
        return list(range(1, n + 1))
    out: set[int] = set()
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            continue
        try:
            i = int(tok)
        except ValueError:
            raise click.UsageError(f"  not a number: {tok!r}")
        if not (1 <= i <= n):
            raise click.UsageError(f"  {i} is out of range 1..{n}")
        out.add(i)
    return sorted(out)


# ---------------------------------------------------------------------------
# Section flows
# ---------------------------------------------------------------------------

def _ask_basics() -> dict[str, Any]:
    _banner("Experiment basics")
    default_name = "run_" + datetime.now().strftime("%Y-%m-%d_%H%M")
    name = click.prompt("Experiment name", default=default_name, show_default=True).strip() or default_name
    model = _menu("Model:", MODEL_CHOICES, default_index=0)
    language = _menu("Language:", LANGUAGE_CHOICES, default_index=0)
    n_responses = _prompt_int("Number of responses to generate", default=10, minimum=1)
    if n_responses > 500:
        click.secho(f"  heads up: {n_responses} is a lot — you'll confirm cost before we run.", fg="yellow")
    response_length = _prompt_int("Sentences per response (1..5)", default=3, minimum=1, maximum=5)
    context_hint = click.prompt(
        "Context hint (optional, e.g. 'workplace situation'; blank to skip)",
        default="", show_default=False,
    ).strip()
    output_dir = click.prompt("Output directory", default="data/output", show_default=True).strip() or "data/output"
    return {
        "name": name,
        "model": model,
        "language": language,
        "n_responses": n_responses,
        "response_length": response_length,
        "context_hint": context_hint,
        "output_dir": output_dir,
    }


def _ask_motives(matrix: MotiveMatrix) -> dict[str, float]:
    """Returns mapping motive_id -> strength."""
    _banner("Motive selection")
    click.echo(
        "Strength scale: 0.1 = barely perceptible, 0.5 = moderate, 1.0 = strongly detectable.\n"
        "You'll be asked category-by-category. Leave blank to skip a category.\n"
    )
    selections: dict[str, float] = {}

    for cat_key in ("A", "L", "M", "F"):
        cat_name = matrix.categories.get(cat_key, cat_key)
        click.secho(f"\n{cat_key} — {cat_name}", bold=True)
        ids = matrix.category_ids(cat_key)
        for i, mid in enumerate(ids, 1):
            cell = matrix.get(mid)
            click.echo(f"  [{i}] {cell.id}  {cell.name}")

        if not click.confirm("Include motives from this category?", default=False):
            continue

        while True:
            raw = click.prompt(
                "  Pick (e.g. '1,3,5' or 'all' or blank to skip)",
                default="", show_default=False,
            )
            try:
                indices = _parse_index_list(raw, len(ids))
            except click.UsageError as err:
                click.secho(str(err), fg="red")
                continue
            break

        if not indices:
            continue

        picked_ids = [ids[i - 1] for i in indices]
        same_strength: float | None = None
        if len(picked_ids) > 1 and click.confirm(
            "  Use the same strength for all picked motives?", default=True
        ):
            same_strength = _prompt_float_strength("  Strength for this category")

        for mid in picked_ids:
            if same_strength is not None:
                s = same_strength
            else:
                s = _prompt_float_strength(f"  Strength for {mid} ({matrix.get(mid).name})")
            selections[mid] = s

    return selections


def _review_summary(basics: dict[str, Any], motives: dict[str, float]) -> None:
    click.echo("")
    click.secho("Review", bold=True)
    click.echo(f"  Experiment:      {basics['name']}")
    click.echo(f"  Model:           {basics['model']}")
    click.echo(f"  Language:        {basics['language']}")
    click.echo(f"  Calls:           {basics['n_responses']}")
    click.echo(f"  Response length: {basics['response_length']} sentences")
    click.echo(f"  Context hint:    {basics['context_hint'] or '(none)'}")
    click.echo(f"  Output dir:      {basics['output_dir']}")
    click.echo(f"  Motives ({len(motives)}):")
    for mid, s in motives.items():
        click.echo(f"    {mid} @ {s}")


# ---------------------------------------------------------------------------
# YAML writer (hand-rolled to keep friendly comments + key order)
# ---------------------------------------------------------------------------

def _render_yaml(basics: dict[str, Any], motives: dict[str, float]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        f"# Generated by synth-data wizard on {now}",
        f"# Re-run with:  python cli.py generate config/{_slug(basics['name'])}.yaml",
        "# Edit freely; run `python cli.py validate <file>` to check.",
        "",
        "experiment:",
        f'  name: "{basics["name"]}"',
    ]
    if basics["output_dir"] and basics["output_dir"] != "data/output":
        lines.append(f'  output_dir: "{basics["output_dir"]}"')
    lines.extend([
        "",
        f'model: "{basics["model"]}"',
        "",
        "generation:",
        f"  n_responses: {basics['n_responses']}",
        f"  response_length: {basics['response_length']}",
        f'  language: "{basics["language"]}"',
        f'  context_hint: "{basics["context_hint"]}"',
        "",
        "runtime:",
        "  concurrency: 5",
        "",
        "motives:",
    ])
    for mid, s in motives.items():
        lines.append(f"  - id: {mid}")
        lines.append(f"    strength: {s}")
    lines.append("")
    return "\n".join(lines)


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)


def _unique_path(base: Path) -> Path:
    if not base.exists():
        return base
    n = 2
    while True:
        candidate = base.with_name(f"{base.stem}-{n}{base.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _save_yaml(basics: dict[str, Any], motives: dict[str, float], save_to: Path | None) -> Path:
    target = save_to or (DEFAULT_CONFIG_DIR / f"{_slug(basics['name'])}.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _unique_path(target)
    target.write_text(_render_yaml(basics, motives), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_wizard(ctx: click.Context, save_to: Path | None = None) -> None:
    """Interactive flow. Builds a YAML, optionally runs it."""
    matrix_path: Path = ctx.obj.get("matrix_path", DEFAULT_MATRIX)
    if not matrix_path.exists():
        raise click.ClickException(f"motive matrix not found: {matrix_path}")
    matrix = MotiveMatrix.load(matrix_path)

    click.secho("\nsynth-data interactive wizard", bold=True)
    click.echo("Ctrl+C at any time to cancel. Nothing is saved until you confirm.\n")

    try:
        while True:
            basics = _ask_basics()
            motives = _ask_motives(matrix)
            if not motives:
                click.secho("\n  No motives selected. Pick at least one.", fg="red")
                continue

            _review_summary(basics, motives)
            click.echo("")
            choice = _menu(
                "What next?",
                [
                    ("run", "Save and run now"),
                    ("save", "Save only (I'll run it later)"),
                    ("back", "Back to change something"),
                    ("cancel", "Cancel"),
                ],
                default_index=0,
            )
            if choice == "back":
                continue
            if choice == "cancel":
                click.echo("cancelled.")
                return

            yaml_path = _save_yaml(basics, motives, save_to)
            click.echo(f"\nsaved: {yaml_path}")

            if choice == "save":
                click.echo(f"\nRun later with:\n  python cli.py generate {yaml_path}")
                return

            # choice == "run" — hand off to the shared generate flow.
            # Import lazily to avoid an import cycle at module load.
            from cli import run_generate
            click.echo("")
            run_generate(
                config_path=yaml_path,
                matrix_path=matrix_path,
                auto_yes=False,  # still show the cost estimate + confirm once
                show_progress=not ctx.obj.get("quiet", False),
            )
            return
    except (KeyboardInterrupt, click.Abort):
        click.echo("\ncancelled.")
        return
