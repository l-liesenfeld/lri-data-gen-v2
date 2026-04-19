# Usage

Two paths to the same result.

---

## Path 1 — Interactive wizard (recommended for first-time users)

```bash
python cli.py
```

The wizard walks you through:

1. **Experiment name** — a label for this run (default: timestamped).
2. **Model** — pick an OpenAI or Anthropic model from the list (pricing shown inline).
3. **Language** — English, Deutsch, or bilingual.
4. **Number of responses** — how many journal entries to generate.
5. **Response length** — 1 to 5 sentences per entry.
6. **Context hint** — optional; e.g. "workplace situation".
7. **Output directory** — where results go.
8. **Motive selection** — category-by-category. For each of the 4 categories you can:
   - Skip entirely.
   - Pick specific motives by number (e.g. `1,3,5`) or type `all`.
   - Set one strength for the whole group or per-motive strengths.

You'll see a review screen at the end with an inline cost estimate, then choose:

- **Save and run now** — writes the YAML and starts generating.
- **Save only** — writes the YAML; you run it later with `python cli.py generate config/<name>.yaml`.
- **Back** — restart the wizard to change something.
- **Cancel** — nothing is saved.

The generated YAML lives in `config/<experiment_name>.yaml`. It's a normal file — edit and re-run any time.

### Explicit subcommand form

```bash
python cli.py wizard                       # same as above
python cli.py wizard --save-to my.yaml     # custom output path
```

---

## Path 2 — Config file

When you're comfortable with the YAML schema (see [`config-reference.md`](config-reference.md)):

```bash
# Copy the template
cp config/example.yaml config/my_run.yaml
# Edit it in your editor of choice
# Then:
python cli.py generate config/my_run.yaml
```

Every `generate` run shows a cost estimate and asks to proceed unless you pass `-y`.

---

## All commands

### `generate CONFIG`

Run an experiment end-to-end: estimate → confirm → execute → export CSV.

Flags:

| Flag | What |
|---|---|
| `--out DIR` | Override the output directory from the config. |
| `--concurrency N` | Override parallel in-flight call limit. |
| `-y`, `--yes` | Skip the cost-confirmation prompt. |
| `--no-csv` | Stop after writing JSONL; skip CSV export. |
| `--resume PATH` | Resume from an existing `results.jsonl` (skip completed response IDs). |

### `estimate CONFIG`

Print a token and cost estimate for a config. No network calls for generation; only loads tiktoken encodings. Run this before `generate` to budget.

### `validate CONFIG`

Schema-check a YAML without any network activity. Exits non-zero with a readable error if anything's wrong.

### `list-motives`

Print the motive matrix: 4 categories, 5 motives each, with IDs.

### `report JSONL`

Convert an existing `results.jsonl` into CSV. Useful if you interrupted a run and want the CSV export after the fact.

```bash
python cli.py report data/output/my_run_2026-04-19_1412/results.jsonl
```

### `wizard`

Explicit alias for the interactive flow. Same as running `python cli.py` with no arguments.

---

## Interruption

`Ctrl+C` during a run stops dispatching new calls but **lets in-flight calls finish**, then flushes JSONL and writes a CSV for whatever completed. A second `Ctrl+C` hard-exits (no CSV, but JSONL is already on disk).

Resume with:

```bash
python cli.py generate config/my_run.yaml \
    --resume data/output/my_run_2026-04-19_1412/results.jsonl
```

Completed response IDs are skipped; everything else is re-attempted.

---

## Environment

Set the API key(s) for whichever provider(s) you plan to use. Put them in `.env`:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

`python-dotenv` picks these up automatically. Only the key for the provider in your config's `model:` prefix is required.
