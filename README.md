# synth-data

A Python CLI for generating synthetic psychological training data. Journal-style text responses with configurable subconscious motives at configurable strengths. Used to produce labeled training data for a detection model.

Supports **OpenAI** (GPT-5.4, GPT-4.1, GPT-4o families) and **Anthropic** (Claude Opus/Sonnet/Haiku 4.x). Pick per run via the `model:` prefix — e.g. `openai:gpt-5.4-mini` or `anthropic:claude-sonnet-4-6`.

---

## Install

Requires Python 3.11+.

```bash
cd synth-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your OPENAI_API_KEY and/or ANTHROPIC_API_KEY
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

## Claude Desktop (MCP)

A local MCP server (`mcp_server.py`) exposes `list_motives`, `estimate_cost`, and `generate` as tools for Claude Desktop. No separate daemon — Claude Desktop spawns the server on demand and tears it down when you quit. Setup and tool reference: [`docs/mcp.md`](docs/mcp.md).

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
| [`docs/mcp.md`](docs/mcp.md) | Claude Desktop integration via the MCP server. |
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

- **Next:** Batch APIs (50% off for OpenAI + Anthropic) for large bulk runs. Local Ollama provider.
- **Later:** persona mode with cached profiles, motive-strength ranges + sampling, experiment orchestration.

See [`CHANGELOG.md`](CHANGELOG.md).
