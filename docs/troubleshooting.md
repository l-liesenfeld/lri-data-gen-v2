# Troubleshooting

## `OPENAI_API_KEY not set`

Put the key in `.env` at the project root:

```
OPENAI_API_KEY=sk-...
```

Or export it in your shell. The CLI reads `.env` automatically via `python-dotenv`.

## `unknown motive id 'X9'`

The ID isn't in the matrix. Valid IDs are `A1..A5, L1..L5, M1..M5, F1..F5`. Run `python cli.py list-motives` to see the catalog.

## `strength must be in [0.1, 1.0]`

Strengths are floats. `1` (integer) is fine, `1.5` is not, `0` is not. The minimum is `0.1` because anything lower is indistinguishable from no motive.

## `generation.language must be one of (...)`

Exactly one of: `english`, `deutsch`, `deutsch-english`. Not `en`, `de`, or `both`.

## `model must be prefixed`

Use `openai:gpt-4o-2024-08-06`, not `gpt-4o-2024-08-06`. Phase 1 only supports the `openai:` prefix.

## `unknown OpenAI model 'gpt-5-...'`

Phase 1 only has `gpt-4o-2024-08-06` in the pricing table. Other models are phase 2. If you need another model urgently, add an entry to `OPENAI_PRICING` in `src/llm/openai.py`.

## Hanging on no-input

`python cli.py` with no stdin TTY (e.g. piped input, CI) prints help instead of launching the wizard. If you genuinely want the wizard in a non-TTY environment, use `python cli.py wizard`.

## Rate limits / 429

Two layers of defense:

**Reactive (on by default).** The OpenAI adapter retries automatically on 408/429/5xx with exponential backoff capped at 60s, jittered ±20%. `Retry-After` headers are respected. Default is 8 retries per call (tune via `runtime.max_retries`).

**Proactive (opt-in, strongly recommended for large runs).** Set your tier's ceilings in the YAML:

```yaml
runtime:
  requests_per_minute: 500     # RPM limit for the chosen model on your tier
  tokens_per_minute: 30000     # TPM limit for the chosen model on your tier
```

The pipeline will pace requests below these limits via a token bucket, so you don't hit 429s at all. Reference values (OpenAI, as of early 2026 — **confirm against your dashboard**):

| Tier | gpt-4o RPM | gpt-4o TPM |
|---|---|---|
| 1 | 500 | 30,000 |
| 2 | 5,000 | 450,000 |
| 3 | 5,000 | 800,000 |
| 4 | 10,000 | 2,000,000 |
| 5 | 10,000 | 30,000,000 |

If you don't know your tier: check [platform.openai.com/settings/organization/limits](https://platform.openai.com/settings/organization/limits). When in doubt, start with Tier 1 values — the pipeline will just run a bit slower, not fail.

**If you still see failures:** the final-summary line categorizes them (`17 failed (17 rate_limited)`). If `rate_limited` dominates and you don't have `requests_per_minute` set, the CLI prints a tip at the end pointing you here. You can also lower `runtime.concurrency`.

## 401 Unauthorized

The API key is invalid, revoked, or doesn't have access to the requested model. The run aborts on the first call (no retries).

## Context length exceeded (400)

Per-call prompt + expected output exceeds the model's context window. Shouldn't happen with phase-1 settings. If it does, you're almost certainly asking for too many motives at once. Reduce `n_responses` isn't the fix — each call is already `n=1` — so check that `response_length` and the motive list aren't pathological.

## Invalid JSON in response

The pipeline retries parse failures once per call. On the second failure the call is recorded with `status="failed"` and `raw_response` preserved in the JSONL for debugging. In the CSV, failed calls appear as a row with `Text = "FAILED: ..."` and all 20 motive strengths set to 0.

## Ctrl+C didn't save anything

First Ctrl+C drains in-flight calls and flushes JSONL + CSV. If you hit Ctrl+C twice quickly, the second one hard-exits before the CSV is written — but JSONL is flushed per-call, so you can always run:

```bash
python cli.py report data/output/<run>/results.jsonl
```

to produce the CSV after the fact.

## Wizard picked wrong default name / directory

Every wizard run writes a fresh YAML to `config/`. Just delete the file and re-run, or edit it. Nothing downstream cares.

## Umlauts appear as `??` in Excel

The CSV is UTF-8 with a BOM. Excel on recent versions handles this automatically. If yours doesn't, in Excel: Data → Get Data → From Text/CSV, pick 65001 (UTF-8) explicitly.

## "No results in jsonl"

You ran `report` against an empty or corrupted file. Check that the run actually produced data — look at `run_meta.json` in the same directory.

## The estimate is way off from actual cost

Input tokens are exact (tiktoken). Output tokens are a heuristic; the formula in `src/cost.py:_estimate_output_tokens` may need calibration — see [`cost.md`](cost.md).
