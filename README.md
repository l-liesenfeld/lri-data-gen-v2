# synth-data (phase 1)

Synthetic psychological training data generator. Phase 1 is a Python CLI that replaces
the Tauri desktop tool with functional parity, changing one thing: each response is its
own API call instead of one bulk call returning N responses.

Phase 1 supports **OpenAI `gpt-4o-2024-08-06` only**. More models + providers next.

## Install

```bash
cd synth-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then paste your OPENAI_API_KEY into .env
```

Requires Python 3.11+.

## First run

```bash
# Show available motives
python cli.py list-motives

# Check your config file
python cli.py validate config/example.yaml

# Print a cost estimate (no network call)
python cli.py estimate config/example.yaml

# Actually run it
python cli.py generate config/example.yaml
```

You'll see a cost estimate and a `Proceed? [y/N]` prompt before any money is spent.
Pass `-y` to skip the prompt.

## Output

Each run writes a timestamped folder under `data/output/`:

```
data/output/<experiment_name>_<YYYY-MM-DD_HHMM>/
  results.jsonl          # one line per call (raw + parsed)
  results.csv            # legacy-compatible schema for the ML pipeline
  run_meta.json          # totals, timings, cost
  config_snapshot.yaml   # copy of the config used
```

The CSV matches the existing tool's schema: metadata header rows, blank line, then
`Response_Number, Text, [German_Text,] A1..A5, L1..L5, M1..M5, F1..F5`. UTF-8 BOM for Excel.

Failed calls still appear as rows with `Text = "FAILED: <error>"` and all motive strengths 0.

## Configuration

Edit `config/example.yaml` or copy it. The motive list accepts three forms:

```yaml
# Explicit per-motive
motives:
  - id: A1
    strength: 0.7
  - id: L3
    strength: 0.4

# Shorthand mapping
motives:
  A1: 0.7
  L3: 0.4

# Category expansion (all 5 cells)
motives:
  - category: A
    strength: 0.5
  - id: L3            # overrides / adds to the category batch
    strength: 0.8
```

## Interruption

`Ctrl+C` stops dispatching new calls but lets in-flight calls finish, then flushes
the JSONL and writes CSV for whatever completed. A second `Ctrl+C` hard-exits.

Resume with:

```bash
python cli.py generate config/example.yaml --resume data/output/<prior_run>/results.jsonl
```

## Commands

| Command | What |
|---|---|
| `generate CONFIG` | full run (estimate → confirm → execute → export) |
| `estimate CONFIG` | dry-run token/cost estimate |
| `validate CONFIG` | schema check, no network |
| `list-motives`    | print the motive matrix |
| `report JSONL`    | convert a `results.jsonl` to CSV after the fact |
