# synth-data

A Python CLI for generating synthetic psychological training data. Journal-style text responses with configurable subconscious motives at configurable strengths. Used to produce labeled training data for a detection model.

Phase 1 supports **OpenAI `gpt-4o-2024-08-06` only**. More models + providers are coming.

---

## Install

Requires Python 3.11+.

```bash
cd synth-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your OPENAI_API_KEY into .env
```

---

## Two ways to use it

### 1. Interactive wizard (easiest)

```bash
python cli.py
```

Answers a handful of questions (name, model, language, number of responses, length, motives, strengths) and writes a YAML to `config/`. At the end you can save and run, or save only.

### 2. Config file

```bash
cp config/example.yaml config/my_run.yaml
# edit config/my_run.yaml
python cli.py generate config/my_run.yaml
```

Either way, the tool shows a cost estimate and asks `Proceed? [y/N]` before spending a cent.

---

## What you get

Each run writes a timestamped folder under `data/output/`:

```
data/output/<name>_<YYYY-MM-DD_HHMM>/
  results.jsonl          # one line per call (raw + parsed)
  results.csv            # legacy-compatible schema for the ML pipeline
  run_meta.json          # totals, timings, cost
  config_snapshot.yaml   # copy of the config used
```

Failed calls still appear in the CSV as `Text = "FAILED: <error>"` with all motive strengths zero.

---

## Commands at a glance

| Command | Purpose |
|---|---|
| `python cli.py` | Interactive wizard (default when no args). |
| `python cli.py generate CONFIG` | Full run: estimate → confirm → execute → export. |
| `python cli.py estimate CONFIG` | Dry-run token + cost estimate. |
| `python cli.py validate CONFIG` | Schema check, no network. |
| `python cli.py list-motives` | Print the 4×5 motive matrix. |
| `python cli.py report JSONL` | Convert an existing `results.jsonl` to CSV. |
| `python cli.py wizard` | Explicit alias for the interactive flow. |

Run `python cli.py <command> --help` for flags.

---

## Documentation

| Page | For |
|---|---|
| [`docs/usage.md`](docs/usage.md) | Full walkthroughs of both usage paths; every subcommand in detail. |
| [`docs/config-reference.md`](docs/config-reference.md) | Exhaustive YAML schema. |
| [`docs/motives.md`](docs/motives.md) | The 20-motive catalog + strength scale. |
| [`docs/output.md`](docs/output.md) | JSONL and CSV schemas (the contract with the ML pipeline). |
| [`docs/prompt.md`](docs/prompt.md) | How the prompt is assembled and why it works. |
| [`docs/cost.md`](docs/cost.md) | Estimation formula, pricing table, calibration. |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Common errors and fixes. |
| [`docs/architecture.md`](docs/architecture.md) | Module map + data flow; for contributors. |

---

## Interruption

`Ctrl+C` drains in-flight calls, flushes JSONL, writes CSV for whatever completed. Resume with:

```bash
python cli.py generate config/my_run.yaml --resume data/output/<prior_run>/results.jsonl
```

---

## Roadmap

- **Phase 2:** additional OpenAI models (GPT-5 family), Anthropic, local Ollama. Persona mode with cached profiles.
- **Phase 3:** motive-strength ranges + sampling, experiment orchestration.

See [`CHANGELOG.md`](CHANGELOG.md).
