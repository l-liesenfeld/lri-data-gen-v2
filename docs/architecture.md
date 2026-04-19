# Architecture (developer-facing)

Phase 1 is intentionally small. This page is the map.

## Module layout

```
cli.py                   # Click entry point; subcommands delegate to src/
src/
  models.py              # dataclasses + YAML config loader/validator
  prompt_builder.py      # template + LANGUAGE_FRAGMENTS + build_prompt()
  pipeline.py            # async orchestrator (semaphore, JSONL, SIGINT)
  cost.py                # estimate() + CostTracker
  report.py              # JSONL -> CSV
  wizard.py              # interactive YAML builder
  llm/
    interface.py         # LLMProvider protocol + error types
    openai.py            # OpenAI adapter (httpx + tiktoken + retry + pricing)
    registry.py          # "openai:..." -> provider instance
prompts/
  legacy.txt             # the prompt template with {placeholders}
data/
  motive_matrix.json     # the 20 motives + category metadata
  output/                # generated; per-run subdirs
scripts/
  gen_motives_doc.py     # regenerates docs/motives.md from the matrix
```

## Data flow

```
YAML file ─────────────────► load_config ─► ExperimentConfig
motive_matrix.json ──► load ─► MotiveMatrix ─┐
                                             ▼
                               prompt_builder.build_prompt
                                             │
                                             ▼
                                       LLMRequest (single, reused)
                                             │
                          ┌──────────────────┴──────────────────┐
                          ▼                                     ▼
                   cost.estimate                        pipeline.run
                     → CostEstimate                            │
                                                               ▼
                                               N × provider.complete (async)
                                                               │
                                                               ▼
                                          parse + validate → GenerationResult
                                                               │
                                                               ▼
                                                  results.jsonl (append+fsync)
                                                               │
                                                               ▼
                                            report.write_csv → results.csv
```

## Key design choices

**Single shared `LLMRequest`.** Every call in a run gets the same prompt. Variation comes from temperature sampling. Simplifies parsing, caching (phase 2), and resumability.

**Per-call JSONL append with fsync.** Ctrl+C can never lose completed work. Resume is trivial: re-read the JSONL, collect `response_id`s with `status="ok"`, skip them.

**Provider adapter owns everything provider-specific.** URL, auth, pricing, tokenizer, request/response mapping, retry policy. Adding Anthropic is `src/llm/anthropic.py` + one entry in `registry.py`. Zero changes to the orchestrator or cost code.

**Prompt is a single text file.** Non-developers can edit `prompts/legacy.txt` without touching Python. `{placeholders}` are minimal: motives, language, context, length, JSON template.

**Wizard writes YAML, then runs generate.** No parallel in-memory pipeline. Wizard's only job is building a config file; generate does the actual work. This keeps the number of code paths to N+0, not N×2.

## Async model

`asyncio.Semaphore(concurrency)` caps in-flight calls. Each `run_one` task:

1. Acquires the semaphore.
2. Checks the shutdown flag (set on SIGINT).
3. Calls `provider.complete(request)` (retries internally on transient errors).
4. Parses the response. On `ValueError`/`JSONDecodeError` retries once, then records as failed.
5. Writes one JSONL line.
6. Updates the progress bar.

`asyncio.gather` collects all tasks. On SIGINT, the shutdown event is set; tasks that haven't started early-return. In-flight tasks finish normally.

## Retry policy

Lives entirely in `src/llm/openai.py:OpenAIProvider.complete`:

- Retryable HTTP status: 408, 409, 425, 429, 500, 502, 503, 504.
- Retryable exceptions: `TimeoutException`, `NetworkError`.
- Backoff: `min(2**attempt, 16) * jitter(±20%)`, up to `max_retries` (default 5).
- `Retry-After` header is honored when present (429).
- Non-retryable (401, 403, 400) raises immediately and kills the run.

## Extending to new providers (phase 2 preview)

1. Add `src/llm/<provider>.py` implementing the `LLMProvider` protocol.
2. Include a pricing dict and a tokenizer.
3. Wire it in `src/llm/registry.py:build_provider`.

That's it. Nothing else changes.

## Extending to new models (same provider)

For OpenAI, add one entry to `OPENAI_PRICING` in `src/llm/openai.py`:

```python
"gpt-5-mini-2025-XX-XX": {"in": 0.25, "out": 1.00, "ctx": 200_000.0},
```

The existing adapter will handle it. Tiktoken auto-selects an encoder; if it doesn't know the model, `o200k_base` is used as a fallback.

## Testing philosophy (phase 1)

Phase 1 has no formal test suite. The golden-file tests described in the original plan (prompt snapshots, CSV parity) are a phase-1.5 task. For now, verify with:

- `python cli.py validate config/example.yaml` → schema-level checks.
- A manual small run (`n_responses: 5`) → end-to-end smoke.
- `report` the resulting JSONL → CSV byte-compatibility with the legacy tool's output, confirmed by the ML team.
