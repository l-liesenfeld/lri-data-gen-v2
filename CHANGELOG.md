# Changelog

## Unreleased

### Added
- Interactive wizard: `python cli.py` with no args asks a handful of questions, writes a YAML to `config/`, optionally runs it. Non-TTY invocations print help instead of hanging.
- `wizard` subcommand as explicit entry point.
- First-class documentation under `docs/`: usage, config reference, motive catalog, output schema, prompt internals, cost model, troubleshooting, architecture.
- Auto-generated `docs/motives.md` via `scripts/gen_motives_doc.py` (keeps the doc in sync with `data/motive_matrix.json`).
- Expanded inline CLI help (`--help` now shows typical-use examples and per-flag descriptions).

### Changed
- `cmd_generate` body extracted into a callable `run_generate` function so the wizard can hand off to the exact same workflow (single cost confirmation, single pipeline).

## 0.1.0 — Phase 1

Initial CLI release. Functional parity with the legacy Tauri tool, with one behavioral change: N individual single-response API calls instead of one bulk call returning N responses.

### Added
- `generate`, `estimate`, `validate`, `list-motives`, `report` subcommands.
- YAML experiment configuration (three motive-selection forms: explicit list, shorthand mapping, category expansion).
- Async pipeline with per-call retry/backoff, semaphore-limited concurrency, per-line JSONL fsync, graceful SIGINT drain, `--resume` support.
- Cost estimation via tiktoken (input tokens exact, output tokens heuristic).
- Legacy-compatible CSV export: 4 metadata rows + blank + 20-column motive grid + optional `German_Text` column, UTF-8 BOM.
- Failed rows rendered in CSV as `FAILED: <error>` with all strengths 0.
- OpenAI provider adapter (`openai:gpt-4o-2024-08-06` only).
- `.env` / environment-variable API key loading.
